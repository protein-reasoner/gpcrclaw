import { execFile } from "node:child_process";
import crypto from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const ROOT = process.cwd();
const RUNS_ROOT = path.join(ROOT, ".gpcrclaw", "runs", "web");
const DEFAULT_REGION = process.env.GPCRCLAW_REGION || "us-central1";

const WORKER_SCRIPTS = {
  rfantibody: "scripts/run_rfantibody_batch.py",
  esmfold2: "scripts/run_esmfold2_batch.py",
  boltz2: "scripts/run_boltz2_batch.py",
  chai1: "scripts/run_chai1_batch.py",
  immunebuilder: "scripts/run_immunebuilder_batch.py",
  thermompnn: "scripts/run_thermompnn_batch.py"
} as const;

const DEFAULT_MANIFESTS: Record<ModelWorker, string> = {
  rfantibody: "examples/rfantibody/lpar1_generation_manifest.json",
  esmfold2: "examples/esmfold2/lpar1_nanobody_fold_manifest.json",
  boltz2: "examples/boltz2/lpar1_nanobody_manifest.json",
  chai1: "examples/chai1/lpar1_nanobody_verifier_manifest.json",
  immunebuilder: "examples/immunebuilder/lpar1_nanobody_qc_manifest.json",
  thermompnn: "examples/thermompnn/lpar1_nanobody_stability_manifest.json"
};

const TERMINAL_STATES = new Set(["SUCCEEDED", "FAILED", "DELETION_IN_PROGRESS", "CANCELLED"]);

export type ModelWorker = keyof typeof WORKER_SCRIPTS;
export type RunStatus = "queued" | "submitting" | "running" | "succeeded" | "failed" | "partially_failed";

export type PipelineRunInput = {
  worker?: ModelWorker;
  workers?: ModelWorker[];
  pipeline?: "primary" | "all";
  manifest?: string;
  manifests?: Partial<Record<ModelWorker, string>>;
  live?: boolean;
  wait?: boolean;
  gpuCount?: number;
  includeTarget?: boolean;
  useMsaServer?: boolean;
  useTemplatesServer?: boolean;
  thermompnnPdb?: string;
};

type CommandResult = {
  ok: boolean;
  stdout: string;
  stderr: string;
};

export type RunJob = {
  worker: ModelWorker;
  submittedAt: string;
  command: string;
  ok: boolean;
  jobName?: string;
  campaignId?: string;
  inputUri?: string;
  outputUri?: string;
  configPath?: string;
  region: string;
  result?: unknown;
  error?: string;
  batch?: unknown;
  outputs?: string[];
};

export type RunAttempt = {
  attempt: number;
  startedAt: string;
  completedAt?: string;
  status: RunStatus;
  workers: ModelWorker[];
  jobs: RunJob[];
  error?: string;
};

export type PipelineRunRecord = {
  id: string;
  createdAt: string;
  updatedAt: string;
  status: RunStatus;
  input: PipelineRunInput;
  attempts: RunAttempt[];
};

export async function startRun(input: unknown): Promise<PipelineRunRecord> {
  const normalized = normalizeInput(input);
  validateRunInput(normalized);
  const now = new Date().toISOString();
  let record: PipelineRunRecord = {
    id: `web-${timestampSlug()}-${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`,
    createdAt: now,
    updatedAt: now,
    status: "queued",
    input: normalized,
    attempts: []
  };

  await saveRun(record);
  record = await submitAttempt(record, workersForInput(normalized));
  return refreshRunStatus(record.id);
}

