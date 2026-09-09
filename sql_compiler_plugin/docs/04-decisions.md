# Design decisions

Why the package is built this way, what the alternative was, and how to reverse
each choice. Roughly in order of how much they shaped the code.

---

## 1. Resolution happens before authorization

**Decision.** Run sqlglot's `qualify()` and scope analysis *before* any
permission check, in Phase 1 rather than Phase 2.

**[plan.txt](notes/plan.txt) put this in Phase 2**, with Phase 1 doing naive
allow-list checks on an unqualified tree.

**Why the change.** Every bypass [chat2-1.txt](notes/chat2-1.txt) lists — bare
`*`, schema-qualified tables, aliases, CTE names read as base tables — has one
root cause: checking an unqualified parse tree. A Phase 1 without qualification
is a validator that demos well and blocks nothing, and its *tests would encode
the wrong behaviour*, which is worse than having no tests. `qualify()` plus
`traverse_scope()` closes all four for roughly the same amount of code.

**Cost.** A catalog becomes mandatory. Without one, nothing compiles.
That is the correct trade — see decision 3.

**To reverse:** you cannot, meaningfully. Everything downstream assumes
resolved names.

---

## 2. The database must remain the security boundary

**Decision.** This package is a fast-fail and feedback layer. Postgres RLS is
the security boundary; `TablePolicy.row_filter` (enforced by
`passes/rowsec.py`) is defence in depth, never a substitute for it.

**[chat.txt](notes/chat.txt) originally proposed** AST injection of
`WHERE tenant_id = …` as the row-security mechanism, via `ast.transform()` over
every `Select`.

**Why not that shape.** [chat2-1.txt](notes/chat2-1.txt) shows that approach
failing three different ways:

- It appends the filter to selects over **CTEs and derived tables**, producing
  `SELECT * FROM high_value_orders WHERE tenant_id = 123` where the CTE never
  selected `tenant_id` — a broken query. The comment claiming it "handles
  subqueries/CTEs too" is exactly inverted.
- On `FROM orders a JOIN orders_archive b`, an unqualified `tenant_id` either
  errors as ambiguous or **binds to one relation and leaves the other
  unfiltered**. Failing open on a security predicate is the worst available
  outcome.
- Building the predicate as an f-string and re-parsing it **reintroduces SQL
  injection inside the anti-injection layer.**

More fundamentally: an in-process rewriter is bypassed by any code path that
reaches the database without going through it. The database applies its rules
regardless of caller — which is exactly why this remains defence in depth, not
the boundary, even once enforced.

**What is implemented instead (`passes/rowsec.py`, Pass 5, after
authorization succeeds):** every base-table *occurrence* — one entry per
FROM/JOIN item, from `ResolvedQuery.table_nodes`, never a name-based
`find_all` that could also match a same-named CTE — is replaced with a
secured derived table: `orders` becomes
`(SELECT * FROM orders WHERE tenant_id = ?) AS orders`. This closes all three
failure modes above: the filter travels with the table reference itself, so
it lands inside a CTE's own definition rather than on an outer select that
never chose the filtered column; a self-join gets one filtered copy per side
instead of an ambiguous or one-sided predicate; and the predicate is parsed
with `sqlglot.parse` into an AST node and re-emitted, never string-formatted,
so there is nothing to re-inject through. A `row_filter` that fails to parse,
or smuggles in a second statement, is a `ConfigurationError` — it was written
into the policy by the host, not produced by the model, so treating it as a
query violation would misattribute the bug.

**To reverse:** remove the call to `apply_row_filters` from `compiler.py` and
`TablePolicy.row_filter` goes back to being recorded and inert.

---

## 3. A missing catalog is a hard failure

**Decision.** No catalog → `EMPTY_CATALOG`, nothing compiles. Unknown table →
`UNKNOWN_TABLE`. `infer_schema=False`.

**Why.** An inferred table is an unauthorized table wearing a disguise. The
alternative — degrade to name-only checking when the schema is unavailable — is
a fail-open path that activates precisely when something is already wrong.

