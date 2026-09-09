"""The compiler: run the passes in order and regenerate safe SQL.

Each pass has one responsibility, and the order is not negotiable -- read-only
enforcement precedes resolution because there is no point resolving names in a
``DROP``, and resolution precedes authorization because authorizing an
unresolved tree authorizes the wrong names.

The hard rule this module exists to enforce:

    Execute only the SQL regenerated from the validated tree, never the
    string the model produced.

Validating one string and executing another is how a validator ends up
enforcing nothing, so :attr:`CompileResult.sql` is always rendered from the
qualified AST and is ``None`` whenever the query was rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .catalog import Catalog
from .errors import (
    CompilationRejected,
    ConfigurationError,
    RepairAction,
    Violation,
    ViolationCode,
)
from .names import TableRef
from .passes.authorize import authorize
from .passes.parse import parse_single_statement
from .passes.readonly import check_read_only
from .passes.resolve import resolve
from .passes.rowsec import apply_row_filters
from .policy import Policy, PolicyProvider


@dataclass
class CompileResult:
    """The outcome of compiling one query.

    ``ok`` and ``sql`` move together: a rejected query never carries SQL, so a
    caller cannot execute a result it forgot to check.
    """

    ok: bool
    sql: Optional[str] = None
    violations: List[Violation] = field(default_factory=list)
    #: Base tables the query reads, for audit logging.
    tables: List[str] = field(default_factory=list)
    #: ``table.column`` pairs the query reads, for audit logging.
    columns: List[str] = field(default_factory=list)
    subject: Optional[str] = None

    def __bool__(self) -> bool:
        return self.ok

    def raise_for_violations(self) -> "CompileResult":
        """Raise :class:`CompilationRejected` unless the query was accepted."""
        if not self.ok:
            raise CompilationRejected(self.violations)
        return self

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": self.ok,
            "violations": [v.to_dict() for v in self.violations],
        }
        if self.sql is not None:
            payload["sql"] = self.sql
        if self.tables:
            payload["tables"] = self.tables
        if self.columns:
            payload["columns"] = self.columns
        if self.subject is not None:
            payload["subject"] = self.subject
        return payload

    def repair_prompt(self) -> str:
        """A compact, structured description of what to fix.

        Intended for a bounded LLM repair loop. It names codes and the objects
        the model already referenced -- never the tables or columns it is not
        allowed to know about.
        """
        if self.ok:
            return ""
        lines = ["The generated SQL was rejected. Fix these problems and try again:"]
        for violation in self.violations:
            target = violation.column or violation.table or violation.function or ""
            suffix = f" ({target})" if target else ""
            lines.append(f"- {violation.code.value}{suffix}: {violation.message}")
        return "\n".join(lines)


class SqlCompiler:
    """Compiles untrusted SQL against a catalog and a policy.

    Typical use::

        compiler = SqlCompiler(catalog=catalog, policy_provider=provider)
        result = compiler.compile(llm_sql, subject=current_user_id)
        if result.ok:
            run(result.sql)      # never run the model's original string

    The instance holds no per-request state, so one compiler can be shared
    across requests.
    """

    def __init__(
        self,
        catalog: Optional[Catalog] = None,
        policy_provider: Optional[PolicyProvider] = None,
        pretty: bool = False,
    ) -> None:
        self.catalog = catalog
        self.policy_provider = policy_provider
        self.pretty = pretty

    def compile(
        self,
        sql: str,
        policy: Optional[Policy] = None,
        subject: Any = None,
        catalog: Optional[Catalog] = None,
    ) -> CompileResult:
        """Compile ``sql``, returning a result rather than raising.

        Supply either ``policy`` directly or ``subject`` plus a
        ``policy_provider``.  A :class:`ConfigurationError` here means the host
        wired something wrong; it is deliberately not turned into a violation,
        because reporting a misconfiguration as "access denied" hides bugs.
        """
        active_catalog = catalog or self.catalog
        if active_catalog is None:
            raise ConfigurationError(
                "no catalog supplied; pass one to SqlCompiler() or to compile()"
            )

        active_policy = self._resolve_policy(policy, subject)
        subject_label = active_policy.subject if active_policy.subject is not None else (
            str(subject) if subject is not None else None
        )

        def rejected(
            violations: List[Violation],
            tables: Optional[List[str]] = None,
            columns: Optional[List[str]] = None,
        ) -> CompileResult:
            return CompileResult(
                ok=False,
                violations=violations,
                subject=subject_label,
                tables=tables or [],
                columns=columns or [],
            )

        # Pass 1: exactly one parseable statement. Anything the pass did not
        # anticipate (e.g. sqlglot's recursion limit on pathological input)
        # must fail closed rather than crash the host -- see
        # _internal_error_violation.
        ok, outcome = self._run_pass(lambda: parse_single_statement(sql, active_catalog.dialect))
        if not ok:
            return rejected([outcome])
        statement, violations = outcome
        if violations or statement is None:
            return rejected(violations)

        # Pass 2: prove it is a pure read before doing any further work.
        ok, outcome = self._run_pass(lambda: check_read_only(statement))
        if not ok:
            return rejected([outcome])
        violations = outcome
        if violations:
            return rejected(violations)

        # Pass 3: resolve every name against the catalog. Anything the pass
        # did not anticipate must fail closed rather than reach the caller as
        # a raw exception -- see _internal_error_violation.
        ok, outcome = self._run_pass(lambda: resolve(statement, active_catalog))
        if not ok:
            return rejected([outcome])
        resolved, violations = outcome
        if violations or resolved is None:
            return rejected(violations)

        tables = sorted(ref.qualified for ref in resolved.base_tables)
        columns = sorted(
            {f"{ref.table.qualified}.{ref.column}" for ref in resolved.column_refs}
        )

        # Pass 4: authorize, collecting every violation for the repair loop.
        ok, outcome = self._run_pass(lambda: authorize(resolved, active_policy))
        if not ok:
            # Audit still wants to know what was attempted.
            return rejected([outcome], tables=tables, columns=columns)
        violations = outcome
        if violations:
            # Audit still wants to know what was attempted.
            return rejected(violations, tables=tables, columns=columns)

        # Pass 5: apply any row-level filters recorded on the policy. Runs
        # only after authorization succeeds, on the tree that will actually
        # be rendered -- see passes/rowsec.py for why appending a WHERE
        # clause to the outer statement instead would fail open.
        ok, outcome = self._run_pass(
            lambda: apply_row_filters(resolved, active_policy, active_catalog)
        )
        if not ok:
            # Audit still wants to know what was attempted.
            return rejected([outcome], tables=tables, columns=columns)

        # Pass 6: regenerate. This, and only this, is what may be executed.
        try:
            safe_sql = resolved.expression.sql(
                dialect=active_catalog.dialect, pretty=self.pretty
            )
        except Exception as exc:
            return rejected(
                [
                    Violation(
                        code=ViolationCode.GENERATION_FAILED,
                        message="The validated query could not be regenerated.",
                        action=RepairAction.NOT_REPAIRABLE,
                        details={"error_type": type(exc).__name__},
                    )
                ]
            )

        return CompileResult(
            ok=True,
            sql=safe_sql,
            violations=[],
            tables=tables,
            columns=columns,
            subject=subject_label,
        )

    def compile_or_raise(
        self,
        sql: str,
        policy: Optional[Policy] = None,
        subject: Any = None,
        catalog: Optional[Catalog] = None,
    ) -> str:
        """Compile and return safe SQL, or raise :class:`CompilationRejected`."""
        result = self.compile(
            sql, policy=policy, subject=subject, catalog=catalog
        ).raise_for_violations()
        assert result.sql is not None  # guaranteed by ok=True
        return result.sql

    @staticmethod
    def _run_pass(fn):
        """Run one compiler pass, fail-closed.

        Returns ``(True, fn()'s result)`` on success or ``(False,
        internal-error violation)`` if ``fn`` raised something unanticipated.
        ``ConfigurationError`` is not caught: it means the host wired
        something wrong, and reporting that as "access denied" would hide
        the bug (see the ``compile`` docstring), so it propagates instead.
        """
        try:
            return True, fn()
        except ConfigurationError:
            raise
        except Exception as exc:
            return False, _internal_error_violation(exc)

    def _resolve_policy(self, policy: Optional[Policy], subject: Any) -> Policy:
        if policy is not None:
            return policy
        if self.policy_provider is None:
            raise ConfigurationError(
                "no policy supplied; pass policy= or configure a policy_provider"
            )
        if subject is None:
            raise ConfigurationError(
                "a subject is required when resolving policy via a policy_provider"
            )
        resolved = self.policy_provider.resolve(subject)
        if not isinstance(resolved, Policy):
            raise ConfigurationError(
                f"policy provider returned {type(resolved).__name__}, expected Policy"
            )
        return resolved


def _internal_error_violation(exc: Exception) -> Violation:
    """A fail-closed violation for a bug the compiler did not anticipate.

    Only the exception's class name is kept. Its message is never included:
    a resolver or authorizer bug can embed a fragment of the offending SQL in
    its message (as a malformed FROM-clause expression once did), and
    surfacing that would turn an internal bug into a disclosure channel.
    """
    return Violation(
        code=ViolationCode.INTERNAL_ERROR,
        message="The query could not be validated due to an internal error.",
        action=RepairAction.NOT_REPAIRABLE,
        details={"error_type": type(exc).__name__},
    )


def compile_sql(
    sql: str,
    catalog: Catalog,
    policy: Policy,
    pretty: bool = False,
) -> CompileResult:
    """One-shot convenience wrapper around :class:`SqlCompiler`."""
    return SqlCompiler(catalog=catalog, pretty=pretty).compile(sql, policy=policy)
