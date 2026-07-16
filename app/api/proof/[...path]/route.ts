import type { NextRequest } from "next/server";

const SAFE_SEGMENT = /^[A-Za-z0-9._~-]+$/;
const FORWARDED_RESPONSE_HEADERS = ["content-type", "content-disposition", "cache-control"] as const;

type RouteContext = { params: Promise<{ path: string[] }> };

function proofBaseUrl(): URL | null {
  const configured = process.env.TNOC_PROOF_API_BASE_URL;
  if (configured) {
    try {
      return new URL(configured);
    } catch {
      return null;
    }
  }
  return process.env.NODE_ENV === "production" ? null : new URL("http://127.0.0.1:8010");
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  if (!path.length || path.some((segment) => !SAFE_SEGMENT.test(segment))) {
    return Response.json({ detail: "Invalid proof API path" }, { status: 400 });
  }
  const base = proofBaseUrl();
  if (!base) {
    return Response.json({ detail: "Proof runner endpoint is not configured" }, { status: 503 });
  }
  if (base.protocol !== "https:" && process.env.NODE_ENV === "production") {
    return Response.json({ detail: "Production proof runner must use HTTPS" }, { status: 503 });
  }

  const target = new URL(`/v1/proof/${path.map(encodeURIComponent).join("/")}`, base);
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual",
      signal: AbortSignal.timeout(10_000),
      duplex: "half",
    } as RequestInit & { duplex: "half" });
  } catch {
    return Response.json({ detail: "Proof runner is offline" }, { status: 502 });
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
