"""What a subject is allowed to read.

The plugin owns this model rather than accepting an opaque callback, so that a
policy is serializable, diffable, and testable without a host present.  Who a
subject *is* -- a user, a service account, a tenant -- is deliberately not
modelled here: the host resolves identity and hands back a :class:`Policy`.

Permissions are keyed on ``(table, column)``, never on column name alone.
``transactions.amount`` and ``payroll.amount`` are different permissions, and
a flat column allow-list cannot express the difference.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field, replace
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional, Sequence, Union

from .catalog import DEFAULT_DIALECT, DEFAULT_SCHEMA
from .errors import ConfigurationError
from .names import TableRef, normalize_identifier


class _AllColumns:
    """Sentinel meaning "every column the catalog lists for this table"."""

    _instance: Optional["_AllColumns"] = None

    def __new__(cls) -> "_AllColumns":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ALL_COLUMNS"

    def __reduce__(self) -> str:
        return "ALL_COLUMNS"


#: Grants every column of a table.  Convenient, but note that it is a
#: *standing* grant: a column added to the table later is readable
#: immediately, with no policy change to review.  Prefer explicit column lists
#: for anything sensitive.
ALL_COLUMNS = _AllColumns()

ColumnGrant = Union[FrozenSet[str], _AllColumns]


#: Deny-by-default allow-list of analytic functions.
#:
#: Names are matched against sqlglot's canonical rendering for the target
#: dialect, which is also the name that actually executes.  This list exists
#: because a query needs no table at all to leak: ``SELECT version()`` and
#: ``SELECT pg_read_file('/etc/passwd')`` both sail past table and column
#: checks untouched.
DEFAULT_ALLOWED_FUNCTIONS: FrozenSet[str] = frozenset(
    {
        # aggregates
        "COUNT", "SUM", "AVG", "MIN", "MAX", "STDDEV", "VARIANCE",
        "ARRAY_AGG", "STRING_AGG", "PERCENTILE_CONT", "PERCENTILE_DISC",
        # window helpers
        "ROW_NUMBER", "RANK", "DENSE_RANK", "NTILE", "LAG", "LEAD",
        "FIRST_VALUE", "LAST_VALUE",
        # numeric
        "ABS", "CEIL", "CEILING", "FLOOR", "ROUND", "TRUNC", "MOD",
        "POWER", "SQRT", "EXP", "LN", "LOG", "GREATEST", "LEAST",
        # null handling / conditionals
        "COALESCE", "NULLIF", "IFNULL", "NVL",
        # strings
        "LOWER", "UPPER", "INITCAP", "LENGTH", "TRIM", "LTRIM", "RTRIM",
        "LPAD", "RPAD", "SUBSTRING", "CONCAT", "CONCAT_WS", "REPLACE",
        "SPLIT_PART", "LEFT", "RIGHT", "REVERSE", "POSITION", "STRPOS",
        # dates
        "DATE_TRUNC", "DATE_PART", "EXTRACT", "DATE_DIFF", "DATEDIFF",
        "DATE_ADD", "DATEADD", "AGE", "TO_DATE", "TO_CHAR", "TO_TIMESTAMP",
        "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP",
        # casting
        "CAST", "TRY_CAST",
    }
)


@dataclass(frozen=True)
class TablePolicy:
    """Column-level grants for one table.

    ``denied_columns`` is evaluated first and always wins, so a deny cannot be
    accidentally overridden by a broad grant such as :data:`ALL_COLUMNS`.
    """

    table: TableRef
    allowed_columns: ColumnGrant = ALL_COLUMNS
    denied_columns: FrozenSet[str] = frozenset()
    #: A boolean SQL predicate, evaluated against this table's own columns,
    #: enforced by ``passes/rowsec.py`` as a filtered derived table. Defence
    #: in depth: row security still belongs in the database first (Postgres
    #: RLS), and this is a second layer behind it, not a replacement.
    row_filter: Optional[str] = None

    def permits_column(self, column: str) -> bool:
        if column in self.denied_columns:
            return False
        if self.allowed_columns is ALL_COLUMNS:
            return True
        return column in self.allowed_columns

    def readable_columns(self, catalog_columns: Sequence[str]) -> list:
        """Columns of this table the subject may actually read.

        Intersected with the catalog so that :data:`ALL_COLUMNS` resolves to
        something concrete for error messages and schema filtering.
        """
        return [c for c in catalog_columns if self.permits_column(c)]

    def to_dict(self) -> Dict[str, Any]:
        # The key must be "columns", matching what `Policy.from_dict` reads:
        # a mismatch would make a serialization roundtrip silently widen an
        # explicit grant to ALL_COLUMNS.
        payload: Dict[str, Any] = {"table": self.table.qualified}
        payload["columns"] = (
            "*" if self.allowed_columns is ALL_COLUMNS else sorted(self.allowed_columns)
        )
        if self.denied_columns:
            payload["denied_columns"] = sorted(self.denied_columns)
        if self.row_filter:
            payload["row_filter"] = self.row_filter
        return payload


@dataclass(frozen=True)
class Policy:
    """The complete set of grants for one subject.

    A table absent from :attr:`tables` is denied.  There is no wildcard that
    grants unlisted tables -- deny-by-default is the whole point, and an
    "allow everything" escape hatch is exactly the thing that gets left on in
    production.
    """

    tables: Mapping[TableRef, TablePolicy] = field(default_factory=dict)
    allowed_functions: FrozenSet[str] = DEFAULT_ALLOWED_FUNCTIONS
    #: Identifies the subject in audit logs.  Never used for authorization.
    subject: Optional[str] = None

    def table_policy(self, ref: TableRef) -> Optional[TablePolicy]:
        return self.tables.get(ref)

    def permits_table(self, ref: TableRef) -> bool:
        return ref in self.tables

    def permits_function(self, candidates: Iterable[str]) -> bool:
        """True if any spelling of a function name is allow-listed.

        sqlglot may canonicalize a function (``DATE_TRUNC`` parses to
        ``TimestampTrunc``), so the caller passes every name the node could
        reasonably be called and a match on one is enough.
        """
        return any(name in self.allowed_functions for name in candidates)

    def with_subject(self, subject: str) -> "Policy":
        return replace(self, subject=subject)

    # -- serialization -------------------------------------------------------

    @classmethod
    def from_dict(
        cls,
        spec: Mapping[str, Any],
        dialect: str = DEFAULT_DIALECT,
        default_schema: str = DEFAULT_SCHEMA,
    ) -> "Policy":
        """Build a policy from plain data.

        Expected shape::

            {
              "subject": "user-123",
              "tables": {
                "public.orders":   {"columns": ["id", "amount"]},
                "public.customers": {"columns": "*", "denied_columns": ["ssn"]},
              },
              "allowed_functions": ["COUNT", "SUM"],   # optional
            }

        A table may also map directly to its column list as a shorthand::

            {"tables": {"public.orders": ["id", "amount"]}}
        """
        raw_tables = spec.get("tables") or {}
        if not isinstance(raw_tables, Mapping):
            raise ConfigurationError("policy 'tables' must be a mapping")

        tables: Dict[TableRef, TablePolicy] = {}
        for raw_name, raw_grant in raw_tables.items():
            ref = TableRef.parse(
                str(raw_name), dialect=dialect, default_schema=default_schema
            )
            tables[ref] = _table_policy_from_spec(ref, raw_grant, dialect)

        raw_functions = spec.get("allowed_functions")
        if raw_functions is None:
            functions = DEFAULT_ALLOWED_FUNCTIONS
        else:
            functions = frozenset(str(name).upper() for name in raw_functions)

        subject = spec.get("subject")
        return cls(
            tables=tables,
            allowed_functions=functions,
            subject=str(subject) if subject is not None else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "tables": {
                ref.qualified: policy.to_dict()
                for ref, policy in sorted(self.tables.items())
            }
        }
        if self.subject is not None:
            payload["subject"] = self.subject
        if self.allowed_functions != DEFAULT_ALLOWED_FUNCTIONS:
            payload["allowed_functions"] = sorted(self.allowed_functions)
        return payload


def _table_policy_from_spec(
    ref: TableRef, grant: Any, dialect: str
) -> TablePolicy:
    """Interpret one entry of a policy's ``tables`` mapping."""
    if isinstance(grant, Mapping):
        raw_columns = grant.get("columns", ALL_COLUMNS)
        raw_denied = grant.get("denied_columns") or ()
        row_filter = grant.get("row_filter")
    elif isinstance(grant, (list, tuple, set, frozenset, str)):
        raw_columns, raw_denied, row_filter = grant, (), None
    else:
        raise ConfigurationError(
            f"grant for {ref} must be a mapping or a column list, "
            f"got {type(grant).__name__}"
        )

    if raw_columns is ALL_COLUMNS or raw_columns == "*":
        allowed: ColumnGrant = ALL_COLUMNS
    elif isinstance(raw_columns, str):
        raise ConfigurationError(
            f"columns for {ref} must be a list or '*', got the string {raw_columns!r}"
        )
    else:
        allowed = frozenset(
            normalize_identifier(str(c), dialect) for c in raw_columns
        )
        if not allowed:
            raise ConfigurationError(
                f"grant for {ref} lists no columns; omit the table to deny it"
            )

    return TablePolicy(
        table=ref,
        allowed_columns=allowed,
        denied_columns=frozenset(
            normalize_identifier(str(c), dialect) for c in raw_denied
        ),
        row_filter=str(row_filter) if row_filter else None,
    )


class PolicyProvider(abc.ABC):
    """How the compiler asks the host what a subject may read.

    Implement this in the application that owns identity.  The compiler calls
    :meth:`resolve` once per compilation and never caches the result, so a
    revoked grant takes effect on the next query.
    """

    @abc.abstractmethod
    def resolve(self, subject: Any) -> Policy:
        """Return the policy for ``subject``.

        Raise :class:`~sql_compiler.errors.ConfigurationError` if the subject
        is unknown.  Returning an empty :class:`Policy` is also valid and
        denies every table -- but do that only when you mean "this subject
        genuinely has no grants", never as an error fallback.
        """


class StaticPolicyProvider(PolicyProvider):
    """A provider backed by an in-memory mapping. Useful for tests and demos."""

    def __init__(self, policies: Mapping[Any, Policy]) -> None:
        self._policies = dict(policies)

    def resolve(self, subject: Any) -> Policy:
        try:
            return self._policies[subject]
        except KeyError as exc:
            raise ConfigurationError(f"no policy registered for subject {subject!r}") from exc
