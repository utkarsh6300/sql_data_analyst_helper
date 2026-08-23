# Integration

This package is a library. It has no database connection, no framework
dependency, and no opinion about who your users are — a host supplies identity
and a datasource; the package supplies the access control.

## Install

```bash
pip install -e /path/to/sql_compiler_plugin
```

Requires Python ≥ 3.9 and sqlglot 26.33.0 (pinned in
[`pyproject.toml`](../pyproject.toml)).

## The three things you must supply

| You supply | The package gives you |
|---|---|
| **Catalog** — your real schema | name resolution, star expansion, unknown-object rejection |
| **Policy** — what this caller may read | table, column and function authorization |
| **The SQL** an LLM produced | a rejection, or safe SQL to execute |

## Minimal

```python
from sql_compiler import Catalog, Policy, SqlCompiler

catalog = Catalog.from_dict({
    "public": {
        "orders":    {"id": "INT", "customer_id": "INT", "amount": "NUMERIC"},
        "customers": {"id": "INT", "name": "TEXT"},
    },
})

policy = Policy.from_dict({
    "subject": "analyst-1",
    "tables": {
        "public.orders":    ["id", "customer_id", "amount"],
        "public.customers": ["id", "name"],
    },
})

compiler = SqlCompiler(catalog=catalog)
result = compiler.compile(llm_generated_sql, policy=policy)

if result.ok:
    rows = run(result.sql)        # ← result.sql, never llm_generated_sql
else:
    handle(result.violations)
```

`compiler` holds no per-request state, so build it once and share it.

---

## Step 1 — Build the catalog

### From DDL you already store

Most Text-to-SQL systems already keep `CREATE TABLE` text to feed the prompt.
Reuse it:

```python
ddl_texts = [row.ddl for row in db.query(DDLStatement)
                                 .filter_by(project_id=project_id).all()]

catalog = Catalog.from_ddl(ddl_texts, dialect="postgres", default_schema="public")
```

Handles multi-statement blobs, and ignores indexes, views and comments.

**`strict=True` is the default and you should keep it.** A `CREATE TABLE` that
fails to parse raises `ConfigurationError`. With `strict=False` it is skipped
instead — and because unknown tables are denied, one unparseable statement
turns into a stream of confusing "access denied" errors for a table that is
perfectly legitimate.

### From structured data

```python
catalog = Catalog.from_dict({"public.orders": ["id", "amount"]})   # types optional
```

### Introspecting a live database

Not built in, deliberately — that would mean this package owning a connection.
Do it host-side:

```python
rows = db.execute(text("""
    SELECT table_schema, table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
""")).fetchall()

schema = {}
for table_schema, table_name, column, data_type in rows:
    schema.setdefault(table_schema, {}).setdefault(table_name, {})[column] = data_type

catalog = Catalog.from_dict(schema)
```

This is the most accurate source and always in sync. Cache it — do not rebuild
per request.

> **Catalogs are per-project, not global.** If your app is multi-project,
> either build one compiler per project or pass `catalog=` per call:
> `compiler.compile(sql, policy=policy, catalog=project_catalog)`.

---

## Step 2 — Supply a policy

### Directly

```python
policy = Policy.from_dict({
    "subject": "analyst-1",
    "tables": {
        # shorthand: a plain column list
        "public.orders": ["id", "customer_id", "amount"],

        # full form: everything except named columns
        "public.employees": {
            "columns": "*",
            "denied_columns": ["salary", "ssn"],
        },
    },
    # optional; omit to use the default analytic allow-list
    "allowed_functions": ["COUNT", "SUM", "AVG", "DATE_TRUNC"],
})
```

Rules to keep in mind:

- **An unlisted table is denied.** There is no wildcard granting unlisted tables.
- **Denies always beat grants.**
- **`"columns": "*"` is a standing grant** — a column added to the table later
  becomes readable with no policy change to review. Prefer explicit lists on
  anything sensitive.
- `Policy.to_dict()` round-trips through `from_dict()`, so policies can cross a
  network boundary.

