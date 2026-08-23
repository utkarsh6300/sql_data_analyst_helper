"""Shared fixtures: a small two-schema catalog and a restrictive policy.

Visible to every test under ``tests/``, both the unit suite and the
integration suite, so the two describe the same world.
"""

from __future__ import annotations

import pytest

from sql_compiler import Catalog, Policy, SqlCompiler


@pytest.fixture
def catalog() -> Catalog:
    """A catalog with a sensitive table and a same-named table in another schema."""
    return Catalog.from_dict(
        {
            "public": {
                "orders": {
                    "id": "INT",
                    "customer_id": "INT",
                    "amount": "NUMERIC",
                    "tenant_id": "INT",
                },
                "customers": {"id": "INT", "name": "TEXT", "region": "TEXT"},
                "employees": {"id": "INT", "name": "TEXT", "salary": "NUMERIC", "ssn": "TEXT"},
            },
            # Same table name, different schema. A check that compares bare
            # names would treat this as public.orders.
            "secret": {
                "orders": {"id": "INT", "internal_note": "TEXT"},
            },
        }
    )


@pytest.fixture
def policy() -> Policy:
    """Grants orders and customers; employees is readable but not salary/ssn."""
    return Policy.from_dict(
        {
            "subject": "analyst-1",
            "tables": {
                "public.orders": ["id", "customer_id", "amount"],
                "public.customers": ["id", "name", "region"],
                "public.employees": {
                    "columns": "*",
                    "denied_columns": ["salary", "ssn"],
                },
            },
        }
    )


@pytest.fixture
def compiler(catalog) -> SqlCompiler:
    return SqlCompiler(catalog=catalog)
