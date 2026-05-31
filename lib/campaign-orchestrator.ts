import { execFile } from "node:child_process";
import crypto from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const ROOT = process.cwd();
const RUN_ROOT = path.join(ROOT, ".gpcrclaw", "campaign-orchestrator", "runs");
const DEFAULT_REGION = process.env.GPCRCLAW_REGION || "us-central1";
const TERMINAL_BATCH_STATES = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "DELETION_IN_PROGRESS"]);
const ACTIVE_RUN_STATUSES = new Set(["running", "waiting"]);

type CommandResult = {
  ok: boolean;
  stdout: string;
  stderr: string;
};

type WorkerLaunchResult = {
  ok: boolean;
  command: string;
  result: Record<string, unknown>;
};

type CampaignCandidate = {
  candidateId: string;
  sequence: string;
  cdr3?: string;
  source?: string;
  targetEpitope?: string;
  raw: Record<string, unknown>;
};

type ValidationScore = {
  status: "pass" | "fail" | "pending";
  score: number;
  metrics: Record<string, number>;
  reasons: string[];
};

type CampaignJob = {
  worker: "rfantibody" | "boltz2";
  jobName: string;
  region: string;
  command: string;
  launchedAt: string;
  inputUri?: string;
  outputUri?: string;
  configPath?: string;
  batchState?: string;
  batchUpdatedAt?: string;
  pollError?: string;
  outputs?: string[];
};

type ValidationJob = CampaignJob & {
  candidateId: string;
  candidate: CampaignCandidate;
  score?: ValidationScore;
};

type CampaignRound = {
  round: number;
  status: "generating" | "waiting_generation_outputs" | "validating" | "passed" | "failed";
  reason?: string;
  generationJob?: CampaignJob;
  candidates: CampaignCandidate[];
  validationJobs: ValidationJob[];
  passedCandidates: Array<CampaignCandidate & { score: ValidationScore }>;
};

export type CampaignRun = {
  runId: string;
  campaignId: string;
  status: "running" | "waiting" | "completed" | "failed";
  stage: "generation" | "validation" | "regeneration" | "complete" | "failed";
  createdAt: string;
  updatedAt: string;
  maxRounds: number;
  candidatesPerRound: number;
  gpuCount: number;
  includeTarget: boolean;
  live: boolean;
  generationManifest: string;
  thresholds: {
    minComplexPlddt: number;
    minPtm: number;
    minIptm: number;
  };
  rounds: CampaignRound[];
  finalCandidates: Array<CampaignCandidate & { score: ValidationScore }>;
  error?: string;
};

export type StartCampaignRunOptions = {
  maxRounds?: number;
  candidatesPerRound?: number;
  gpuCount?: number;
  includeTarget?: boolean;
  generationManifest?: string;
};

export async function startCampaignRun(options: StartCampaignRunOptions = {}) {
  const now = new Date().toISOString();
  const runId = `campaign-${timestampSlug()}-${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`;
  const run: CampaignRun = {
    runId,
    campaignId: runId.replace(/-/g, "_").toUpperCase(),
    status: "running",
    stage: "generation",
    createdAt: now,
    updatedAt: now,
    maxRounds: positiveInt(options.maxRounds, envInt("GPCRCLAW_CAMPAIGN_MAX_ROUNDS", 3)),
    candidatesPerRound: positiveInt(options.candidatesPerRound, envInt("GPCRCLAW_CAMPAIGN_CANDIDATES_PER_ROUND", 4)),
    gpuCount: positiveInt(options.gpuCount, envInt("GPCRCLAW_WEB_GPU_COUNT", 1)),
    includeTarget: Boolean(options.includeTarget),
    live: true,
    generationManifest: options.generationManifest || path.join(ROOT, "examples", "rfantibody", "lpar1_generation_manifest.json"),
    thresholds: {
      minComplexPlddt: envNumber("GPCRCLAW_CAMPAIGN_MIN_COMPLEX_PLDDT", 70),
      minPtm: envNumber("GPCRCLAW_CAMPAIGN_MIN_PTM", 0.5),
      minIptm: envNumber("GPCRCLAW_CAMPAIGN_MIN_IPTM", 0),
    },
    rounds: [],
    finalCandidates: [],
  };

  await saveRun(await submitNextGenerationRound(run, "initial_generation"));
  return run;
}

export async function campaignRunSnapshot() {
  const runs = await readRuns();
  const advanced = [];
  for (const run of runs) {
    advanced.push(ACTIVE_RUN_STATUSES.has(run.status) ? await advanceCampaignRun(run) : run);
  }
  return {
    root: RUN_ROOT,
    runs: advanced.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).slice(0, 20),
  };
}

