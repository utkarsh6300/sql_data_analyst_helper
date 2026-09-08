"""Identifier normalization and qualified table names.

Every comparison the compiler makes -- catalog lookup, policy lookup, column
authorization -- is a string comparison between an identifier written by an
LLM and an identifier written by a human configuring a policy.  If those two
normalize differently, authorization silently compares the wrong strings, so
all normalization funnels through this module.

Normalization is delegated to the dialect rather than hardcoded: Postgres
folds unquoted identifiers to lower case, Snowflake folds to upper, and both
preserve quoted identifiers verbatim.  ``"Orders"`` and ``Orders`` are
genuinely different tables in Postgres, and treating them as one would be a
bypass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlglot import exp
from sqlglot.dialects.dialect import Dialect

from .errors import ConfigurationError


def normalize_identifier(name: str, dialect: Optional[str], quoted: bool = False) -> str:
    """Fold a bare identifier according to the dialect's case rules."""
    identifier = exp.to_identifier(name, quoted=quoted)
    if identifier is None:
        raise ConfigurationError(f"{name!r} is not a usable identifier")
    try:
        resolved_dialect = Dialect.get_or_raise(dialect)
    except Exception as exc:
        raise ConfigurationError(f"{dialect!r} is not a supported SQL dialect") from exc
    return resolved_dialect.normalize_identifier(identifier).name


@dataclass(frozen=True, order=True)
class TableRef:
    """A schema-qualified table name, already normalized.

    Instances are only ever produced by the constructors below, so anything
    holding a ``TableRef`` can compare it directly.  Keeping the schema part
    mandatory is what closes the ``other_schema.transactions`` bypass -- an
    unqualified name is resolved against the catalog's default schema exactly
    once, here, rather than being compared bare.
    """

    schema: str
    name: str

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"

    def __str__(self) -> str:
        return self.qualified

    @classmethod
    def parse(cls, raw: str, dialect: Optional[str], default_schema: str) -> "TableRef":
        """Build a ref from a config string such as ``orders`` or ``public.orders``."""
        if not raw or not raw.strip():
            raise ConfigurationError("table name cannot be empty")

        try:
            table = exp.to_table(raw.strip(), dialect=dialect)
        except Exception as exc:
            raise ConfigurationError(f"{raw!r} does not name a table") from exc
        if table.catalog:
            raise ConfigurationError(
                f"three-part name {raw!r} is not supported; "
                "cross-database references are out of scope"
            )
        if not table.name:
            raise ConfigurationError(f"{raw!r} does not name a table")

        return cls.from_table_node(table, dialect=dialect, default_schema=default_schema)

    @classmethod
    def from_table_node(
        cls,
        table: exp.Table,
        dialect: Optional[str],
        default_schema: str,
    ) -> "TableRef":
        """Build a ref from an ``exp.Table`` node found in a parsed query."""
        name_id = table.this
        schema_id = table.args.get("db")

        name = _normalize_part(name_id, dialect) if isinstance(name_id, exp.Identifier) else None
        if not name:
            raise ConfigurationError(f"cannot read a table name from {table.sql()!r}")

        schema = (
            _normalize_part(schema_id, dialect)
            if isinstance(schema_id, exp.Identifier) and schema_id.name
            else default_schema
        )
        return cls(schema=schema, name=name)


def _normalize_part(identifier: exp.Identifier, dialect: Optional[str]) -> str:
    """Normalize one identifier node, honouring whether it was quoted."""
    return normalize_identifier(identifier.name, dialect, quoted=identifier.quoted)
