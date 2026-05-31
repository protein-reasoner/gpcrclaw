import { NextResponse } from "next/server";
import { listRuns, startRun } from "@/lib/run-control";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const runs = await listRuns();
  return NextResponse.json({ runs });
}

export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const run = await startRun(body);
    return NextResponse.json({ run }, { status: 202 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Could not start run" }, { status: 400 });
  }
}
