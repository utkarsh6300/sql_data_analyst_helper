# Architecture

## The shape of the thing

```
                     ┌───────────────────────────────────────┐
   LLM SQL  ────────▶│              SqlCompiler              │
   (untrusted)       │                                       │
                     │  1  parse      one statement or stop  │
   Catalog  ────────▶│  2  read-only  whole tree, deny-first │
   (your schema)     │  3  resolve    qualify + scope        │──▶ CompileResult
                     │  4  authorize  tables/columns/funcs   │     .ok
   Policy   ────────▶│  5  generate   render from the tree   │     .sql        ← execute THIS
   (what may be read)└───────────────────────────────────────┘     .violations
                                                                   .tables/.columns  ← audit
```

Passes 1–3 are **fatal**: they short-circuit, because there is nothing
meaningful to do next. Pass 4 **collects** every violation, so a repair loop
learns all the problems in one round trip rather than one per attempt.

The compiler holds no per-request state. One instance is safe to share across
requests; the policy is what varies per caller.

## Module map

```
sql_compiler/
├── names.py          identifier normalization + TableRef   ← everything compares through here
├── catalog.py        the schema, from DDL text or a dict
├── policy.py         what a subject may read + PolicyProvider
├── errors.py         Violation, ViolationCode, RepairAction
├── ir.py             ResolvedQuery — what resolve produces, authorize reads
├── schema_view.py    permission-filtered schema for the prompt
├── compiler.py       runs the passes, owns CompileResult
└── passes/
    ├── parse.py      pass 1
    ├── readonly.py   pass 2
    ├── resolve.py    pass 3   ← the one that matters
    └── authorize.py  pass 4
```

Roughly 1,200 lines of implementation and 1,500 of tests. The ratio is
deliberate: the value of this package is entirely in the cases it refuses.

---

## `names.py` — why identifier handling is its own module

Every authorization decision ends as a string comparison between an identifier
an **LLM** wrote and an identifier a **human** wrote in a policy. If those two
normalize differently, you are comparing the wrong strings and only *believe*
you are secure.

So normalization happens in exactly one place, and is delegated to the SQL
dialect rather than hardcoded:

```python
normalize_identifier("ORDERS", "postgres")   # → "orders"   (Postgres folds down)
normalize_identifier("orders", "snowflake")  # → "ORDERS"   (Snowflake folds up)
normalize_identifier("Orders", "postgres", quoted=True)   # → "Orders"  (preserved)
```

That last case is not pedantry. In Postgres, `"Orders"` and `orders` are
genuinely **different tables**. Folding them together would let a policy for
one authorize the other.

`TableRef` is the other half: a table name that is **always schema-qualified**,
normalized at construction. Because a `TableRef` can only be built through its
constructors, anything holding one can compare it directly and safely. This
single decision is what closes the `secret.orders` bypass — an unqualified name
is resolved against the default schema exactly once, here, instead of being
compared bare somewhere downstream.

---

## `catalog.py` — the schema to resolve against

Name resolution needs a real `{schema: {table: {column: type}}}` map. Without
one you cannot expand `SELECT *`, cannot map an alias back to its table, and
cannot distinguish a CTE from a table — which is to say you cannot authorize
anything. **A missing catalog is therefore a hard failure, never a silent
pass.**

Two constructors, because hosts have the schema in one of two shapes:

```python
Catalog.from_dict({"public": {"orders": {"id": "INT", "amount": "NUMERIC"}}})
Catalog.from_ddl(["CREATE TABLE orders (id INT, amount NUMERIC);"])
```

`from_ddl` exists because Text-to-SQL systems typically already store raw
`CREATE TABLE` text to feed the prompt. It is written for real DDL dumps: it
skips indexes, views and comments, and it skips table-level constraints like
`PRIMARY KEY (a, b)` that sit among the column definitions but define no
column.

`from_dict` accepts nested or flat keys, and column lists with or without
types — types are never used for authorization, only names.

---

## `policy.py` — what a subject may read

Permissions are **`(table, column)` pairs**, never bare column names:

```python
Policy.from_dict({
    "tables": {
        "public.transactions": ["id", "amount"],
        "public.payroll":      ["id"],
    },
})
```

`transactions.amount` is granted; `payroll.amount` is not. A flat allow-list
like `{"id", "amount"}` cannot express that difference — it would grant
`amount` on every table that has one.

Three rules, each with a test pinning it:

- **Denies beat grants.** A deny that a broad grant could override is not a deny.
- **An unlisted table is denied.** There is deliberately no wildcard that grants
  unlisted tables; an "allow everything" escape hatch is the thing that gets
  left on in production.