**Consequence you will hit:** a project whose DDL has not been loaded rejects
every query. That is intended, but it means catalog loading needs to be a
visible, monitored step, not a best-effort one. It is also why
`Catalog.from_ddl(strict=True)` is the default.

---

## 4. Permissions are `(table, column)` pairs

**Decision.** `Policy` keys grants by schema-qualified table, with per-table
column sets.

**[chat.txt](notes/chat.txt) used** a flat global `ALLOWED_COLUMNS = {"user_id",
"amount"}`.

**Why.** A flat set cannot express "`amount` on `transactions` but not on
`payroll`" — it grants `amount` on every table that has one.
[plan.txt §11](notes/plan.txt) and [chat2-1.txt](notes/chat2-1.txt) both name this as
a concrete flaw. A test pins it.

---

## 5. The read-only check walks the whole tree

**Decision.** Check every node, not just the root, against a deny list.

**[chat.txt](notes/chat.txt) advised** inspecting the root node only.

**Why.** Postgres data-modifying CTEs have a `Select` root and still write:

```sql
WITH x AS (INSERT INTO orders VALUES (1) RETURNING id) SELECT * FROM x
```

Same for `SELECT … INTO` and `SELECT … FOR UPDATE`. A root check passes all
of them.

---

## 6. `exp.Command` is denied

**Decision.** The deny list's most important entry.

**Why.** sqlglot does not fail on syntax it cannot model — it wraps it in a
`Command` node and continues. Allowing `Command` means **everything the parser
does not understand is permitted**: vendor extensions, future grammar, anything
unusual. That inverts deny-by-default at precisely the point where you can
least reason about what you just allowed.

A test pins `Command` into the list so it is not "cleaned up" later.

---

## 7. Deny-by-default function allow-list

**Decision.** Functions are denied unless allow-listed. The default list covers
analytic functions only.

**Why.** A query needs no table at all to be dangerous:

```sql
SELECT version()
SELECT pg_read_file('/etc/passwd')
```

Both are invisible to table and column checks. [chat2-1.txt](notes/chat2-1.txt)
names `SELECT version()` as one of the four bypasses.

**Implementation wrinkle worth knowing.** sqlglot canonicalizes functions, so
one call has several names. `exp.Anonymous.sql_name()` returns the literal
string `"ANONYMOUS"` — the real name is in `node.this`. And `DATE_TRUNC` parses
to a `TimestampTrunc` node whose `sql_name()` is `TIMESTAMP_TRUNC` but which
renders back as `DATE_TRUNC`. So each call carries **every name it could be
matched by**, and one match suffices.

**To customise:** pass `allowed_functions` in the policy. It replaces the
default entirely.

---

## 8. `SELECT *` is expanded and checked, not rejected

**Decision.** Stars expand into explicit columns; each is authorized
individually; the query is rejected only if some column is denied.

**[plan.txt §10](notes/plan.txt) preferred** rejecting `*` outright at first,
adding "safe expansion later".

**Why the change.** That preference assumed expansion was hard. With a catalog
in place it is one flag (`expand_stars=True`), and expansion is strictly safer
than rejection *and* strictly more useful — `SELECT * FROM customers` works
when every column is permitted, and `SELECT * FROM employees` is rejected
naming `salary` and `ssn` specifically, which is exactly what a repair loop
needs.

**To reverse:** reject on any `exp.Star` before pass 3.

---

## 9. `ALL_COLUMNS` exists, with a warning

**Decision.** `{"columns": "*"}` grants every catalog column for that table.

**The risk, stated plainly:** it is a **standing** grant. Add a column to the
table later and it is readable immediately, with no policy change for anyone to
review. A sensitive column added six months from now is exposed by a decision
made today.

**Why keep it.** Without it, every schema change requires a policy edit, and
policies that are painful to maintain get replaced by something permissive.
`denied_columns` composes with it and always wins.

