# Documentation

Four documents, in the order that makes them easiest to absorb.

| # | Document | Answers |
|---|---|---|
| 1 | [Architecture](01-architecture.md) | How does it work? What does each file do? |
| 2 | [Security model](02-security-model.md) | What does it actually stop, and what does it not? |
| 3 | [Integration](03-integration.md) | How do I attach this to my application? |
| 4 | [Design decisions](04-decisions.md) | Why is it built this way, and how do I change it? |

The [top-level README](../README.md) is the short version — API reference and
a usage example. These go underneath it.

[notes/](notes/) holds the raw design transcripts these four documents were
written against. They are unedited source material, cited throughout
[Design decisions](04-decisions.md) — not documentation in their own right.

## The 60-second version

An LLM writes SQL. You cannot trust it. Before that SQL reaches your database,
this package:

1. **parses** it — one statement only, or reject;
2. **proves it is a read** — walking the whole tree, not just the root;
3. **resolves every name** against your real schema — expanding `SELECT *`,
   turning `p.amount` into `transactions.amount`, telling CTEs apart from
   tables;
4. **authorizes** the resolved tables, columns and functions against a policy;
5. **regenerates** the SQL from the validated tree.

Step 5 is the one that makes the rest matter: **you execute what came out of
step 5, never the string the model produced.** Validating one string and
executing another is how a validator ends up enforcing nothing.

Step 3 is the one that makes steps 2 and 4 *correct*. It is the step both
source transcripts underweight, and it is where four separate-looking bypasses
turn out to be a single missing phase. [Architecture](01-architecture.md)
explains that in detail; [Security model](02-security-model.md) catalogues the
bypasses.

## The most important caveat

This is a **validation layer, not a security boundary.** One bug in a
traversal, or one code path that reaches the database without going through
here, and enforcement evaporates. The database is the only place where
enforcement is unconditional.

Read [Security model § What this does not defend against](02-security-model.md#what-this-does-not-defend-against)
before putting this in front of real data.
