"""Pass 5: apply row-level security filters recorded on the policy.

``TablePolicy.row_filter`` used to be recorded and never acted on (see
``docs/04-decisions.md#2``) because the obvious approach -- appending
``WHERE row_filter`` to the outer statement -- fails three ways: it lands on
CTEs and derived tables that never selected the filtered column, it silently
picks one side of a self-join (or errors as ambiguous) and leaves the other
unfiltered, and building the predicate as a string reintroduces injection
inside the layer meant to stop it.

This pass instead replaces every base-table *occurrence* with a filtered
derived table -- ``orders`` becomes
``(SELECT * FROM orders WHERE <row_filter>) AS orders`` -- using the exact
node recorded in :attr:`ResolvedQuery.table_nodes`, not a name-based search.
That composes correctly through joins, CTEs and subqueries because the filter
travels with the table reference itself rather than being bolted onto some
outer, possibly unrelated, WHERE clause, and a self-join gets one filtered
copy per side since each occurrence has its own node.

This is defence in depth, not the security boundary -- see
``docs/02-security-model.md``. Enforce the real policy with Postgres RLS.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from ..catalog import Catalog
from ..errors import ConfigurationError
from ..ir import ResolvedQuery
from ..policy import Policy


def apply_row_filters(resolved: ResolvedQuery, policy: Policy, catalog: Catalog) -> None:
    """Rewrite ``resolved.expression`` in place, wrapping filtered tables.

    A malformed ``row_filter`` is the host's bug, not the query's -- it was
    written into the policy, not produced by the model -- so it raises
    :class:`ConfigurationError` rather than becoming a violation the repair
    loop would try to fix.
    """
    predicate_cache: dict = {}

    for ref, table_node in resolved.table_nodes:
        table_policy = policy.table_policy(ref)
        if table_policy is None or not table_policy.row_filter:
            continue

        if table_policy.row_filter not in predicate_cache:
            predicate_cache[table_policy.row_filter] = _parse_row_filter(
                table_policy.row_filter, catalog.dialect, ref
            )
        predicate = predicate_cache[table_policy.row_filter]

        alias_name = table_node.alias_or_name
        bare_table = table_node.copy()
        bare_table.set("alias", None)

        filtered = (
            exp.select("*")
            .from_(bare_table)
            .where(predicate.copy())
            .subquery(alias_name)
        )
        table_node.replace(filtered)


def _parse_row_filter(row_filter: str, dialect: str, ref) -> exp.Expression:
    """Parse a policy's row filter into an AST predicate.

    Parsed with sqlglot rather than embedded as a string, exactly as
    ``docs/04-decisions.md`` prescribes: "Build predicates as AST nodes,
    never strings." Requiring exactly one statement closes the same door
    ``parse_single_statement`` closes for the query itself -- a stray
    ``; DROP TABLE ...`` after the boolean expression must not disappear
    silently the way ``sqlglot.parse_one`` would let it.
    """
    try:
        statements = [s for s in sqlglot.parse(row_filter, dialect=dialect) if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise ConfigurationError(
            f"row_filter for {ref} is not valid SQL: {exc}"
        ) from exc

    if len(statements) != 1:
        raise ConfigurationError(
            f"row_filter for {ref} must be exactly one boolean expression, "
            f"got {len(statements)} statements"
        )

    predicate = statements[0]
    if predicate.find(exp.Command) is not None or isinstance(predicate, exp.Command):
        raise ConfigurationError(
            f"row_filter for {ref} contains syntax that could not be parsed "
            "as a boolean expression"
        )

    return predicate
