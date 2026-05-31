import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { demoCampaign, rankedCandidates } from "@/lib/demo-data";

type CampaignPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function CampaignPage({ params }: CampaignPageProps) {
  const { id } = await params;

  return (
    <main>
      <header className="site-header compact">
        <Link className="brand" href="/">
          <span className="brand-mark">G</span>
          <span>GPCRclaw</span>
        </Link>
        <Link className="back-link" href="/">
          <ArrowLeft size={17} aria-hidden="true" /> Back to overview
        </Link>
      </header>

      <section className="campaign-detail">
        <div className="detail-heading">
          <span className="label">Campaign ID</span>
          <h1>{id}</h1>
          <p>
            Campaign state for {demoCampaign.target}. This demo uses local RFantibody-interface
            candidate artifacts and a validation/retry loop so the full product flow is visible.
          </p>
        </div>

        <div className="summary-strip">
          <div>
            <span>Target</span>
            <strong>{demoCampaign.target}</strong>
          </div>
          <div>
            <span>Template</span>
            <strong>{demoCampaign.template}</strong>
          </div>
          <div>
            <span>Evidence</span>
            <strong>{demoCampaign.evidenceMode}</strong>
          </div>
          <div>
            <span>Status</span>
            <strong>report_ready</strong>
          </div>
        </div>

        <section className="candidate-section" aria-labelledby="candidate-heading">
          <div className="section-heading">
            <h2 id="candidate-heading">Ranked candidates</h2>
            <p>Local demo results backed by generated sequence, FASTA, binder PDB, and downstream manifest artifacts.</p>
          </div>
          <div className="candidate-table" role="table" aria-label="Ranked candidate table">
            <div className="candidate-row table-head" role="row">
              <span>Rank</span>
              <span>Candidate</span>
              <span>CDR3</span>
              <span>Interface</span>
              <span>Specificity</span>
              <span>Developability</span>
              <span>Score</span>
            </div>
            {rankedCandidates.map((candidate) => (
              <div className="candidate-row" role="row" key={candidate.id}>
                <span>{candidate.rank}</span>
                <strong>{candidate.id}</strong>
                <span>{candidate.cdr3Length} aa</span>
                <span>{candidate.interfaceScore.toFixed(3)}</span>
                <span>{candidate.specificityMargin.toFixed(3)}</span>
                <span>{candidate.developabilityScore.toFixed(3)}</span>
                <span>{candidate.rankScore.toFixed(4)}</span>
              </div>
            ))}
          </div>
        </section>

        <div className="report-note">
          <div>
            <h2>Report boundary</h2>
            <p>
              Computational research-support output only. Live model output must not be interpreted
              as clinical or therapeutic validation.
            </p>
          </div>
          <a className="button secondary" href="/api/campaign">
            API seed <ExternalLink size={16} aria-hidden="true" />
          </a>
        </div>
      </section>
    </main>
  );
}
