import crypto from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { rankedCandidates } from "@/lib/demo-data";

const ROOT = process.cwd();
const RUN_STATE_PATH = path.join(ROOT, ".gpcrclaw", "web-demo-run.json");

type PersistedRun = {
  runId: string;
  startedAt: string;
};

export type DemoRunStageStatus = "pending" | "running" | "done" | "warning";

export type DemoRunStage = {
  id: "inputs" | "generation" | "validation" | "retry" | "final";
  label: string;
  status: DemoRunStageStatus;
  detail: string;
};

export type DemoRunCandidate = {
  id: string;
  generation: "pending" | "generated" | "regenerated";
  validation: "pending" | "passed" | "failed";
  retryCount: number;
  outputUri: string;
  note: string;
};

export type DemoRunResult = {
  runId: string;
  startedAt: string;
  updatedAt: string;
  currentStage: string;
  validationStatus: "pending" | "failed" | "retrying" | "passed";
  retryCount: number;
  outputUri: string | null;
  stages: DemoRunStage[];
  generatedCandidates: DemoRunCandidate[];
  finalReturnedResult: typeof rankedCandidates | null;
};

export async function startLocalDemoRun() {
  const run: PersistedRun = {
    runId: `local-${new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14)}-${crypto.randomUUID().slice(0, 6)}`,
    startedAt: new Date().toISOString()
  };
  await mkdir(path.dirname(RUN_STATE_PATH), { recursive: true });
  await writeFile(RUN_STATE_PATH, `${JSON.stringify(run, null, 2)}\n`, "utf8");
  return demoRunSnapshot(run);
}

export async function localDemoRunSnapshot() {
  if (!existsSync(RUN_STATE_PATH)) {
    return demoRunSnapshot({
      runId: "local-seeded-demo",
      startedAt: new Date(Date.now() - 8_000).toISOString()
    });
  }

  const body = await readFile(RUN_STATE_PATH, "utf8").catch(() => "");
  try {
    const parsed = JSON.parse(body) as Partial<PersistedRun>;
    if (typeof parsed.runId === "string" && typeof parsed.startedAt === "string") {
      return demoRunSnapshot(parsed as PersistedRun);
    }
  } catch {
    // Fall through to the seeded demo state.
  }

  return demoRunSnapshot({
    runId: "local-seeded-demo",
    startedAt: new Date(Date.now() - 8_000).toISOString()
  });
}

function demoRunSnapshot(run: PersistedRun): DemoRunResult {
  const elapsedMs = Math.max(0, Date.now() - Date.parse(run.startedAt));
  const generated = elapsedMs >= 1_200;
  const validated = elapsedMs >= 2_800;
  const retried = elapsedMs >= 4_400;
  const final = elapsedMs >= 6_200;
  const validationStatus = final ? "passed" : retried ? "retrying" : validated ? "failed" : "pending";
  const retryCount = retried ? 1 : 0;
  const rootUri = "local://.gpcrclaw/examples/rfantibody/output";

  return {
    runId: run.runId,
    startedAt: run.startedAt,
    updatedAt: new Date().toISOString(),
    currentStage: currentStage(elapsedMs),
    validationStatus,
    retryCount,
    outputUri: final ? `${rootUri}/reports/campaign_report.json` : null,
    stages: buildStages(elapsedMs),
    generatedCandidates: buildCandidates(rootUri, generated, validated, retried),
    finalReturnedResult: final ? rankedCandidates : null
  };
}

function currentStage(elapsedMs: number) {
  if (elapsedMs < 1_200) return "inputs";
  if (elapsedMs < 2_800) return "generation";
  if (elapsedMs < 4_400) return "validation failed";
  if (elapsedMs < 6_200) return "retry/regenerate";
  return "final candidates returned";
}

function buildStages(elapsedMs: number): DemoRunStage[] {
  return [
    {
      id: "inputs",
      label: "Inputs",
      status: elapsedMs < 1_200 ? "running" : "done",
      detail: "LPAR1 target, 7TD0 template, ECL2 residues, hotspot constraints"
    },
    {
      id: "generation",
      label: "Generation",
      status: stageStatus(elapsedMs, 1_200, 2_800),
      detail: "Generate VHH candidates against the compiled ECL2 design brief"
    },
    {
      id: "validation",
      label: "Validation",
      status: elapsedMs < 2_800 ? "pending" : elapsedMs < 4_400 ? "warning" : "done",
      detail: "Filter with Boltz-2 ipSAE, epitope contacts, ipTM, pTM, VHH sequence gates, and required artifacts"
    },
    {
      id: "retry",
      label: "Retry/regenerate",
      status: elapsedMs < 4_400 ? "pending" : elapsedMs < 6_200 ? "running" : "done",
      detail: "Regenerate the failed candidate and carry forward the retry count"
    },
    {
      id: "final",
      label: "Final returned candidates",
      status: elapsedMs < 6_200 ? "pending" : "done",
      detail: "Return ranked candidates with output URI and research boundary"
    }
  ];
}

function stageStatus(elapsedMs: number, startMs: number, doneMs: number): DemoRunStageStatus {
  if (elapsedMs < startMs) return "pending";
  if (elapsedMs < doneMs) return "running";
  return "done";
}

function buildCandidates(rootUri: string, generated: boolean, validated: boolean, retried: boolean): DemoRunCandidate[] {
  if (!generated) {
    return [];
  }

  const candidates: DemoRunCandidate[] = [
    {
      id: "LPAR1_RFNB_001",
      generation: "generated",
      validation: validated ? "passed" : "pending",
      retryCount: 0,
      outputUri: `${rootUri}/boltz2_manifests/LPAR1_RFNB_001.json`,
      note: "ECL2-targeted VHH demo candidate with local FASTA and binder PDB artifacts"
    },
    {
      id: "LPAR1_RFNB_004",
      generation: "generated",
      validation: validated ? "passed" : "pending",
      retryCount: 0,
      outputUri: `${rootUri}/boltz2_manifests/LPAR1_RFNB_004.json`,
      note: "passes specificity and developability gates in the local demo scorer"
    },
    {
      id: "LPAR1_RFNB_003",
      generation: "generated",
      validation: validated ? "failed" : "pending",
      retryCount: 0,
      outputUri: `${rootUri}/boltz2_manifests/LPAR1_RFNB_003.json`,
      note: "failed the first validation pass and triggers a replacement candidate"
    }
  ];

  if (retried) {
    candidates.push({
      id: "LPAR1_RFNB_002",
      generation: "regenerated",
      validation: "passed",
      retryCount: 1,
      outputUri: `${rootUri}/boltz2_manifests/LPAR1_RFNB_002.json`,
      note: "replacement candidate from retry wave"
    });
  }

  return candidates;
}
