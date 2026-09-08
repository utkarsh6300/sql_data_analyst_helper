"""Policy model: grants, denies, serialization, providers."""

from __future__ import annotations

import pickle

import pytest

from sql_compiler import (
    ALL_COLUMNS,
    DEFAULT_ALLOWED_FUNCTIONS,
    ConfigurationError,
    Policy,
    PolicyProvider,
    StaticPolicyProvider,
    TablePolicy,
    TableRef,
)

pytestmark = pytest.mark.unit


ORDERS = TableRef("public", "orders")


# -- column grants -----------------------------------------------------------


def test_explicit_column_list_grants_only_those():
    policy = TablePolicy(table=ORDERS, allowed_columns=frozenset({"id", "amount"}))
    assert policy.permits_column("id")
    assert not policy.permits_column("tenant_id")


def test_all_columns_grants_everything():
    policy = TablePolicy(table=ORDERS, allowed_columns=ALL_COLUMNS)
    assert policy.permits_column("anything_at_all")


def test_all_columns_is_the_default_grant():
    assert TablePolicy(table=ORDERS).allowed_columns is ALL_COLUMNS


def test_deny_beats_all_columns():
    policy = TablePolicy(
        table=ORDERS, allowed_columns=ALL_COLUMNS, denied_columns=frozenset({"ssn"})
    )
    assert policy.permits_column("id")
    assert not policy.permits_column("ssn")


def test_deny_beats_an_explicit_grant():
    # A deny that could be overridden by a broad grant is not a deny.
    policy = TablePolicy(
        table=ORDERS,
        allowed_columns=frozenset({"id", "ssn"}),
        denied_columns=frozenset({"ssn"}),
    )
    assert not policy.permits_column("ssn")


def test_readable_columns_resolves_all_against_the_catalog():
    policy = TablePolicy(
        table=ORDERS, allowed_columns=ALL_COLUMNS, denied_columns=frozenset({"ssn"})
    )
    assert policy.readable_columns(["id", "ssn", "amount"]) == ["id", "amount"]


def test_readable_columns_keeps_catalog_order():
    # Prompt rendering reads this, so a stable order keeps prompts stable.
    policy = TablePolicy(table=ORDERS, allowed_columns=frozenset({"a", "b", "c"}))
    assert policy.readable_columns(["c", "a", "b"]) == ["c", "a", "b"]


def test_readable_columns_ignores_columns_not_in_the_catalog():
    # A grant for a dropped column must not conjure it back into a prompt.
    policy = TablePolicy(table=ORDERS, allowed_columns=frozenset({"id", "removed"}))
    assert policy.readable_columns(["id"]) == ["id"]


# -- the ALL_COLUMNS sentinel ------------------------------------------------


def test_all_columns_is_a_singleton():
    # `allowed_columns is ALL_COLUMNS` is the actual check in permits_column,
    # so a second instance would silently stop granting anything.
    assert type(ALL_COLUMNS)() is ALL_COLUMNS


def test_all_columns_survives_pickling():
    # Hosts cache policies; a round trip that produced a copy would break the
    # identity check above.
    assert pickle.loads(pickle.dumps(ALL_COLUMNS)) is ALL_COLUMNS


def test_all_columns_reprs_readably():
    assert repr(ALL_COLUMNS) == "ALL_COLUMNS"


# -- table grants ------------------------------------------------------------


def test_unlisted_table_is_denied():
    policy = Policy(tables={ORDERS: TablePolicy(table=ORDERS)})
    assert policy.permits_table(ORDERS)
    assert not policy.permits_table(TableRef("public", "payroll"))


def test_table_policy_is_none_for_an_unlisted_table():
    assert Policy().table_policy(ORDERS) is None


def test_a_policy_with_no_tables_denies_everything():
    # There is deliberately no wildcard that grants unlisted tables.
    assert not Policy().permits_table(ORDERS)


def test_same_column_name_in_two_tables_is_two_permissions():
    # The flaw plan.txt section 11 calls out: a flat column allow-list cannot
    # distinguish transactions.amount from payroll.amount.
    transactions = TableRef("public", "transactions")
    payroll = TableRef("public", "payroll")
    policy = Policy.from_dict(
        {"tables": {"transactions": ["id", "amount"], "payroll": ["id"]}}
    )
    assert policy.table_policy(transactions).permits_column("amount")
    assert not policy.table_policy(payroll).permits_column("amount")