- **Policies are serializable both ways.** `to_dict()` output feeds back into
  `from_dict()` unchanged, so a policy can cross a network boundary.

`PolicyProvider` is the seam for a host that owns identity. It is called once
per compilation and never cached, so a revoked grant takes effect on the next
query.

---

## Pass 1 — `parse.py`

Parse to **exactly one** statement, or reject.

```
SELECT 1; DROP TABLE orders     →  MULTIPLE_STATEMENTS
```

This is the stacked-query bypass. Analyse statement one, hand the original
string to the driver, lose the table. Rejecting multi-statement input outright
means every later pass is analysing the thing that will actually run.

---

## Pass 2 — `readonly.py`

[chat.txt](notes/chat.txt) advises: *"inspect the root node… reject UPDATE,
INSERT, DELETE, DROP, ALTER."* **That is not enough on Postgres.** All four of
these have a root node of `Select`, and all four write:

| Query | Root | Hidden node |
|---|---|---|
| `WITH x AS (INSERT INTO orders VALUES (1) RETURNING id) SELECT * FROM x` | `Select` | `Insert` |
| `WITH d AS (DELETE FROM orders RETURNING id) SELECT * FROM d` | `Select` | `Delete` |
| `SELECT id INTO new_table FROM orders` | `Select` | `Into` |
| `SELECT * FROM orders FOR UPDATE` | `Select` | `Lock` |

So the pass walks the **entire tree**, checking every node against a deny list.

### The single most important entry: `exp.Command`

sqlglot does not fail on syntax it cannot model — it wraps it in a `Command`
node and moves on:

```
VACUUM FULL   →  'VACUUM FULL' contains unsupported syntax.
                  Falling back to parsing as a 'Command'.
```

If `Command` were allowed, **everything the parser does not understand would be
silently permitted** — deny-by-default inverted at exactly the point where you
have the least ability to reason about what you just let through. Vendor
extensions, future grammar, anything unusual. A test pins `Command` into the
deny list so nobody "tidies it up" later.

Two deliberate exclusions:

- **`Fetch` is allowed** — `FETCH FIRST 10 ROWS ONLY` is standard row limiting,
  not a cursor operation.
- **The deny list resolves class names via `getattr`**, so a sqlglot release
  that renames an expression class degrades gracefully instead of breaking the
  import.

---

## Pass 3 — `resolve.py` — the pass that matters

An unqualified parse tree tells you a node is named `amount`. It does **not**
tell you which relation it belongs to. Authorizing that tree authorizes the
wrong names.

Everything the source transcripts call "the catch" is this one missing phase.
Running `qualify()` first collapses four separate-looking bypasses into one
solved problem:

| Query | Without resolution | With resolution |
|---|---|---|
| `SELECT * FROM employees` | `*` is a `Star`, not a `Column` — **zero** column checks run | expanded to explicit columns, each checked |
| `SELECT p.ssn FROM employees p` | a column of some relation `p` | `p` → `employees`, so `employees.ssn` |
| `SELECT id FROM secret.orders` | `table.name == "orders"` — matches the grant | `secret.orders` ≠ `public.orders`, denied |
| `WITH t AS (…) SELECT * FROM t` | `t` looks like an unauthorized table — **falsely rejected** | `t` known to be a CTE; its body checked instead |

### How scope resolution actually works

The mechanism is `scope.sources`, which maps every visible name to either an
`exp.Table` (a real base table) or a `Scope` (a CTE or derived table). Here is
a real trace:

```sql
WITH hv AS (SELECT customer_id, amount FROM orders)
SELECT c.name, h.amount FROM hv h JOIN customers c ON c.id = h.customer_id
```

```
scope 0  (the CTE body)
  sources = {'orders': Table}                       → base table: authorize orders
  columns = [orders.customer_id, orders.amount]     → authorize both

scope 1  (the outer query)
  sources = {'hv': Scope, 'h': Scope, 'c': Table}   → only 'c' is a base table
  columns = [c.name, h.amount, c.id, h.customer_id]
              └─ authorize      └─ source is a Scope: already covered by scope 0
```

Two things fall out of this for free:

- A **CTE name is never mistaken for a table**, because it resolves to a
  `Scope`, not an `exp.Table`.
- Columns reading *from* a CTE need no separate handling, because the CTE's own
  scope already authorized the base columns it was built from. Nested CTEs
  chain the same way.

This is the entire "symbol table and local scope" machinery
[chat.txt](notes/chat.txt) spends 800 words describing — already built, already
correct, and not something to hand-roll.

> **Not taken: the "inline the CTEs" shortcut.** [chat.txt](notes/chat.txt)
> suggests expanding CTEs away to avoid scope handling. Recursive CTEs cannot
> be inlined at all, and inlining changes materialization behaviour — it can
> multiply the cost of the query you are about to run.

