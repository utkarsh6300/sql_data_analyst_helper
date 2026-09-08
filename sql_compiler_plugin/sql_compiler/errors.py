"""Structured, machine-readable compiler diagnostics.

Every rejection the compiler emits is a :class:`Violation` with a stable
``code``.  Nothing here formats prose for an end user, and nothing here ever
carries a raw database error message: the host decides what a human sees, and
the LLM repair loop consumes ``code``/``action`` rather than parsing English.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ViolationCode(str, Enum):
    """Stable identifiers for every way a query can be rejected.

    These are part of the public contract -- hosts and the repair loop switch
    on them, so codes are added but never renamed or repurposed.
    """

    # --- Stage 1: parsing and statement shape -------------------------------
    PARSE_ERROR = "PARSE_ERROR"
    EMPTY_STATEMENT = "EMPTY_STATEMENT"
    MULTIPLE_STATEMENTS = "MULTIPLE_STATEMENTS"

    # --- Stage 2: read-only enforcement -------------------------------------
    NON_SELECT_STATEMENT = "NON_SELECT_STATEMENT"
    FORBIDDEN_EXPRESSION = "FORBIDDEN_EXPRESSION"

    # --- Stage 3: name resolution -------------------------------------------
    EMPTY_CATALOG = "EMPTY_CATALOG"
    UNKNOWN_TABLE = "UNKNOWN_TABLE"
    NAME_RESOLUTION_FAILED = "NAME_RESOLUTION_FAILED"
    NATURAL_JOIN_NOT_SUPPORTED = "NATURAL_JOIN_NOT_SUPPORTED"

    # --- Stage 4: authorization ---------------------------------------------
    TABLE_ACCESS_DENIED = "TABLE_ACCESS_DENIED"
    COLUMN_ACCESS_DENIED = "COLUMN_ACCESS_DENIED"
    FUNCTION_NOT_ALLOWED = "FUNCTION_NOT_ALLOWED"

    # --- Stage 5: code generation -------------------------------------------
    GENERATION_FAILED = "GENERATION_FAILED"

    # --- Cross-cutting: unanticipated failures ------------------------------
    INTERNAL_ERROR = "INTERNAL_ERROR"


class RepairAction(str, Enum):
    """A hint telling the caller (or the LLM) how to fix a violation.

    Deliberately coarse.  A precise instruction would leak the very
    information the violation exists to withhold -- naming the columns a user
    *may* use is fine, naming the ones they may not is not.
    """

    REWRITE_QUERY = "REWRITE_QUERY"
    REMOVE_TABLE = "REMOVE_TABLE"
    REMOVE_COLUMN = "REMOVE_COLUMN"
    REMOVE_FUNCTION = "REMOVE_FUNCTION"
    USE_SINGLE_SELECT = "USE_SINGLE_SELECT"
    NOT_REPAIRABLE = "NOT_REPAIRABLE"


@dataclass(frozen=True)
class Violation:
    """One reason a query was rejected."""

    code: ViolationCode
    message: str
    action: RepairAction = RepairAction.REWRITE_QUERY
    table: Optional[str] = None
    column: Optional[str] = None
    function: Optional[str] = None
    # Free-form, non-sensitive extras (e.g. the offending node type).
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe form, for HTTP responses and LLM repair prompts."""
        payload: Dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
            "action": self.action.value,
        }
        for key in ("table", "column", "function"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.details:
            payload["details"] = dict(self.details)
        return payload

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"[{self.code.value}] {self.message}"


class SqlCompilerError(Exception):
    """Base class for everything this package raises."""


class CompilationRejected(SqlCompilerError):
    """Raised by the strict entry point when a query fails to compile.

    The non-raising entry point returns a ``CompileResult`` instead; both carry
    the same violations, so hosts can choose exceptions or result objects
    without losing detail.
    """

    def __init__(self, violations: List[Violation]) -> None:
        self.violations = list(violations)
        summary = "; ".join(str(v) for v in self.violations) or "query rejected"
        super().__init__(summary)

    def to_dict(self) -> Dict[str, Any]:
        return {"violations": [v.to_dict() for v in self.violations]}


class ConfigurationError(SqlCompilerError):
    """The host handed the compiler an unusable catalog or policy.

    Distinct from ``CompilationRejected`` on purpose: this is the host's bug,
    not the query's, and it must never be reported to an end user as "access
    denied".
    """


def first_line(message: str) -> str:
    """Reduce a third-party error to one short, safe line.

    Parser and optimizer messages are the only outside text that reaches
    ``Violation.details``.  They can run to many lines and can quote the query
    back, so every pass truncates them the same way rather than each inventing
    its own limit.
    """
    lines = message.strip().splitlines()
    return lines[0][:200] if lines else ""
