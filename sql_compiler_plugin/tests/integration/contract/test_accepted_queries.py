"""Legitimate analyst queries must survive the compiler.

The rest of the suite is mostly about what gets rejected, which only proves
half of the contract.  A compiler that denied everything would pass all of it.
These are the queries a real analyst workload produces, and they have to
compile -- otherwise the plugin is a availability outage dressed as security.
"""

from __future__ import annotations

import pytest
import sqlglot

from sql_compiler import SqlCompiler

pytestmark = pytest.mark.integration


ACCEPTED = [
    # plain projection
    "SELECT id, amount FROM orders",
    "SELECT o.id, o.amount FROM orders o",
    "SELECT amount AS total FROM orders",
    # filtering and ordering
    "SELECT id FROM orders WHERE amount > 100",
    "SELECT id FROM orders WHERE amount BETWEEN 1 AND 2 ORDER BY amount DESC",
    "SELECT id FROM orders ORDER BY amount LIMIT 10 OFFSET 5",
    "SELECT id FROM orders WHERE customer_id IN (SELECT id FROM customers)",
    "SELECT id FROM orders WHERE amount IS NOT NULL",
    # aggregation
    "SELECT COUNT(*) FROM orders",
    "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id",
    "SELECT customer_id, AVG(amount) FROM orders GROUP BY customer_id HAVING AVG(amount) > 10",
    "SELECT MIN(amount), MAX(amount) FROM orders",
    "SELECT COUNT(DISTINCT customer_id) FROM orders",
    # joins
    "SELECT c.name, o.amount FROM orders o JOIN customers c ON c.id = o.customer_id",
    "SELECT c.name FROM customers c LEFT JOIN orders o ON o.customer_id = c.id",
    (
        "SELECT c.region, SUM(o.amount) FROM orders o "
        "JOIN customers c ON c.id = o.customer_id GROUP BY c.region"
    ),
    # CTEs
    "WITH t AS (SELECT id, amount FROM orders) SELECT * FROM t",
    (
        "WITH per_customer AS ("
        "  SELECT customer_id, SUM(amount) AS total FROM orders GROUP BY customer_id"
        ") SELECT c.name, p.total FROM per_customer p "
        "JOIN customers c ON c.id = p.customer_id"
    ),
    # derived tables
    "SELECT x.total FROM (SELECT SUM(amount) AS total FROM orders) x",
    # set operations
    "SELECT id FROM orders UNION SELECT id FROM customers",
    "SELECT id FROM orders UNION ALL SELECT id FROM customers",
    # window functions
    (
        "SELECT id, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY amount) "
        "FROM orders"
    ),
    "SELECT id, LAG(amount) OVER (ORDER BY id) FROM orders",
    # allow-listed scalar functions
    "SELECT UPPER(name) FROM customers",
    "SELECT COALESCE(amount, 0) FROM orders",
    "SELECT ROUND(amount, 2) FROM orders",
    "SELECT CAST(amount AS INT) FROM orders",
    # a partially readable table, staying inside the grant
    "SELECT id, name FROM employees",
    "SELECT COUNT(*) FROM employees",
    # a star over a fully granted table
    "SELECT * FROM customers",
    # explicit schema qualification of a granted table
    "SELECT id FROM public.orders",
    # case and whitespace the model may emit
    "select ID from ORDERS",
    "SELECT\n  id,\n  amount\nFROM orders\n",
    "SELECT id FROM orders;",
    # recursive CTEs
    (
        "WITH RECURSIVE nums AS ("
        "  SELECT 1 AS n UNION ALL SELECT n + 1 FROM nums WHERE n < 5"
        ") SELECT n FROM nums"
    ),
    # grouping extensions
    "SELECT id, amount FROM orders GROUP BY GROUPING SETS ((id), (amount), ())",
    "SELECT customer_id, SUM(amount) FROM orders GROUP BY ROLLUP (customer_id)",
    "SELECT customer_id, SUM(amount) FROM orders GROUP BY CUBE (customer_id)",
    "SELECT customer_id, SUM(amount) FROM orders GROUP BY 1",
    # DISTINCT ON and FILTER
    (
        "SELECT DISTINCT ON (customer_id) customer_id, amount FROM orders "
        "ORDER BY customer_id, amount DESC"
    ),
    "SELECT SUM(amount) FILTER (WHERE amount > 100) FROM orders",
    # LATERAL and correlated subqueries
    (
        "SELECT o.id FROM orders o LEFT JOIN LATERAL ("
        "  SELECT amount FROM orders o2 "
        "  WHERE o2.customer_id = o.customer_id LIMIT 1"
        ") x ON true"
    ),
    (
        "SELECT c.name FROM customers c "
        "WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id)"
    ),
    # self-join
    "SELECT a.id FROM customers a JOIN customers b ON a.region = b.region AND a.id <> b.id",
    # qualified star over a fully-granted table
    "SELECT c.* FROM customers c",
    # CASE WHEN
    "SELECT id, CASE WHEN amount > 100 THEN 'big' ELSE 'small' END FROM orders",
    # set operations beyond UNION
    "SELECT id FROM orders INTERSECT SELECT id FROM customers",
    "SELECT id FROM orders EXCEPT SELECT id FROM customers",
]


@pytest.mark.parametrize("sql", ACCEPTED)
def test_legitimate_queries_compile(sql, compiler, policy):
    result = compiler.compile(sql, policy=policy)
    assert result.ok, (sql, [v.to_dict() for v in result.violations])


@pytest.mark.parametrize("sql", ACCEPTED)
def test_accepted_output_is_valid_sql(sql, compiler, policy):
    # The regenerated string is what actually reaches the database, so it has
    # to parse -- a validator that emits broken SQL has only moved the failure.
    result = compiler.compile(sql, policy=policy)
    assert sqlglot.parse_one(result.sql, dialect="postgres") is not None


@pytest.mark.parametrize("sql", ACCEPTED)
def test_accepted_output_is_stable_when_recompiled(sql, compiler, policy):
    # Feeding the output back in must be a fixed point; if it is not, the
    # compiler is rewriting semantics rather than just qualifying names.
    once = compiler.compile(sql, policy=policy).sql
    twice = compiler.compile(once, policy=policy)
    assert twice.ok, (once, twice.violations)
    assert twice.sql == once


@pytest.mark.parametrize("sql", ACCEPTED)
def test_accepted_queries_report_what_they_read(sql, compiler, policy):
    # Every accepted query must leave an audit trail; an empty one would mean
    # authorization had nothing to check.
    result = compiler.compile(sql, policy=policy)
    for qualified in result.tables:
        assert qualified in {"public.orders", "public.customers", "public.employees"}


def test_pretty_output_is_still_valid_and_accepted(catalog, policy):
    pretty = SqlCompiler(catalog=catalog, pretty=True)
    result = pretty.compile(
        "SELECT c.name, o.amount FROM orders o JOIN customers c ON c.id = o.customer_id",
        policy=policy,
    )
    assert result.ok
    assert "\n" in result.sql
    assert pretty.compile(result.sql, policy=policy).ok


def test_a_query_reading_no_table_is_accepted(compiler, policy):
    # Nothing is read, so there is nothing to deny.
    assert compiler.compile("SELECT 1", policy=policy).ok
