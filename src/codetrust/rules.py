from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from codetrust.models import ChangedFile, Finding, Severity

Rule = Callable[[list[ChangedFile]], list[Finding]]
Applicability = Callable[[list[ChangedFile]], bool]
SOURCE_SUFFIXES = (
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".dart",
    ".erl",
    ".ex",
    ".exs",
    ".fs",
    ".fsx",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".lua",
    ".m",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".svelte",
    ".ts",
    ".tsx",
    ".vb",
    ".vue",
)
NON_PRODUCTION_PREFIXES = ("docs/", "tests/", "test/", "demo/", "examples/", "fixtures/")


@dataclass(frozen=True)
class RuleSpec:
    name: str
    check: Rule
    applies: Applicability


def run_rules(files: list[ChangedFile]) -> tuple[list[Finding], list[str], list[str]]:
    selected = [
        RuleSpec("secret-exposure", _exposed_secret, _has_added_lines),
        RuleSpec("debug-residue", _debug_residue, _has_production_source),
        RuleSpec("change-test-coverage", _source_change_without_tests, _has_production_source),
        RuleSpec("async-safety", _blocking_io_in_async, _has_async_python_change),
        RuleSpec("payment-idempotency", _retry_without_idempotency, _has_payment_retry_change),
        RuleSpec("api-compatibility", _removed_api_contract, _has_contract_removal),
        RuleSpec("rollback-safety", _migration_without_rollback, _has_migration_change),
        RuleSpec("failure-coverage", _success_only_tests, _has_sensitive_change),
    ]
    findings: list[Finding] = []
    applicable: list[str] = []
    skipped: list[str] = []
    for rule in selected:
        if not rule.applies(files):
            skipped.append(rule.name)
            continue
        applicable.append(rule.name)
        findings.extend(rule.check(files))
    findings.sort(key=lambda item: (-_weight(item.severity), item.path, item.line))
    return findings, applicable, skipped


def _exposed_secret(files: list[ChangedFile]) -> list[Finding]:
    assignment = re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|client[_-]?secret|password|private[_-]?key)\b"
        r"\s*[:=]\s*[\"']([^\"']{8,})[\"']"
    )
    placeholders = ("example", "placeholder", "test", "your_", "your-", "<", "${")
    results: list[Finding] = []
    for file in files:
        for line in file.added:
            match = assignment.search(line.text)
            if not match or any(token in match.group(2).lower() for token in placeholders):
                continue
            results.append(
                Finding(
                    rule_id="CT-SEC-001",
                    title="Potential credential added to repository",
                    severity=Severity.CRITICAL,
                    confidence=0.96,
                    path=file.path,
                    line=line.line,
                    evidence=f"{match.group(1)}=<redacted>",
                    impact="Committed credentials can grant unintended access and persist in history.",
                    challenge="Why is this value safe to store in source control?",
                    suggested_test="Revoke the value, remove it from history, and run repository secret scanning.",
                )
            )
    return results


def _debug_residue(files: list[ChangedFile]) -> list[Finding]:
    pattern = re.compile(
        r"(?:\bbreakpoint\(\)|\bpdb\.set_trace\(\)|\bdebugger\s*;|\bTODO\s*:?\s*remove\b)",
        re.I,
    )
    results: list[Finding] = []
    for file in _production_source_files(files):
        for line in file.added:
            if not pattern.search(line.text):
                continue
            results.append(
                Finding(
                    rule_id="CT-DEBUG-001",
                    title="Debug-only behavior added to production source",
                    severity=Severity.MEDIUM,
                    confidence=0.94,
                    path=file.path,
                    line=line.line,
                    evidence=line.text.strip(),
                    impact="Debug hooks can pause, expose, or alter production execution.",
                    challenge="Should this debug behavior ship?",
                    suggested_test="Remove the hook and run the affected path in a production-like build.",
                )
            )
    return results


def _source_change_without_tests(files: list[ChangedFile]) -> list[Finding]:
    production = _production_source_files(files)
    if not production or any(_is_test_file(file.path) for file in files):
        return []
    target = production[0]
    anchor = target.added[0] if target.added else target.removed[0]
    return [
        Finding(
            rule_id="CT-TEST-002",
            title="Source change has no changed verification",
            severity=Severity.LOW,
            confidence=0.8,
            path=target.path,
            line=anchor.line,
            evidence="Production source changed without a test file in this pull request.",
            impact="Behavior may change without repeatable proof of the intended outcome.",
            challenge="What automated check proves this change works and prevents regression?",
            suggested_test="Add or update a focused test for the changed behavior.",
        )
    ]


