from __future__ import annotations

import re
from dataclasses import dataclass

from codetrust.models import (
    AlignmentStatus,
    ChangedFile,
    Finding,
    IntentSnapshot,
    InterpretationClaim,
    ScopeAlignment,
    Severity,
)

SECTION_NAMES = {
    "goal": "outcome",
    "outcome": "outcome",
    "business outcome": "outcome",
    "in scope": "in_scope",
    "scope": "in_scope",
    "out of scope": "out_of_scope",
    "non goals": "out_of_scope",
    "acceptance criteria": "acceptance_criteria",
    "requirements": "acceptance_criteria",
}
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "must",
    "no",
    "not",
    "of",
    "on",
    "only",
    "or",
    "should",
    "the",
    "this",
    "to",
    "up",
    "without",
}


@dataclass(frozen=True)
class ScopeResult:
    snapshot: IntentSnapshot
    findings: list[Finding]
    alignments: list[ScopeAlignment]
    questions: list[str]
    coverage: int | None
    drift: int


def analyze_scope(
    ticket: str,
    files: list[ChangedFile],
    interpretations: list[InterpretationClaim] | None = None,
) -> ScopeResult:
    snapshot = parse_intent_snapshot(ticket)
    claims = interpretations or []
    findings: list[Finding] = []
    alignments: list[ScopeAlignment] = []
    questions: list[str] = []
    changed_files = [file for file in files if file.added or file.removed]
    contradicted_paths: set[str] = set()

    for clause in snapshot.out_of_scope:
        for file in changed_files:
            if not _related(clause, _file_text(file)):
                continue
            anchor = _anchor(file, clause)
            contradicted_paths.add(file.path)
            alignments.append(
                ScopeAlignment(
                    status=AlignmentStatus.CONTRADICTED,
                    clause=clause,
                    path=file.path,
                    line=anchor.line,
                    change_evidence=anchor.text.strip(),
                    rationale="Changed surface overlaps an explicit out-of-scope product clause.",
                )
            )
            question = f"Did product owner approve expanding scope beyond: {clause}?"
            questions.append(question)
            findings.append(
                Finding(
                    rule_id="CT-SCOPE-001",
                    title="Change crosses explicit product boundary",
                    severity=Severity.HIGH,
                    confidence=0.9,
                    path=file.path,
                    line=anchor.line,
                    evidence=anchor.text.strip(),
                    impact="Technically valid code can implement behavior product did not approve.",
                    challenge="Where is product-owner approval for this scope expansion?",
                    suggested_test="Update approved intent or split unrelated behavior into a new task.",
                    human_question=question,
                    ticket_evidence=clause,
                )
            )

    for claim in claims:
        for clause in snapshot.out_of_scope:
            if not _related(clause, claim.text):
                continue
            matching_file = next(
                (file for file in changed_files if _related(clause, _file_text(file))),
                None,
            )
            if matching_file is None:
                continue
            anchor = _anchor(matching_file, clause)
            alignments.append(
                ScopeAlignment(
                    status=AlignmentStatus.CONTRADICTED,
                    clause=clause,
                    path=matching_file.path,
                    line=anchor.line,
                    change_evidence=claim.text,
                    rationale=f"{claim.role.title()} interpretation overlaps forbidden scope.",
                    actor=claim.role,
                )
            )
            question = (
                f"Should product owner accept {claim.role} interpretation, or restore original scope?"
            )
            questions.append(question)
            findings.append(
                Finding(
                    rule_id="CT-INTERP-001",
                    title=f"{claim.role.title()} interpretation conflicts with product intent",
                    severity=Severity.HIGH,
                    confidence=0.86,
                    path=matching_file.path,
                    line=anchor.line,
                    evidence=claim.text,
                    impact="Review agreement can still authorize wrong business behavior.",
                    challenge="Which approved product decision changed this boundary?",
                    suggested_test="Record product-owner decision, revise acceptance criteria, then rerun.",
                    human_question=question,
                    ticket_evidence=clause,
                )
            )

    positive_clauses = [*snapshot.in_scope, *snapshot.acceptance_criteria]
    matched = 0
    for clause in positive_clauses:
        file = next((item for item in changed_files if _related(clause, _file_text(item))), None)
        if file:
            matched += 1
            anchor = _anchor(file, clause)
            alignments.append(
                ScopeAlignment(
                    status=AlignmentStatus.SUPPORTED,
                    clause=clause,
                    path=file.path,
                    line=anchor.line,
                    change_evidence=anchor.text.strip(),
                    rationale="Changed surface supplies lexical evidence for approved scope.",
                )
            )
        else:
            alignments.append(
                ScopeAlignment(
                    status=AlignmentStatus.AMBIGUOUS,
                    clause=clause,
                    path="",
                    line=0,
                    change_evidence="No matching changed surface found.",
                    rationale="Coverage signal cannot prove this clause was implemented.",
                )
            )

    coverage = round(matched / len(positive_clauses) * 100) if positive_clauses else None
    drift = round(len(contradicted_paths) / len(changed_files) * 100) if changed_files else 0
    return ScopeResult(
        snapshot=snapshot,
        findings=findings,
        alignments=alignments,
        questions=list(dict.fromkeys(questions)),
        coverage=coverage,
        drift=drift,
    )


def parse_intent_snapshot(ticket: str) -> IntentSnapshot:
    sections: dict[str, list[str]] = {
        "outcome": [],
        "in_scope": [],
        "out_of_scope": [],
        "acceptance_criteria": [],
    }
    current: str | None = None
    inline = re.compile(
        r"^(goal|outcome|business outcome|in scope|scope|out of scope|non-?goals|acceptance criteria|requirements)\s*:\s*(.*)$",
        re.I,
    )
    for raw_line in ticket.splitlines():
        value = raw_line.strip()
        if not value:
            continue
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", value)
        if heading:
            current = SECTION_NAMES.get(_normalize_heading(heading.group(1)))
            continue
        labeled = inline.match(value)
        if labeled:
            current = SECTION_NAMES.get(_normalize_heading(labeled.group(1)))
            content = _clean_clause(labeled.group(2))
            if current and content:
                sections[current].append(content)
            continue
        if current:
            content = _clean_clause(value)
            if content:
                sections[current].append(content)
    return IntentSnapshot(**{key: tuple(values) for key, values in sections.items()})


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z ]", "", value.lower().replace("-", " ")).strip()


def _clean_clause(value: str) -> str:
    return re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", value).strip()


def _terms(value: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9]*", value.lower().replace("_", " ").replace("-", " "))
    return {_stem(word) for word in words if word not in STOP_WORDS and len(word) > 2}


def _stem(word: str) -> str:
    if word.endswith("ies") and len(word) > 5:
        return f"{word[:-3]}y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 4:
        return word[:-1]
    return word


def _related(clause: str, evidence: str) -> bool:
    expected = _terms(clause)
    actual = _terms(evidence)
    if not expected:
        return False
    overlap = expected & actual
    required = 1 if len(expected) <= 2 else 2
    return len(overlap) >= required and len(overlap) / len(expected) >= 0.35


def _file_text(file: ChangedFile) -> str:
    return f"{file.path}\n{file.added_text}\n{file.removed_text}"


def _anchor(file: ChangedFile, clause: str):
    expected = _terms(clause)
    lines = [*file.added, *file.removed]
    return max(lines, key=lambda item: len(expected & _terms(f"{file.path} {item.text}")))
