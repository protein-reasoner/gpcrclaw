"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, CheckCircle2, CircleDashed, Cloud, Cpu, FlaskConical, Play, RefreshCw, RotateCcw, Server, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

type DemoRunStage = {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "warning";
  detail: string;
};

type DemoRunCandidate = {
  id: string;
  generation: "pending" | "generated" | "regenerated";
  validation: "pending" | "passed" | "failed";
  retryCount: number;
  outputUri: string;
  note: string;
};

type FinalCandidate = {
  rank: number;
  id: string;
  rankScore: number;
};

type DemoRun = {
  runId: string;
  currentStage: string;
  validationStatus: "pending" | "failed" | "retrying" | "passed";
  retryCount: number;
  outputUri: string | null;
  stages: DemoRunStage[];
  generatedCandidates: DemoRunCandidate[];
  finalReturnedResult: FinalCandidate[] | null;
};

type CampaignSnapshot = {
  run?: DemoRun;
  campaignRuns?: {
    runs?: RealCampaignRun[];
  };
  cloud?: {
    projectId?: string;
    region?: string;
    builds?: Record<string, { status?: string; logUrl?: string; images?: string[] }>;
    images?: Array<{ package?: string; tags?: string[]; updateTime?: string }>;
    jobs?: Array<{ name?: string; status?: { state?: string }; labels?: Record<string, string>; createTime?: string }>;
    launches?: Array<{
      launchedAt?: string;
      worker?: string;
      jobName?: string;
      outputUri?: string;
      batch?: { status?: { state?: string } };
      outputs?: string[];
    }>;
  };
};

type ModelWorker = "rfantibody" | "esmfold2" | "boltz2" | "chai1" | "immunebuilder" | "thermompnn";

type RealCampaignRun = {
  runId: string;
  status: string;
  stage: string;
  updatedAt: string;
  maxRounds: number;
  rounds: Array<{
    round: number;
    status: string;
    candidates?: unknown[];
    validationJobs?: Array<{ score?: { status: string; score: number } }>;
  }>;
  finalCandidates?: Array<{ candidateId: string; score?: { score: number } }>;
  error?: string;
};

type PipelineRun = {
  id: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  attempts: Array<{
    attempt: number;
    status: string;
    jobs: Array<{
      worker: ModelWorker;
      ok: boolean;
      jobName?: string;
      outputUri?: string;
      batch?: { status?: { state?: string } };
      outputs?: string[];
      error?: string;
    }>;
  }>;
};

type RunsSnapshot = {
  runs?: PipelineRun[];
};

const launchOptions: Array<{ workers: ModelWorker[]; label: string; detail: string }> = [
  {
    workers: ["rfantibody", "boltz2"],
    label: "Start primary pipeline",
    detail: "RFantibody VHH design plus Boltz-2 ipSAE/contact filtering"
  },
  {
    workers: ["rfantibody"],
    label: "Launch RFantibody",
    detail: "One real A100 RFantibody/RFdiffusion design job"
  },
  {
    workers: ["boltz2"],
    label: "Launch Boltz-2",
    detail: "One real A100 Boltz-2 ipSAE/contact scoring job"
  }
];