**Recommendation:** explicit column lists on anything sensitive.

---

## 10. Only regenerated SQL is executed

**Decision.** `CompileResult.sql` is rendered from the validated tree, and is
`None` whenever the query was rejected.

**Why.** Validating one string and executing another is how a validator ends up
enforcing nothing. Both source documents call this non-negotiable.

Returning `None` on rejection is the second half: a caller who forgets to check
`.ok` gets a `None`, not an unvalidated query. Failure is loud.

This also collapses most of the **parser-differential** risk. A validator whose
parser disagrees with the database's is a known vulnerability class; handing
the database sqlglot's own fully-qualified, explicitly-quoted output means a
misparse becomes a correctness bug rather than a bypass.

---

## 11. Authorization collects all violations

**Decision.** Passes 1–3 short-circuit; pass 4 collects everything.

**Why.** A repair loop that learns one problem per round trip converges slowly
and burns tokens. `SELECT salary, ssn FROM employees` reports both columns at
once.

Passes 1–3 short-circuit because there is genuinely nothing to do next — you
cannot resolve names in a `DROP`.

---

## 12. Violations never echo query text

**Decision.** Messages and details name codes and objects, never the SQL.

**Why.** These payloads flow back to an LLM and often onward to a user.
Echoing rejected SQL turns a rejection into a disclosure channel. Relatedly, a
denied *table* does not enumerate its columns — that would confirm which
columns exist on a table the subject cannot see.

A test asserts this.

---

## 13. `ConfigurationError` is never a violation

**Decision.** Missing catalog, unknown subject, or a provider returning the
wrong type raises rather than producing a violation.

**Why.** Reporting a wiring bug as "access denied" hides the bug and sends
users chasing permissions they already have. Host errors and query errors are
different categories and should surface differently — a 500, not a 403.

---

## 14. Schema filtering happens before generation

**Decision.** `render_schema_prompt()` ships as part of the package.

**Why.** Guarding only the output means the prompt still contains tables the
caller cannot read — a metadata leak, and a generator of avoidable rejections.
Filtering first improves accuracy and reduces exposure at once, which is the
rare change that helps both. [plan.txt §4](notes/plan.txt) makes the same point.

A test asserts everything the filter advertises actually compiles, so it cannot
drift from what is enforced.

---

## 15. Identifier normalization is delegated to the dialect

**Decision.** One helper, dialect-driven, quoting-aware.

**Why.** Postgres folds unquoted identifiers down, Snowflake folds up, and both
preserve quoted ones. In Postgres `"Orders"` is a **different table** from
`orders`; a validator that lowercases everything lets a policy for one
authorize the other. Hardcoding `.lower()` would be a bypass on Snowflake and
wrong on quoted identifiers everywhere.

---

## 16. Python package, no service, no framework

**Decision.** An importable library. No HTTP sidecar, no CLI, no database
connection, no imports from any host application.

**Why.** The value is being attachable to existing systems. Owning a connection
or a web framework makes it one application's component instead of a reusable
one. Identity lives in the host; a future project that owns users can wrap this
in a service without changing any of it.

**To reverse:** add a thin FastAPI layer over `SqlCompiler` — additive, not a
rewrite.

---

## Open questions for the next phase

1. **Where does the database-side RLS get configured** — Postgres policies
   keyed on `SET LOCAL app.tenant_id`, or secured views per role? `row_filter`
   is now enforced in-process (decision 2), but that is defence in depth, not
   a substitute for the database policy this question is about.
2. **Cost gating**: `EXPLAIN` before execution, or just `statement_timeout` and
   an enforced `LIMIT`? The former needs a connection, which changes the
   package's shape.
3. **Inference protection**: is minimum-group-size enforcement in scope? It is
   a semantic rule, not an AST one, and needs its own policy vocabulary.
4. **Catalog freshness**: who invalidates it when a project's DDL changes?
   Currently the host's problem, and easy to get wrong.
