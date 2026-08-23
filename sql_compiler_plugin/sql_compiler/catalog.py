"""The database catalog the compiler resolves names against.

Name resolution is the phase everything else depends on.  Without a catalog
you cannot expand ``SELECT *``, cannot map ``p.amount`` back to
``transactions.amount``, and cannot tell a CTE name apart from a real table --
which is to say you cannot authorize anything.  A missing catalog is therefore
a hard failure, never a silent pass.

Two constructors are provided because hosts have the schema in one of two
shapes: already structured (:meth:`Catalog.from_dict`) or as the raw ``CREATE
TABLE`` text they were already storing for prompt context
(:meth:`Catalog.from_ddl`).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import sqlglot
from sqlglot import exp

from .errors import ConfigurationError
from .names import TableRef, normalize_identifier

DEFAULT_DIALECT = "postgres"
DEFAULT_SCHEMA = "public"

#: Placeholder type used when a column's type is unknown.  ``qualify`` only
#: needs column *names* to resolve and expand stars, so an unknown type never
#: blocks authorization.
UNKNOWN_TYPE = "UNKNOWN"


class Catalog:
    """Normalized ``{schema: {table: {column: type}}}`` with lookup helpers."""

    def __init__(
        self,
        tables: Mapping[TableRef, Mapping[str, str]],
        dialect: str = DEFAULT_DIALECT,
        default_schema: str = DEFAULT_SCHEMA,
    ) -> None:
        self.dialect = dialect
        self.default_schema = normalize_identifier(default_schema, dialect)
        self._tables: Dict[TableRef, Dict[str, str]] = {
            ref: dict(columns) for ref, columns in tables.items()
        }

    # -- construction --------------------------------------------------------

    @classmethod
    def from_dict(
        cls,
        schema: Mapping[str, Any],
        dialect: str = DEFAULT_DIALECT,
        default_schema: str = DEFAULT_SCHEMA,
    ) -> "Catalog":
        """Build from a nested or flat mapping.

        Accepts either shape, since hosts write both::

            {"public": {"orders": {"id": "INT"}}}     # nested by schema
            {"public.orders": {"id": "INT"}}          # flat, qualified
            {"orders": {"id": "INT"}}                 # flat, default schema
            {"orders": ["id", "amount"]}              # names only, no types

        Ambiguity between the nested and flat forms is resolved by inspecting
        the values: a mapping whose values are themselves mappings-of-mappings
        is nested.
        """
        normalized_default = normalize_identifier(default_schema, dialect)
        tables: Dict[TableRef, Dict[str, str]] = {}

        for key, value in schema.items():
            if _is_nested_schema(value):
                schema_name = normalize_identifier(str(key), dialect)
                for table_name, columns in value.items():
                    ref = TableRef.parse(
                        f"{schema_name}.{table_name}",
                        dialect=dialect,
                        default_schema=normalized_default,
                    )
                    tables[ref] = _normalize_columns(columns, dialect, ref)
            else:
                ref = TableRef.parse(
                    str(key), dialect=dialect, default_schema=normalized_default
                )
                tables[ref] = _normalize_columns(value, dialect, ref)

        return cls(tables, dialect=dialect, default_schema=default_schema)

    @classmethod
    def from_ddl(
        cls,
        statements: Iterable[str],
        dialect: str = DEFAULT_DIALECT,
        default_schema: str = DEFAULT_SCHEMA,
        strict: bool = True,
    ) -> "Catalog":
        """Build by parsing ``CREATE TABLE`` statements.

        ``statements`` may be a list of individual statements or of multi-
        statement blobs -- the kind of free text a retrieval layer typically
        stores.  Non-``CREATE TABLE`` statements (indexes, comments, views)
        are ignored rather than treated as errors, since real DDL dumps are
        full of them.

        With ``strict=True`` a statement that will not parse raises
        :class:`ConfigurationError`.  Set ``strict=False`` only if you accept
        that an unparseable ``CREATE TABLE`` yields a catalog missing that
        table -- which, because unknown tables are denied, turns a schema
        problem into a stream of confusing access denials.
        """
        normalized_default = normalize_identifier(default_schema, dialect)
        tables: Dict[TableRef, Dict[str, str]] = {}

        for blob in statements:
            if not blob or not blob.strip():
                continue
            try:
                parsed = sqlglot.parse(blob, dialect=dialect)
            except sqlglot.errors.ParseError as exc:
                if strict:
                    raise ConfigurationError(
                        f"could not parse DDL: {exc}"
                    ) from exc
                continue

            for statement in parsed:
                extracted = _table_from_create(statement, dialect, normalized_default)
                if extracted is not None:
                    ref, columns = extracted
                    tables[ref] = columns

        return cls(tables, dialect=dialect, default_schema=default_schema)

    # -- lookup --------------------------------------------------------------

    def __bool__(self) -> bool:
        return bool(self._tables)

    def __len__(self) -> int:
        return len(self._tables)

    def __contains__(self, ref: object) -> bool:
        return ref in self._tables

    @property
    def tables(self) -> List[TableRef]:
        return sorted(self._tables)

    def columns(self, ref: TableRef) -> List[str]:
        """Column names for ``ref``; empty if the table is unknown."""
        return list(self._tables.get(ref, {}))

    def has_column(self, ref: TableRef, column: str) -> bool:
        return column in self._tables.get(ref, {})

    def ref(self, raw: str) -> TableRef:
        """Parse a name against this catalog's dialect and default schema."""
        return TableRef.parse(
            raw, dialect=self.dialect, default_schema=self.default_schema
        )

    def to_mapping_schema(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        """Render as the nested dict sqlglot's ``qualify`` expects."""
        nested: Dict[str, Dict[str, Dict[str, str]]] = {}
        for ref, columns in self._tables.items():
            nested.setdefault(ref.schema, {})[ref.name] = dict(columns)
        return nested


# -- helpers -----------------------------------------------------------------


def _is_nested_schema(value: Any) -> bool:
    """True if ``value`` looks like ``{table: {column: type}}``."""
    if not isinstance(value, Mapping) or not value:
        return False
    return all(isinstance(inner, (Mapping, list, tuple, set, frozenset)) for inner in value.values())


def _normalize_columns(
    columns: Any, dialect: Optional[str], ref: TableRef
) -> Dict[str, str]:
    """Accept ``{name: type}`` or a bare sequence of names."""
    if isinstance(columns, Mapping):
        pairs: Sequence[Tuple[str, str]] = [
            (str(name), str(type_ or UNKNOWN_TYPE)) for name, type_ in columns.items()
        ]
    elif isinstance(columns, (list, tuple, set, frozenset)):
        pairs = [(str(name), UNKNOWN_TYPE) for name in columns]
    else:
        raise ConfigurationError(
            f"columns for {ref} must be a mapping or a sequence, got {type(columns).__name__}"
        )

    if not pairs:
        raise ConfigurationError(f"table {ref} has no columns")

    return {normalize_identifier(name, dialect): type_ for name, type_ in pairs}


def _table_from_create(
    statement: Optional[exp.Expression],
    dialect: str,
    default_schema: str,
) -> Optional[Tuple[TableRef, Dict[str, str]]]:
    """Pull ``(ref, columns)`` out of a ``CREATE TABLE``, or ``None``."""
    if not isinstance(statement, exp.Create):
        return None
    if (statement.args.get("kind") or "").upper() != "TABLE":
        return None

    target = statement.this
    # A `CREATE TABLE x AS SELECT ...` has a bare Table here and no column
    # definitions, so there is nothing to harvest.
    if not isinstance(target, exp.Schema) or not isinstance(target.this, exp.Table):
        return None

    ref = TableRef.from_table_node(
        target.this, dialect=dialect, default_schema=default_schema
    )

    columns: Dict[str, str] = {}
    for definition in target.expressions:
        if not isinstance(definition, exp.ColumnDef):
            # Table-level constraints (PRIMARY KEY (a, b), FOREIGN KEY ...)
            # live alongside column defs; they carry no column of their own.
            continue
        kind = definition.args.get("kind")
        columns[normalize_identifier(definition.name, dialect)] = (
            kind.sql(dialect=dialect) if kind is not None else UNKNOWN_TYPE
        )

    if not columns:
        return None
    return ref, columns
