from __future__ import annotations

import hashlib
from dataclasses import dataclass

from codetrust.diff_parser import parse_unified_diff
from codetrust.github import load_repository_context
from codetrust.llm import infer_repository_scope
from codetrust.models import ScopeComparison


@dataclass(frozen=True)
class RepositoryIntent:
    content: str
    source: dict[str, str]
    questions: tuple[str, ...] = ()
    comparison: ScopeComparison | None = None


def resolve_repository_intent(
    repo: str,
    revision: str,
    diff: str,
    change_claim: str,
    *,
    offline: bool,
) -> RepositoryIntent:
    """Infer scope and PR distance from exact base-repository evidence."""
    claim_sha256 = hashlib.sha256(change_claim.encode()).hexdigest()
    changed_paths = tuple(file.path for file in parse_unified_diff(diff))
    context = load_repository_context(repo, revision, changed_paths)
    inference = infer_repository_scope(context, change_claim, diff, offline=offline)
    comparison = ScopeComparison(
        repository_purpose=(
            inference.repository_purpose or "Repository purpose could not be established."
        ),
        change_summary=inference.change_summary or "PR change could not be summarized reliably.",
        relationship=inference.relationship,
        distance=inference.distance,
        differences=inference.differences,
        evidence_paths=inference.evidence_paths,
        rationale=inference.rationale,
    )
    common_source = {
        "repository_context_sha256": context.sha256,
        "repository_documents_read": str(len(context.documents)),
        "repository_source_files_read": str(len(context.source_files)),
        "repository_history_entries_read": str(len(context.history)),
        "repository_tree_truncated": str(context.tree_truncated).lower(),
        "pr_content_role": "untrusted-change-claim",
        "pr_content_sha256": claim_sha256,
        "scope_confidence": inference.confidence,
        "scope_evidence_paths": ", ".join(inference.evidence_paths),
        "scope_model": inference.model or "disabled",
        "scope_model_attempts": str(inference.attempts),
        "scope_model_duration_ms": str(inference.duration_ms),
    }
    if inference.status == "sufficient":
        return RepositoryIntent(
            content=inference.intent,
            source={
                **common_source,
                "intent_source": "repository-inference",
                "intent_trust": "inferred",
                "scope_inference_rationale": inference.rationale,
            },
            comparison=comparison,
        )

    return RepositoryIntent(
        content=inference.intent,
        source={
            **common_source,
            "intent_source": "insufficient-repository-evidence",
            "intent_trust": "insufficient",
            "scope_inference_rationale": inference.rationale,
        },
        questions=(
            "Which additional base-repository evidence would resolve this scope comparison?",
        ),
        comparison=comparison,
    )