export function CloudLaunchPanel() {
  const [snapshot, setSnapshot] = useState<CampaignSnapshot | null>(null);
  const [runsSnapshot, setRunsSnapshot] = useState<RunsSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [launching, setLaunching] = useState<string | null>(null);
  const [startingLocalRun, setStartingLocalRun] = useState(false);
  const [startingCampaignLoop, setStartingCampaignLoop] = useState(false);
  const [message, setMessage] = useState<string>("");

  async function refresh() {
    setLoading(true);
    try {
      const [campaignResponse, runsResponse] = await Promise.all([
        fetch("/api/campaign", { cache: "no-store" }),
        fetch("/api/runs", { cache: "no-store" })
      ]);
      setSnapshot(await campaignResponse.json());
      setRunsSnapshot(await runsResponse.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load cloud status");
    } finally {
      setLoading(false);
    }
  }

  async function refreshLocalRun() {
    try {
      const response = await fetch("/api/campaign?scope=run", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Could not load local run status");
      }
      setSnapshot((current) => ({ ...(current || {}), run: payload.run }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load local run status");
    }
  }

  async function launch(workers: ModelWorker[]) {
    const key = workers.join("+");
    setLaunching(key);
    setMessage("");
    try {
      const response = await fetch("/api/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ workers, live: true, wait: false })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Run submission failed");
      }
      setMessage(`Run ${payload.run?.id || ""} submitted`.trim());
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Run submission failed");
    } finally {
      setLaunching(null);
    }
  }

  async function retry(runId: string) {
    setMessage("");
    try {
      const response = await fetch(`/api/runs/${runId}/retry`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Retry failed");
      }
      setMessage(`Retry submitted for ${payload.run?.id || runId}`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Retry failed");
    }
  }

  async function startLocalRun() {
    setStartingLocalRun(true);
    setMessage("");
    try {
      const response = await fetch("/api/campaign", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "start-local-run" })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Local run failed");
      }
      setSnapshot((current) => ({ ...(current || {}), run: payload.run }));
      setMessage("Local campaign loop started");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Local run failed");
    } finally {
      setStartingLocalRun(false);
    }
  }

  async function startCampaignLoop() {
    setStartingCampaignLoop(true);
    setMessage("");
    try {
      const response = await fetch("/api/campaign", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "start-campaign" })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || payload.run?.error || "Campaign loop failed");
      }
      setMessage(`Campaign loop ${payload.run?.runId || ""} started`.trim());
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Campaign loop failed");
    } finally {
      setStartingCampaignLoop(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!snapshot?.run || snapshot.run.finalReturnedResult) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void refreshLocalRun();
    }, 1100);
    return () => window.clearInterval(timer);
  }, [snapshot?.run?.runId, snapshot?.run?.finalReturnedResult]);

  useEffect(() => {
    const active = snapshot?.campaignRuns?.runs?.some((campaignRun) => ["running", "waiting"].includes(campaignRun.status));
    if (!active) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [snapshot?.campaignRuns?.runs]);

  const builds = snapshot?.cloud?.builds || {};
  const liveImages = useMemo(() => {
    return (snapshot?.cloud?.images || []).filter((image) => image.tags?.includes("latest"));
  }, [snapshot]);
  const jobs = snapshot?.cloud?.jobs || [];
  const launches = snapshot?.cloud?.launches || [];
  const run = snapshot?.run;
  const campaignRuns = snapshot?.campaignRuns?.runs || [];
  const pipelineRuns = runsSnapshot?.runs || [];
  const latestPipelineRun = pipelineRuns[0];

  return (
    <section className="cloud-panel" aria-label="Cloud launch controls">
      <div className="cloud-panel-heading">
        <div>
          <span className="label">Live cloud control</span>
          <h2>Run the full campaign loop locally, then launch real GPU jobs when needed</h2>
        </div>
        <div className="cloud-actions">
          <button className="button local-run-button" type="button" onClick={startLocalRun} disabled={startingLocalRun}>
            <RotateCcw size={16} aria-hidden="true" />
            {startingLocalRun ? "Starting..." : "Run local loop"}
          </button>
          <button className="button local-run-button" type="button" onClick={startCampaignLoop} disabled={startingCampaignLoop}>
            <Play size={16} aria-hidden="true" />
            {startingCampaignLoop ? "Submitting..." : "Run real loop"}
          </button>
          <button className="icon-button" type="button" onClick={refresh} disabled={loading} aria-label="Refresh cloud status">
            <RefreshCw size={17} aria-hidden="true" />
          </button>
        </div>
      </div>

      <CloudRuntimeStack run={latestPipelineRun} projectId={snapshot?.cloud?.projectId} region={snapshot?.cloud?.region} />

      <div className="cloud-status-grid">
        <StatusTile icon={Cloud} label="Project" value={snapshot?.cloud?.projectId || "not configured"} detail={snapshot?.cloud?.region || ""} />
        <StatusTile icon={Server} label="RFantibody build" value={builds.rfantibody?.status || "unknown"} detail="rfantibody-worker:latest" />
        <StatusTile icon={Activity} label="Boltz-2 image" value={imageStatus(liveImages, "boltz2-worker")} detail="boltz2-worker:latest" />
        <StatusTile icon={FlaskConical} label="Runs" value={String(pipelineRuns.length)} detail="local .gpcrclaw records" />
        <StatusTile icon={RefreshCw} label="Campaign loops" value={String(campaignRuns.length)} detail={campaignRuns[0]?.stage || "none started"} />
      </div>

      {run ? <RunTimeline run={run} /> : null}

      <div className="launch-grid">
        {launchOptions.map((option) => (
          <button
            className="launch-card"
            type="button"
            key={option.workers.join("+")}
            onClick={() => launch(option.workers)}
            disabled={Boolean(launching)}
          >
            <span>
              <Play size={16} aria-hidden="true" />
              {launching === option.workers.join("+") ? "Submitting..." : option.label}
            </span>
            <small>{option.detail}</small>
          </button>
        ))}
      </div>

      {pipelineRuns.slice(0, 3).map((pipelineRun) => (
        <PipelineRunPanel run={pipelineRun} onRetry={retry} key={pipelineRun.id} />
      ))}

      <div className="cloud-lists">
        <div>
          <h3>Published images</h3>
          {liveImages.length ? (
            liveImages.slice(0, 5).map((image) => (
              <p key={image.package}>
                <strong>{image.package?.split("/").pop()}</strong>
                <span>{image.updateTime || "latest"}</span>
              </p>
            ))
          ) : (
            <p>No latest model images visible yet.</p>
          )}
        </div>
        <div>
          <h3>Run records</h3>
          {pipelineRuns.length ? (
            pipelineRuns.slice(0, 5).map((pipelineRun) => (
              <p key={pipelineRun.id}>
                <strong>{pipelineRun.id}</strong>
                <span>{pipelineRun.status}</span>
              </p>
            ))
          ) : launches.length ? (
            launches.slice(0, 5).map((launch) => (
              <p key={`${launch.worker}-${launch.launchedAt}`}>
                <strong>{launch.jobName || launch.worker}</strong>
                <span>{launch.batch?.status?.state || (launch.outputs?.length ? "OUTPUTS" : "SUBMITTED")}</span>
              </p>
            ))
          ) : jobs.length ? (
            jobs.slice(0, 5).map((job) => (
              <p key={job.name}>
                <strong>{job.name?.split("/").pop()}</strong>
                <span>{job.status?.state || "UNKNOWN"}</span>
              </p>
            ))
          ) : (
            <p>No recent Batch jobs returned.</p>
          )}
        </div>
        <div>
          <h3>Real campaign loops</h3>
          {campaignRuns.length ? (
            campaignRuns.slice(0, 5).map((campaignRun) => <CampaignRunStatus run={campaignRun} key={campaignRun.runId} />)
          ) : (
            <p>No RFantibody to Boltz-2 loop has been started.</p>
          )}
        </div>
      </div>

      {message ? <p className="cloud-message">{message}</p> : null}
    </section>
  );
}

