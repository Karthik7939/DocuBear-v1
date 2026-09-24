import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.AGENT_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ slug: string }> }
) {
  const { slug } = await params;
  if (!slug) {
    return NextResponse.json({ hasMarkdown: false }, { status: 200 });
  }

  try {
    const res = await fetch(
      `${BACKEND_URL}/api/requirements/has-markdown/${encodeURIComponent(slug)}`,
      { cache: "no-store" }
    );

    if (!res.ok) {
      return NextResponse.json({ hasMarkdown: false }, { status: 200 });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ hasMarkdown: false }, { status: 200 });
  }
}
