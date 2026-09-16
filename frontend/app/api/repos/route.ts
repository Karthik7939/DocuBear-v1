import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { Repo } from "@/types";

export async function GET() {
  const repos = await db.listRepos();
  return NextResponse.json(repos);
}

export async function POST(req: NextRequest) {
  const { owner, name, gitbookSpaceId } = await req.json();

  const repo: Repo = {
    id: `${owner}_${name}`,
    owner,
    name,
    fullName: `${owner}/${name}`,
    connectedAt: new Date().toISOString(),
    webhookActive: false,
    gitbookSpaceId,
  };

  await db.addRepo(repo);
  return NextResponse.json(repo);
}
