import { execFile } from "node:child_process";
import crypto from "node:crypto";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const ROOT = process.cwd();
const PROJECT_ID = process.env.GPCRCLAW_PROJECT_ID || process.env.GOOGLE_CLOUD_PROJECT || "build-wgemini26sfo-2005";
const DEFAULT_REGION = process.env.GPCRCLAW_REGION || "us-central1";
const RFANTIBODY_BUILD_ID = process.env.GPCRCLAW_RFANTIBODY_BUILD_ID || "335a71f4-7680-41b1-ae50-7f8b3e87d178";
const ESMFOLD2_BUILD_ID = process.env.GPCRCLAW_ESMFOLD2_BUILD_ID || "384f8b72-53c3-4261-9f6f-95fd6087aae5";
const DEFAULT_REGIONS = process.env.GPCRCLAW_FLEET_REGIONS || "us-central1,us-east1,us-east4,us-west1";

type CommandResult = {
  ok: boolean;
  stdout: string;
  stderr: string;
};

export type LaunchWorker = "rfantibody" | "esmfold2" | "rfantibody-fleet";

export async function cloudSnapshot() {
  const [rfantibodyBuild, esmfold2Build, images, jobs] = await Promise.all([
    describeBuild(RFANTIBODY_BUILD_ID),
    describeBuild(ESMFOLD2_BUILD_ID),
    listImages(),
    listBatchJobs(DEFAULT_REGION)
  ]);

  return {
    projectId: PROJECT_ID,
    region: DEFAULT_REGION,
    builds: {
      rfantibody: rfantibodyBuild,
      esmfold2: esmfold2Build
    },
    images,
    jobs
  };
}

export async function launchWorker(worker: LaunchWorker) {
  if (worker === "rfantibody-fleet") {
    const wave = `web-${timestampSlug()}`;
    return runJson("python3", [
      "scripts/saturate_generation_gpus.py",
      "--manifest",
      "examples/rfantibody/lpar1_generation_manifest.json",
      "--live",
      "--regions",
      DEFAULT_REGIONS,
      "--standard-gpus",
      process.env.GPCRCLAW_WEB_STANDARD_GPUS || "16",
      "--spot-gpus",
      process.env.GPCRCLAW_WEB_SPOT_GPUS || "64",
      "--candidates-per-job",
      process.env.GPCRCLAW_WEB_CANDIDATES_PER_JOB || "64",
      "--wave-id",
      wave,
      "--run-id",
      wave,
      "--max-submit",
      process.env.GPCRCLAW_WEB_MAX_SUBMIT || "8"
    ]);
  }

  if (worker === "rfantibody") {
    return runJson("python3", [
      "scripts/run_rfantibody_batch.py",
      "--job-name",
      uniqueJobName("rfab"),
      "--live",
      "--gpu-count",
      process.env.GPCRCLAW_WEB_GPU_COUNT || "1",
      "--no-wait"
    ]);
  }

  return runJson("python3", [
    "scripts/run_esmfold2_batch.py",
    "--job-name",
    uniqueJobName("esm"),
    "--live",
    "--gpu-count",
    process.env.GPCRCLAW_WEB_GPU_COUNT || "1",
    "--no-wait"
  ]);
}

async function describeBuild(buildId: string) {
  const result = await runCommand("gcloud", [
    "builds",
    "describe",
    buildId,
    "--project",
    PROJECT_ID,
    "--format=json(id,status,logUrl,images,finishTime)"
  ]);
  return parseJsonOrFallback(result);
}

async function listImages() {
  const result = await runCommand("gcloud", [
    "artifacts",
    "docker",
    "images",
    "list",
    `us-central1-docker.pkg.dev/${PROJECT_ID}/gpcrclaw`,
    "--include-tags",
    "--format=json(package,tags,updateTime)"
  ]);
  const parsed = parseJsonOrFallback(result);
  return Array.isArray(parsed) ? parsed : [];
}

async function listBatchJobs(region: string) {
  const result = await runCommand("gcloud", [
    "batch",
    "jobs",
    "list",
    "--location",
    region,
    "--limit",
    "40",
    "--sort-by=~createTime",
    "--format=json(name,status.state,labels,createTime)"
  ]);
  const parsed = parseJsonOrFallback(result);
  return Array.isArray(parsed) ? parsed : [];
}

async function runJson(command: string, args: string[]) {
  const result = await runCommand(command, args, 120_000);
  const parsed = parseJsonOrFallback(result);
  return {
    ok: result.ok,
    command: [command, ...args].join(" "),
    result: parsed
  };
}

async function runCommand(command: string, args: string[], timeout = 20_000): Promise<CommandResult> {
  try {
    const { stdout, stderr } = await execFileAsync(command, args, {
      cwd: ROOT,
      timeout,
      env: process.env,
      maxBuffer: 1024 * 1024 * 6
    });
    return { ok: true, stdout, stderr };
  } catch (error) {
    const err = error as { stdout?: string; stderr?: string; message?: string };
    return { ok: false, stdout: err.stdout || "", stderr: err.stderr || err.message || "" };
  }
}

function parseJsonOrFallback(result: CommandResult) {
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

function timestampSlug() {
  return new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14).toLowerCase();
}

function uniqueJobName(prefix: string) {
  const entropy = crypto.randomUUID().replace(/-/g, "").slice(0, 8);
  return `gpcrclaw-${prefix}-web-${timestampSlug()}-${entropy}`.slice(0, 63);
}
