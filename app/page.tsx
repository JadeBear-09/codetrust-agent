"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Incident = {
  id: string;
  title: string;
  description: string;
  submitted_by: string;
  submitted_at: string;
  domain: string;
  resource_ids: string[];
  source_record_count: number;
  file: string;
};

type MissionConfig = {
  service: string;
  live_available: boolean;
  default_model: string;
  model_calls_per_run: number;
  agents: string[];
  incidents: Incident[];
  truth_boundary: string;
};

type Finding = {
  specialist: string;
  candidate_codes: string[];
  evidence_ids: string[];
  summary: string;
  confidence: number;
  uncertainty: string[];
};

type Decision = {
  root_cause_code: string;
  confidence: number;
  evidence_ids: string[];
  reasoning_summary: string;
  uncertainty: string[];
  safe_to_plan: boolean;
};

type Recommendation = {
  action_mode: string;
  title: string;
  recommendation: string;
  target_resource_ids: string[];
  ordered_steps: string[];
  success_signals: string[];
  stop_conditions: string[];
  requires_human_approval: boolean;
  confidence: number;
};

type LogEvent = {
  observed_at: string;
  event: string;
  agent?: string;
  node?: string;
  attempt?: number;
  duration_ms?: number;
  quota_wait_ms?: number;
  model?: string;
  provider?: string;
  usage?: Record<string, number>;
  evidence?: unknown[];
  output?: Record<string, unknown>;
  [key: string]: unknown;
};