### The correlated-subquery edge case

In a correlated subquery, a column can appear in the **inner** scope while its
source lives in the **outer** one:

```sql
SELECT c.name FROM customers c
WHERE EXISTS (SELECT 1 FROM employees e WHERE e.ssn = c.name)
```

```
scope 0:  columns = [e.ssn, c.name]   external = [c.name]   ← 'c' is not a source here
scope 1:  columns = [c.name]                                ← but it is here
```

Because the outer scope reports the same column, skipping externals loses no
coverage. Anything else that cannot be resolved **fails closed** with
`NAME_RESOLUTION_FAILED` rather than being skipped.

### Fail-closed settings

```python
qualify(
    infer_schema=False,             # never guess at a table the catalog lacks
    expand_stars=True,              # so star columns get checked
    validate_qualify_columns=True,  # unresolvable column → error, not a pass
)
```

An inferred table is an unauthorized table wearing a disguise.

There is also a defensive check that **no star survived** expansion. One that
did would mean unchecked columns reaching the database. (Verified not to
false-positive on `COUNT(*)`, whose star is an aggregate argument, not a
projection.)

### Function collection

Functions need care because sqlglot canonicalizes them, and one call can
legitimately be spelled several ways:

| Written | Node class | `sql_name()` | Renders back as |
|---|---|---|---|
| `DATE_TRUNC('day', x)` | `TimestampTrunc` | `TIMESTAMP_TRUNC` | `DATE_TRUNC` |
| `version()` | `Anonymous` | **`ANONYMOUS`** ← useless | `VERSION` |
| `pg_read_file('/etc/passwd')` | `Anonymous` | **`ANONYMOUS`** | `PG_READ_FILE` |

For `Anonymous` nodes the real name lives in `node.this`, not `sql_name()`. So
each call is collected with **every name it could reasonably be matched by**,
and an allow-list entry matching any one of them is enough.

---

## Pass 4 — `authorize.py`

By now every name is fully resolved, so authorization is a set of plain
lookups. **That is the point.** All the difficulty lives in pass 3; if
authorization ever looks clever, something upstream is wrong.

Three checks — tables, then columns, then functions — collecting violations
rather than stopping at the first.

Two details that are about disclosure rather than access:

- **A denied table does not also enumerate its columns.** Listing them would
  confirm which columns exist on a table the subject cannot see.
- **Violations never echo the query text.** These payloads flow back to an LLM
  and possibly to a user; echoing rejected SQL turns a rejection into a
  disclosure channel. A test asserts this.

The function check is what stops queries that reference nothing at all:

```
SELECT version()                      →  FUNCTION_NOT_ALLOWED
SELECT pg_read_file('/etc/passwd')    →  FUNCTION_NOT_ALLOWED
```

No table, no column, no `FROM` — invisible to the other two checks.

---

## Pass 5 — generation

```python
safe_sql = resolved.expression.sql(dialect=catalog.dialect)
```

Input:

```sql
select o.amount from orders o where o.amount > 1000
```

Output — what actually executes:

```sql
SELECT "o"."amount" AS "amount" FROM "public"."orders" AS "o" WHERE "o"."amount" > 1000
```

Fully qualified, quoted, star-expanded. Beyond being the validated form, this
collapses most of the **parser-differential** risk: a validator whose parser
disagrees with the database's parser is a known vulnerability class (it is how
WAF bypasses work). Regenerating from the tree means the database is handed
sqlglot's unambiguous interpretation, not the model's ambiguous original.

`CompileResult.sql` is `None` whenever the query was rejected — so a caller who
forgets to check `.ok` gets a `None`, not an unvalidated query.

---

## `schema_view.py` — filtering *before* generation

Guarding only the compiler's output means the prompt still contains tables the
subject cannot read. That is a metadata leak in its own right, and it actively
hurts accuracy: the model keeps producing queries that must then be rejected.

```python
render_schema_prompt(catalog, policy)
```

```sql
CREATE TABLE public.employees (
  id INT,
  name TEXT
);
```

— with `salary` and `ssn` simply absent. Tables with no readable columns are
omitted entirely, since an empty table entry still discloses that the table
exists.

A test asserts that **everything this advertises actually compiles**, so the
filter cannot silently drift away from what the compiler enforces.

---

## Tests

Full layout and rationale live in the README's [Test layout](../README.md#test-layout)
section rather than duplicated here, so it can't drift out of sync again.
Start at `tests/integration/security/test_adversarial.py` — the bypasses this
package exists to close.

```bash
.venv/bin/python -m pytest -q
```

Add to `test_adversarial.py` before adding features.
