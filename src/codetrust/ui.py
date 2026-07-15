from __future__ import annotations

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="CodeTrust evidence-first pull-request verification">
  <title>CodeTrust · Verify pull requests</title>
  <style>
    :root {
      --ink:#eef2ef;
      --muted:#8c9991;
      --dim:#69736d;
      --bg:#090b0a;
      --panel:#101411;
      --panel-2:#151a17;
      --line:#252c28;
      --green:#8af5b2;
      --green-deep:#163622;
      --red:#ff7b7b;
      --red-deep:#361919;
      --amber:#ffc66d;
      --amber-deep:#382b16;
      --blue:#8db8ff;
      --shadow:0 24px 80px rgba(0,0,0,.35);
    }
    * { box-sizing:border-box; }
    [hidden] { display:none !important; }
    html { color-scheme:dark; scroll-behavior:smooth; }
    body {
      margin:0;
      min-height:100vh;
      color:var(--ink);
      background:
        radial-gradient(circle at 80% -10%,rgba(64,125,86,.14),transparent 28rem),
        radial-gradient(circle at -10% 55%,rgba(82,101,91,.08),transparent 24rem),
        var(--bg);
      font:14px/1.5 Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    }
    button,input,textarea { font:inherit; }
    button,a { -webkit-tap-highlight-color:transparent; }
    button { color:inherit; }
    a { color:inherit; }
    .app { min-height:100vh; display:grid; grid-template-columns:264px minmax(0,1fr); }
    .rail {
      position:sticky;
      top:0;
      height:100vh;
      padding:28px 20px;
      border-right:1px solid var(--line);
      background:rgba(10,12,11,.86);
      backdrop-filter:blur(18px);
      display:flex;
      flex-direction:column;
      z-index:5;
    }
    .brand { display:flex; align-items:center; gap:11px; font-weight:850; letter-spacing:-.02em; font-size:17px; }
    .mark {
      width:34px;
      height:34px;
      display:grid;
      place-items:center;
      color:#09100b;
      background:var(--green);
      border-radius:10px;
      font-weight:950;
      box-shadow:0 0 30px rgba(138,245,178,.13);
    }
    .rail-copy { margin:34px 0 18px; color:var(--dim); font-size:11px; text-transform:uppercase; letter-spacing:.14em; font-weight:800; }
    .nav-button {
      width:100%;
      border:1px solid transparent;
      background:transparent;
      padding:11px 12px;
      border-radius:10px;
      text-align:left;
      cursor:pointer;
      color:var(--muted);
      display:flex;
      align-items:center;
      gap:10px;
    }
    .nav-button.active { color:var(--ink); border-color:var(--line); background:var(--panel-2); }
    .nav-dot { width:7px; height:7px; border-radius:50%; background:currentColor; }
    .history { margin-top:8px; overflow:auto; min-height:0; }
    .history-empty { color:var(--dim); padding:12px; font-size:12px; }
    .history-item {
      width:100%;
      padding:11px 12px;
      margin:0 0 6px;
      border:1px solid transparent;
      border-radius:10px;
      background:transparent;
      text-align:left;
      cursor:pointer;
    }
    .history-item:hover,.history-item:focus-visible { border-color:var(--line); background:var(--panel); outline:none; }
    .history-item strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px; }
    .history-meta { display:flex; justify-content:space-between; gap:8px; color:var(--dim); font-size:10px; margin-top:4px; text-transform:uppercase; letter-spacing:.06em; }
    .history-verdict.PASS { color:var(--green); }
    .history-verdict.BLOCK { color:var(--red); }
    .history-verdict.NEEDS_REVIEW { color:var(--amber); }
    .rail-foot { margin-top:auto; padding-top:20px; border-top:1px solid var(--line); }
    .service-status { display:flex; align-items:flex-start; gap:9px; color:var(--muted); font-size:12px; }
    .status-light { width:8px; height:8px; flex:0 0 auto; margin-top:5px; border-radius:50%; background:var(--dim); }
    .status-light.ready { background:var(--green); box-shadow:0 0 14px rgba(138,245,178,.5); }
    .status-light.warn { background:var(--amber); }
    .main { min-width:0; }
    .topbar {
      height:72px;
      padding:0 clamp(22px,4vw,58px);
      display:flex;
      align-items:center;
      justify-content:space-between;
      border-bottom:1px solid var(--line);
      background:rgba(9,11,10,.62);
      backdrop-filter:blur(18px);
    }
    .top-title { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.14em; font-weight:800; }
    .top-links { display:flex; gap:8px; }
    .button,.link-button {
      min-height:40px;
      border:1px solid var(--line);
      background:var(--panel-2);
      border-radius:10px;
      padding:9px 14px;
      font-weight:750;
      cursor:pointer;
      text-decoration:none;
      display:inline-flex;
      align-items:center;
      justify-content:center;
      gap:8px;
    }
    .button:hover,.link-button:hover { border-color:#3c4740; transform:translateY(-1px); }
    .button.primary { border-color:var(--green); background:var(--green); color:#09110c; box-shadow:0 8px 30px rgba(138,245,178,.12); }
    .button.primary:disabled { opacity:.55; cursor:wait; transform:none; }
    .button.ghost { background:transparent; color:var(--muted); }
    .content { width:min(1220px,calc(100% - 44px)); margin:0 auto; padding:58px 0 96px; }
    .hero { display:grid; grid-template-columns:minmax(0,1.05fr) minmax(360px,.95fr); gap:clamp(30px,6vw,84px); align-items:center; }
    .eyebrow { color:var(--green); text-transform:uppercase; letter-spacing:.16em; font-size:11px; font-weight:850; }
    h1 { margin:18px 0 20px; max-width:12ch; font-size:clamp(46px,6vw,78px); line-height:.96; letter-spacing:-.065em; font-weight:870; }
    .lead { max-width:58ch; color:#aab5ae; font-size:17px; line-height:1.65; }
    .principles { display:flex; flex-wrap:wrap; gap:8px; margin-top:28px; }
    .principle { padding:8px 11px; border:1px solid var(--line); border-radius:99px; color:var(--muted); font-size:11px; }
    .panel { border:1px solid var(--line); background:linear-gradient(150deg,rgba(20,25,22,.98),rgba(13,16,14,.98)); border-radius:18px; box-shadow:var(--shadow); }
    .verify-card { padding:26px; }
    .card-head { display:flex; align-items:start; justify-content:space-between; gap:18px; margin-bottom:22px; }
    .card-head h2 { margin:0 0 4px; font-size:20px; letter-spacing:-.03em; }
    .card-head p { margin:0; color:var(--muted); font-size:12px; }
    .mode-pill { padding:7px 9px; border:1px solid var(--line); border-radius:99px; color:var(--green); font-size:10px; text-transform:uppercase; letter-spacing:.08em; font-weight:850; white-space:nowrap; }
    label.field-label { display:block; color:#b6c0ba; font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:.1em; margin:17px 0 8px; }
    .hint { color:var(--dim); font-size:11px; font-weight:500; text-transform:none; letter-spacing:0; float:right; }
    input[type="url"],input[type="text"],textarea {
      width:100%;
      border:1px solid var(--line);
      background:#0b0e0c;
      color:var(--ink);
      border-radius:11px;
      padding:13px 14px;
      outline:none;
    }
    input:focus,textarea:focus { border-color:#60806b; box-shadow:0 0 0 3px rgba(138,245,178,.06); }
    textarea { min-height:136px; resize:vertical; line-height:1.55; }
    ::placeholder { color:#505953; }
    .options { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:16px; }
    .check { display:flex; align-items:center; gap:9px; color:var(--muted); cursor:pointer; user-select:none; }
    .check input { accent-color:var(--green); width:16px; height:16px; }
    .form-actions { display:flex; gap:9px; margin-top:20px; }
    .form-actions .primary { flex:1; }
    .error { display:none; margin-top:14px; border:1px solid #593232; background:#261414; color:#ffaaaa; padding:11px 13px; border-radius:10px; font-size:12px; white-space:pre-wrap; }
    .running { display:none; margin-top:14px; color:var(--muted); font-size:12px; }
    .running.show { display:flex; align-items:center; gap:10px; }
    .spinner { width:15px; height:15px; border-radius:50%; border:2px solid var(--line); border-top-color:var(--green); animation:spin .8s linear infinite; }
    @keyframes spin { to { transform:rotate(360deg); } }
    .results { display:none; margin-top:68px; }
    .results.show { display:block; }
    .result-banner { padding:28px; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:28px; align-items:center; }
    .verdict-line { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
    .verdict {
      display:inline-flex;
      align-items:center;
      padding:6px 9px;
      border-radius:7px;
      font-weight:900;
      font-size:12px;
      letter-spacing:.08em;
    }
    .verdict.PASS { background:var(--green-deep); color:var(--green); }
    .verdict.BLOCK { background:var(--red-deep); color:var(--red); }
    .verdict.NEEDS_REVIEW { background:var(--amber-deep); color:var(--amber); }
    .run-id { color:var(--dim); font:11px ui-monospace,SFMono-Regular,Menlo,monospace; }
    .result-banner h2 { margin:0; font-size:clamp(24px,3vw,38px); letter-spacing:-.045em; line-height:1.08; }
    .summary-copy { color:var(--muted); max-width:72ch; margin:13px 0 0; }
    .score { text-align:right; min-width:140px; }
    .score strong { display:block; font-size:62px; line-height:.9; letter-spacing:-.07em; }
    .score span { color:var(--dim); text-transform:uppercase; letter-spacing:.1em; font-size:10px; font-weight:800; }
    .metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:1px; border-top:1px solid var(--line); background:var(--line); }
    .metric { background:var(--panel); padding:18px 24px; }
    .metric strong { display:block; font-size:17px; }
    .metric span { color:var(--dim); text-transform:uppercase; letter-spacing:.09em; font-size:9px; font-weight:800; }
    .source-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }
    .source-actions .link-button { min-height:34px; padding:7px 11px; font-size:11px; }
    .section { margin-top:42px; }
    .section-title { display:flex; align-items:end; justify-content:space-between; gap:16px; margin-bottom:14px; }
    .section-title h3 { margin:0; font-size:20px; letter-spacing:-.03em; }
    .section-title p { margin:0; color:var(--dim); font-size:11px; }
    .decision-list { display:grid; gap:8px; }
    .decision { padding:16px 18px; border-left:3px solid var(--amber); }
    .decision p { margin:0; color:#d7d0c2; }
    .findings { display:grid; gap:12px; min-width:0; }
    .finding { padding:22px; box-shadow:none; min-width:0; }
    .finding-top { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }
    .finding-top > div { min-width:0; }
    .finding-title { margin:7px 0 0; font-size:18px; letter-spacing:-.02em; }
    .rule { color:var(--blue); font:11px ui-monospace,SFMono-Regular,Menlo,monospace; }
    .severity { padding:5px 8px; border-radius:6px; font-size:9px; letter-spacing:.1em; font-weight:900; text-transform:uppercase; }
    .severity.critical,.severity.high { background:var(--red-deep); color:var(--red); }
    .severity.medium { background:var(--amber-deep); color:var(--amber); }
    .severity.low { background:var(--green-deep); color:var(--green); }
    .location { margin-top:15px; color:var(--muted); overflow-wrap:anywhere; font:11px ui-monospace,SFMono-Regular,Menlo,monospace; }
    .evidence { max-width:100%; margin:8px 0 0; padding:13px; border:1px solid var(--line); background:#090c0a; border-radius:9px; color:#c5cec8; white-space:pre-wrap; overflow-wrap:anywhere; overflow-x:auto; font:11px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace; }
    .finding-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-top:17px; }
    .finding-block span { display:block; margin-bottom:5px; color:var(--dim); font-size:9px; text-transform:uppercase; letter-spacing:.1em; font-weight:850; }
    .finding-block p { margin:0; color:#aeb8b2; }
    .proof { border-color:#33453a; background:rgba(22,54,34,.35); padding:12px; border-radius:9px; }
    .two-col { display:grid; grid-template-columns:1.15fr .85fr; gap:14px; }
    .compact-panel { padding:20px; box-shadow:none; }
    .timeline { display:grid; gap:0; }
    .timeline-item { position:relative; padding:0 0 17px 24px; color:var(--muted); }
    .timeline-item:last-child { padding-bottom:0; }
    .timeline-item::before { content:""; position:absolute; left:5px; top:7px; bottom:-4px; border-left:1px solid var(--line); }
    .timeline-item:last-child::before { display:none; }
    .timeline-item::after { content:""; position:absolute; left:1px; top:5px; width:9px; height:9px; border-radius:50%; background:var(--green); box-shadow:0 0 0 3px var(--green-deep); }
    .timeline-item strong { display:block; color:var(--ink); text-transform:capitalize; font-size:12px; }
    .timeline-item span { font-size:11px; }
    .impact-list { display:flex; flex-wrap:wrap; gap:8px; }
    .impact-chip { border:1px solid var(--line); padding:9px 11px; border-radius:9px; color:var(--muted); }
    .impact-chip strong { color:var(--ink); }
    .alignment-list { display:grid; gap:8px; }
    .alignment { padding:13px; border:1px solid var(--line); border-radius:9px; }
    .alignment strong { display:block; margin-bottom:4px; }
    .alignment p { margin:0; color:var(--muted); font-size:12px; }
    .alignment-status { color:var(--green); text-transform:uppercase; letter-spacing:.08em; font-size:9px; }
    .alignment-status.contradicted { color:var(--red); }
    .alignment-status.ambiguous { color:var(--amber); }
    .empty-findings { padding:24px; color:var(--muted); text-align:center; }
    .footer { margin-top:56px; padding-top:20px; border-top:1px solid var(--line); display:flex; justify-content:space-between; gap:20px; color:var(--dim); font-size:11px; }
    .mobile-brand { display:none; }
    @media(max-width:980px) {
      .app { grid-template-columns:1fr; }
      .rail { display:none; }
      .mobile-brand { display:flex; align-items:center; gap:9px; font-weight:850; }
      .top-title { display:none; }
      .content { padding-top:36px; }
      .hero { grid-template-columns:1fr; }
      h1 { max-width:14ch; }
    }
    @media(max-width:680px) {
      .topbar { padding:0 16px; }
      .content { width:min(100% - 28px,1220px); }
      .hero { gap:30px; }
      h1 { font-size:44px; }
      .verify-card { padding:20px; }
      .result-banner { grid-template-columns:1fr; }
      .score { text-align:left; }
      .metrics { grid-template-columns:1fr 1fr; }
      .finding-grid,.two-col { grid-template-columns:1fr; }
      .finding { padding:18px; }
      .footer { flex-direction:column; }
      .top-links .button { display:none; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="rail">
      <div class="brand"><span class="mark">C</span><span>CodeTrust</span></div>
      <div class="rail-copy">Workspace</div>
      <button class="nav-button active" type="button" id="newRun"><span class="nav-dot"></span>New verification</button>
      <div class="rail-copy">Recent runs</div>
      <div class="history" id="history"><div class="history-empty">No verification runs yet.</div></div>
      <div class="rail-foot">
        <div class="service-status">
          <span class="status-light" id="modelLight"></span>
          <span><strong id="modelLabel">Checking model…</strong><br><span id="modelDetail">Backend configuration</span></span>
        </div>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="mobile-brand"><span class="mark">C</span><span>CodeTrust</span></div>
        <div class="top-title">Evidence-first pull-request verification</div>
        <div class="top-links">
          <a class="link-button" href="/docs" target="_blank" rel="noreferrer">API docs</a>
          <button class="button ghost" type="button" id="refreshRuns">Refresh</button>
        </div>
      </header>

      <div class="content">
        <section class="hero" id="verify">
          <div>
            <div class="eyebrow">Verification firewall</div>
            <h1>Trust evidence, not confidence.</h1>
            <p class="lead">Give CodeTrust a real pull request and approved intent. The agent fetches the live diff, maps scope and impact, runs deterministic gates, then routes unresolved risk to a human.</p>
            <div class="principles">
              <span class="principle">Never executes PR code</span>
              <span class="principle">Deterministic verdict</span>
              <span class="principle">Model-bounded explanation</span>
            </div>
          </div>

          <form class="panel verify-card" id="verifyForm">
            <div class="card-head">
              <div><h2>Verify pull request</h2><p>GitHub PR must be visible to authenticated GitHub CLI.</p></div>
              <span class="mode-pill">Live PR</span>
            </div>
            <label class="field-label" for="prReference">GitHub pull request</label>
            <input id="prReference" name="reference" type="text" required autocomplete="url" placeholder="https://github.com/owner/repository/pull/42">

            <label class="field-label" for="intent">Approved intent <span class="hint">Optional · PR description used when blank</span></label>
            <textarea id="intent" name="intent" placeholder="Outcome, in-scope behavior, out-of-scope boundaries, and acceptance criteria…"></textarea>

            <div class="options">
              <label class="check" for="useModel"><input id="useModel" type="checkbox" checked>Use configured model for synthesis</label>
            </div>
            <div class="form-actions">
              <button class="button primary" id="verifyButton" type="submit">Verify pull request</button>
              <button class="button ghost" id="stopButton" type="button" hidden>Stop request</button>
            </div>
            <div class="running" id="running"><span class="spinner"></span><span>Fetching live diff and running verification gates…</span></div>
            <div class="error" id="error" role="alert"></div>
          </form>
        </section>

        <section class="results" id="results" aria-live="polite">
          <div class="panel">
            <div class="result-banner">
              <div>
                <div class="verdict-line"><span class="verdict" id="verdict"></span><span class="run-id" id="runId"></span></div>
                <h2 id="intentTitle"></h2>
                <p class="summary-copy" id="summary"></p>
                <div class="source-actions" id="sourceActions"></div>
              </div>
              <div class="score"><strong id="score">0</strong><span>risk score / 100</span></div>
            </div>
            <div class="metrics">
              <div class="metric"><strong id="filesMetric">0</strong><span>files changed</span></div>
              <div class="metric"><strong id="findingsMetric">0</strong><span>findings</span></div>
              <div class="metric"><strong id="driftMetric">0%</strong><span>scope drift</span></div>
              <div class="metric"><strong id="modelMetric">Offline</strong><span>synthesis</span></div>
            </div>
          </div>

          <div class="section" id="decisionSection" hidden>
            <div class="section-title"><h3>Human decisions</h3><p>Automation stops here</p></div>
            <div class="decision-list" id="decisions"></div>
          </div>

          <div class="section">
            <div class="section-title"><h3>Evidence-backed findings</h3><p>File · line · evidence · impact · proof</p></div>
            <div class="findings" id="findings"></div>
          </div>

          <div class="section two-col">
            <div class="panel compact-panel">
              <div class="section-title"><h3>Verification trace</h3><p>Deterministic workflow</p></div>
              <div class="timeline" id="timeline"></div>
            </div>
            <div class="panel compact-panel">
              <div class="section-title"><h3>Impact map</h3><p>Affected surfaces</p></div>
              <div class="impact-list" id="impact"></div>
            </div>
          </div>

          <div class="section" id="alignmentSection" hidden>
            <div class="section-title"><h3>Scope alignment</h3><p>Intent-to-change evidence</p></div>
            <div class="alignment-list" id="alignments"></div>
          </div>
        </section>

        <footer class="footer"><span>CodeTrust verifies changes. It never merges, deploys, or claims proof beyond configured gates.</span><span id="evidenceHash"></span></footer>
      </div>
    </main>
  </div>

  <script>
    const byId = id => document.getElementById(id);
    let activeController = null;
    let config = null;

    function textNode(tag, className, value) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      node.textContent = value ?? "";
      return node;
    }

    function showError(message) {
      const node = byId("error");
      node.textContent = message;
      node.style.display = "block";
    }

    function clearError() {
      byId("error").style.display = "none";
      byId("error").textContent = "";
    }

    function setRunning(running) {
      byId("verifyButton").disabled = running;
      byId("stopButton").hidden = !running;
      byId("running").classList.toggle("show", running);
    }

    function sourceLink(label, href) {
      const link = textNode("a", "link-button", label);
      link.href = href;
      link.target = "_blank";
      link.rel = "noreferrer";
      return link;
    }

    function renderFinding(item) {
      const article = document.createElement("article");
      article.className = "panel finding";
      const top = document.createElement("div");
      top.className = "finding-top";
      const titleWrap = document.createElement("div");
      titleWrap.append(textNode("div", "rule", item.rule_id), textNode("h4", "finding-title", item.title));
      top.append(titleWrap, textNode("span", `severity ${item.severity}`, item.severity));
      article.append(top);
      article.append(textNode("div", "location", `${item.path}:${item.line} · ${Math.round(item.confidence * 100)}% confidence`));
      article.append(textNode("pre", "evidence", item.evidence));

      const grid = document.createElement("div");
      grid.className = "finding-grid";
      const impact = document.createElement("div");
      impact.className = "finding-block";
      impact.append(textNode("span", "", "Impact"), textNode("p", "", item.impact));
      const proof = document.createElement("div");
      proof.className = "finding-block proof";
      proof.append(textNode("span", "", "Suggested verification"), textNode("p", "", item.suggested_test));
      grid.append(impact, proof);
      article.append(grid);
      return article;
    }

    function renderReport(data, scroll = true) {
      const verdict = byId("verdict");
      verdict.className = `verdict ${data.verdict}`;
      verdict.textContent = data.verdict.replace("_", " ");
      byId("runId").textContent = data.run_id;
      byId("intentTitle").textContent = data.intent;
      byId("summary").textContent = data.summary;
      byId("score").textContent = data.risk_score;
      byId("filesMetric").textContent = data.files_changed;
      byId("findingsMetric").textContent = data.findings.length;
      byId("driftMetric").textContent = `${data.scope_drift ?? 0}%`;
      byId("modelMetric").textContent = data.model_used || "Offline";
      byId("evidenceHash").textContent = data.evidence_hash ? `Evidence ${data.evidence_hash.slice(0, 12)}…` : "";

      const actions = byId("sourceActions");
      actions.replaceChildren();
      if (data.source?.url) actions.append(sourceLink("Open pull request ↗", data.source.url));
      if (data.source?.repo) actions.append(sourceLink("Open repository ↗", `https://github.com/${data.source.repo}`));
      if (data.source?.state) actions.append(textNode("span", "link-button", `PR ${data.source.state}`));

      const decisions = byId("decisions");
      decisions.replaceChildren(...(data.unresolved_questions || []).map(question => {
        const node = document.createElement("div");
        node.className = "panel decision";
        node.append(textNode("p", "", question));
        return node;
      }));
      byId("decisionSection").hidden = !(data.unresolved_questions || []).length;

      const findings = byId("findings");
      if (data.findings.length) findings.replaceChildren(...data.findings.map(renderFinding));
      else findings.replaceChildren(textNode("div", "panel empty-findings", "Configured gates found no blocker. PASS remains scoped, not universal proof."));

      byId("timeline").replaceChildren(...(data.timeline || []).map(event => {
        const node = document.createElement("div");
        node.className = "timeline-item";
        node.append(textNode("strong", "", event.step.replaceAll("-", " ")), textNode("span", "", event.detail));
        return node;
      }));

      const impact = byId("impact");
      const areas = data.impact_areas || [];
      if (areas.length) impact.replaceChildren(...areas.map(area => {
        const node = document.createElement("div");
        node.className = "impact-chip";
        node.append(textNode("strong", "", area.name), document.createTextNode(` · ${area.risk} · ${area.paths.length} file(s)`));
        return node;
      }));
      else impact.replaceChildren(textNode("span", "history-empty", "No configured impact area matched."));

      const alignment = byId("alignments");
      const alignments = data.alignments || [];
      alignment.replaceChildren(...alignments.map(item => {
        const node = document.createElement("div");
        node.className = "alignment";
        node.append(textNode("span", `alignment-status ${item.status}`, item.status));
        node.append(textNode("strong", "", item.clause));
        node.append(textNode("p", "", `${item.path}:${item.line} · ${item.rationale}`));
        return node;
      }));
      byId("alignmentSection").hidden = !alignments.length;

      byId("results").classList.add("show");
      if (scroll) byId("results").scrollIntoView({behavior:"smooth", block:"start"});
    }

    async function loadRuns() {
      const response = await fetch("/api/runs?limit=20");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not load run history");
      const history = byId("history");
      if (!data.runs.length) {
        history.replaceChildren(textNode("div", "history-empty", "No verification runs yet."));
        return;
      }
      history.replaceChildren(...data.runs.map(run => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "history-item";
        button.append(textNode("strong", "", run.source?.reference || run.intent || run.run_id));
        const meta = document.createElement("div");
        meta.className = "history-meta";
        meta.append(textNode("span", `history-verdict ${run.verdict}`, run.verdict.replace("_", " ")));
        meta.append(textNode("span", "", `${run.risk_score}/100`));
        button.append(meta);
        button.onclick = () => renderReport(run);
        return button;
      }));
    }

    async function loadConfig() {
      const response = await fetch("/api/config");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Configuration check failed");
      config = data;
      const configured = Boolean(data.model?.configured);
      byId("modelLight").className = `status-light ${configured ? "ready" : "warn"}`;
      byId("modelLabel").textContent = configured ? `${data.model.provider} ready` : "Offline mode";
      byId("modelDetail").textContent = configured ? data.model.model : "Add backend API key";
      byId("useModel").checked = configured;
      byId("useModel").disabled = !configured;
    }

    async function verifyPullRequest(event) {
      event.preventDefault();
      clearError();
      activeController = new AbortController();
      setRunning(true);
      try {
        const response = await fetch("/api/github", {
          method:"POST",
          headers:{"content-type":"application/json"},
          signal:activeController.signal,
          body:JSON.stringify({
            reference:byId("prReference").value.trim(),
            intent:byId("intent").value.trim(),
            offline:!byId("useModel").checked
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Verification failed");
        renderReport(data);
        await loadRuns();
      } catch (error) {
        showError(error.name === "AbortError" ? "Request stopped. Pull request remains unchanged." : error.message);
      } finally {
        activeController = null;
        setRunning(false);
      }
    }

    function resetForm() {
      byId("verifyForm").reset();
      byId("useModel").checked = Boolean(config?.model?.configured);
      byId("results").classList.remove("show");
      clearError();
      byId("verify").scrollIntoView({behavior:"smooth", block:"start"});
      byId("prReference").focus();
    }

    async function init() {
      byId("verifyForm").onsubmit = verifyPullRequest;
      byId("stopButton").onclick = () => activeController?.abort();
      byId("newRun").onclick = resetForm;
      byId("refreshRuns").onclick = () => loadRuns().catch(error => showError(error.message));
      await Promise.all([loadConfig(), loadRuns()]);
    }

    init().catch(error => showError(error.message));
  </script>
</body>
</html>"""
