"""Pass 4: check what the query reads against what the subject may read.

By the time this runs every name is fully resolved, so authorization is a set
of plain lookups -- which is the point.  All the difficulty lives in the
resolve pass; if authorization looks clever, something upstream is wrong.

Violations are collected rather than raised at the first failure, so a repair
loop learns about every problem in one round trip instead of discovering them
one query at a time.
"""

from __future__ import annotations

from typing import List, Set, Tuple

from ..errors import RepairAction, Violation, ViolationCode
from ..ir import ResolvedQuery
from ..names import TableRef
from ..policy import Policy

#: Identifies one ``(table, column)`` pair, for de-duplicating reports.
ColumnKey = Tuple[TableRef, str]


def authorize(resolved: ResolvedQuery, policy: Policy) -> List[Violation]:
    """Return every access violation in ``resolved`` under ``policy``."""
    violations: List[Violation] = []

    denied_tables = _check_tables(resolved, policy, violations)
    _check_columns(resolved, policy, denied_tables, violations)
    _check_functions(resolved, policy, violations)

    return violations


def _check_tables(
    resolved: ResolvedQuery, policy: Policy, violations: List[Violation]
) -> Set[TableRef]:
    """Authorize base tables; return the ones that were denied."""
    denied: Set[TableRef] = set()

    for ref in sorted(resolved.base_tables):
        if policy.permits_table(ref):
            continue
        denied.add(ref)
        violations.append(
            Violation(
                code=ViolationCode.TABLE_ACCESS_DENIED,
                message=f"Access to table '{ref}' is not permitted.",
                action=RepairAction.REMOVE_TABLE,
                table=ref.qualified,
            )
        )

    return denied


def _check_columns(
    resolved: ResolvedQuery,
    policy: Policy,
    denied_tables: Set[TableRef],
    violations: List[Violation],
) -> None:
    """Authorize every resolved column reference."""
    reported: Set[ColumnKey] = set()

    for column_ref in resolved.column_refs:
        # A denied table already explains why its columns are unreachable.
        # Listing them too would be noise, and would confirm which columns
        # exist on a table the subject cannot see.
        if column_ref.table in denied_tables:
            continue

        table_policy = policy.table_policy(column_ref.table)
        if table_policy is None:
            # Only reachable if a column resolved to a table that never
            # appeared as a base table. Deny rather than reason about it.
            violations.append(
                Violation(
                    code=ViolationCode.TABLE_ACCESS_DENIED,
                    message=f"Access to table '{column_ref.table}' is not permitted.",
                    action=RepairAction.REMOVE_TABLE,
                    table=column_ref.table.qualified,
                )
            )
            denied_tables.add(column_ref.table)
            continue

        if table_policy.permits_column(column_ref.column):
            continue

        key = (column_ref.table, column_ref.column)
        if key in reported:
            continue
        reported.add(key)

        violations.append(
            Violation(
                code=ViolationCode.COLUMN_ACCESS_DENIED,
                message=(
                    f"Access to column '{column_ref.column}' of table "
                    f"'{column_ref.table}' is not permitted."
                ),
                action=RepairAction.REMOVE_COLUMN,
                table=column_ref.table.qualified,
                column=column_ref.column,
            )
        )


def _check_functions(
    resolved: ResolvedQuery, policy: Policy, violations: List[Violation]
) -> None:
    """Authorize function calls against the allow-list.

    Without this a query needs no table at all to be dangerous:
    ``SELECT version()`` and ``SELECT pg_read_file('/etc/passwd')`` reference
    nothing the table and column checks can see.
    """
    reported: Set[str] = set()

    for function in resolved.functions:
        if policy.permits_function(function.candidates):
            continue
        if function.display in reported:
            continue
        reported.add(function.display)

        violations.append(
            Violation(
                code=ViolationCode.FUNCTION_NOT_ALLOWED,
                message=f"The function '{function.display}' is not permitted.",
                action=RepairAction.REMOVE_FUNCTION,
                function=function.display,
            )
        )
