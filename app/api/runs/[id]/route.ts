import { NextResponse } from "next/server";
import { refreshRunStatus } from "@/lib/run-control";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  try {
    const { id } = await context.params;
    const run = await refreshRunStatus(id);
    return NextResponse.json({ run });
  } catch (error) {
    return NextResponse.json({ error: "Run not found" }, { status: 404 });
  }
}