export async function advanceCampaignRun(run: CampaignRun): Promise<CampaignRun> {
  if (!ACTIVE_RUN_STATUSES.has(run.status)) {
    return run;
  }
  const current = run.rounds.at(-1);
  if (!current) {
    return saveAndReturn(await submitNextGenerationRound(run, "resume_without_round"));
  }

  if (current.status === "generating" || current.status === "waiting_generation_outputs") {
    await pollJob(current.generationJob);
    if (current.generationJob?.batchState === "SUCCEEDED") {
      const generation = await readWorkerJson(current.generationJob.outputUri, "metrics.json");
      if (generation.ok && isRecord(generation.payload)) {
        current.candidates = candidatesFromGenerationMetrics(generation.payload);
        if (!current.candidates.length) {
          current.status = "failed";
          current.reason = "RFantibody completed without candidate records.";
          return saveAndReturn(await failOrRegenerate(run, "generation_empty"));
        }
        current.status = "validating";
        run.stage = "validation";
        current.validationJobs = await submitValidationJobs(run, current);
      } else {
        current.status = "waiting_generation_outputs";
        current.reason = generation.error || "Waiting for RFantibody metrics.json in GCS.";
        run.status = "waiting";
      }
    } else if (current.generationJob?.batchState && TERMINAL_BATCH_STATES.has(current.generationJob.batchState)) {
      current.status = "failed";
      current.reason = `RFantibody job ended in ${current.generationJob.batchState}.`;
      return saveAndReturn(await failOrRegenerate(run, "generation_failed"));
    }
    return saveAndReturn(touch(run));
  }

  if (current.status === "validating") {
    for (const job of current.validationJobs) {
      await pollJob(job);
      if (job.score || job.batchState !== "SUCCEEDED") {
        continue;
      }
      const validation = await readWorkerJson(job.outputUri, "metrics.json");
      if (validation.ok && isRecord(validation.payload)) {
        job.score = scoreValidationMetrics(validation.payload, run.thresholds);
      } else if (job.batchState && TERMINAL_BATCH_STATES.has(job.batchState)) {
        job.score = {
          status: "fail",
          score: 0,
          metrics: {},
          reasons: [validation.error || "Boltz-2 metrics.json missing after terminal job state."],
        };
      }
    }

    const passed = current.validationJobs
      .filter((job) => job.score?.status === "pass")
      .map((job) => ({ ...job.candidate, score: job.score as ValidationScore }))
      .sort((a, b) => b.score.score - a.score.score);
    current.passedCandidates = passed;

    if (passed.length) {
      current.status = "passed";
      run.status = "completed";
      run.stage = "complete";
      run.finalCandidates = passed;
      return saveAndReturn(touch(run));
    }

    const allTerminal = current.validationJobs.every((job) => job.score || (job.batchState && TERMINAL_BATCH_STATES.has(job.batchState)));
    if (allTerminal) {
      current.status = "failed";
      current.reason = "All Boltz-2 validation jobs completed without a passing candidate.";
      return saveAndReturn(await failOrRegenerate(run, "validation_failed"));
    }
    run.status = "running";
    return saveAndReturn(touch(run));
  }

  return saveAndReturn(touch(run));
}

async function submitNextGenerationRound(run: CampaignRun, reason: string): Promise<CampaignRun> {
  const roundNumber = run.rounds.length + 1;
  if (roundNumber > run.maxRounds) {
    run.status = "failed";
    run.stage = "failed";
    run.error = `No candidate passed validation after ${run.maxRounds} rounds.`;
    return touch(run);
  }

  const round: CampaignRound = {
    round: roundNumber,
    status: "generating",
    reason,
    candidates: [],
    validationJobs: [],
    passedCandidates: [],
  };
  run.rounds.push(round);
  run.status = "running";
  run.stage = roundNumber === 1 ? "generation" : "regeneration";

  const manifestPath = await writeGenerationManifest(run, roundNumber);
  const jobName = uniqueJobName("gpcrclaw-campaign-rfab", run.runId, `r${roundNumber}`);
  const launch = await runWorkerScript("python3", [
    "scripts/run_rfantibody_batch.py",
    "--manifest",
    manifestPath,
    "--job-name",
    jobName,
    "--live",
    "--gpu-count",
    String(run.gpuCount),
    "--no-wait",
  ]);
  if (!launch.ok) {
    round.status = "failed";
    round.reason = stringValue(launch.result.error) || "RFantibody launch failed.";
    run.status = "failed";
    run.stage = "failed";
    run.error = round.reason;
    return touch(run);
  }
  round.generationJob = jobFromLaunch("rfantibody", launch);
  return touch(run);
}