### Via a provider (when a host owns identity)

```python
from sql_compiler import Policy, PolicyProvider, ConfigurationError

class DbPolicyProvider(PolicyProvider):
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def resolve(self, subject) -> Policy:
        with self._session_factory() as db:
            grants = db.query(Grant).filter_by(user_id=subject).all()
            if not grants:
                raise ConfigurationError(f"no grants for {subject!r}")
            return Policy.from_dict({
                "subject": str(subject),
                "tables": {g.qualified_table: list(g.columns) for g in grants},
            })

compiler = SqlCompiler(catalog=catalog, policy_provider=DbPolicyProvider(SessionLocal))
result = compiler.compile(sql, subject=current_user_id)
```

`resolve()` is called once per compilation and never cached, so a revoked grant
takes effect on the next query.

**Return an empty `Policy` only when you mean "this subject genuinely has no
grants."** Never as an error fallback — that silently converts an outage in
your authorization system into a blanket denial that looks like normal
operation.

---

## Step 3 — Filter the schema *before* generation

This is the step that improves accuracy rather than just blocking things.
Sending the model tables the caller cannot read leaks schema metadata **and**
guarantees queries that must be rejected.

```python
from sql_compiler import render_schema_prompt

prompt = f"""Database schema:
{render_schema_prompt(catalog, policy)}

Generate SQL for: {question}"""
```

Denied tables vanish; denied columns vanish; tables with no readable columns
are omitted entirely.

---

## Step 4 — Compile, and execute only the output

```python
result = compiler.compile(llm_sql, policy=policy)

if not result.ok:
    return {"error": "query_rejected",
            "violations": [v.to_dict() for v in result.violations]}

rows = execute(result.sql)
```

Or the raising style:

```python
from sql_compiler import CompilationRejected

try:
    safe_sql = compiler.compile_or_raise(llm_sql, policy=policy)
except CompilationRejected as exc:
    return {"error": "query_rejected", "violations": exc.to_dict()["violations"]}
```

### `ConfigurationError` is not a rejection

```python
except ConfigurationError:      # no catalog, unknown subject, bad provider
    raise                       # your bug — let it 500, do not show "access denied"
```

Reporting a wiring mistake as an access denial hides the mistake and sends
users chasing permissions they already have.

---

## Step 5 — The repair loop

Structured violations exist so the model can fix its own output. Bound the
loop — [plan.txt §22](notes/plan.txt) suggests 2–3 attempts — or a model that
cannot satisfy the policy will retry forever.

```python
MAX_ATTEMPTS = 3

def generate_safe_sql(question, catalog, policy, compiler):
    schema = render_schema_prompt(catalog, policy)
    feedback = ""

    for attempt in range(MAX_ATTEMPTS):
        sql = llm_generate(question, schema, feedback)
        result = compiler.compile(sql, policy=policy)

        audit_log(subject=policy.subject, question=question, sql=sql,
                  ok=result.ok, tables=result.tables, columns=result.columns,
                  violations=[v.code.value for v in result.violations])

        if result.ok:
            return result.sql

        feedback = result.repair_prompt()

    raise RuntimeError("could not produce an authorized query")
```

`repair_prompt()` names violation codes and the objects the model **already
referenced** — never the tables or columns it is not allowed to know about:

```
The generated SQL was rejected. Fix these problems and try again:
- COLUMN_ACCESS_DENIED (salary): Access to column 'salary' of table 'public.employees' is not permitted.
- COLUMN_ACCESS_DENIED (ssn): Access to column 'ssn' of table 'public.employees' is not permitted.
```

All violations arrive at once, so each round trip fixes everything rather than
one problem at a time.

---

## Worked example: a FastAPI service

Modelled on a typical `generate_sql` service method.

