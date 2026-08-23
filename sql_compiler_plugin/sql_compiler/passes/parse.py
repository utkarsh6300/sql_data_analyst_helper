"""Pass 1: turn a string into exactly one statement, or reject it.

This pass is what makes every later pass meaningful.  A validator that
analyses the first statement of ``SELECT 1; DROP TABLE orders`` and then hands
the *original string* to the driver has validated nothing -- so the compiler
rejects multi-statement input outright and, from here on, only ever works with
the parsed tree.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import sqlglot
from sqlglot import exp

from ..errors import RepairAction, Violation, ViolationCode, first_line


def parse_single_statement(
    sql: str, dialect: str
) -> Tuple[Optional[exp.Expression], List[Violation]]:
    """Parse ``sql`` into one statement.

    Returns ``(expression, [])`` on success or ``(None, violations)``.  Failure
    here is always fatal: there is no tree to run further passes against.
    """
    if not sql or not sql.strip():
        return None, [
            Violation(
                code=ViolationCode.EMPTY_STATEMENT,
                message="No SQL was provided.",
                action=RepairAction.REWRITE_QUERY,
            )
        ]

    try:
        statements = sqlglot.parse(sql, dialect=dialect)
    except sqlglot.errors.ParseError as exc:
        return None, [
            Violation(
                code=ViolationCode.PARSE_ERROR,
                message="The query is not valid SQL and could not be parsed.",
                action=RepairAction.REWRITE_QUERY,
                details={"parser_message": first_line(str(exc))},
            )
        ]

    # sqlglot yields a None entry for a trailing semicolon or a stray comment.
    statements = [s for s in statements if s is not None]

    if not statements:
        return None, [
            Violation(
                code=ViolationCode.EMPTY_STATEMENT,
                message="The query contains no executable statement.",
                action=RepairAction.REWRITE_QUERY,
            )
        ]

    if len(statements) > 1:
        return None, [
            Violation(
                code=ViolationCode.MULTIPLE_STATEMENTS,
                message=(
                    f"The query contains {len(statements)} statements; "
                    "exactly one SELECT is allowed."
                ),
                action=RepairAction.USE_SINGLE_SELECT,
                details={"statement_count": len(statements)},
            )
        ]

    return statements[0], []
