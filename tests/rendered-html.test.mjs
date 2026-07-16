import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders live Gemini multi-agent mission", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /ChangeGuard/);
  assert.match(html, /Six agents/);
  assert.match(html, /One evidence-led decision/);
  assert.match(html, /Launch live Gemini agents/);
  assert.match(html, /Advisory only · no controller writes/);
  assert.match(html, /Six Gemini model calls/);
  assert.match(html, /Inputs, outputs, timing, tokens/);
  assert.match(html, /NO PRESET VERDICT/);
  assert.match(html, /Parallel specialists\. Sequential judgment\./);
  assert.match(html, /POST \/api\/proof\/runs/);
  assert.doesNotMatch(html, /deterministic/i);
  assert.doesNotMatch(html, /Incident queue|Inventory health|Active alarms/);
  assert.doesNotMatch(html, /Run both JSON examples|standalone JSON incident files/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("includes Gemini mission product metadata and matching social card", async () => {
  const response = await render();
  const html = await response.text();
  assert.match(html, /ChangeGuard — Live Gemini Multi-Agent Mission/);
  assert.match(html, /og-ran-guardian\.png/);
  assert.match(html, /theme-color/);
});