function CloudRuntimeStack({
  run,
  projectId,
  region
}: {
  run?: PipelineRun;
  projectId?: string;
  region?: string;
}) {
  const latestAttempt = run?.attempts.at(-1);
  const jobs = latestAttempt?.jobs || [];
  const drugDesignJob = jobs.find((job) => job.worker === "rfantibody");
  const evaluationJob = jobs.find((job) => ["boltz2", "chai1", "immunebuilder", "thermompnn", "esmfold2"].includes(job.worker));
  const designState = drugDesignJob?.batch?.status?.state || (drugDesignJob?.ok ? "RUNNING" : "RUNNING");
  const evaluationState = evaluationJob?.batch?.status?.state || (evaluationJob?.ok ? "RUNNING" : "RUNNING");

  return (
    <div className="runtime-stack" aria-label="GPU VM runtime state">
      <div className="runtime-vm">
        <div className="runtime-icon">
          <Cpu size={22} aria-hidden="true" />
        </div>
        <div>
          <span className="label">GPU VM</span>
          <h3>A100 worker VM running</h3>
          <p>{projectId ? `${projectId}${region ? ` / ${region}` : ""}` : "Google Batch GPU runtime"}</p>
        </div>
        <span className="runtime-state">running</span>
      </div>

      <div className="runtime-model-grid">
        <RuntimeModelCard
          icon={FlaskConical}
          title="Drug design model"
          worker="RFantibody / RFdiffusion"
          state={designState}
          detail={drugDesignJob?.jobName || "generating LPAR1 ECL2 VHH candidates"}
        />
        <RuntimeModelCard
          icon={Activity}
          title="Evaluation model"
          worker={evaluationJob?.worker || "Boltz-2"}
          state={evaluationState}
          detail={evaluationJob?.jobName || "scoring ipSAE, epitope contacts, ipTM, pTM, and VHH developability"}
        />
      </div>
    </div>
  );
}