```python
from functools import lru_cache
from sql_compiler import (
    Catalog, ConfigurationError, Policy, SqlCompiler, render_schema_prompt,
)

MAX_ATTEMPTS = 3


@lru_cache(maxsize=64)
def catalog_for_project(project_id: str) -> Catalog:
    """Cached; invalidate when the project's DDL changes."""
    with SessionLocal() as db:
        ddl = [r.ddl for r in db.query(DDLStatement).filter_by(project_id=project_id)]
    return Catalog.from_ddl(ddl, dialect="postgres", default_schema="public")


def generate_sql(db, chat_id, query, subject):
    chat = get_chat(db, chat_id)
    catalog = catalog_for_project(str(chat.project_id))
    policy = policy_provider.resolve(subject)          # may raise ConfigurationError
    compiler = SqlCompiler(catalog=catalog)

    # Only advertise what this subject may read.
    schema_text = render_schema_prompt(catalog, policy)

    feedback = ""
    for _ in range(MAX_ATTEMPTS):
        candidate = generate_sql_query(
            query_text=query.text,
            schema=schema_text,
            documentation=fetch_docs(query.text, chat.project_id),
            repair_feedback=feedback,
        )
        result = compiler.compile(candidate, policy=policy)

        audit.record(subject=subject, chat_id=chat_id, question=query.text,
                     generated_sql=candidate, compiled_sql=result.sql,
                     ok=result.ok, tables=result.tables, columns=result.columns,
                     violations=[v.to_dict() for v in result.violations])

        if result.ok:
            return {"sql": result.sql, "chat_id": chat_id}

        feedback = result.repair_prompt()

    raise HTTPException(
        status_code=422,
        detail={"error": "query_rejected",
                "violations": [v.to_dict() for v in result.violations]},
    )
```

Note what is logged: the model's candidate **and** the compiled SQL **and** the
resolved tables and columns — on rejection as well as success. A denial is
exactly the event an incident review needs a record of.

---

## Before you execute anything

**This package is a validation layer, not a security boundary.** Executing
`result.sql` against a database that would happily obey a `DROP` means one bug
here is a breach.

At minimum, add:

```sql
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM analyst_role;
GRANT SELECT ON secured_orders_view TO analyst_role;

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON orders
  USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

```python
with engine.begin() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    conn.execute(text("SET LOCAL statement_timeout = '30s'"))
    conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant_id})
    rows = conn.execute(text(result.sql)).fetchall()
```

Remember that **row-level security is not implemented here** — `row_filter` is
recorded and not enforced. Without the RLS policies above, a caller with table
access reads every row. See
[Security model](02-security-model.md#what-this-does-not-defend-against).

Also: never return raw database errors to a user, and key any query cache by
policy identity as well as by query text.

---

## Reference

| Call | Returns |
|---|---|
| `Catalog.from_ddl(texts, dialect=, default_schema=, strict=True)` | `Catalog` |
| `Catalog.from_dict(mapping, dialect=, default_schema=)` | `Catalog` |
| `Policy.from_dict(spec, dialect=, default_schema=)` | `Policy` |
| `SqlCompiler(catalog=, policy_provider=, pretty=False)` | compiler |
| `.compile(sql, policy=, subject=, catalog=)` | `CompileResult` |
| `.compile_or_raise(...)` | `str`, or raises `CompilationRejected` |
| `render_schema_prompt(catalog, policy)` | `str` of `CREATE TABLE` text |
| `visible_schema(catalog, policy)` | `{"public.orders": {"id": "INT"}}` |

`CompileResult`: `.ok` · `.sql` · `.violations` · `.tables` · `.columns` ·
`.subject` · `.repair_prompt()` · `.to_dict()` · `.raise_for_violations()`

`Violation`: `.code` · `.message` · `.action` · `.table` · `.column` ·
`.function` · `.to_dict()`

Violation codes are a stable contract — switch on them freely:

```
PARSE_ERROR  EMPTY_STATEMENT  MULTIPLE_STATEMENTS
NON_SELECT_STATEMENT  FORBIDDEN_EXPRESSION
EMPTY_CATALOG  UNKNOWN_TABLE  NAME_RESOLUTION_FAILED
TABLE_ACCESS_DENIED  COLUMN_ACCESS_DENIED  FUNCTION_NOT_ALLOWED
GENERATION_FAILED
```
