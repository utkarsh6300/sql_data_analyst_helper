"""Pass 3: resolve every name in the query to a real table and column.

This is the phase the transcripts underweight and everything else depends on.
An unqualified parse tree tells you a node is called ``amount``; it does not
tell you which relation it belongs to, whether ``*`` covers a column you must
not expose, or whether ``regional_sales`` is a table or a locally-defined CTE.
Authorizing against that tree authorizes the wrong thing.

Running qualification first collapses four separate bypasses into one solved
problem:

* ``SELECT *``            -- expanded into explicit columns, so they get checked
* ``p.amount``            -- alias resolved to ``transactions.amount``
* ``secret.orders``       -- schema made explicit, so it cannot pose as ``public.orders``
* ``WITH t AS (...)``     -- CTE names distinguished from base tables

Qualification is also a fail-closed gate: if a name cannot be resolved against
the catalog, the query is rejected rather than passed along unresolved.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple, Type

from sqlglot import exp
from sqlglot.errors import OptimizeError, SqlglotError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

from ..catalog import Catalog
from ..errors import ConfigurationError, RepairAction, Violation, ViolationCode, first_line
from ..ir import ColumnRef, FunctionRef, ResolvedQuery
from ..names import TableRef, normalize_identifier

#: Matches a function rendering of the form ``NAME(``.  Requiring the paren
#: avoids picking up an operand when a function renders as an operator (for
#: example Postgres rendering CONCAT as ``a || b``).
_FUNCTION_CALL = re.compile(r'^\s*"?([A-Za-z_][A-Za-z0-9_]*)"?\s*\(')


def _resolve_types(names: Tuple[str, ...]) -> Tuple[Type[exp.Expression], ...]:
    """Resolve class names against ``exp``, skipping any this version lacks.

    Mirrors ``passes/readonly.py``'s own resolver: sqlglot renames and adds
    expression classes between releases, so looking them up by name keeps
    this working across versions instead of failing to import on an
    unrelated upgrade.
    """
    resolved = []
    for name in names:
        node_type = getattr(exp, name, None)
        if isinstance(node_type, type) and issubclass(node_type, exp.Expression):
            resolved.append(node_type)
    return tuple(resolved)


#: Node types that are structural SQL syntax rather than callable functions,
#: even though sqlglot models them via the ``Func`` base class for parsing
#: convenience:
#:
#: * ``Connector`` (``AND``/``OR``/``XOR``) -- logical connectives.
#: * ``SubqueryPredicate`` (``EXISTS``) -- a boolean subquery operator.
#: * ``Case``, ``If`` -- conditional expressions.
#:
#: Every one of these is unavoidable, ordinary SQL syntax that a correct
#: query cannot omit. Deny-by-default is meant for callable functions whose
#: presence or absence is a meaningful capability decision -- treating these
#: the same way would reject nearly every non-trivial query outright.
_NON_FUNCTION_SYNTAX_TYPES = _resolve_types(("Connector", "SubqueryPredicate", "Case", "If"))


def resolve(
    statement: exp.Expression, catalog: Catalog
) -> Tuple[Optional[ResolvedQuery], List[Violation]]:
    """Qualify ``statement`` against ``catalog`` and extract what it reads.

    Returns ``(resolved, [])`` or ``(None, violations)``.  Failure is fatal:
    without resolution there is nothing trustworthy to authorize.
    """
    if not catalog:
        return None, [
            Violation(
                code=ViolationCode.EMPTY_CATALOG,
                message=(
                    "No database schema is registered, so the query cannot be "
                    "validated."
                ),
                action=RepairAction.NOT_REPAIRABLE,
            )
        ]

    # NATURAL JOIN's join condition is an implicit equality over every
    # same-named column on both sides. sqlglot's qualify() does not expand it
    # into real Column nodes -- it stays a bare `method=NATURAL` marker -- so
    # a shared column denied on one side is compared at execution time
    # without ever being seen by authorization. Reject unconditionally rather
    # than trying to reconstruct the predicate ourselves.
    if _find_natural_join(statement) is not None:
        return None, [_natural_join_violation()]

    # Check table existence before qualification. sqlglot reports a missing
    # table as an unresolvable *column*, which is an actively misleading thing
    # to hand back to a repair loop.
    unknown = _unknown_base_tables(statement, catalog)
    if unknown:
        return None, [
            Violation(
                code=ViolationCode.UNKNOWN_TABLE,
                message=f"Table '{ref}' does not exist in the schema.",
                action=RepairAction.REMOVE_TABLE,
                table=ref.qualified,
            )
            for ref in sorted(unknown)
        ]

    try:
        qualified = qualify(
            statement.copy(),
            schema=catalog.to_mapping_schema(),
            dialect=catalog.dialect,
            db=catalog.default_schema,
            # Never guess at a schema the catalog does not describe; an
            # inferred table is an unauthorized table wearing a disguise.
            infer_schema=False,
            # Expands `SELECT *` into real columns so they can be checked.
            expand_stars=True,
            qualify_columns=True,
            # Turns an unresolvable column into an error instead of a pass.
            validate_qualify_columns=True,
        )
    except (OptimizeError, SqlglotError) as exc:
        return None, [
            Violation(
                code=ViolationCode.NAME_RESOLUTION_FAILED,
                message=(
                    "The query refers to a table or column that could not be "
                    "resolved against the schema."
                ),
                action=RepairAction.REWRITE_QUERY,
                details={"resolver_message": first_line(str(exc))},
            )
        ]

    return _extract(qualified, catalog)


def _extract(
    qualified: exp.Expression, catalog: Catalog
) -> Tuple[Optional[ResolvedQuery], List[Violation]]:
    """Walk every scope and collect base tables, columns and functions."""
    resolved = ResolvedQuery(expression=qualified)

    try:
        scopes = traverse_scope(qualified)
    except SqlglotError as exc:
        return None, [
            Violation(
                code=ViolationCode.NAME_RESOLUTION_FAILED,
                message="The structure of the query could not be analysed.",
                action=RepairAction.REWRITE_QUERY,
                details={"resolver_message": first_line(str(exc))},
            )
        ]

    for scope in scopes:
        # `scope.sources` maps each visible name to either an exp.Table (a real
        # base table) or a Scope (a CTE or derived table). That distinction is
        # what stops a CTE name from being treated as an unauthorized table,
        # and what lets us skip columns that an inner scope already checked.
        source_refs: Dict[str, TableRef] = {}
        for name, source in scope.sources.items():
            if isinstance(source, exp.Table):
                try:
                    ref = TableRef.from_table_node(
                        source,
                        dialect=catalog.dialect,
                        default_schema=catalog.default_schema,
                    )
                except ConfigurationError:
                    # `source` is an exp.Table that does not name a real
                    # table -- sqlglot represents an unmodelled relation
                    # (a table-valued function such as generate_series() or
                    # jsonb_each(), used directly in FROM/JOIN) this way.
                    # There is no catalog entry to authorize against, so
                    # fail closed instead of guessing.
                    return None, [_unsupported_table_expression_violation()]
                source_refs[name] = ref
                resolved.base_tables.add(ref)

        # A correlated subquery references columns owned by an enclosing
        # scope. They are unresolvable here but appear again in that enclosing
        # scope's own columns, so skipping them loses no coverage.
        external = {id(column) for column in scope.external_columns}

        for column in scope.columns:
            if id(column) in external:
                continue

            source_name = column.table
            if not source_name:
                # Qualification sets a source on every resolvable column, so a
                # bare one here means resolution silently fell short.
                return None, [_unresolved_column_violation()]

            if source_name in source_refs:
                resolved.column_refs.append(
                    ColumnRef(
                        table=source_refs[source_name],
                        column=normalize_identifier(column.name, catalog.dialect),
                    )
                )
            elif source_name in scope.sources:
                # Resolves to a CTE or derived table. Its own scope was
                # visited separately, where its base columns were recorded.
                continue
            else:
                return None, [_unresolved_column_violation()]

        # `expand_stars` should have removed every star. One surviving here
        # would mean unchecked columns reaching the database.
        for star in scope.stars:
            if isinstance(star, exp.Star) or star.find(exp.Star):
                return None, [
                    Violation(
                        code=ViolationCode.NAME_RESOLUTION_FAILED,
                        message=(
                            "A wildcard in the query could not be expanded into "
                            "explicit columns."
                        ),
                        action=RepairAction.REWRITE_QUERY,
                    )
                ]

    resolved.functions = _collect_functions(qualified, catalog.dialect)
    return resolved, []


def _unknown_base_tables(statement: exp.Expression, catalog: Catalog) -> Set[TableRef]:
    """Base tables referenced by the query that the catalog does not describe.

    Runs on the unqualified tree, so it must distinguish CTE names itself --
    which ``scope.sources`` does, exactly as it does after qualification.
    """
    unknown: Set[TableRef] = set()
    try:
        scopes = traverse_scope(statement)
    except SqlglotError:
        # Diagnostics only. Qualification below will reject the query anyway.
        return unknown

    for scope in scopes:
        for source in scope.sources.values():
            if not isinstance(source, exp.Table):
                continue
            try:
                ref = TableRef.from_table_node(
                    source,
                    dialect=catalog.dialect,
                    default_schema=catalog.default_schema,
                )
            except Exception:
                continue
            if ref not in catalog:
                unknown.add(ref)
    return unknown


def _collect_functions(expression: exp.Expression, dialect: str) -> List[FunctionRef]:
    """Collect every function call with all the names it may be known by.

    sqlglot canonicalizes function classes, so one call can legitimately be
    spelled several ways: ``DATE_TRUNC`` parses to a ``TimestampTrunc`` node
    whose ``sql_name()`` is ``TIMESTAMP_TRUNC`` but which renders back as
    ``DATE_TRUNC``. An allow-list entry may match any of them.

    Nodes matching :data:`_NON_FUNCTION_SYNTAX_TYPES` are skipped entirely.
    ``exp.Exists`` (``EXISTS``/``NOT EXISTS``), ``exp.Connector``
    (``AND``/``OR``/``XOR``) and ``exp.Case``/``exp.If`` (``CASE WHEN``) are
    all, structurally, subclasses of ``exp.Func`` in sqlglot's hierarchy --
    a parsing convenience, not a sign that they are callable functions a
    policy should have to allow-list. Treating them as functions would
    deny-by-default reject nearly every non-trivial query: there is no
    query with a correlated subquery, a boolean predicate, or a conditional
    expression that does not use at least one of them.
    """
    functions: List[FunctionRef] = []
    seen: Set[frozenset] = set()

    for node in expression.find_all(exp.Func):
        if isinstance(node, _NON_FUNCTION_SYNTAX_TYPES):
            continue

        candidates: Set[str] = set()

        if isinstance(node, exp.Anonymous):
            # `sql_name()` is the useless literal "ANONYMOUS" here; the real
            # name -- pg_read_file, version -- lives in `this`.
            display = str(node.this or "").upper()
            if display:
                candidates.add(display)
        else:
            display = node.sql_name().upper()
            candidates.add(display)
            candidates.add(node.key.upper())

        try:
            match = _FUNCTION_CALL.match(node.sql(dialect=dialect))
        except Exception:
            match = None
        if match:
            rendered = match.group(1).upper()
            candidates.add(rendered)
            if not display:
                display = rendered

        if not candidates:
            continue

        key = frozenset(candidates)
        if key in seen:
            continue
        seen.add(key)
        functions.append(
            FunctionRef(display=display or sorted(candidates)[0], candidates=key)
        )

    return functions


def _find_natural_join(statement: exp.Expression) -> Optional[exp.Join]:
    for join in statement.find_all(exp.Join):
        if join.args.get("method") == "NATURAL":
            return join
    return None


def _natural_join_violation() -> Violation:
    return Violation(
        code=ViolationCode.NATURAL_JOIN_NOT_SUPPORTED,
        message=(
            "NATURAL JOIN is not supported because its join columns cannot "
            "be verified against the access policy. Use an explicit "
            "JOIN ... ON or JOIN ... USING (...) instead."
        ),
        action=RepairAction.REWRITE_QUERY,
    )


def _unsupported_table_expression_violation() -> Violation:
    return Violation(
        code=ViolationCode.NAME_RESOLUTION_FAILED,
        message=(
            "The query's FROM clause uses a table expression that is not a "
            "table, view, CTE or subquery, so it could not be resolved."
        ),
        action=RepairAction.REWRITE_QUERY,
    )


def _unresolved_column_violation() -> Violation:
    return Violation(
        code=ViolationCode.NAME_RESOLUTION_FAILED,
        message=(
            "A column in the query could not be traced to the table it reads "
            "from."
        ),
        action=RepairAction.REWRITE_QUERY,
    )