def test_grant_in_one_schema_does_not_reach_another():
    policy = Policy.from_dict({"tables": {"public.orders": ["id"]}})
    assert policy.permits_table(ORDERS)
    assert not policy.permits_table(TableRef("secret", "orders"))


# -- from_dict ---------------------------------------------------------------


def test_from_dict_shorthand_column_list():
    policy = Policy.from_dict({"tables": {"public.orders": ["id", "amount"]}})
    assert policy.table_policy(ORDERS).allowed_columns == frozenset({"id", "amount"})


def test_from_dict_full_form_with_denies_and_row_filter():
    policy = Policy.from_dict(
        {
            "subject": "user-123",
            "tables": {
                "public.orders": {
                    "columns": "*",
                    "denied_columns": ["ssn"],
                    "row_filter": "tenant_id = 7",
                }
            },
        }
    )
    table_policy = policy.table_policy(ORDERS)
    assert table_policy.allowed_columns is ALL_COLUMNS
    assert table_policy.denied_columns == frozenset({"ssn"})
    assert table_policy.row_filter == "tenant_id = 7"
    assert policy.subject == "user-123"


def test_from_dict_omitting_columns_grants_all_of_them():
    policy = Policy.from_dict({"tables": {"public.orders": {"denied_columns": ["ssn"]}}})
    assert policy.table_policy(ORDERS).allowed_columns is ALL_COLUMNS


def test_bare_star_string_as_a_whole_table_grant_means_all_columns():
    # {"table": "*"} is a shorthand distinct from {"table": {"columns": "*"}}
    # -- both must resolve to ALL_COLUMNS; only a bare string that is *not*
    # "*" (see test_bare_string_column_grant_is_rejected) is rejected.
    policy = Policy.from_dict({"tables": {"public.orders": "*"}})
    table_policy = policy.table_policy(TableRef("public", "orders"))
    assert table_policy.allowed_columns is ALL_COLUMNS


def test_from_dict_normalizes_identifier_case():
    policy = Policy.from_dict({"tables": {"PUBLIC.Orders": ["ID"]}})
    assert policy.permits_table(ORDERS)
    assert policy.table_policy(ORDERS).permits_column("id")


def test_from_dict_normalizes_denied_column_case():
    # A deny written in the wrong case would silently stop denying.
    policy = Policy.from_dict(
        {"tables": {"orders": {"columns": "*", "denied_columns": ["SSN"]}}}
    )
    assert not policy.table_policy(ORDERS).permits_column("ssn")


def test_from_dict_applies_the_default_schema():
    policy = Policy.from_dict({"tables": {"orders": ["id"]}}, default_schema="analytics")
    assert policy.permits_table(TableRef("analytics", "orders"))
    assert not policy.permits_table(ORDERS)


def test_empty_policy_denies_everything():
    policy = Policy.from_dict({})
    assert not policy.permits_table(ORDERS)


def test_empty_column_list_is_a_configuration_error():
    # Silently meaning "no columns" would look like a working grant.
    with pytest.raises(ConfigurationError, match="lists no columns"):
        Policy.from_dict({"tables": {"orders": []}})


def test_bare_string_column_grant_is_rejected():
    # "id,amount" would otherwise be read as a set of characters.
    with pytest.raises(ConfigurationError, match="must be a list"):
        Policy.from_dict({"tables": {"orders": "id,amount"}})


def test_non_mapping_tables_block_is_rejected():
    with pytest.raises(ConfigurationError, match="'tables' must be a mapping"):
        Policy.from_dict({"tables": ["orders"]})


def test_grant_of_an_unsupported_type_is_rejected():
    with pytest.raises(ConfigurationError, match="must be a mapping or a column list"):
        Policy.from_dict({"tables": {"orders": 7}})


def test_roundtrip_through_dict():
    spec = {
        "subject": "user-1",
        "tables": {"public.orders": {"columns": ["amount", "id"]}},
    }
    policy = Policy.from_dict(spec)
    restored = Policy.from_dict(policy.to_dict())
    assert restored.tables == policy.tables
    assert restored.subject == policy.subject


def test_roundtrip_does_not_widen_an_explicit_grant():
    # If to_dict wrote a key from_dict does not read, an explicit column list
    # would come back as ALL_COLUMNS -- a silent privilege escalation.
    policy = Policy.from_dict({"tables": {"orders": ["id"]}})
    restored = Policy.from_dict(policy.to_dict())
    assert restored.table_policy(ORDERS).allowed_columns == frozenset({"id"})


