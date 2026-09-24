import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file");
    const repository = formData.get("repository");

    if (!file || !repository) {
      return NextResponse.json(
        { error: "Both 'file' and 'repository' are required in form data." },
        { status: 400 }
      );
    }

    const backendFormData = new FormData();
    backendFormData.append("file", file);
    backendFormData.append("repository", repository);

    const res = await fetch(`${BACKEND_URL}/api/requirements/upload`, {
      method: "POST",
      body: backendFormData,
    });

    const contentType = res.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      const text = await res.text().catch(() => "");
      return NextResponse.json(
        { error: `Backend returned unexpected response (${res.status}): ${text.slice(0, 150)}` },
        { status: res.status >= 400 ? res.status : 502 }
      );
    }

    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(
        { error: data?.detail || "Requirements analysis failed." },
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
