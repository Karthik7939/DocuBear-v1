import { NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

/**
 * GET /api/rag/knowledge-base
 *
 * Proxies to the Python backend and returns every repository
 * that has been bootstrapped with embeddings, along with
 * their vector counts and file counts.
 */
export async function GET() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000);

    const res = await fetch(`${BACKEND_URL}/api/rag/knowledge-base`, {
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    const contentType = res.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      return NextResponse.json(
        { backend: "local", repos: [] },
        { status: 200 }
      );
    }

    const data = await res.json().catch(() => ({ backend: "local", repos: [] }));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { backend: "local", repos: [] },
      { status: 200 }
    );
  }
}


/**
 * DELETE /api/rag/knowledge-base?repo=owner/repo
 *
 * Proxies to the Python backend to erase a repository's embeddings.
 */
export async function DELETE(req: Request) {
  try {
    const url = new URL(req.url);
    const repo = url.searchParams.get("repo");
    if (!repo) {
      return NextResponse.json({ error: "Missing repo parameter" }, { status: 400 });
    }

    const res = await fetch(`${BACKEND_URL}/api/rag/knowledge-base/${encodeURIComponent(repo)}`, {
      method: "DELETE",
    });
    
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      return NextResponse.json(
        { error: errorData.detail || "Failed to delete" },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend unavailable" }, { status: 503 });
  }
}