def _blocking_io_in_async(files: list[ChangedFile]) -> list[Finding]:
    results: list[Finding] = []
    for file in _production_source_files(files):
        text = file.added_text
        if "async def " not in text:
            continue
        for line in file.added:
            if re.search(r"\b(requests\.(get|post|put|delete)|time\.sleep)\s*\(", line.text):
                results.append(
                    Finding(
                        rule_id="CT-ASYNC-001",
                        title="Blocking I/O inside async path",
                        severity=Severity.HIGH,
                        confidence=0.98,
                        path=file.path,
                        line=line.line,
                        evidence=line.text.strip(),
                        impact="Default worker or event-loop capacity can stall under load.",
                        challenge="Why is synchronous network I/O safe inside this async execution path?",
                        suggested_test="Run concurrent reconciliations with a delayed provider and assert bounded latency.",
                    )
                )
    return results


def _retry_without_idempotency(files: list[ChangedFile]) -> list[Finding]:
    results: list[Finding] = []
    payment_terms = re.compile(r"\b(charge|payment|capture|debit|reconcile)\b", re.I)
    retry_terms = re.compile(r"\b(retry|attempt|backoff|for\s+\w+\s+in\s+range)\b", re.I)
    for file in _production_source_files(files):
        text = file.added_text
        if not (payment_terms.search(text) and retry_terms.search(text)):
            continue
        if re.search(r"idempotenc|deduplic|operation[_-]?id", text, re.I):
            continue
        line = next((item for item in file.added if payment_terms.search(item.text)), file.added[0])
        results.append(
            Finding(
                rule_id="CT-PAY-001",
                title="Retried payment action lacks idempotency evidence",
                severity=Severity.CRITICAL,
                confidence=0.94,
                path=file.path,
                line=line.line,
                evidence=line.text.strip(),
                impact="Timeout-after-success can execute customer payment more than once.",
                challenge="What proves two attempts for one operation cannot produce two charges?",
                suggested_test="Simulate provider success followed by client timeout; retry with same operation ID and assert one charge.",
                human_question="Which stable business key should define payment idempotency across markets?",
            )
        )
    return results


def _removed_api_contract(files: list[ChangedFile]) -> list[Finding]:
    results: list[Finding] = []
    contract_suffixes = (".avsc", ".graphql", ".json", ".proto", ".thrift", ".yaml", ".yml")
    for file in files:
        if _is_non_production(file.path):
            continue
        if not file.path.lower().endswith(contract_suffixes):
            continue
        for line in file.removed:
            value = line.text.strip()
            if re.match(r"^[A-Za-z_][\w-]*:\s*", value) and not value.startswith(
                ("#", "description:")
            ):
                field = value.split(":", 1)[0]
                results.append(
                    Finding(
                        rule_id="CT-API-001",
                        title=f"API contract removes `{field}`",
                        severity=Severity.HIGH,
                        confidence=0.86,
                        path=file.path,
                        line=line.line,
                        evidence=value,
                        impact="Older clients or market adapters can fail after deployment.",
                        challenge="Where is compatibility proof or versioned migration for removed field?",
                        suggested_test=f"Replay previous contract fixture containing `{field}` against new implementation.",
                        human_question="Can all consuming markets upgrade before this contract change ships?",
                    )
                )
                break
    return results


def _migration_without_rollback(files: list[ChangedFile]) -> list[Finding]:
    results: list[Finding] = []
    for file in files:
        if _is_non_production(file.path):
            continue
        if not re.search(r"(migration|migrations|alembic|flyway|liquibase)", file.path, re.I):
            continue
        text = file.added_text
        if not re.search(r"\b(CREATE|ALTER|DROP|upgrade\s*\()", text, re.I):
            continue
        if re.search(r"\b(downgrade\s*\(|rollback|down\s*\()", text, re.I):
            continue
        line = next(
            (
                item
                for item in file.added
                if re.search(r"\b(CREATE|ALTER|DROP|upgrade\s*\()", item.text, re.I)
            ),
            file.added[0],
        )
        results.append(
            Finding(
                rule_id="CT-DB-001",
                title="Schema change has no rollback path",
                severity=Severity.HIGH,
                confidence=0.9,
                path=file.path,
                line=line.line,
                evidence=line.text.strip(),
                impact="Failed rollout can leave partially processed records or incompatible schema.",
                challenge="How does rollback restore schema and in-flight data safely?",
                suggested_test="Apply migration, seed in-flight records, then execute and verify rollback.",
            )
        )
    return results


