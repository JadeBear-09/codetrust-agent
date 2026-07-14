from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from codetrust.agent import verify_change
from codetrust.github import load_pull_request


class VerifyRequest(BaseModel):
    ticket: str = Field(min_length=1, max_length=20_000)
    diff: str = Field(min_length=1, max_length=500_000)
    offline: bool = True


class GitHubRequest(BaseModel):
    reference: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9]\d*$")
    offline: bool = True


app = FastAPI(
    title="CodeTrust",
    version="0.2.0",
    description="Evidence-first verification API for AI-generated changes.",
)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_HTML


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "codetrust"}


@app.get("/api/demo")
def demo() -> dict[str, str]:
    root = Path.cwd()
    ticket = root / "demo/tickets/payment-reconciliation.md"
    diff = root / "demo/patches/risky-payment.diff"
    if not ticket.exists() or not diff.exists():
        raise HTTPException(status_code=404, detail="Run server from CodeTrust repository root")
    return {"ticket": ticket.read_text(), "diff": diff.read_text()}


@app.post("/api/verify")
def verify(request: VerifyRequest) -> dict:
    return verify_change(
        request.ticket,
        request.diff,
        offline=request.offline,
        source={"type": "dashboard-diff"},
    ).to_dict()


@app.post("/api/github")
def verify_github(request: GitHubRequest) -> dict:
    try:
        change = load_pull_request(request.reference)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return verify_change(
        change.ticket,
        change.diff,
        offline=request.offline,
        source={
            "type": "github-pr",
            "reference": request.reference,
            "url": change.url,
            "base_sha": change.base_sha,
            "head_sha": change.head_sha,
        },
    ).to_dict()


