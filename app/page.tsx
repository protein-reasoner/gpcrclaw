import Link from "next/link";
import { Activity, ArrowRight, BookOpen, CheckCircle2, Cpu, Database, FileCheck, Layers3, Microscope, ShieldCheck, Target } from "lucide-react";
import { demoCampaign, pipelineStages } from "@/lib/demo-data";
import { CloudLaunchPanel } from "@/app/components/CloudLaunchPanel";

const scaleStats = [
  {
    icon: Database,
    value: "516",
    label: "approved drugs target GPCRs"
  },
  {
    icon: Activity,
    value: "36%",
    label: "of approved drugs act on GPCRs"
  },
  {
    icon: Target,
    value: "121",
    label: "GPCR targets have approved drugs"
  },
  {
    icon: BookOpen,
    value: "2025",
    label: "Nature Reviews Drug Discovery reference"
  }
];

const proofPoints = [
  {
    icon: Microscope,
    label: "Structure-native",
    text: "The campaign starts from receptor structure, loop context, and hotspot constraints rather than a text-only target brief."
  },
  {
    icon: Cpu,
    label: "GPU-native",
    text: "Design and evaluation jobs run as explicit model workers with artifact paths, model names, and retryable run state."
  },
  {
    icon: FileCheck,
    label: "Evidence-first",
    text: "Every returned candidate is framed as a research-support dossier: structures, metrics, provenance, and limitations."
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
          <h1>A third of approved drugs act through GPCRs. GPCRclaw makes nanobody campaigns inspectable.</h1>
          <p>
            GPCRs are one of medicine's largest target classes. GPCRclaw turns an ECL2-focused
            receptor brief into a GPU-run VHH design campaign with visible structures, model
            outputs, rankings, and research-use boundaries.
          </p>
          <ul className="hero-checks" aria-label="Product capabilities">
            <li><CheckCircle2 size={17} aria-hidden="true" /> Structure-native nanobody design</li>
            <li><CheckCircle2 size={17} aria-hidden="true" /> Cloud GPU model execution</li>
            <li><CheckCircle2 size={17} aria-hidden="true" /> Evidence-rich candidate dossiers</li>
          </ul>
          <div className="hero-actions">
            <Link className="button primary" href={{ pathname: "/viewer" }}>
              Open LPAR1 demo <ArrowRight size={18} aria-hidden="true" />
            </Link>
          </div>
        </div>

        <div className="hero-science" aria-label="GPCR scale and campaign preview">
          <div className="scale-mark">
            <strong>36%</strong>
            <span>of approved drugs target GPCRs</span>
          </div>
          <div className="receptor-visual hero-receptor" aria-hidden="true">
            <div className="membrane" />
            <div className="helix helix-one" />
            <div className="helix helix-two" />
            <div className="helix helix-three" />
            <div className="helix helix-four" />
            <div className="ecl-loop">ECL2</div>
            <div className="binder">VHH</div>
          </div>
          <div className="campaign-panel hero-campaign-panel" aria-label="Campaign summary">
            <div className="panel-header">
              <div>
                <span className="label">Active path</span>
                <h2>{demoCampaign.name}</h2>
              </div>
              <span className="status-pill live">cloud</span>
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
            <div className="mini-model-stack" aria-label="Model execution preview">
              <p><Cpu size={15} aria-hidden="true" /><strong>A100 GPU VM</strong><span>running</span></p>
              <p><Microscope size={15} aria-hidden="true" /><strong>RFantibody</strong><span>design</span></p>
              <p><Activity size={15} aria-hidden="true" /><strong>Boltz-2</strong><span>evaluate</span></p>
            </div>
          </div>
        </div>
      </section>

      <section className="scale-band" aria-label="Why GPCR campaigns matter">
        {scaleStats.map((stat) => {
          const Icon = stat.icon;
          return (
            <article className="scale-stat" key={stat.label}>
              <Icon size={24} aria-hidden="true" />
              <strong>{stat.value}</strong>
              <span>{stat.label}</span>
            </article>
          );
        })}
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
          <h2>Built for GPCR drug discovery teams</h2>
          <p>Nanobodies are useful because they can stabilize specific GPCR conformations. GPCRclaw makes that campaign logic visible from receptor context to ranked evidence.</p>
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
        <span>Scale claims: Nature Reviews Drug Discovery 2025; VHH role: Frontiers in Molecular Biosciences 2022.</span>
        <span>Research support only. No clinical or therapeutic conclusion is implied.</span>
      </footer>
    </main>
  );
}
