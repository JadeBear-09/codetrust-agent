from __future__ import annotations

import html
import json
from pathlib import Path

from codetrust.models import VerificationReport


def write_reports(report: VerificationReport, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = "latest"
    paths = {
        "json": output_dir / f"{stem}.json",
        "markdown": output_dir / f"{stem}.md",
        "html": output_dir / f"{stem}.html",
        "tests": output_dir / "adversarial-tests.md",
    }
    paths["json"].write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    paths["markdown"].write_text(render_markdown(report))
    paths["html"].write_text(render_html(report))
    paths["tests"].write_text(render_adversarial_tests(report))
    return paths


def render_markdown(report: VerificationReport) -> str:
    lines = [
        "# CodeTrust evidence report",
        "",
        f"**Verdict:** {report.verdict.value}",
        f"**Risk score:** {report.risk_score}/100",
        f"**Run:** `{report.run_id}`",
        f"**Evidence SHA-256:** `{report.evidence_hash}`",
        "",
        "## Reconstructed intent",
        "",
        report.intent,
        "",
        "## Executive summary",
        "",
        report.summary,
        "",
        "## Evidence-backed findings",
        "",
    ]
    for index, item in enumerate(report.findings, 1):
        lines.extend(
            [
                f"### {index}. [{item.severity.value.upper()}] {item.title}",
                "",
                f"- Location: `{item.path}:{item.line}`",
                f"- Confidence: {item.confidence:.0%}",
                f"- Evidence: `{item.evidence}`",
                *([f"- Product clause: {item.ticket_evidence}"] if item.ticket_evidence else []),
                f"- Impact: {item.impact}",
                f"- Challenge: {item.challenge}",
                f"- Missing proof: {item.suggested_test}",
                "",
            ]
        )
    if not report.findings:
        lines.extend(["No deterministic finding. This is not proof of safety.", ""])
    lines.extend(
        [
            "## Scope alignment",
            "",
            (
                f"- Coverage signal: {report.scope_coverage}%"
                if report.scope_coverage is not None
                else "- Coverage signal: not available"
            ),
            f"- Drift signal: {report.scope_drift}%",
        ]
    )
    for item in report.alignments:
        location = f" `{item.path}:{item.line}`" if item.path else ""
        lines.append(f"- **{item.status.value}**{location}: {item.clause}")
    lines.extend(["", "## Impact map", ""])
    for area in report.impact_areas:
        paths = ", ".join(f"`{path}`" for path in area.paths)
        lines.append(f"- **{area.name}** ({area.risk}): {paths}")
    if not report.impact_areas:
        lines.append("- No configured impact area matched.")
    lines.extend(["", "## Generated adversarial tests", ""])
    for test in report.adversarial_tests:
        lines.append(f"- `{test.name}` for {test.rule_id}: {test.rationale}")
    if not report.adversarial_tests:
        lines.append("- None generated.")
    lines.extend(["", "## Human decisions", ""])
    lines.extend(f"- {item}" for item in report.unresolved_questions)
    if not report.unresolved_questions:
        lines.append("- None raised by current gates.")
    lines.extend(["", "## Agent trace", ""])
    lines.extend(f"- `{event.step}` — {event.status}: {event.detail}" for event in report.timeline)
    lines.extend(["", f"Model: `{report.model_used or 'offline'}`", ""])
    return "\n".join(lines)


def render_adversarial_tests(report: VerificationReport) -> str:
    lines = [
        "# CodeTrust generated adversarial tests",
        "",
        "These templates encode missing proof. Adapt fixtures to target repository before execution.",
        "",
    ]
    for test in report.adversarial_tests:
        lines.extend(
            [
                f"## {test.name}",
                "",
                f"Rule: `{test.rule_id}`",
                "",
                test.rationale,
                "",
                "```python",
                test.code.rstrip(),
                "```",
                "",
            ]
        )
    if not report.adversarial_tests:
        lines.append("No adversarial test generated for current findings.\n")
    return "\n".join(lines)


def render_html(report: VerificationReport) -> str:
    color = {"BLOCK": "#ff4d6d", "NEEDS_REVIEW": "#ffb703", "PASS": "#2dd4bf"}[report.verdict.value]
    cards = (
        "".join(
            f"""
        <article class="finding">
          <div class="finding-head"><span class="severity {item.severity.value}">{item.severity.value}</span><code>{html.escape(item.rule_id)}</code></div>
          <h3>{html.escape(item.title)}</h3>
          <p class="location">{html.escape(item.path)}:{item.line} · {item.confidence:.0%} confidence</p>
          <pre>{html.escape(item.evidence)}</pre>
          <p><strong>Impact</strong> {html.escape(item.impact)}</p>
          <p><strong>Challenge</strong> {html.escape(item.challenge)}</p>
          <p><strong>Missing proof</strong> {html.escape(item.suggested_test)}</p>
        </article>"""
            for item in report.findings
        )
        or '<article class="finding"><h3>No deterministic blocker found</h3><p>Absence of findings is not proof of safety.</p></article>'
    )
    trace = "".join(
        f"<li><span>{html.escape(event.step)}</span><b>{html.escape(event.status)}</b><p>{html.escape(event.detail)}</p></li>"
        for event in report.timeline
    )
    questions = (
        "".join(f"<li>{html.escape(item)}</li>" for item in report.unresolved_questions)
        or "<li>None raised.</li>"
    )
    impacts = (
        "".join(
            f"<li><b>{html.escape(area.name)}</b><span>{html.escape(area.kind)} · {html.escape(area.risk)}</span><p>{html.escape(', '.join(area.paths))}</p></li>"
            for area in report.impact_areas
        )
        or "<li>No configured impact area matched.</li>"
    )
    generated = (
        "".join(
            f'<article class="finding"><div class="finding-head"><span class="severity medium">generated proof</span><code>{html.escape(test.rule_id)}</code></div><h3>{html.escape(test.name)}</h3><p>{html.escape(test.rationale)}</p><pre>{html.escape(test.code)}</pre></article>'
            for test in report.adversarial_tests
        )
        or '<article class="finding"><h3>No test generated</h3></article>'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CodeTrust · {report.verdict.value}</title>
<style>
:root{{--bg:#07111f;--panel:#0d1b2c;--line:#20344f;--text:#e9f1fb;--muted:#91a4bd;--accent:#8b5cf6;--verdict:{color}}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 15% 0,#172c4b 0,transparent 32%),var(--bg);color:var(--text);font:15px/1.55 Inter,ui-sans-serif,system-ui,sans-serif}}
.shell{{max-width:1180px;margin:auto;padding:44px 24px 80px}} header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:42px}} .brand{{font-weight:900;letter-spacing:-.04em;font-size:24px}} .brand i{{color:#2dd4bf;font-style:normal}} .hash{{font:12px ui-monospace;color:var(--muted)}}
.hero{{display:grid;grid-template-columns:1.4fr .6fr;gap:20px;margin-bottom:24px}} .panel,.finding{{background:linear-gradient(145deg,rgba(18,38,63,.94),rgba(10,25,43,.95));border:1px solid var(--line);border-radius:18px;box-shadow:0 16px 60px #0005}} .panel{{padding:28px}}
.eyebrow{{text-transform:uppercase;letter-spacing:.16em;color:var(--muted);font-size:11px;font-weight:800}} h1{{font-size:40px;line-height:1.05;letter-spacing:-.045em;margin:12px 0}} .summary{{color:#bfd0e4;max-width:65ch}} .verdict{{font-weight:950;font-size:38px;color:var(--verdict)}} .score{{font-size:72px;font-weight:950;letter-spacing:-.07em;line-height:1}} .score small{{font-size:18px;color:var(--muted)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} h2{{margin-top:38px;letter-spacing:-.025em}} .finding{{padding:22px}} .finding-head{{display:flex;justify-content:space-between}} .severity{{font-size:11px;text-transform:uppercase;font-weight:900;letter-spacing:.12em}} .critical{{color:#ff4d6d}} .high{{color:#ff8c42}} .medium{{color:#ffca3a}} .low{{color:#2dd4bf}} code,.location{{color:var(--muted)}} pre{{white-space:pre-wrap;background:#06101c;border:1px solid var(--line);padding:12px;border-radius:10px;color:#cae2ff;overflow:auto}} strong{{color:#fff;display:block;font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin-top:14px}}
.trace{{list-style:none;padding:0}} .trace li{{display:grid;grid-template-columns:180px 90px 1fr;border-top:1px solid var(--line);padding:14px 0}} .trace span{{font-family:ui-monospace}} .trace b{{color:#2dd4bf}} .trace p{{margin:0;color:var(--muted)}} footer{{margin-top:48px;color:var(--muted)}}
@media(max-width:800px){{.hero,.grid{{grid-template-columns:1fr}} h1{{font-size:32px}} .trace li{{grid-template-columns:1fr}} .hash{{display:none}}}}
</style></head><body><main class="shell">
<header><div class="brand">Code<i>Trust</i></div><div class="hash">EVIDENCE {report.evidence_hash[:16]}</div></header>
<section class="hero"><div class="panel"><div class="eyebrow">Reconstructed intent</div><h1>{html.escape(report.intent)}</h1><p class="summary">{html.escape(report.summary)}</p></div><div class="panel"><div class="eyebrow">Decision</div><div class="verdict">{report.verdict.value}</div><div class="score">{report.risk_score}<small>/100</small></div><p>{report.files_changed} files · {len(report.findings)} risks</p></div></section>
<h2>Evidence-backed findings</h2><section class="grid">{cards}</section>
<h2>Impact map</h2><section class="panel"><ol class="trace">{impacts}</ol></section>
<h2>Generated adversarial tests</h2><section class="grid">{generated}</section>
<section class="panel" style="margin-top:24px"><div class="eyebrow">Human boundary</div><h2 style="margin-top:8px">Unresolved decisions</h2><ul>{questions}</ul></section>
<h2>Agent trace</h2><section class="panel"><ol class="trace">{trace}</ol></section>
<footer>CodeTrust · verification evidence, not automatic approval · model {html.escape(report.model_used or "offline")}</footer>
</main></body></html>"""
