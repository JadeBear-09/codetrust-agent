import type { NextRequest } from "next/server";

const SAFE_SEGMENT = /^[A-Za-z0-9._~-]+$/;
const FORWARDED_REQUEST_HEADERS = [
  "authorization",
  "content-type",
  "idempotency-key",
  "x-tenant-id",
] as const;
const FORWARDED_RESPONSE_HEADERS = ["content-type", "cache-control"] as const;

type RouteContext = { params: Promise<{ path: string[] }> };

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  if (!path.length || path.some((segment) => !SAFE_SEGMENT.test(segment))) {
    return Response.json({ detail: "Invalid API path" }, { status: 400 });
  }

  let base: URL;
  try {
    base = new URL(requiredEnvironment("TNOC_API_BASE_URL"));
  } catch {
    return Response.json({ detail: "Backend endpoint is not configured" }, { status: 503 });
  }
  if (base.protocol !== "https:" && process.env.NODE_ENV === "production") {
    return Response.json({ detail: "Production backend endpoint must use HTTPS" }, { status: 503 });
  }

  const target = new URL(`/v1/${path.map(encodeURIComponent).join("/")}`, base);
  target.search = request.nextUrl.search;
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (!headers.has("x-tenant-id") && process.env.TNOC_ENABLE_DEVELOPMENT_AUTH === "true") {
    headers.set("x-tenant-id", requiredEnvironment("TNOC_DEVELOPMENT_TENANT_ID"));
  }

  const timeout = Number(requiredEnvironment("TNOC_PROXY_TIMEOUT_MS"));
  if (!Number.isFinite(timeout) || timeout <= 0) {
    return Response.json({ detail: "Invalid proxy timeout configuration" }, { status: 503 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual",
      signal: AbortSignal.timeout(timeout),
      // Required by Node-compatible fetch when forwarding a request stream.
      duplex: "half",
    } as RequestInit & { duplex: "half" });
  } catch {
    return Response.json({ detail: "Backend unavailable" }, { status: 502 });
  }

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  responseHeaders.set("x-content-type-options", "nosniff");
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const dynamic = "force-dynamic";
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