async function failOrRegenerate(run: CampaignRun, reason: string): Promise<CampaignRun> {
  if (run.rounds.length >= run.maxRounds) {
    run.status = "failed";
    run.stage = "failed";
    run.error = `Campaign stopped after ${run.maxRounds} rounds: ${reason}.`;
    return touch(run);
  }
  return submitNextGenerationRound(run, reason);
}

async function submitValidationJobs(run: CampaignRun, round: CampaignRound): Promise<ValidationJob[]> {
  const jobs: ValidationJob[] = [];
  for (const candidate of round.candidates) {
    const manifestPath = await writeBoltz2Manifest(run, round.round, candidate);
    const jobName = uniqueJobName("gpcrclaw-campaign-boltz", run.runId, `r${round.round}`, candidate.candidateId);
    const args = [
      "scripts/run_boltz2_batch.py",
      "--manifest",
      manifestPath,
      "--job-name",
      jobName,
      "--live",
      "--no-wait",
    ];
    const launch = await runWorkerScript("python3", args);
    const job = jobFromLaunch("boltz2", launch) as ValidationJob;
    job.candidateId = candidate.candidateId;
    job.candidate = candidate;
    if (!launch.ok) {
      const pollError = stringValue(launch.result.error) || "Boltz-2 launch failed.";
      job.batchState = "FAILED";
      job.pollError = pollError;
      job.score = { status: "fail", score: 0, metrics: {}, reasons: [pollError] };
    }
    jobs.push(job);
  }
  return jobs;
}

async function pollJob(job: CampaignJob | undefined): Promise<void> {
  if (!job?.jobName) {
    return;
  }
  const [batch, outputs] = await Promise.all([describeBatchJob(job.jobName, job.region), listOutputs(job.outputUri)]);
  if (batch.ok && isRecord(batch.payload)) {
    const status = isRecord(batch.payload.status) ? batch.payload.status : {};
    job.batchState = typeof status.state === "string" ? status.state : job.batchState;
    job.batchUpdatedAt = typeof batch.payload.updateTime === "string" ? batch.payload.updateTime : job.batchUpdatedAt;
    job.pollError = undefined;
  } else if (batch.error) {
    job.pollError = batch.error;
  }
  job.outputs = outputs;
}

async function writeGenerationManifest(run: CampaignRun, round: number): Promise<string> {
  const templatePath = path.isAbsolute(run.generationManifest) ? run.generationManifest : path.join(ROOT, run.generationManifest);
  const template = JSON.parse(await readFile(templatePath, "utf8")) as Record<string, unknown>;
  const workerOptions = isRecord(template.worker_options) ? { ...template.worker_options } : {};
  const rfantibody = isRecord(workerOptions.rfantibody) ? { ...workerOptions.rfantibody } : {};
  rfantibody.dry_run = false;
  rfantibody.num_candidates = run.candidatesPerRound;
  rfantibody.candidate_prefix = `${run.campaignId}_R${round}_RFNB`;
  workerOptions.rfantibody = rfantibody;
  template.campaign_id = `${run.campaignId}_ROUND_${round}`;
  template.batch_id = `batch_campaign_generation_round_${round}`;
  template.job_id = `job_campaign_generation_round_${round}`;
  template.evidence_mode = "live";
  template.seed = positiveInt(Number(template.seed), 1) + round - 1;
  template.worker_options = workerOptions;
  const outputPath = path.join(runDir(run.runId), `round-${round}`, "rfantibody-manifest.json");
  await writeJson(outputPath, template);
  return outputPath;
}

async function writeBoltz2Manifest(run: CampaignRun, round: number, candidate: CampaignCandidate): Promise<string> {
  const templatePath = path.join(ROOT, "examples", "boltz2", "lpar1_nanobody_manifest.json");
  const template = JSON.parse(await readFile(templatePath, "utf8")) as Record<string, unknown>;
  const workerOptions = isRecord(template.worker_options) ? { ...template.worker_options } : {};
  const boltz2 = isRecord(workerOptions.boltz2) ? { ...workerOptions.boltz2 } : {};
  boltz2.dry_run = false;
  boltz2.use_msa_server = false;
  boltz2.target_chain_id = stringValue(boltz2.target_chain_id) || "A";
  boltz2.candidate_chain_id = stringValue(boltz2.candidate_chain_id) || "B";
  workerOptions.boltz2 = boltz2;
  template.campaign_id = `${run.campaignId}_ROUND_${round}`;
  template.batch_id = `batch_campaign_boltz2_round_${round}`;
  template.job_id = `job_campaign_boltz2_${slugify(candidate.candidateId).slice(0, 34)}`;
  template.evidence_mode = "live";
  template.candidate = {
    candidate_id: candidate.candidateId,
    cdr3: candidate.cdr3 || "",
    sequence: candidate.sequence,
    source: candidate.source || "rfantibody",
    target_epitope: candidate.targetEpitope || "ECL2",
  };
  template.worker_options = workerOptions;
  const outputPath = path.join(runDir(run.runId), `round-${round}`, "boltz2", `${slugify(candidate.candidateId)}.json`);
  await writeJson(outputPath, template);
  return outputPath;
}