def test_roundtrip_preserves_denies_and_row_filter():
    policy = Policy.from_dict(
        {
            "tables": {
                "orders": {
                    "columns": "*",
                    "denied_columns": ["ssn"],
                    "row_filter": "tenant_id = 7",
                }
            }
        }
    )
    restored = Policy.from_dict(policy.to_dict())
    assert restored.table_policy(ORDERS).denied_columns == frozenset({"ssn"})
    assert restored.table_policy(ORDERS).row_filter == "tenant_id = 7"


def test_to_dict_omits_the_default_function_list():
    # Serializing the whole default list would freeze it into every stored
    # policy, so a later addition would not reach existing subjects.
    assert "allowed_functions" not in Policy.from_dict({}).to_dict()


def test_to_dict_includes_a_customized_function_list():
    payload = Policy.from_dict({"allowed_functions": ["count"]}).to_dict()
    assert payload["allowed_functions"] == ["COUNT"]


def test_to_dict_omits_an_absent_subject():
    assert "subject" not in Policy.from_dict({}).to_dict()


def test_to_dict_sorts_tables():
    payload = Policy.from_dict(
        {"tables": {"public.orders": ["id"], "public.customers": ["id"]}}
    ).to_dict()
    assert list(payload["tables"]) == ["public.customers", "public.orders"]


# -- subject -----------------------------------------------------------------


def test_with_subject_returns_a_new_policy():
    policy = Policy.from_dict({"tables": {"orders": ["id"]}})
    labelled = policy.with_subject("user-9")
    assert labelled.subject == "user-9"
    assert policy.subject is None
    assert labelled.tables == policy.tables


def test_subject_does_not_affect_authorization():
    # The subject is an audit label only; treating it as a credential would
    # make relabelling a policy a privilege change.
    granted = Policy.from_dict({"tables": {"orders": ["id"]}})
    assert granted.with_subject("anyone").permits_table(ORDERS)


# -- functions ---------------------------------------------------------------


def test_default_function_list_allows_aggregates_and_denies_the_rest():
    policy = Policy.from_dict({})
    assert policy.permits_function(["COUNT"])
    assert not policy.permits_function(["PG_READ_FILE"])
    assert not policy.permits_function(["VERSION"])


def test_any_matching_candidate_name_allows_the_function():
    # sqlglot canonicalizes DATE_TRUNC to TimestampTrunc, so the check must
    # accept any spelling the node could carry.
    policy = Policy.from_dict({})
    assert policy.permits_function(["TIMESTAMP_TRUNC", "DATE_TRUNC"])


def test_no_candidate_names_is_not_a_pass():
    assert not Policy.from_dict({}).permits_function([])


def test_custom_function_list_replaces_the_default():
    policy = Policy.from_dict({"tables": {}, "allowed_functions": ["count"]})
    assert policy.permits_function(["COUNT"])
    assert not policy.permits_function(["SUM"])


def test_an_empty_function_list_denies_every_function():
    # Distinct from omitting the key, which keeps the defaults.
    assert not Policy.from_dict({"allowed_functions": []}).permits_function(["COUNT"])


def test_the_default_list_excludes_system_and_filesystem_functions():
    # A query needs no table at all to leak if these are reachable.
    for dangerous in ("VERSION", "PG_READ_FILE", "PG_SLEEP", "DBLINK", "LO_IMPORT"):
        assert dangerous not in DEFAULT_ALLOWED_FUNCTIONS


# -- providers ---------------------------------------------------------------


def test_static_provider_resolves_and_reports_unknown_subjects():
    policy = Policy.from_dict({"tables": {"orders": ["id"]}})
    provider = StaticPolicyProvider({"user-1": policy})
    assert provider.resolve("user-1") is policy
    with pytest.raises(ConfigurationError, match="no policy registered"):
        provider.resolve("nobody")


def test_static_provider_copies_its_mapping():
    policies = {"user-1": Policy.from_dict({"tables": {"orders": ["id"]}})}
    provider = StaticPolicyProvider(policies)
    policies.clear()
    assert provider.resolve("user-1") is not None


def test_provider_base_class_cannot_be_used_directly():
    # Forgetting to implement resolve must fail loudly at construction rather
    # than return None at authorization time.
    with pytest.raises(TypeError):
        PolicyProvider()  # type: ignore[abstract]
