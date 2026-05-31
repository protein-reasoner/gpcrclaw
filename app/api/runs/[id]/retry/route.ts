import { NextResponse } from "next/server";
import { retryRun, retryStatus } from "@/lib/run-control";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  try {
    const { id } = await context.params;
    return NextResponse.json(await retryStatus(id));
  } catch (error) {
    return NextResponse.json({ error: "Run not found" }, { status: 404 });
  }
}

export async function POST(request: Request, context: RouteContext) {
  try {
    const { id } = await context.params;
    const body = await request.json().catch(() => ({}));
    const run = await retryRun(id, body);
    return NextResponse.json({ run }, { status: 202 });
  } catch (error) {
    if (error instanceof Error && error.message.includes("ENOENT")) {
      return NextResponse.json({ error: "Run not found" }, { status: 404 });
    }
    return NextResponse.json({ error: error instanceof Error ? error.message : "Could not retry run" }, { status: 400 });
  }
}