def _success_only_tests(files: list[ChangedFile]) -> list[Finding]:
    test_files = [file for file in files if re.search(r"(^|/)(test_|tests?/|.*_test\.)", file.path)]
    production_files = [
        file for file in files if file not in test_files and not _is_non_production(file.path)
    ]
    if not production_files:
        return []
    test_text = "\n".join(file.added_text for file in test_files)
    sensitive = any(
        re.search(r"payment|retry|async|migration|reconcile", file.added_text, re.I)
        for file in production_files
    )
    if not sensitive or re.search(
        r"timeout|failure|duplicate|idempot|rollback|concurr", test_text, re.I
    ):
        return []
    target = test_files[0] if test_files else production_files[0]
    line = target.added[0] if target.added else production_files[0].added[0]
    return [
        Finding(
            rule_id="CT-TEST-001",
            title="Risk-sensitive change lacks failure-path coverage",
            severity=Severity.MEDIUM,
            confidence=0.82,
            path=target.path,
            line=line.line,
            evidence="No timeout, duplicate, idempotency, rollback, or concurrency assertion in changed tests.",
            impact="Happy-path suite can pass while production failure modes remain untested.",
            challenge="Which test fails before retry, timeout, or rollback behavior is corrected?",
            suggested_test="Add adversarial test matching highest-severity production risk.",
        )
    ]


def _weight(severity: Severity) -> int:
    return {
        Severity.CRITICAL: 40,
        Severity.HIGH: 25,
        Severity.MEDIUM: 12,
        Severity.LOW: 5,
    }[severity]


def _production_source_files(files: list[ChangedFile]) -> list[ChangedFile]:
    return [
        file
        for file in files
        if file.path.lower().endswith(SOURCE_SUFFIXES)
        and not _is_non_production(file.path)
        and not _is_test_file(file.path)
    ]


def _is_non_production(path: str) -> bool:
    normalized = path.lower().lstrip("./")
    return normalized.startswith(NON_PRODUCTION_PREFIXES)


def _is_test_file(path: str) -> bool:
    return bool(re.search(r"(^|/)(test_|tests?/|.*_test\.)", path, re.I))


def _has_added_lines(files: list[ChangedFile]) -> bool:
    return any(file.added for file in files)


def _has_production_source(files: list[ChangedFile]) -> bool:
    return bool(_production_source_files(files))


def _has_async_python_change(files: list[ChangedFile]) -> bool:
    return any(
        file.path.lower().endswith(".py") and "async def " in file.added_text
        for file in _production_source_files(files)
    )


def _has_payment_retry_change(files: list[ChangedFile]) -> bool:
    payment = re.compile(r"\b(charge|payment|capture|debit|reconcile)\b", re.I)
    retry = re.compile(r"\b(retry|attempt|backoff|for\s+\w+\s+in\s+range)\b", re.I)
    return any(payment.search(file.added_text) and retry.search(file.added_text) for file in _production_source_files(files))


def _has_contract_removal(files: list[ChangedFile]) -> bool:
    suffixes = (".avsc", ".graphql", ".json", ".proto", ".thrift", ".yaml", ".yml")
    return any(
        file.removed and file.path.lower().endswith(suffixes) and not _is_non_production(file.path)
        for file in files
    )


def _has_migration_change(files: list[ChangedFile]) -> bool:
    return any(
        re.search(r"(migration|migrations|alembic|flyway|liquibase)", file.path, re.I)
        and re.search(r"\b(CREATE|ALTER|DROP|upgrade\s*\()", file.added_text, re.I)
        for file in files
        if not _is_non_production(file.path)
    )


def _has_sensitive_change(files: list[ChangedFile]) -> bool:
    return any(
        re.search(r"payment|retry|async|migration|reconcile", file.added_text, re.I)
        for file in _production_source_files(files)
    )


def risk_score(findings: list[Finding]) -> int:
    confidence_weighted = sum(_weight(item.severity) * item.confidence for item in findings)
    return min(100, round(confidence_weighted))
