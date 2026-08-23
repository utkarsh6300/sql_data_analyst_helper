"""The intermediate form the resolve pass produces and authorize consumes.

Kept out of either pass so that neither depends on the other.  A pass owning
the type its peer reads would make the pipeline's shape a matter of import
order rather than of the compiler's explicit sequencing.

Everything here is post-resolution: a :class:`ColumnRef` names the base table
it actually reads, never an alias or a CTE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

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
    """Everything the authorization pass needs, and nothing else."""

    expression: exp.Expression
    base_tables: Set[TableRef] = field(default_factory=set)
    column_refs: List[ColumnRef] = field(default_factory=list)
    functions: List[FunctionRef] = field(default_factory=list)
