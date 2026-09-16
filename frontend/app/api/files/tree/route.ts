import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000";

/**
 * GET /api/files/tree?repository=owner/repo
 *
 * Proxies to the Python backend's file-tree endpoint for one repository's
 * local clone (repositories/<owner>_<repo>/).
 */
export async function GET(req: NextRequest) {
  const repository = req.nextUrl.searchParams.get("repository");
  if (!repository) {
    return NextResponse.json({ error: "repository query param required" }, { status: 400 });
  }

  try {
    const res = await fetch(
      `${BACKEND_URL}/api/files/tree/${encodeURIComponent(repository)}`,
      { cache: "no-store" }
    );

    const contentType = res.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      const text = await res.text().catch(() => "");
      return NextResponse.json(
        { error: `Backend returned non-JSON response (${res.status}): ${text.slice(0, 100)}` },
        { status: res.status >= 400 ? res.status : 502 }
      );
    }

    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { error: data?.detail || "Failed to load file tree" },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: `Backend unavailable: ${message}` },
      { status: 503 }
    );
  }
}