def run_server(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CodeTrust · Verification firewall</title>
  <style>
    :root { --bg:#070914; --panel:#101525; --line:#29314a; --text:#f6f7fb; --muted:#9aa6bd; --cyan:#25e6c8; --magenta:#e20074; --red:#ff4f6f; --amber:#ffb224; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--text); background:radial-gradient(circle at 75% -10%,#341146 0,transparent 30%),radial-gradient(circle at 10% 0,#0a3944 0,transparent 28%),var(--bg); font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif; min-height:100vh; }
    .shell { width:min(1240px,calc(100% - 36px)); margin:auto; padding:28px 0 80px; }
    header { display:flex; align-items:center; justify-content:space-between; padding:8px 0 30px; }
    .brand { font-size:24px; font-weight:950; letter-spacing:-.05em; } .brand i { color:var(--cyan); font-style:normal; }
    .status { color:var(--muted); display:flex; gap:8px; align-items:center; font-size:12px; text-transform:uppercase; letter-spacing:.12em; font-weight:800; }
    .dot { width:8px; height:8px; border-radius:50%; background:var(--cyan); box-shadow:0 0 18px var(--cyan); }
    .hero { display:grid; grid-template-columns:1.1fr .9fr; gap:20px; align-items:stretch; }
    .panel { background:linear-gradient(145deg,rgba(18,24,42,.96),rgba(10,14,27,.96)); border:1px solid var(--line); border-radius:20px; box-shadow:0 20px 70px #0008; }
    .intro { padding:34px; } .eyebrow { color:var(--cyan); text-transform:uppercase; letter-spacing:.16em; font-size:11px; font-weight:900; }
    h1 { font-size:clamp(38px,6vw,72px); line-height:.96; letter-spacing:-.065em; margin:18px 0; max-width:10ch; }
    .intro p { color:#bac4d8; max-width:58ch; font-size:17px; }
    .flow { display:grid; grid-template-columns:repeat(4,1fr); gap:7px; margin-top:28px; }
    .flow span { padding:10px 8px; border:1px solid var(--line); border-radius:9px; text-align:center; color:var(--muted); font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:.07em; transition:.25s; }
    .flow span.active { border-color:var(--cyan); color:var(--cyan); background:#25e6c813; }
    .form { padding:26px; } .tabs { display:flex; padding:4px; background:#080b14; border-radius:11px; margin-bottom:20px; }
    .tabs button { flex:1; border:0; color:var(--muted); background:transparent; padding:10px; border-radius:8px; font-weight:850; cursor:pointer; }
    .tabs button.active { color:white; background:#20283b; }
    label { display:block; margin:14px 0 7px; color:var(--muted); font-size:11px; font-weight:900; text-transform:uppercase; letter-spacing:.1em; }
    textarea,input { width:100%; color:var(--text); background:#080b14; border:1px solid var(--line); border-radius:10px; padding:12px; font:12px/1.45 ui-monospace,SFMono-Regular,monospace; outline:none; }
    textarea:focus,input:focus { border-color:var(--cyan); } textarea { min-height:118px; resize:vertical; }
    .actions { display:flex; gap:10px; align-items:center; margin-top:16px; }
    button.primary,button.secondary { border:0; border-radius:10px; padding:12px 16px; font-weight:900; cursor:pointer; }
    button.primary { flex:1; color:#07110f; background:var(--cyan); } button.primary:disabled { opacity:.45; cursor:wait; }
    button.secondary { color:white; background:#242c40; }
    .check { display:flex; align-items:center; gap:7px; color:var(--muted); font-size:12px; } .check input { width:auto; }
    #results { display:none; margin-top:22px; } .result-top { display:grid; grid-template-columns:1.3fr .7fr; gap:18px; }
    .summary { padding:28px; } .summary h2 { font-size:30px; letter-spacing:-.04em; margin:9px 0; } .summary p { color:var(--muted); }
    .decision { padding:26px; } .verdict { font-size:30px; font-weight:950; color:var(--red); } .score { font-size:68px; font-weight:950; line-height:1; letter-spacing:-.07em; } .score small { color:var(--muted); font-size:16px; }
    h3.section { margin:32px 0 13px; font-size:22px; letter-spacing:-.03em; }
    .grid { display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }
    .card { padding:20px; } .card-head { display:flex; justify-content:space-between; align-items:center; gap:12px; }
    .badge { font-size:10px; font-weight:950; text-transform:uppercase; letter-spacing:.12em; color:var(--amber); } .critical { color:var(--red); } .high { color:#ff8548; } .medium { color:var(--amber); }
    code { color:var(--muted); } .location { color:var(--muted); font:12px ui-monospace; } pre { white-space:pre-wrap; overflow:auto; padding:12px; color:#cfe5ff; background:#080b14; border:1px solid var(--line); border-radius:9px; }
    .impact { display:flex; flex-wrap:wrap; gap:9px; } .chip { padding:10px 12px; border:1px solid var(--line); border-radius:99px; background:#101727; } .chip b { color:var(--cyan); }
    .error { display:none; margin-top:14px; color:#ff9aae; background:#3a1320; border:1px solid #6b2035; padding:12px; border-radius:9px; }
    footer { margin-top:42px; color:var(--muted); font-size:12px; }
    @media(max-width:850px) { .hero,.result-top,.grid { grid-template-columns:1fr; } h1 { max-width:none; } .flow { grid-template-columns:1fr 1fr; } }
  </style>
</head>
<body><main class="shell">
  <header><div class="brand">Code<i>Trust</i></div><div class="status"><span class="dot"></span>verification firewall online</div></header>
  <section class="hero">
    <div class="panel intro"><div class="eyebrow">Evidence before approval</div><h1>Trust code at agent speed.</h1><p>Coding agents create pull requests. CodeTrust reconstructs intent, maps impact, challenges failure paths, generates missing proof, and routes only unresolved risk to humans.</p><div class="flow"><span>scope</span><span>impact</span><span>challenge</span><span>decision</span></div></div>
    <div class="panel form">
      <div class="tabs"><button id="diffTab" class="active">Ticket + diff</button><button id="prTab">GitHub PR</button></div>
      <div id="diffForm"><label for="ticket">Ticket / acceptance criteria</label><textarea id="ticket" placeholder="What must this change guarantee?"></textarea><label for="diff">Unified diff</label><textarea id="diff" placeholder="diff --git ..."></textarea></div>
      <div id="prForm" hidden><label for="pr">Pull request</label><input id="pr" placeholder="OWNER/REPO#123"></div>
      <div class="actions"><button class="secondary" id="sample">Load demo</button><label class="check"><input id="offline" type="checkbox" checked> Offline</label><button class="primary" id="run">Run verification</button></div>
      <div class="error" id="error"></div>
    </div>
  </section>
  <section id="results"><div class="result-top"><div class="panel summary"><div class="eyebrow">Reconstructed intent</div><h2 id="intent"></h2><p id="summary"></p></div><div class="panel decision"><div class="eyebrow">Decision</div><div class="verdict" id="verdict"></div><div class="score"><span id="score"></span><small>/100</small></div><p id="meta"></p></div></div><h3 class="section">Impact map</h3><div class="impact" id="impact"></div><h3 class="section">Evidence-backed findings</h3><div class="grid" id="findings"></div><h3 class="section">Generated adversarial proof</h3><div class="grid" id="tests"></div></section>
  <footer>CodeTrust · local-first POC · deterministic verdicts · model-bounded explanation</footer>
</main>
<script>
const $=id=>document.getElementById(id); let mode='diff';
function setMode(next){mode=next;$('diffForm').hidden=next!=='diff';$('prForm').hidden=next!=='pr';$('sample').hidden=next!=='diff';$('diffTab').classList.toggle('active',next==='diff');$('prTab').classList.toggle('active',next==='pr');}
$('diffTab').onclick=()=>setMode('diff'); $('prTab').onclick=()=>setMode('pr');
$('sample').onclick=async()=>{try{const r=await fetch('/api/demo');const d=await r.json();if(!r.ok)throw Error(d.detail);$('ticket').value=d.ticket;$('diff').value=d.diff;}catch(e){showError(e.message)}};
function showError(message){$('error').textContent=message;$('error').style.display='block';}
function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
function render(data){$('results').style.display='block';$('intent').textContent=data.intent;$('summary').textContent=data.summary;$('verdict').textContent=data.verdict;$('verdict').style.color=data.verdict==='PASS'?'var(--cyan)':data.verdict==='BLOCK'?'var(--red)':'var(--amber)';$('score').textContent=data.risk_score;$('meta').textContent=`${data.files_changed} files · ${data.findings.length} risks · ${data.model_used||'offline'}`;
  $('impact').replaceChildren(...data.impact_areas.map(a=>{const n=el('div','chip');n.append(el('b','',a.name),document.createTextNode(` · ${a.risk} · ${a.paths.length} file(s)`));return n;}));
  $('findings').replaceChildren(...data.findings.map(f=>{const n=el('article','panel card');const h=el('div','card-head');h.append(el('span',`badge ${f.severity}`,f.severity),el('code','',f.rule_id));n.append(h,el('h3','',f.title),el('p','location',`${f.path}:${f.line} · ${Math.round(f.confidence*100)}%`),el('pre','',f.evidence),el('p','',f.impact));return n;}));
  $('tests').replaceChildren(...data.adversarial_tests.map(t=>{const n=el('article','panel card');n.append(el('div','badge','generated test'),el('h3','',t.name),el('p','',t.rationale),el('pre','',t.code));return n;})); window.scrollTo({top:$('results').offsetTop-20,behavior:'smooth'});
}
$('run').onclick=async()=>{const btn=$('run');$('error').style.display='none';btn.disabled=true;document.querySelectorAll('.flow span').forEach((n,i)=>setTimeout(()=>n.classList.add('active'),i*180));try{const isPr=mode==='pr';const body=isPr?{reference:$('pr').value,offline:$('offline').checked}:{ticket:$('ticket').value,diff:$('diff').value,offline:$('offline').checked};const r=await fetch(isPr?'/api/github':'/api/verify',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Verification failed');render(d);}catch(e){showError(e.message)}finally{btn.disabled=false;}};
</script></body></html>"""
