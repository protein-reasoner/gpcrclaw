import Link from "next/link";
import { Activity, ArrowRight, Layers3, ShieldCheck } from "lucide-react";
import { demoCampaign, pipelineStages } from "@/lib/demo-data";
import { CloudLaunchPanel } from "@/app/components/CloudLaunchPanel";

const proofPoints = [
  {
    icon: Layers3,
    label: "Campaign object",
    text: "Target, template, ECL2 range, hotspots, batches, jobs, candidates, metrics, and report state."
  },
  {
    icon: Activity,
    label: "Worker spine",
    text: "A file contract for manifests, model outputs, artifacts, logs, and provenance."
  },
  {
    icon: ShieldCheck,
    label: "Claim boundary",
    text: "Computational research-support output only, with mock and live evidence labeled separately."
  }
];

export default function Home() {
  return (
    <main>
      <header className="site-header">
        <Link className="brand" href="/" aria-label="GPCRclaw home">
          <span className="brand-mark">G</span>
          <span>GPCRclaw</span>
        </Link>
        <nav className="nav-links" aria-label="Primary">
          <a href="#workflow">Workflow</a>
          <a href="#stack">Stack</a>
          <Link href="/campaign/lpar1-demo">Demo Campaign</Link>
        </nav>
      </header>

      <section className="hero-section">
        <div className="hero-copy">
          <h1>GPCR nanobody campaigns, compiled into inspectable evidence.</h1>
          <p>
            A lightweight workbench skeleton for turning an ECL2-focused target brief into a ranked
            VHH candidate campaign with explicit artifacts, metrics, and limitations.
          </p>
          <div className="hero-actions">
            <Link className="button primary" href={{ pathname: "/viewer" }}>
              Open LPAR1 demo <ArrowRight size={18} aria-hidden="true" />
            </Link>
          </div>
        </div>

        <div className="campaign-panel" aria-label="Campaign summary">
          <div className="panel-header">
            <div>
              <span className="label">Active path</span>
              <h2>{demoCampaign.name}</h2>
            </div>
            <span className="status-pill live">cloud</span>
          </div>
          <div className="receptor-visual" aria-hidden="true">
            <div className="membrane" />
            <div className="helix helix-one" />
            <div className="helix helix-two" />
            <div className="helix helix-three" />
            <div className="ecl-loop">ECL2</div>
            <div className="binder">VHH</div>
          </div>
          <dl className="target-grid">
            <div>
              <dt>Target</dt>
              <dd>{demoCampaign.target}</dd>
            </div>
            <div>
              <dt>Template</dt>
              <dd>{demoCampaign.template}</dd>
            </div>
            <div>
              <dt>ECL2</dt>
              <dd>{demoCampaign.ecl2Range}</dd>
            </div>
            <div>
              <dt>Candidates</dt>
              <dd>{demoCampaign.candidateCount}</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="content-band">
        <CloudLaunchPanel />
      </section>

      <section className="content-band" id="workflow">
        <div className="section-heading">
          <h2>Live workflow</h2>
          <p>The live path now follows one GPU VM from launch through drug design and model-based evaluation.</p>
        </div>
        <div className="stage-list">
          {pipelineStages.map((stage, index) => (
            <article className="stage-row" key={stage.name}>
              <span className="stage-index">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3>{stage.name}</h3>
                <p>{stage.description}</p>
              </div>
              <span className="stage-state">{stage.state}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="content-band stack-band" id="stack">
        <div className="section-heading">
          <h2>Deployment stack</h2>
          <p>Small enough for a hackathon demo, aligned with Vercel, and ready to connect to the Python runtime later.</p>
        </div>
        <div className="proof-grid">
          {proofPoints.map((point) => {
            const Icon = point.icon;
            return (
              <article className="proof-card" key={point.label}>
                <Icon size={22} aria-hidden="true" />
                <h3>{point.label}</h3>
                <p>{point.text}</p>
              </article>
            );
          })}
        </div>
      </section>

      <footer className="site-footer">
        <span>Next.js App Router, TypeScript, plain CSS, Vercel config.</span>
        <span>Research support only. No clinical or therapeutic conclusion is implied.</span>
      </footer>
    </main>
  );
}
