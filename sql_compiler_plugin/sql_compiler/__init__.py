"""A plug-and-play SQL security compiler for Text-to-SQL systems.

Parses LLM-generated SQL, resolves every name against a catalog, authorizes
tables and columns against a policy, and regenerates the SQL to execute.
"""

from __future__ import annotations

from .catalog import Catalog
from .compiler import CompileResult, SqlCompiler, compile_sql
from .errors import (
    CompilationRejected,
    ConfigurationError,
    RepairAction,
    SqlCompilerError,
    Violation,
    ViolationCode,
)
from .names import TableRef
from .policy import (
    ALL_COLUMNS,
    DEFAULT_ALLOWED_FUNCTIONS,
    Policy,
    PolicyProvider,
    StaticPolicyProvider,
    TablePolicy,
)
from .schema_view import render_schema_prompt, visible_schema

__version__ = "0.1.0"

__all__ = [
    "ALL_COLUMNS",
    "DEFAULT_ALLOWED_FUNCTIONS",
    "Catalog",
    "CompilationRejected",
    "CompileResult",
    "ConfigurationError",
    "Policy",
    "PolicyProvider",
    "RepairAction",
    "SqlCompiler",
    "SqlCompilerError",
    "StaticPolicyProvider",
    "TablePolicy",
    "TableRef",
    "Violation",
    "ViolationCode",
    "compile_sql",
    "render_schema_prompt",
    "visible_schema",
]
