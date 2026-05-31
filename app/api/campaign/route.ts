import { NextResponse } from "next/server";
import { demoCampaign, pipelineStages, rankedCandidates } from "@/lib/demo-data";
import { cloudSnapshot, launchWorker, type LaunchWorker } from "@/lib/cloud-control";
import { campaignRunSnapshot, startCampaignRun, type StartCampaignRunOptions } from "@/lib/campaign-orchestrator";
import { localDemoRunSnapshot, startLocalDemoRun } from "@/lib/local-demo-run";
import { startRun, type ModelWorker } from "@/lib/run-control";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request) {
  const scope = new URL(request.url).searchParams.get("scope");
  if (scope === "run") {
    return NextResponse.json({
      run: await localDemoRunSnapshot()
    });
  }

  return NextResponse.json({
    campaign: demoCampaign,
    stages: pipelineStages,
    rankedCandidates,
    run: await localDemoRunSnapshot(),
    campaignRuns: await campaignRunSnapshot(),
    cloud: await cloudSnapshot(),
    limitations: [
      "Computational research-support output only.",
      "Live cloud jobs are research artifacts and must not be interpreted as clinical validation.",
      "No clinical or therapeutic conclusion is implied."
    ]
  });
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    action?: string;
    worker?: LaunchWorker | "campaign-orchestrator" | ModelWorker;
    workers?: ModelWorker[];
  } & StartCampaignRunOptions;
  if (body.action === "start-local-run") {
    return NextResponse.json({
      action: body.action,
      run: await startLocalDemoRun()
    }, { status: 202 });
  }

  if (body.action === "start-campaign" || body.worker === "campaign-orchestrator") {
    const run = await startCampaignRun({
      maxRounds: body.maxRounds,
      candidatesPerRound: body.candidatesPerRound,
      gpuCount: body.gpuCount,
      includeTarget: body.includeTarget,
      generationManifest: body.generationManifest
    });
    return NextResponse.json({
      worker: "campaign-orchestrator",
      launchedAt: new Date().toISOString(),
      run
    }, { status: run.status === "failed" ? 500 : 202 });
  }

  if (Array.isArray(body.workers) || isModelWorker(body.worker)) {
    const run = await startRun(body);
    return NextResponse.json({ run }, { status: 202 });
  }

  const worker = body.worker || "rfantibody";
  if (!["rfantibody", "boltz2", "esmfold2", "rfantibody-fleet"].includes(worker)) {
    return NextResponse.json({ error: `Unsupported worker: ${worker}` }, { status: 400 });
  }

  const launch = await launchWorker(worker);
  return NextResponse.json({
    worker,
    launchedAt: new Date().toISOString(),
    launch
  }, { status: launch.ok ? 202 : 500 });
}

function isModelWorker(worker: unknown): worker is ModelWorker {
  return typeof worker === "string" && ["rfantibody", "esmfold2", "boltz2", "chai1", "immunebuilder", "thermompnn"].includes(worker);
}
