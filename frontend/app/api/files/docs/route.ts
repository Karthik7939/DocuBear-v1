import { NextRequest, NextResponse } from "next/server";
import { FileDocSummary } from "@/types";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000";

interface BackendFileDocSummary {
  id: string;
  repo_id: string;
  title: string;
  source_path: string;
  created_at: string;
  has_changes: boolean;
}

function toFileDocSummary(doc: BackendFileDocSummary): FileDocSummary {
  return {
    id: doc.id,
    repoId: doc.repo_id,
    title: doc.title,
    sourcePath: doc.source_path,
    createdAt: doc.created_at,
    hasChanges: doc.has_changes,
  };
}

/**
 * GET /api/files/docs?repository=owner/repo
 *
 * Proxies to the Python backend's list-previously-generated-file-docs
 * endpoint, so the file-docs page can show what's already been documented
 * even after a page refresh.
 */
export async function GET(req: NextRequest) {
  const repository = req.nextUrl.searchParams.get("repository");
  if (!repository) {
    return NextResponse.json({ error: "repository query param required" }, { status: 400 });
  }

  try {
    const res = await fetch(
      `${BACKEND_URL}/api/files/docs/${encodeURIComponent(repository)}`,
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
        { error: data?.detail || "Failed to load generated docs" },
        { status: res.status }
      );
    }

    return NextResponse.json((data as BackendFileDocSummary[]).map(toFileDocSummary));
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: `Backend unavailable: ${message}` },
      { status: 503 }
    );
  }
}
