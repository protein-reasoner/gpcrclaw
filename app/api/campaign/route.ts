import { NextResponse } from "next/server";
import { demoCampaign, pipelineStages, rankedCandidates } from "@/lib/demo-data";
import { cloudSnapshot, launchWorker, type LaunchWorker } from "@/lib/cloud-control";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({
    campaign: demoCampaign,
    stages: pipelineStages,
    rankedCandidates,
    cloud: await cloudSnapshot(),
    limitations: [
      "Computational research-support output only.",
      "Live cloud jobs are research artifacts and must not be interpreted as clinical validation.",
      "No clinical or therapeutic conclusion is implied."
    ]
  });
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as { worker?: LaunchWorker };
  const worker = body.worker || "rfantibody";
  if (!["rfantibody", "esmfold2", "rfantibody-fleet"].includes(worker)) {
    return NextResponse.json({ error: `Unsupported worker: ${worker}` }, { status: 400 });
  }

  const launch = await launchWorker(worker);
  return NextResponse.json({
    worker,
    launchedAt: new Date().toISOString(),
    launch
  }, { status: launch.ok ? 202 : 500 });
}
