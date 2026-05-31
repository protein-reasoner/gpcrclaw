"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, Cloud, FlaskConical, Play, RefreshCw, Server } from "lucide-react";
import type { LucideIcon } from "lucide-react";

type CampaignSnapshot = {
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

type LaunchWorker = "rfantibody" | "esmfold2" | "rfantibody-fleet";

const launchOptions: Array<{ worker: LaunchWorker; label: string; detail: string }> = [
  {
    worker: "rfantibody",
    label: "Launch RFantibody",
    detail: "One real A100 RFantibody/RFdiffusion design job"
  },
  {
    worker: "esmfold2",
    label: "Launch ESMFold2",
    detail: "One real A100 ESMFold2 folding job"
  },
  {
    worker: "rfantibody-fleet",
    label: "Fill RFantibody fleet",
    detail: "Submit a bounded multi-region A100 generation wave"
  }
];

export function CloudLaunchPanel() {
  const [snapshot, setSnapshot] = useState<CampaignSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [launching, setLaunching] = useState<LaunchWorker | null>(null);
  const [message, setMessage] = useState<string>("");

  async function refresh() {
    setLoading(true);
    try {
      const response = await fetch("/api/campaign", { cache: "no-store" });
      setSnapshot(await response.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load cloud status");
    } finally {
      setLoading(false);
    }
  }

  async function launch(worker: LaunchWorker) {
    setLaunching(worker);
    setMessage("");
    try {
      const response = await fetch("/api/campaign", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ worker })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Launch failed");
      }
      setMessage(payload.launch?.ok ? `${worker} submitted` : `${worker} returned a launch error`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Launch failed");
    } finally {
      setLaunching(null);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const builds = snapshot?.cloud?.builds || {};
  const liveImages = useMemo(() => {
    return (snapshot?.cloud?.images || []).filter((image) => image.tags?.includes("latest"));
  }, [snapshot]);
  const jobs = snapshot?.cloud?.jobs || [];
  const launches = snapshot?.cloud?.launches || [];

  return (
    <section className="cloud-panel" aria-label="Cloud launch controls">
      <div className="cloud-panel-heading">
        <div>
          <span className="label">Live cloud control</span>
          <h2>Publish, launch, and watch the real GPU jobs</h2>
        </div>
        <button className="icon-button" type="button" onClick={refresh} disabled={loading} aria-label="Refresh cloud status">
          <RefreshCw size={17} aria-hidden="true" />
        </button>
      </div>

      <div className="cloud-status-grid">
        <StatusTile icon={Cloud} label="Project" value={snapshot?.cloud?.projectId || "loading"} detail={snapshot?.cloud?.region || ""} />
        <StatusTile icon={Server} label="RFantibody build" value={builds.rfantibody?.status || "unknown"} detail="rfantibody-worker:latest" />
        <StatusTile icon={Activity} label="ESMFold2 build" value={builds.esmfold2?.status || "unknown"} detail="esmfold2-worker:latest" />
        <StatusTile icon={FlaskConical} label="Launches" value={String(launches.length)} detail="website-submitted jobs" />
      </div>

      <div className="launch-grid">
        {launchOptions.map((option) => (
          <button className="launch-card" type="button" key={option.worker} onClick={() => launch(option.worker)} disabled={Boolean(launching)}>
            <span>
              <Play size={16} aria-hidden="true" />
              {launching === option.worker ? "Submitting..." : option.label}
            </span>
            <small>{option.detail}</small>
          </button>
        ))}
      </div>

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
          <h3>Website launches</h3>
          {launches.length ? (
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
      </div>

      {message ? <p className="cloud-message">{message}</p> : null}
    </section>
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