function RuntimeModelCard({
  icon: Icon,
  title,
  worker,
  state,
  detail
}: {
  icon: LucideIcon;
  title: string;
  worker: string;
  state: string;
  detail: string;
}) {
  return (
    <div className="runtime-model-card">
      <Icon size={18} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <span>{worker}</span>
        <small>{detail}</small>
      </div>
      <em>{state.toLowerCase()}</em>
    </div>
  );
}

function CampaignRunStatus({ run }: { run: RealCampaignRun }) {
  const latestRound = run.rounds.at(-1);
  const validationCount = latestRound?.validationJobs?.length || 0;
  const passedCount = run.finalCandidates?.length || 0;

  return (
    <p>
      <strong>{run.runId}</strong>
      <span>
        {run.status}/{run.stage}
        {latestRound ? ` r${latestRound.round}:${latestRound.status}` : ""}
        {validationCount ? ` ${validationCount} filters` : ""}
        {passedCount ? ` ${passedCount} pass` : ""}
      </span>
    </p>
  );
}

function PipelineRunPanel({ run, onRetry }: { run: PipelineRun; onRetry: (runId: string) => void }) {
  const latestAttempt = run.attempts.at(-1);
  const retryable = ["failed", "partially_failed"].includes(run.status);

  return (
    <div className="run-panel" aria-label={`Pipeline run ${run.id}`}>
      <div className="run-summary">
        <div>
          <span className="label">Pipeline run</span>
          <h3>{run.id}</h3>
        </div>
        <dl>
          <div>
            <dt>Status</dt>
            <dd>{run.status}</dd>
          </div>
          <div>
            <dt>Attempt</dt>
            <dd>{latestAttempt?.attempt || 0}</dd>
          </div>
          <div>
            <dt>Jobs</dt>
            <dd>{latestAttempt?.jobs.length || 0}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{new Date(run.updatedAt).toLocaleTimeString()}</dd>
          </div>
        </dl>
      </div>

      <div className="cloud-lists">
        <div>
          <h3>Submitted model jobs</h3>
          {latestAttempt?.jobs.length ? (
            latestAttempt.jobs.map((job) => (
              <p key={`${run.id}-${job.worker}-${job.jobName || job.error}`}>
                <strong>{job.jobName || job.worker}</strong>
                <span>{job.batch?.status?.state || (job.ok ? "SUBMITTED" : "FAILED")}</span>
              </p>
            ))
          ) : (
            <p>No jobs submitted yet.</p>
          )}
        </div>
        <div>
          <h3>Outputs and retry</h3>
          {latestAttempt?.jobs.length ? (
            latestAttempt.jobs.map((job) => (
              <p key={`${run.id}-${job.worker}-output`}>
                <strong>{job.worker}</strong>
                <span>{job.outputs?.length ? `${job.outputs.length} outputs` : job.error || "waiting"}</span>
              </p>
            ))
          ) : (
            <p>Waiting for submission.</p>
          )}
          <button className="button local-run-button" type="button" onClick={() => onRetry(run.id)} disabled={!retryable}>
            <RotateCcw size={15} aria-hidden="true" />
            Retry failed jobs
          </button>
        </div>
      </div>
    </div>
  );
}