function candidatesFromGenerationMetrics(metrics: Record<string, unknown>): CampaignCandidate[] {
  const rawCandidates = Array.isArray(metrics.candidates) ? metrics.candidates : isRecord(metrics.candidate) ? [metrics.candidate] : [];
  return rawCandidates.flatMap((candidate) => {
    if (!isRecord(candidate)) {
      return [];
    }
    const candidateId = stringValue(candidate.candidate_id);
    const sequence = stringValue(candidate.sequence || candidate.binder_sequence || candidate.nanobody_sequence);
    if (!candidateId || !sequence) {
      return [];
    }
    return [
      {
        candidateId,
        sequence,
        cdr3: stringValue(candidate.cdr3),
        source: stringValue(candidate.source),
        targetEpitope: stringValue(candidate.target_epitope),
        raw: candidate,
      },
    ];
  });
}

function scoreValidationMetrics(metricsPayload: Record<string, unknown>, thresholds: CampaignRun["thresholds"]): ValidationScore {
  const metrics: Record<string, number> = {};
  if (Array.isArray(metricsPayload.metrics)) {
    for (const item of metricsPayload.metrics) {
      if (!isRecord(item)) {
        continue;
      }
      const name = stringValue(item.name);
      const value = numberValue(item.value);
      if (name && value !== undefined) {
        metrics[name] = value;
      }
    }
  }
  const complexPlddt = metrics.complex_plddt ?? metrics.mean_plddt;
  const ptm = metrics.ptm;
  const iptm = metrics.iptm ?? 0;
  const reasons = [];
  if (complexPlddt === undefined || complexPlddt < thresholds.minComplexPlddt) {
    reasons.push(`complex_plddt<${thresholds.minComplexPlddt}`);
  }
  if (ptm === undefined || ptm < thresholds.minPtm) {
    reasons.push(`ptm<${thresholds.minPtm}`);
  }
  if (iptm < thresholds.minIptm) {
    reasons.push(`iptm<${thresholds.minIptm}`);
  }
  const score = (Math.max(0, complexPlddt || 0) / 100) * 0.45 + Math.max(0, iptm) * 0.35 + Math.max(0, ptm || 0) * 0.2;
  return {
    status: reasons.length ? "fail" : "pass",
    score,
    metrics,
    reasons: reasons.length ? reasons : ["passes_boltz2_thresholds"],
  };
}

async function runWorkerScript(command: string, args: string[]): Promise<WorkerLaunchResult> {
  const result = await runCommand(command, args, 120_000);
  const parsed = parseJsonOrFallback(result);
  return {
    ok: result.ok,
    command: [command, ...args].join(" "),
    result: isRecord(parsed) ? parsed : { value: parsed },
  };
}

function jobFromLaunch(worker: "rfantibody" | "boltz2", launch: WorkerLaunchResult): CampaignJob {
  const result = launch.result;
  return {
    worker,
    jobName: stringValue(result.job_name) || `launch-failed-${crypto.randomUUID().slice(0, 8)}`,
    region: stringValue(result.region) || DEFAULT_REGION,
    command: launch.command,
    launchedAt: new Date().toISOString(),
    inputUri: stringValue(result.input_uri),
    outputUri: stringValue(result.output_uri),
    configPath: stringValue(result.config_path),
    pollError: launch.ok ? undefined : stringValue(result.error) || "Launch failed.",
  };
}

async function describeBatchJob(jobName: string, region: string): Promise<{ ok: boolean; payload?: unknown; error?: string }> {
  const result = await runCommand("gcloud", [
    "batch",
    "jobs",
    "describe",
    jobName,
    "--location",
    region,
    "--format=json(name,status.state,status.statusEvents,createTime,updateTime)",
  ]);
  const parsed = parseJsonOrFallback(result);
  return result.ok ? { ok: true, payload: parsed } : { ok: false, payload: parsed, error: errorFromParsed(parsed) };
}

