import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

/**
 * GET /api/rag/status?repo=owner/repo
 *
 * Proxies the RAG status check to the Python backend.
 * Returns real Pinecone vector count and indexing status.
 */
export async function GET(req: NextRequest) {
  const repo = req.nextUrl.searchParams.get("repo");
  if (!repo) {
    return NextResponse.json({ error: "repo query param required" }, { status: 400 });
  }

  try {
    const res = await fetch(
      `${BACKEND_URL}/api/rag/status/${encodeURIComponent(repo)}`,
      { cache: "no-store" }
    );
    const contentType = res.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      return NextResponse.json(
        { indexed: false, vector_count: 0, error: "Backend returned non-JSON" },
        { status: 200 }
      );
    }
    const data = await res.json().catch(() => ({ indexed: false, vector_count: 0 }));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { indexed: false, vector_count: 0, error: "Backend unavailable" },
      { status: 200 }
    );
  }
}