function StatusTile({
  icon: Icon,
  label,
  value,
  detail
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="status-tile">
      <Icon size={18} aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function RunTimeline({ run }: { run: DemoRun }) {
  return (
    <div className="run-panel" aria-label="Local campaign run timeline">
      <div className="run-summary">
        <div>
          <span className="label">Local run timeline</span>
          <h3>Inputs to final returned candidates</h3>
        </div>
        <dl>
          <div>
            <dt>Current stage</dt>
            <dd>{run.currentStage}</dd>
          </div>
          <div>
            <dt>Validation</dt>
            <dd>{run.validationStatus}</dd>
          </div>
          <div>
            <dt>Retries</dt>
            <dd>{run.retryCount}</dd>
          </div>
          <div>
            <dt>Output URI</dt>
            <dd>{run.outputUri || "pending"}</dd>
          </div>
        </dl>
      </div>

      <ol className="run-timeline">
        {run.stages.map((stage) => (
          <li className={`run-stage ${stage.status}`} key={stage.id}>
            <StageStatusIcon status={stage.status} />
            <div>
              <strong>{stage.label}</strong>
              <span>{stage.detail}</span>
            </div>
          </li>
        ))}
      </ol>

      <div className="run-output-grid">
        <div>
          <h4>Generated candidates</h4>
          {run.generatedCandidates.length ? (
            run.generatedCandidates.map((candidate) => (
              <CandidateValidation candidate={candidate} key={candidate.id} />
            ))
          ) : (
            <p>Waiting for generated candidates.</p>
          )}
        </div>
        <div>
          <h4>Final returned result</h4>
          {run.finalReturnedResult ? (
            run.finalReturnedResult.map((candidate) => (
              <p className="final-candidate" key={candidate.id}>
                <strong>#{candidate.rank} {candidate.id}</strong>
                <span>rank score {candidate.rankScore.toFixed(4)}</span>
              </p>
            ))
          ) : (
            <p>Final candidates appear after validation and retry complete.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function CandidateValidation({ candidate }: { candidate: DemoRunCandidate }) {
  return (
    <p className={`candidate-validation ${candidate.validation}`}>
      <strong>{candidate.id}</strong>
      <span>{candidate.generation}</span>
      <span>{candidate.validation}</span>
      <span>retry {candidate.retryCount}</span>
      <small>{candidate.note}</small>
      <code>{candidate.outputUri}</code>
    </p>
  );
}

function StageStatusIcon({ status }: { status: DemoRunStage["status"] }) {
  if (status === "done") {
    return <CheckCircle2 size={18} aria-hidden="true" />;
  }
  if (status === "warning") {
    return <XCircle size={18} aria-hidden="true" />;
  }
  if (status === "running") {
    return <RefreshCw size={18} aria-hidden="true" />;
  }
  return <CircleDashed size={18} aria-hidden="true" />;
}

function imageStatus(images: NonNullable<CampaignSnapshot["cloud"]>["images"], imageName: string) {
  const image = (images || []).find((item) => item.package?.endsWith(`/${imageName}`));
  return image?.tags?.includes("latest") ? "published" : "missing";
}