async function listOutputs(outputUri: string | undefined): Promise<string[]> {
  if (!outputUri) {
    return [];
  }
  if (outputUri.startsWith("local://") || outputUri.startsWith("file://")) {
    return [];
  }
  const result = await runCommand("gcloud", ["storage", "ls", `${outputUri.replace(/\/$/, "")}/**`], 15_000);
  if (!result.ok) {
    return [];
  }
  return result.stdout
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

async function readWorkerJson(outputUri: string | undefined, fileName: string): Promise<{ ok: boolean; payload?: unknown; error?: string }> {
  if (!outputUri) {
    return { ok: false, error: "missing output URI" };
  }
  const base = outputUri.replace(/\/$/, "");
  if (base.startsWith("local://")) {
    const localPath = path.join(ROOT, base.slice("local://".length), fileName);
    return readLocalJson(localPath);
  }
  if (base.startsWith("file://")) {
    return readLocalJson(path.join(base.slice("file://".length), fileName));
  }
  const result = await runCommand("gcloud", ["storage", "cat", `${base}/${fileName}`], 15_000);
  if (!result.ok) {
    return { ok: false, error: result.stderr || `missing ${fileName}` };
  }
  try {
    return { ok: true, payload: JSON.parse(result.stdout) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : `invalid ${fileName}` };
  }
}

async function readLocalJson(localPath: string): Promise<{ ok: boolean; payload?: unknown; error?: string }> {
  try {
    return { ok: true, payload: JSON.parse(await readFile(localPath, "utf8")) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : `could not read ${localPath}` };
  }
}

async function readRuns(): Promise<CampaignRun[]> {
  if (!existsSync(RUN_ROOT)) {
    return [];
  }
  const entries = await readdir(RUN_ROOT, { withFileTypes: true }).catch(() => []);
  const runs = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const statePath = path.join(RUN_ROOT, entry.name, "state.json");
    try {
      const parsed = JSON.parse(await readFile(statePath, "utf8"));
      if (isCampaignRun(parsed)) {
        runs.push(parsed);
      }
    } catch {
      // Ignore incomplete local state files.
    }
  }
  return runs;
}

async function saveRun(run: CampaignRun): Promise<void> {
  await writeJson(path.join(runDir(run.runId), "state.json"), run);
}

async function saveAndReturn(run: CampaignRun): Promise<CampaignRun> {
  await saveRun(run);
  return run;
}

async function writeJson(filePath: string, payload: unknown): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

async function runCommand(command: string, args: string[], timeout = 20_000): Promise<CommandResult> {
  try {
    const { stdout, stderr } = await execFileAsync(command, args, {
      cwd: ROOT,
      timeout,
      env: process.env,
      maxBuffer: 1024 * 1024 * 8,
    });
    return { ok: true, stdout, stderr };
  } catch (error) {
    const err = error as { stdout?: string; stderr?: string; message?: string };
    return { ok: false, stdout: err.stdout || "", stderr: err.stderr || err.message || "" };
  }
}

function parseJsonOrFallback(result: CommandResult): unknown {
  const raw = result.stdout.trim();
  if (!raw) {
    return { ok: result.ok, error: result.stderr || "empty command output" };
  }
  try {
    return JSON.parse(raw);
  } catch {
    return { ok: result.ok, stdout: raw, stderr: result.stderr };
  }
}

function isCampaignRun(value: unknown): value is CampaignRun {
  return isRecord(value) && typeof value.runId === "string" && Array.isArray(value.rounds);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.length ? value : undefined;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function errorFromParsed(value: unknown): string | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  return stringValue(value.error) || stringValue(value.stderr) || stringValue(value.stdout);
}

function touch(run: CampaignRun): CampaignRun {
  run.updatedAt = new Date().toISOString();
  return run;
}

function runDir(runId: string) {
  return path.join(RUN_ROOT, runId);
}

function timestampSlug() {
  return new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14).toLowerCase();
}

function uniqueJobName(prefix: string, runId: string, ...parts: string[]) {
  const tail = crypto.randomUUID().replace(/-/g, "").slice(0, 6);
  const suffix = slugify([...parts, tail].join("-"));
  const base = slugify(`${prefix}-${runId}`);
  const maxBase = Math.max(10, 63 - suffix.length - 1);
  return `${base.slice(0, maxBase).replace(/-$/, "")}-${suffix}`.slice(0, 63);
}

function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function envInt(name: string, fallback: number) {
  return positiveInt(Number(process.env[name]), fallback);
}

function envNumber(name: string, fallback: number) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? value : fallback;
}

function positiveInt(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}
