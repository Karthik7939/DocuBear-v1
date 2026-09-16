import { NextRequest, NextResponse } from "next/server";
import { DocVersion, FileDocVersion } from "@/types";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000";

interface BackendFileDocument {
  id: string;
  repo_id: string;
  title: string;
  source_path: string;
  status: DocVersion["status"];
  created_at: string;
  has_changes: boolean;
  content: string;
  previous_content: string | null;
  warnings: string[];
  imports: string[];
  exports: string[];
}

function toFileDocVersion(doc: BackendFileDocument): FileDocVersion {
  return {
    id: doc.id,
    repoId: doc.repo_id,
    title: doc.title,
    content: doc.content,
    previousContent: doc.previous_content ?? undefined,
    hasChanges: doc.has_changes,
    status: doc.status,
    createdAt: doc.created_at,
    sourcePath: doc.source_path,
    warnings: doc.warnings ?? [],
    imports: doc.imports ?? [],
    exports: doc.exports ?? [],
  };
}

/**
 * POST /api/files/generate-doc
 * Body: { repository: string, path: string, force?: boolean }
 *
 * Proxies to the Python backend's get-or-generate single-file documentation
 * endpoint, mapping the snake_case response to the camelCase DocVersion
 * shape the existing doc-review components (DocPreview, DiffViewer,
 * ApprovalActions) already expect.
 */
export async function POST(req: NextRequest) {
  const { repository, path, force } = await req.json();

  if (!repository || !path) {
    return NextResponse.json({ error: "repository and path are required" }, { status: 400 });
  }

  try {
    const res = await fetch(`${BACKEND_URL}/api/files/generate-doc`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repository_name: repository,
        path,
        force: Boolean(force),
      }),
      cache: "no-store",
    });

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
        { error: data?.detail || "Failed to generate file documentation" },
        { status: res.status }
      );
    }

    return NextResponse.json(toFileDocVersion(data as BackendFileDocument));
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: `Backend unavailable: ${message}` },
      { status: 503 }
    );
  }
}
