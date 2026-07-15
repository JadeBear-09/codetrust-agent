from __future__ import annotations

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="CodeTrust pull-request verification">
  <title>CodeTrust</title>
  <style>
    :root {
      color-scheme: dark;
      --bg:#080b09; --panel:#111612; --panel-2:#0d110e; --line:#263128;
      --text:#f4f7f4; --muted:#9ba79d; --green:#78e7a2; --red:#ff7d7d;
      --amber:#ffd166; --shadow:0 18px 55px #0007;
    }
    * { box-sizing:border-box }
    body { margin:0; background:radial-gradient(circle at 50% -20%,#183421 0,transparent 42%),var(--bg); color:var(--text); font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif }
    button,input,textarea { font:inherit }
    a { color:inherit }
    .shell { width:min(880px,calc(100% - 32px)); margin:auto; padding:28px 0 70px }
    header { display:flex; align-items:center; justify-content:space-between; margin-bottom:48px }
    .brand { font-size:20px; font-weight:900; letter-spacing:-.04em }
    .brand span { color:var(--green) }
    .model-status { display:flex; align-items:center; gap:8px; color:var(--muted); font-size:13px }
    .dot { width:8px; height:8px; border-radius:50%; background:var(--amber); box-shadow:0 0 0 4px #ffd16618 }
    .dot.ready { background:var(--green); box-shadow:0 0 0 4px #78e7a218 }
    h1 { margin:0; font-size:clamp(34px,7vw,58px); line-height:1; letter-spacing:-.065em; max-width:700px }
    .sub { color:var(--muted); font-size:17px; margin:18px 0 28px }
    .card { background:linear-gradient(145deg,#121814,#0d110e); border:1px solid var(--line); border-radius:20px; box-shadow:var(--shadow) }
    form { padding:24px }
    label { display:block; margin-bottom:9px; font-size:12px; color:#cbd4cc; text-transform:uppercase; letter-spacing:.1em; font-weight:800 }
    input,textarea { width:100%; border:1px solid #303b32; border-radius:12px; color:var(--text); background:#090d0a; outline:none; padding:14px 15px }
    input:focus,textarea:focus { border-color:var(--green); box-shadow:0 0 0 3px #78e7a214 }
    input { font-size:16px }
    textarea { min-height:160px; resize:vertical }
    details { border-top:1px solid var(--line); margin-top:18px; padding-top:16px }
    summary { color:var(--muted); cursor:pointer; user-select:none; list-style:none; font-weight:700 }
    summary::-webkit-details-marker { display:none }
    summary::after { content:"+"; float:right; color:var(--green) }
    details[open] summary::after { content:"−" }
    .advanced-copy { margin:8px 0 12px; color:var(--muted); font-size:13px }
    .actions { display:flex; gap:12px; margin-top:20px }
    button { border:0; border-radius:12px; cursor:pointer; font-weight:900 }
    .primary { flex:1; padding:14px 18px; color:#061109; background:var(--green) }
    .primary:hover { filter:brightness(1.06) }
    .primary:disabled { cursor:not-allowed; opacity:.45 }
    .cancel { padding:14px 16px; color:var(--muted); background:transparent; border:1px solid var(--line) }
    .running { display:none; align-items:center; gap:10px; margin-top:16px; color:var(--muted); font-size:13px }
    .running.show { display:flex }
    .spinner { width:14px; height:14px; border:2px solid #314035; border-top-color:var(--green); border-radius:50%; animation:spin .8s linear infinite }
    @keyframes spin { to { transform:rotate(360deg) } }
    .error { display:none; margin-top:18px; padding:16px; border:1px solid #6d3434; border-radius:12px; background:#251313; color:#ffd1d1 }
    .error.show { display:block }
    .error strong { display:block; margin-bottom:4px }
    .principles { display:flex; gap:8px; flex-wrap:wrap; margin-top:14px }
    .chip { border:1px solid var(--line); border-radius:999px; padding:6px 10px; color:var(--muted); font-size:12px }
    .result { display:none; margin-top:24px; overflow:hidden }
    .result.show { display:block }
    .result-head { display:grid; grid-template-columns:1fr auto; gap:24px; padding:26px }
    .verdict { display:inline-flex; border-radius:7px; padding:5px 9px; background:#243127; color:var(--green); font-size:12px; font-weight:950; letter-spacing:.1em }
    .verdict.BLOCK { background:#351a1a; color:var(--red) }
    .verdict.NEEDS_REVIEW { background:#342d18; color:var(--amber) }
    .result h2 { margin:12px 0 7px; font-size:27px; line-height:1.15; letter-spacing:-.035em }
    .summary { color:var(--muted); margin:0; max-width:620px }
    .score { text-align:right; font-size:48px; line-height:1; font-weight:950; letter-spacing:-.06em }
    .score small { display:block; margin-top:7px; color:var(--muted); font-size:10px; letter-spacing:.1em; text-transform:uppercase }
    .meta { display:flex; flex-wrap:wrap; gap:8px; padding:0 26px 24px }
    .comparison { display:grid; grid-template-columns:1fr 1fr; gap:12px; padding:0 26px 26px }
    .comparison-card { padding:16px; border:1px solid var(--line); border-radius:12px; background:#090d0a }
    .comparison-card.wide { grid-column:1/-1 }
    .comparison-card b { display:block; margin-bottom:6px; color:var(--green); font-size:10px; text-transform:uppercase; letter-spacing:.1em }
    .comparison-card p { margin:0; color:#dbe3dc }
    .difference-list { margin:0; padding-left:18px; color:#dbe3dc }
    .difference-list li + li { margin-top:5px }
    .section { margin-top:30px }
    .section h3 { margin:0 0 12px; font-size:18px; letter-spacing:-.025em }
    .finding { padding:0; margin:0 0 10px; border-top:1px solid var(--line) }
    .finding summary { padding:16px 20px; color:var(--text) }
    .finding summary::after { margin-left:12px }
    .finding-top { display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:12px; color:var(--muted); font-size:12px }
    .finding-name { color:var(--text); font-size:14px; font-weight:850 }
    .finding-body { padding:0 20px 20px }
    .severity { text-transform:uppercase; font-weight:900; color:var(--amber) }
    .severity.critical,.severity.high { color:var(--red) }
    .evidence { margin:0; padding:12px; border-radius:9px; background:#080b09; color:#dce4dd; font:12px/1.5 ui-monospace,SFMono-Regular,monospace; overflow-wrap:anywhere }
    .finding-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:14px }
    .finding-grid b { display:block; margin-bottom:4px; color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.1em }
    .finding-grid p { margin:0 }
    .empty { padding:20px; color:var(--muted) }
    .trace { padding:0 22px 20px; margin:0; list-style:none }
    .trace li { padding:10px 0; border-top:1px solid var(--line); color:var(--muted) }
    .trace b { color:var(--text); margin-right:8px; text-transform:capitalize }
    .source-links { display:flex; gap:10px; padding:0 26px 26px }
    .source-links a { text-decoration:none; border:1px solid var(--line); border-radius:9px; padding:8px 11px; color:var(--muted); font-size:12px }
    .history { margin-top:30px }
    .history-list { display:grid; gap:8px; margin-top:12px }
    .history button { width:100%; display:flex; justify-content:space-between; padding:13px; color:var(--muted); background:var(--panel-2); border:1px solid var(--line); text-align:left }
    footer { margin-top:44px; color:#667068; font-size:12px; text-align:center }
    @media(max-width:640px) { header{margin-bottom:34px}.result-head{grid-template-columns:1fr}.score{text-align:left}.comparison{grid-template-columns:1fr}.comparison-card.wide{grid-column:auto}.finding-grid{grid-template-columns:1fr}.shell{width:min(100% - 20px,880px)}form{padding:18px} }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div class="brand">Code<span>Trust</span></div>
      <div class="model-status"><i class="dot" id="modelDot"></i><span id="modelStatus">Checking model…</span></div>
    </header>

    <h1>Verify pull request.</h1>
    <p class="sub">Paste URL. Agent reads base repository, understands PR change, and measures scope distance.</p>

    <form class="card" id="verifyForm">
      <label for="prReference">GitHub pull request</label>
      <input id="prReference" name="reference" type="url" required autocomplete="url" placeholder="https://github.com/owner/repo/pull/42">
      <div class="actions">
        <button class="primary" id="verifyButton" type="submit">Verify pull request</button>
        <button class="cancel" id="cancelButton" type="button" hidden>Stop waiting</button>
      </div>
      <div class="running" id="running"><i class="spinner"></i><span>Learning repository baseline and comparing PR…</span></div>
      <div class="error" id="error" role="alert"></div>
      <div class="principles"><span class="chip">No PR code execution</span><span class="chip">No silent model fallback</span><span class="chip">No repository mutation</span></div>
    </form>

    <section class="card result" id="result" aria-live="polite">
      <div class="result-head">
        <div><span class="verdict" id="verdict"></span><h2 id="intentTitle"></h2><p class="summary" id="summary"></p></div>
        <div class="score"><span id="score"></span><small id="scoreLabel">scope distance / 100</small></div>
      </div>
      <div class="meta" id="meta"></div>
      <div class="comparison" id="comparison"></div>
      <div class="source-links" id="sourceLinks"></div>
      <details>
        <summary style="padding:0 26px 16px">Verification details</summary>
        <ul class="trace" id="trace"></ul>
      </details>
    </section>

    <section class="section" id="findingsSection" hidden>
      <h3>Evidence-backed findings</h3>
      <div id="findings"></div>
    </section>

    <details class="history" id="historySection">
      <summary>Recent runs</summary>
      <div class="history-list" id="history"></div>
    </details>
    <footer>CodeTrust verifies. It never merges, deploys, or changes pull requests.</footer>
  </main>

  <script>
    const byId = id => document.getElementById(id);
    let controller = null;
    let modelConfigured = false;

    function node(tag, className, text) {
      const element = document.createElement(tag);
      if (className) element.className = className;
      if (text !== undefined) element.textContent = text;
      return element;
    }

    function setRunning(active) {
      byId("running").classList.toggle("show", active);
      byId("verifyButton").disabled = active || !modelConfigured;
      byId("cancelButton").hidden = !active;
    }

    function showError(detail) {
      const error = byId("error");
      error.replaceChildren(node("strong", "", "Verification failed"), node("span", "", detail));
      error.classList.add("show");
      byId("result").classList.remove("show");
      byId("findingsSection").hidden = true;
    }

    function errorText(payload) {
      const detail = payload?.detail;
      if (typeof detail === "string") return detail;
      if (detail?.message) return detail.code ? `${detail.code}: ${detail.message}` : detail.message;
      return "Request failed. Pull request was not changed.";
    }

    function chip(text) { return node("span", "chip", text); }

    function renderFinding(item, index) {
      const card = node("details", "card finding");
      card.open = index === 0;
      const heading = node("summary");
      const top = node("div", "finding-top");
      top.append(
        node("span", `severity ${item.severity}`, item.severity),
        node("span", "finding-name", item.title),
        node("span", "", `${item.path}:${item.line}`)
      );
      heading.append(top);
      const body = node("div", "finding-body");
      const evidence = node("p", "evidence", item.evidence);
      const grid = node("div", "finding-grid");
      const impact = node("div");
      impact.append(node("b", "", "Impact"), node("p", "", item.impact));
      const proof = node("div");
      proof.append(node("b", "", "Verify"), node("p", "", item.suggested_test));
      grid.append(impact, proof);
      body.append(evidence, grid);
      card.append(heading, body);
      return card;
    }

    function renderReport(data, scroll = true) {
      const comparison = data.scope_comparison;
      const relationship = comparison?.relationship || (data.source?.intent_trust === "insufficient" ? "insufficient" : "unscored");
      const verdict = byId("verdict");
      const relationshipClass = relationship === "divergent" || relationship === "insufficient" ? "NEEDS_REVIEW" : "PASS";
      verdict.className = `verdict ${relationshipClass}`;
      verdict.textContent = `${relationship.toUpperCase()} SCOPE`;
      byId("intentTitle").textContent = comparison?.repository_purpose || data.intent;
      byId("summary").textContent = comparison?.rationale || data.summary;
      byId("score").textContent = comparison?.distance ?? "—";
      byId("scoreLabel").textContent = "scope distance / 100";

      const intentSource = data.source?.intent_source;
      const sourceLabel = intentSource === "repository-inference"
          ? `INFERRED scope · ${data.source.scope_confidence || "unknown"} confidence`
          : intentSource === "insufficient-repository-evidence"
            ? "scope evidence insufficient"
            : "repository-derived scope";
      byId("meta").replaceChildren(
        chip(`${data.files_changed} files`),
        chip(`${data.findings.length} findings`),
        chip(`${data.applicable_checks?.length || 0} gates`),
        chip(`decision · ${data.verdict.replaceAll("_", " ")}`),
        chip(`risk · ${data.risk_score}/100`),
        chip(sourceLabel),
        ...(data.source?.scope_evidence_paths ? [chip(`base evidence · ${data.source.scope_evidence_paths}`)] : []),
        chip(`${data.model_used || "model not recorded"} · ${data.synthesis_attempts || 0} attempt(s)`),
        chip(`${data.duration_ms ?? data.synthesis_duration_ms ?? 0} ms total`),
        ...(data.synthesis_input_truncated ? [chip("model input truncated")] : [])
      );

      const comparisonElement = byId("comparison");
      comparisonElement.replaceChildren();
      if (comparison) {
        const baseline = node("div", "comparison-card");
        baseline.append(node("b", "", "Repository baseline"), node("p", "", comparison.repository_purpose));
        const change = node("div", "comparison-card");
        change.append(node("b", "", "PR changes"), node("p", "", comparison.change_summary));
        const differences = node("div", "comparison-card wide");
        differences.append(node("b", "", "How PR differs"));
        const list = node("ul", "difference-list");
        const items = comparison.differences?.length ? comparison.differences : ["No material scope difference identified."];
        list.append(...items.map(item => node("li", "", item)));
        differences.append(list);
        const evidence = node("div", "comparison-card wide");
        evidence.append(node("b", "", "Base-repository evidence"), node("p", "", (comparison.evidence_paths || []).join(" · ") || "No validated evidence paths."));
        comparisonElement.append(baseline, change, differences, evidence);
      }

      const links = byId("sourceLinks");
      links.replaceChildren();
      if (data.source?.url) {
        const pr = node("a", "", "Open pull request ↗");
        pr.href = data.source.url; pr.target = "_blank"; pr.rel = "noreferrer"; links.append(pr);
      }
      if (data.source?.repo) {
        const repo = node("a", "", "Open repository ↗");
        repo.href = `https://github.com/${data.source.repo}`; repo.target = "_blank"; repo.rel = "noreferrer"; links.append(repo);
      }

      byId("trace").replaceChildren(...(data.timeline || []).map(event => {
        const row = node("li"); row.append(node("b", "", event.step.replaceAll("-", " ")), document.createTextNode(event.detail)); return row;
      }));
      byId("result").classList.add("show");

      const findings = byId("findings");
      findings.replaceChildren(...(data.findings || []).map(renderFinding));
      if (!(data.findings || []).length) findings.append(node("div", "card empty", "No blocker found by applicable gates."));
      byId("findingsSection").hidden = false;
      if (scroll) byId("result").scrollIntoView({behavior:"smooth", block:"start"});
    }

    async function loadConfig() {
      const response = await fetch("/api/config");
      const data = await response.json();
      modelConfigured = Boolean(data.model?.configured);
      byId("modelDot").classList.toggle("ready", modelConfigured);
      byId("modelStatus").textContent = modelConfigured
        ? `${data.model.provider} configured · ${data.model.model}`
        : "Model not configured";
      byId("verifyButton").disabled = !modelConfigured;
      if (!modelConfigured) showError("Add backend API key, then restart CodeTrust.");
    }

    async function loadRuns() {
      const response = await fetch("/api/runs?limit=5");
      if (!response.ok) return;
      const data = await response.json();
      const history = byId("history");
      const currentRuns = data.runs.filter(run => run.schema_version === 3);
      history.replaceChildren(...currentRuns.map(run => {
        const button = node("button");
        button.type = "button";
        button.append(node("span", "", run.source?.reference || run.intent), node("span", "", run.verdict));
        button.onclick = () => renderReport(run);
        return button;
      }));
      byId("historySection").hidden = !currentRuns.length;
    }

    byId("verifyForm").addEventListener("submit", async event => {
      event.preventDefault();
      byId("error").classList.remove("show");
      controller = new AbortController();
      setRunning(true);
      try {
        const response = await fetch("/api/github", {
          method:"POST",
          headers:{"content-type":"application/json"},
          signal:controller.signal,
          body:JSON.stringify({
            reference:byId("prReference").value.trim(),
            model_mode:"required"
          })
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(errorText(data));
        }
        renderReport(data);
        await loadRuns();
      } catch (error) {
        showError(error.name === "AbortError" ? "Stopped waiting. Pull request was not changed." : error.message);
      } finally {
        controller = null;
        setRunning(false);
      }
    });

    byId("cancelButton").onclick = () => controller?.abort();
    loadConfig().then(loadRuns).catch(() => showError("CodeTrust backend unavailable."));
  </script>
</body>
</html>
"""