type MissionReport = {
  run_id: string;
  execution_mode: string;
  model: string;
  incident: Incident;
  findings: Finding[];
  decision: Decision;
  recommendation: Recommendation;
  usage: {
    completed_model_calls: number;
    failed_model_attempts: number;
    total_model_latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
};

type MissionState = {
  run_id: string;
  status: "queued" | "running" | "completed" | "failed";
  mode: string;
  model: string;
  incident_id: string;
  error: string | null;
  progress: {
    event_count: number;
    completed_model_calls: number;
    expected_model_calls: number;
  };
  events: LogEvent[];
  report: MissionReport | null;
  log_url: string;
};

const ROLE_COPY: Record<string, { title: string; scope: string }> = {
  telemetry: { title: "Telemetry specialist", scope: "Metrics only" },
  topology: { title: "Topology specialist", scope: "Dependencies only" },
  change_history: { title: "Change specialist", scope: "Change records only" },
  security: { title: "Security specialist", scope: "Threat evidence only" },
  adjudicator: { title: "Lead adjudicator", scope: "Specialist findings" },
  response_planner: { title: "Response planner", scope: "Adjudicated mission" },
};

function words(value: string): string {
  return value.replace(/[._:-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function eventAgent(event: LogEvent): string | undefined {
  if (event.agent) return event.agent;
  if (!event.node) return undefined;
  if (event.node.startsWith("mission-specialist:")) return event.node.split(":")[1];
  if (event.node === "mission-adjudicator") return "adjudicator";
  if (event.node === "mission-response-planner") return "response_planner";
  return undefined;
}

function roleState(role: string, mission: MissionState | null): "ready" | "queued" | "active" | "complete" {
  if (!mission) return "ready";
  const relevant = mission.events.filter((event) => eventAgent(event) === role);
  if (relevant.some((event) => event.event === "agent_responded")) return "complete";
  if (relevant.some((event) => event.event === "model_call_started")) return "active";
  return mission.status === "running" || mission.status === "queued" ? "queued" : "ready";
}

function logPayload(event: LogEvent): string {
  if (event.event === "agent_context_loaded") {
    return JSON.stringify(event.evidence ?? [], null, 2);
  }
  if (event.event === "agent_responded") {
    return JSON.stringify(event.output ?? {}, null, 2);
  }
  if (event.event === "model_call_started") {
    return `attempt=${event.attempt ?? 1} · provider=${event.provider ?? "google_genai"} · model=${event.model ?? "Gemini"}`;
  }
  if (event.event === "model_call_completed") {
    const tokens = event.usage?.total_tokens ?? 0;
    return `duration=${Math.round(event.duration_ms ?? 0)}ms · quota_wait=${Math.round(event.quota_wait_ms ?? 0)}ms · tokens=${tokens}`;
  }
  const hidden = new Set(["observed_at", "event"]);
  const remainder = Object.fromEntries(Object.entries(event).filter(([key]) => !hidden.has(key)));
  return Object.keys(remainder).length ? JSON.stringify(remainder, null, 2) : "recorded";
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export default function Home() {
  const [config, setConfig] = useState<MissionConfig | null>(null);
  const [selectedIncident, setSelectedIncident] = useState("ran-capacity-congestion");
  const [mission, setMission] = useState<MissionState | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const logEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fetch("/api/proof/config", { cache: "no-store" })
      .then(async (response) => {
        const body = (await response.json()) as MissionConfig | { detail?: string };
        if (!response.ok) throw new Error("detail" in body ? body.detail : "Mission API offline");
        return body as MissionConfig;
      })
      .then((body) => {
        setConfig(body);
        if (body.incidents[0]) setSelectedIncident(body.incidents[0].id);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Mission API offline"));
  }, []);

  useEffect(() => {
    if (!running) return;
    const started = window.performance.now();
    const timer = window.setInterval(() => setElapsedMs(Math.round(window.performance.now() - started)), 100);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [mission?.events.length]);

  const incident = config?.incidents.find((item) => item.id === selectedIncident) ?? null;
  const report = mission?.report ?? null;
  const agents = config?.agents ?? [
    "telemetry",
    "topology",
    "change_history",
    "security",
    "adjudicator",
    "response_planner",
  ];
  const responseEvents = useMemo(
    () => mission?.events.filter((event) => event.event === "agent_responded") ?? [],
    [mission],
  );

  async function runMission() {
    if (!config) return;
    setRunning(true);
    setError(null);
    setMission(null);
    setElapsedMs(0);
    try {
      const response = await fetch("/api/proof/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          mode: "live",
          model: config.default_model,
          incident_id: selectedIncident,
        }),
      });
      const body = (await response.json()) as MissionState | { detail?: string };
      if (!response.ok) throw new Error("detail" in body && body.detail ? body.detail : "Mission failed to start");
      let state = body as MissionState;
      setMission(state);
      for (let poll = 0; poll < 600 && !["completed", "failed"].includes(state.status); poll += 1) {
        await sleep(750);
        const update = await fetch(`/api/proof/runs/${state.run_id}`, { cache: "no-store" });
        const next = (await update.json()) as MissionState | { detail?: string };
        if (!update.ok) throw new Error("detail" in next && next.detail ? next.detail : "Mission status failed");
        state = next as MissionState;
        setMission(state);
      }
      if (state.status === "failed") throw new Error(state.error ?? "Gemini mission failed");
      if (state.status !== "completed") throw new Error("Mission polling timed out");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Gemini mission failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="app-shell agent-console">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="ChangeGuard home">
          <span className="brand-mark">CG</span>
          <span><strong>ChangeGuard</strong><small>Gemini multi-agent command</small></span>
        </a>
        <div className="header-status">
          <span><i className={config?.live_available ? "online" : ""} />{config?.live_available ? "Gemini key ready" : "Gemini key missing"}</span>
          <span className="boundary">Advisory only · no controller writes</span>
        </div>
      </header>

      <section className="hero agent-hero" id="top">
        <div className="hero-copy">
          <span className="eyebrow">LIVE GEMINI MULTI-AGENT MISSION</span>
          <h1>Six agents.<br /><em>One evidence-led decision.</em></h1>
          <p>Four isolated Gemini specialists investigate real-world telecom incident records in parallel. Gemini adjudicator decides root cause. Gemini response planner owns final recommendation.</p>
          <div className="truth-row">
            <span><b>LIVE</b> Six Gemini model calls</span>
            <span><b>VISIBLE</b> Inputs, outputs, timing, tokens</span>
            <span><b>NO PRESET VERDICT</b> Agent result rules</span>
          </div>
        </div>

        <aside className="launch-panel" aria-label="Mission controls">
          <div className="panel-heading">
            <div><span className="eyebrow">MISSION CONTROL</span><h2>Select incident</h2></div>
            <span className={`feed-state ${config?.live_available ? "live" : "cached"}`}>
              {config?.live_available ? "Live only" : "Key required"}
            </span>
          </div>
          <div className="scenario-list mission-list" role="radiogroup" aria-label="Incident">
            {config?.incidents.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={selectedIncident === item.id ? "selected" : ""}
                onClick={() => setSelectedIncident(item.id)}
                role="radio"
                aria-checked={selectedIncident === item.id}
              >
                <i>{String(index + 1).padStart(2, "0")}</i>
                <span><strong>{item.title}</strong><small>{words(item.domain)} · {item.source_record_count} evidence records</small></span>
              </button>
            )) ?? <div className="loading-line">Loading incidents…</div>}
          </div>
          <button className="run-button" type="button" onClick={() => void runMission()} disabled={!config?.live_available || running}>
            <span>{running ? `Agents working · ${(elapsedMs / 1000).toFixed(1)}s` : "Launch live Gemini agents"}</span><i>→</i>
          </button>
          <p className="scenario-caption">{incident?.description ?? "Incident evidence loads here."}</p>
        </aside>
      </section>

      {error && <div className="error-banner" role="alert"><strong>Mission error</strong><span>{error}</span></div>}

      <section className="flow-preview" aria-label="Gemini agent workflow">
        <div className="flow-intro">
          <div>
            <span className="eyebrow">AGENT ORCHESTRATION</span>
            <h2>Parallel specialists. Sequential judgment.</h2>
            <p>Each specialist receives one evidence source. Adjudicator sees their structured findings. Response planner sees adjudicated mission state. Every card below maps to live Gemini call.</p>
          </div>
          <div className="request-receipt" aria-live="polite">
            <span>{mission?.run_id ?? "POST /api/proof/runs"}</span>
            <strong className={running ? "request-live" : ""}>{mission ? words(mission.status) : "READY"}</strong>
            <small>{mission ? `${mission.progress.completed_model_calls}/${mission.progress.expected_model_calls} model calls · ${mission.progress.event_count} log events` : `${config?.model_calls_per_run ?? 6} live calls per mission`}</small>
          </div>
        </div>
        <div className="agent-flow-grid">
          {agents.map((role, index) => {
            const state = roleState(role, mission);
            const copy = ROLE_COPY[role] ?? { title: words(role), scope: "Mission scope" };
            const output = responseEvents.find((event) => event.agent === role)?.output;
            return (
              <article className={state} key={role}>
                <div><span>{String(index + 1).padStart(2, "0")}</span><i>{state === "complete" ? "✓" : state === "active" ? "●" : ""}</i></div>
                <small>{copy.scope}</small>
                <strong>{copy.title}</strong>
                <p>{output && "confidence" in output ? `${Math.round(Number(output.confidence) * 100)}% confidence · ${String(output.summary ?? output.root_cause_code ?? output.title ?? "response recorded")}` : state === "active" ? "Gemini reasoning now…" : "Waiting for mission state"}</p>
                {index < agents.length - 1 && <b>→</b>}
              </article>
            );
          })}
        </div>
      </section>

      {mission && (
        <section className="demo-output mission-output" aria-live="polite">
          <section className="live-log-panel" id="logs">
            <div className="section-heading">
              <div><span className="eyebrow">LIVE AGENT LOG</span><h2>What every agent received and returned.</h2></div>
              {mission.events.length > 0 && <a href={mission.log_url}>Download JSONL</a>}
            </div>
            <div className="log-stream">
              {mission.events.map((event, index) => (
                <article key={`${event.observed_at}-${event.event}-${index}`} className={event.event === "agent_responded" ? "agent-output" : ""}>
                  <div className="log-meta">
                    <time>{new Date(event.observed_at).toLocaleTimeString()}</time>
                    <span>{eventAgent(event) ? words(eventAgent(event) as string) : "Orchestrator"}</span>
                    <strong>{words(event.event)}</strong>
                  </div>
                  <pre>{logPayload(event)}</pre>
                </article>
              ))}
              {mission.events.length === 0 && <div className="log-empty">Mission queued. Waiting for first agent receipt…</div>}
              <div ref={logEnd} />
            </div>
          </section>

          {report && (
            <>
              <section className="decision-grid">
                <article className="decision-card">
                  <span className="eyebrow">GEMINI ADJUDICATOR</span>
                  <h2>{words(report.decision.root_cause_code)}</h2>
                  <div className="confidence"><span style={{ width: `${report.decision.confidence * 100}%` }} /></div>
                  <strong>{Math.round(report.decision.confidence * 100)}% confidence</strong>
                  <p>{report.decision.reasoning_summary}</p>
                  <small>Evidence: {report.decision.evidence_ids.join(", ") || "none cited"}</small>
                </article>
                <article className="decision-card recommendation-card">
                  <span className="eyebrow">GEMINI RESPONSE PLANNER · {words(report.recommendation.action_mode)}</span>
                  <h2>{report.recommendation.title}</h2>
                  <p>{report.recommendation.recommendation}</p>
                  <ol>{report.recommendation.ordered_steps.map((step) => <li key={step}>{step}</li>)}</ol>
                  <small>{report.recommendation.requires_human_approval ? "Human approval required before mutation" : "Advisory response only"}</small>
                </article>
              </section>

              <section className="finding-section">
                <div className="section-heading"><div><span className="eyebrow">SPECIALIST OUTPUTS</span><h2>Independent evidence views.</h2></div><span>{report.usage.completed_model_calls} live calls · {report.usage.total_tokens.toLocaleString()} tokens</span></div>
                <div className="finding-grid">
                  {report.findings.map((finding) => (
                    <article key={finding.specialist}>
                      <span>{words(finding.specialist)}</span>
                      <strong>{finding.candidate_codes.map(words).join(" · ")}</strong>
                      <p>{finding.summary}</p>
                      <small>{Math.round(finding.confidence * 100)}% confidence · cites {finding.evidence_ids.join(", ")}</small>
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}
        </section>
      )}

      <footer>
        <div><strong>ChangeGuard</strong><span>Gemini multi-agent telecom incident command.</span></div>
        <p>{config?.truth_boundary ?? "Live model outputs. No controller execution."}</p>
      </footer>
    </main>
  );
}
