"""The schema a subject is allowed to know about.

Guarding only the compiler's *output* means the prompt still contains tables
and columns the subject cannot read.  That is a metadata leak in its own right
-- schema names are often sensitive -- and it actively hurts accuracy, because
the model keeps generating queries that must then be rejected.

Filtering the schema *before* generation fixes both at once: fewer rejections
and less exposure.  Use :func:`render_schema_prompt` where the retrieval layer
currently drops raw DDL into the prompt.
"""

from __future__ import annotations

from typing import Dict, List

from .catalog import Catalog
from .policy import Policy


def visible_schema(catalog: Catalog, policy: Policy) -> Dict[str, Dict[str, str]]:
    """The subset of ``catalog`` that ``policy`` permits.

    Keyed by qualified table name.  Tables with no readable columns are
    omitted entirely rather than shown empty, since an empty table entry still
    discloses that the table exists.
    """
    visible: Dict[str, Dict[str, str]] = {}

    for ref in catalog.tables:
        table_policy = policy.table_policy(ref)
        if table_policy is None:
            continue

        columns = catalog.columns(ref)
        readable = table_policy.readable_columns(columns)
        if not readable:
            continue

        types = catalog.to_mapping_schema().get(ref.schema, {}).get(ref.name, {})
        visible[ref.qualified] = {name: types.get(name, "") for name in readable}

    return visible


def render_schema_prompt(catalog: Catalog, policy: Policy) -> str:
    """Render the permitted schema as CREATE TABLE text for a prompt.

    DDL is used rather than prose because models follow it more reliably, and
    because it is the same shape the host was already feeding them.
    """
    blocks: List[str] = []

    for qualified, columns in visible_schema(catalog, policy).items():
        lines = [f"CREATE TABLE {qualified} ("]
        rendered = [
            f"  {name} {type_}".rstrip() for name, type_ in columns.items()
        ]
        lines.append(",\n".join(rendered))
        lines.append(");")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
