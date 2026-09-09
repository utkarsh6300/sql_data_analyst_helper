"""The intermediate form the resolve pass produces and authorize/rowsec consume.

Kept out of either pass so that neither depends on the other.  A pass owning
the type its peer reads would make the pipeline's shape a matter of import
order rather than of the compiler's explicit sequencing.

Everything here is post-resolution: a :class:`ColumnRef` names the base table
it actually reads, never an alias or a CTE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set, Tuple

from sqlglot import exp

from .names import TableRef


@dataclass(frozen=True)
class ColumnRef:
    """A column use, resolved to the base table it actually reads."""

    table: TableRef
    column: str


@dataclass(frozen=True)
class FunctionRef:
    """A function call, with every name it could reasonably be matched by."""

    display: str
    candidates: frozenset


@dataclass
class ResolvedQuery:
    """Everything the authorization and row-security passes need, and nothing else."""

    expression: exp.Expression
    base_tables: Set[TableRef] = field(default_factory=set)
    column_refs: List[ColumnRef] = field(default_factory=list)
    functions: List[FunctionRef] = field(default_factory=list)
    #: Every base-table occurrence in ``expression``, paired with the ref it
    #: resolved to. One entry per FROM/JOIN item, so a self-join yields two
    #: entries for the same :class:`TableRef` against two distinct nodes.
    #: Kept separate from a name-based lookup (``find_all(exp.Table)``)
    #: because a CTE reference is also an ``exp.Table`` node with the same
    #: name as a real table it happens to shadow -- the row-security pass
    #: must never mistake one for the other.
    table_nodes: List[Tuple[TableRef, exp.Table]] = field(default_factory=list)
