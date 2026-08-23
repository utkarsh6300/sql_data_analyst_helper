"""Pass 2: prove the statement is a pure read, deny-by-default.

Checking the root node is necessary but nowhere near sufficient.  Postgres
allows data-modifying CTEs, so all of these have a root of ``Select``:

    WITH x AS (INSERT INTO orders VALUES (1) RETURNING id) SELECT * FROM x
    WITH d AS (DELETE FROM orders RETURNING id) SELECT * FROM d
    SELECT id INTO new_table FROM orders
    SELECT * FROM orders FOR UPDATE

So the whole tree is walked, not just its root.

The most important entry in the deny list is ``Command``.  sqlglot falls back
to a ``Command`` node for any syntax it does not model -- ``VACUUM FULL``,
vendor extensions, future grammar.  Letting ``Command`` through would mean
that everything the parser does not understand is silently permitted, which
inverts deny-by-default exactly where it matters most.
"""

from __future__ import annotations

from typing import List, Tuple, Type

from sqlglot import exp

from ..errors import RepairAction, Violation, ViolationCode


def _resolve(names: Tuple[str, ...]) -> Tuple[Type[exp.Expression], ...]:
    """Resolve class names against ``exp``, skipping any this version lacks.

    sqlglot renames and adds expression classes between releases.  Looking
    them up by name keeps the deny list working across versions instead of
    failing to import on an unrelated upgrade.
    """
    resolved = []
    for name in names:
        node_type = getattr(exp, name, None)
        if isinstance(node_type, type) and issubclass(node_type, exp.Expression):
            resolved.append(node_type)
    return tuple(resolved)


#: Statement types permitted at the root of a query.
ALLOWED_ROOT_TYPES: Tuple[Type[exp.Expression], ...] = _resolve(
    ("Select", "SetOperation", "Union", "Except", "Intersect", "Subquery", "Paren")
)

#: Node types that may not appear anywhere in the tree.
#:
#: ``Fetch`` is deliberately absent: ``FETCH FIRST n ROWS ONLY`` is standard
#: row limiting, not a cursor operation.
FORBIDDEN_NODE_TYPES: Tuple[Type[exp.Expression], ...] = _resolve(
    (
        # Anything the parser could not model. Must stay first in spirit:
        # this is what keeps unknown syntax denied rather than ignored.
        "Command",
        # DML
        "Insert", "Update", "Delete", "Merge",
        # DDL
        "Create", "Drop", "Alter", "AlterTable", "TruncateTable", "Rename",
        # Privileges
        "Grant", "Revoke",
        # Session and transaction state
        "Set", "Use", "Transaction", "Commit", "Rollback", "Savepoint",
        # Filesystem and bulk movement
        "Copy", "Export", "LoadData",
        # Table creation hiding inside a SELECT
        "Into",
        # Write locks: SELECT ... FOR UPDATE needs a writable transaction
        "Lock",
        # Maintenance and introspection statements
        "Analyze", "Vacuum", "Describe", "Pragma", "Cache", "Uncache",
        "Attach", "Detach", "Refresh", "Kill",
        # Procedural execution
        "Call", "Execute", "Prepare",
    )
)


def check_read_only(statement: exp.Expression) -> List[Violation]:
    """Return violations if ``statement`` is anything other than a pure read."""
    violations: List[Violation] = []

    if not isinstance(statement, ALLOWED_ROOT_TYPES):
        violations.append(
            Violation(
                code=ViolationCode.NON_SELECT_STATEMENT,
                message=(
                    f"Only SELECT statements are permitted; got "
                    f"{_friendly(statement)}."
                ),
                action=RepairAction.USE_SINGLE_SELECT,
                details={"statement_type": _friendly(statement)},
            )
        )
        # The root is already disqualifying; walking further would only add
        # noise about nodes belonging to a statement that cannot run anyway.
        return violations

    seen = set()
    for node in statement.walk():
        if isinstance(node, FORBIDDEN_NODE_TYPES):
            label = _friendly(node)
            if label in seen:
                continue
            seen.add(label)
            violations.append(
                Violation(
                    code=ViolationCode.FORBIDDEN_EXPRESSION,
                    message=(
                        f"The query contains a {label} operation, which is not "
                        "permitted in a read-only query."
                    ),
                    action=RepairAction.REWRITE_QUERY,
                    details={"expression_type": label},
                )
            )

    return violations


def _friendly(node: exp.Expression) -> str:
    """A readable name for an expression node."""
    if isinstance(node, exp.Command):
        # `this` holds the leading keyword of the unmodelled statement.
        keyword = str(node.this or "").strip().upper()
        return f"unsupported statement ({keyword})" if keyword else "unsupported statement"
    return type(node).__name__.upper()