export async function listRuns(): Promise<PipelineRunRecord[]> {
  if (!existsSync(RUNS_ROOT)) {
    return [];
  }
  const entries = await readdir(RUNS_ROOT, { withFileTypes: true }).catch(() => []);
  const records = await Promise.all(
    entries
      .filter((entry) => entry.isDirectory())
      .map((entry) => loadRun(entry.name).catch(() => null))
  );
  return records
    .filter((record): record is PipelineRunRecord => record !== null)
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

export async function refreshRunStatus(id: string): Promise<PipelineRunRecord> {
  const record = await loadRun(id);
  let changed = false;
  const attempts = await Promise.all(
    record.attempts.map(async (attempt) => {
      const jobs = await Promise.all(
        attempt.jobs.map(async (job) => {
          const [batch, outputs] = await Promise.all([
            job.jobName ? describeBatchJob(job.jobName, job.region) : Promise.resolve(job.batch),
            job.outputUri ? listOutputs(job.outputUri) : Promise.resolve(job.outputs || [])
          ]);
          changed = true;
          return { ...job, batch, outputs };
        })
      );
      return { ...attempt, jobs, status: statusForJobs(jobs, attempt.status) };
    })
  );
  const next: PipelineRunRecord = {
    ...record,
    attempts,
    updatedAt: changed ? new Date().toISOString() : record.updatedAt,
    status: statusForAttempts(attempts)
  };
  if (changed) {
    await saveRun(next);
  }
  return next;
}

export async function retryStatus(id: string) {
  const record = await refreshRunStatus(id);
  const workers = retryableWorkers(record);
  return {
    runId: record.id,
    retryable: workers.length > 0,
    workers,
    status: record.status,
    attempts: record.attempts.length
  };
}

export async function retryRun(id: string, input: unknown): Promise<PipelineRunRecord> {
  const record = await refreshRunStatus(id);
  const body = isRecord(input) ? input : {};
  const requestedWorkers = Array.isArray(body.workers)
    ? body.workers.filter(isModelWorker)
    : isModelWorker(body.worker)
      ? [body.worker]
      : retryableWorkers(record);

  if (!requestedWorkers.length) {
    throw new Error("No retryable workers for this run.");
  }

  return submitAttempt(record, uniqueWorkers(requestedWorkers));
}

async function submitAttempt(record: PipelineRunRecord, workers: ModelWorker[]): Promise<PipelineRunRecord> {
  const attempt: RunAttempt = {
    attempt: record.attempts.length + 1,
    startedAt: new Date().toISOString(),
    status: "submitting",
    workers,
    jobs: []
  };
  let next: PipelineRunRecord = {
    ...record,
    status: "submitting",
    updatedAt: attempt.startedAt,
    attempts: [...record.attempts, attempt]
  };
  await saveRun(next);

  for (const worker of workers) {
    const job = await submitWorker(worker, record.input);
    attempt.jobs.push(job);
    attempt.status = statusForJobs(attempt.jobs, "submitting");
    next = {
      ...next,
      status: statusForAttempts(next.attempts),
      updatedAt: new Date().toISOString(),
      attempts: [...next.attempts.slice(0, -1), attempt]
    };
    await saveRun(next);
  }

  attempt.completedAt = new Date().toISOString();
  attempt.status = statusForJobs(attempt.jobs, "running");
  next = {
    ...next,
    status: statusForAttempts([...next.attempts.slice(0, -1), attempt]),
    updatedAt: attempt.completedAt,
    attempts: [...next.attempts.slice(0, -1), attempt]
  };
  await saveRun(next);
  return next;
}

async function submitWorker(worker: ModelWorker, input: PipelineRunInput): Promise<RunJob> {
  const args = argsForWorker(worker, input);
  const result = await runCommand("python3", args, 180_000);
  const parsed = parseJsonOrFallback(result);
  const parsedRecord = isRecord(parsed) ? parsed : {};
  return {
    worker,
    submittedAt: new Date().toISOString(),
    command: ["python3", ...args].join(" "),
    ok: result.ok,
    jobName: stringValue(parsedRecord.job_name),
    campaignId: stringValue(parsedRecord.campaign_id),
    inputUri: stringValue(parsedRecord.input_uri),
    outputUri: stringValue(parsedRecord.output_uri),
    configPath: stringValue(parsedRecord.config_path),
    region: DEFAULT_REGION,
    result: parsed,
    error: result.ok ? stringValue(parsedRecord.error) : result.stderr || "worker submission failed"
  };
}

function argsForWorker(worker: ModelWorker, input: PipelineRunInput): string[] {
  const manifest = input.manifest || input.manifests?.[worker] || DEFAULT_MANIFESTS[worker];
  const args = [
    WORKER_SCRIPTS[worker],
    "--manifest",
    safeRepoRelativePath(manifest),
    "--job-name",
    uniqueJobName(worker)
  ];
  if (input.live !== false) {
    args.push("--live");
  }
  if (input.wait) {
    args.push("--wait");
  } else {
    args.push("--no-wait");
  }
  if ((worker === "rfantibody" || worker === "esmfold2") && input.gpuCount) {
    args.push("--gpu-count", String(input.gpuCount));
  }
  if (worker === "esmfold2" && input.includeTarget) {
    args.push("--include-target");
  }
  if ((worker === "boltz2" || worker === "chai1") && input.useMsaServer) {
    args.push("--use-msa-server");
  }
  if (worker === "chai1" && input.useTemplatesServer) {
    args.push("--use-templates-server");
  }
  if (worker === "thermompnn" && input.thermompnnPdb) {
    args.push("--pdb", safeRepoRelativePath(input.thermompnnPdb));
  }
  return args;
}

async function loadRun(id: string): Promise<PipelineRunRecord> {
  if (!/^[a-zA-Z0-9_.-]+$/.test(id)) {
    throw new Error("Invalid run id.");
  }
  const raw = await readFile(path.join(RUNS_ROOT, id, "run.json"), "utf8");
  return JSON.parse(raw) as PipelineRunRecord;
}

async function saveRun(record: PipelineRunRecord): Promise<void> {
  const dir = path.join(RUNS_ROOT, record.id);
  await mkdir(dir, { recursive: true });
  await Promise.all([
    writeFile(path.join(dir, "run.json"), `${JSON.stringify(record, null, 2)}\n`, "utf8"),
    writeFile(path.join(dir, "input.json"), `${JSON.stringify(record.input, null, 2)}\n`, "utf8")
  ]);
}

async function describeBatchJob(jobName: string, region: string) {
  const result = await runCommand("gcloud", [
    "batch",
    "jobs",
    "describe",
    jobName,
    "--location",
    region,
    "--format=json(name,status.state,status.statusEvents,createTime,updateTime)"
  ]);
  return parseJsonOrFallback(result);
}

async function listOutputs(outputUri: string): Promise<string[]> {
  const result = await runCommand("gcloud", ["storage", "ls", `${outputUri}/**`], 15_000);
  return result.stdout
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

async function runCommand(command: string, args: string[], timeout = 20_000): Promise<CommandResult> {
  try {
    const { stdout, stderr } = await execFileAsync(command, args, {
      cwd: ROOT,
      timeout,
      env: process.env,
      maxBuffer: 1024 * 1024 * 8
    });
    return { ok: true, stdout, stderr };
  } catch (error) {
    const err = error as { stdout?: string; stderr?: string; message?: string };
    return { ok: false, stdout: err.stdout || "", stderr: err.stderr || err.message || "" };
  }
}

function normalizeInput(input: unknown): PipelineRunInput {
  const body = isRecord(input) ? input : {};
  const normalized: PipelineRunInput = {
    live: body.live === false ? false : true,
    wait: body.wait === true
  };
  if (body.worker !== undefined && !isModelWorker(body.worker)) {
    throw new Error(`Unsupported worker: ${String(body.worker)}`);
  }
  if (isModelWorker(body.worker)) {
    normalized.worker = body.worker;
  }
  if (Array.isArray(body.workers)) {
    const invalid = body.workers.find((worker) => !isModelWorker(worker));
    if (invalid !== undefined) {
      throw new Error(`Unsupported worker: ${String(invalid)}`);
    }
    if (!body.workers.length) {
      throw new Error("At least one worker is required.");
    }
    normalized.workers = uniqueWorkers(body.workers.filter(isModelWorker));
  }
  if (body.pipeline === "primary" || body.pipeline === "all") {
    normalized.pipeline = body.pipeline;
  }
  if (typeof body.manifest === "string") {
    normalized.manifest = body.manifest;
  }
  if (isRecord(body.manifests)) {
    normalized.manifests = {};
    for (const [key, value] of Object.entries(body.manifests)) {
      if (isModelWorker(key) && typeof value === "string") {
        normalized.manifests[key] = value;
      }
    }
  }
  if (typeof body.gpuCount === "number" && [1, 2, 4, 8].includes(body.gpuCount)) {
    normalized.gpuCount = body.gpuCount;
  }
  if (body.includeTarget === true) {
    normalized.includeTarget = true;
  }
  if (body.useMsaServer === true) {
    normalized.useMsaServer = true;
  }
  if (body.useTemplatesServer === true) {
    normalized.useTemplatesServer = true;
  }
  if (typeof body.thermompnnPdb === "string") {
    normalized.thermompnnPdb = body.thermompnnPdb;
  }
  return normalized;
}

function workersForInput(input: PipelineRunInput): ModelWorker[] {
  if (input.workers?.length) {
    return uniqueWorkers(input.workers);
  }
  if (input.worker) {
    return [input.worker];
  }
  if (input.pipeline === "all") {
    return ["rfantibody", "esmfold2", "boltz2", "chai1", "immunebuilder", "thermompnn"];
  }
  return ["rfantibody", "boltz2"];
}

function validateRunInput(input: PipelineRunInput): void {
  for (const worker of workersForInput(input)) {
    const manifest = input.manifest || input.manifests?.[worker] || DEFAULT_MANIFESTS[worker];
    safeRepoRelativePath(manifest);
  }
  if (input.thermompnnPdb) {
    safeRepoRelativePath(input.thermompnnPdb);
  }
}

function retryableWorkers(record: PipelineRunRecord): ModelWorker[] {
  const latestByWorker = new Map<ModelWorker, RunJob>();
  for (const attempt of record.attempts) {
    for (const job of attempt.jobs) {
      latestByWorker.set(job.worker, job);
    }
  }
  const failed = [...latestByWorker.values()]
    .filter((job) => !job.ok || batchState(job.batch) === "FAILED" || batchState(job.batch) === "CANCELLED")
    .map((job) => job.worker);
  return failed.length ? uniqueWorkers(failed) : record.status === "failed" ? workersForInput(record.input) : [];
}

function statusForAttempts(attempts: RunAttempt[]): RunStatus {
  if (!attempts.length) {
    return "queued";
  }
  const statuses = attempts.map((attempt) => attempt.status);
  if (statuses.includes("submitting")) {
    return "submitting";
  }
  if (statuses.includes("running")) {
    return "running";
  }
  if (statuses.includes("succeeded") && statuses.some((status) => status === "failed" || status === "partially_failed")) {
    return "partially_failed";
  }
  if (statuses.every((status) => status === "succeeded")) {
    return "succeeded";
  }
  if (statuses.includes("partially_failed")) {
    return "partially_failed";
  }
  return "failed";
}

function statusForJobs(jobs: RunJob[], fallback: RunStatus): RunStatus {
  if (!jobs.length) {
    return fallback;
  }
  const states = jobs.map((job) => batchState(job.batch));
  if (jobs.some((job) => !job.ok)) {
    return jobs.some((job) => job.ok) ? "partially_failed" : "failed";
  }
  if (states.some((state) => state && !TERMINAL_STATES.has(state))) {
    return "running";
  }
  if (states.some((state) => state === "FAILED" || state === "CANCELLED")) {
    return states.some((state) => state === "SUCCEEDED") ? "partially_failed" : "failed";
  }
  if (states.length && states.every((state) => state === "SUCCEEDED")) {
    return "succeeded";
  }
  return "running";
}

function batchState(batch: unknown): string | undefined {
  if (!isRecord(batch)) {
    return undefined;
  }
  const status = batch.status;
  if (isRecord(status) && typeof status.state === "string") {
    return status.state;
  }
  return typeof batch.state === "string" ? batch.state : undefined;
}

function parseJsonOrFallback(result: CommandResult): unknown {
  const raw = result.stdout.trim();
  if (!raw) {
    return {
      ok: result.ok,
      error: result.stderr || "empty command output"
    };
  }
  try {
    return JSON.parse(raw);
  } catch {
    return {
      ok: result.ok,
      stdout: raw,
      stderr: result.stderr
    };
  }
}

function safeRepoRelativePath(value: string): string {
  if (path.isAbsolute(value)) {
    throw new Error("Absolute paths are not accepted by the run API.");
  }
  const resolved = path.resolve(ROOT, value);
  if (!resolved.startsWith(`${ROOT}${path.sep}`)) {
    throw new Error("Path must stay inside the repository.");
  }
  return path.relative(ROOT, resolved);
}

function uniqueJobName(worker: ModelWorker): string {
  const entropy = crypto.randomUUID().replace(/-/g, "").slice(0, 8);
  return `gpcrclaw-${worker}-web-${timestampSlug()}-${entropy}`.slice(0, 63);
}

function timestampSlug(): string {
  return new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14).toLowerCase();
}

function uniqueWorkers(workers: ModelWorker[]): ModelWorker[] {
  return [...new Set(workers)];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isModelWorker(value: unknown): value is ModelWorker {
  return typeof value === "string" && value in WORKER_SCRIPTS;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}
