import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { demoCampaign, rankedCandidates, scoreWeights } from "@/lib/demo-data";

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
            <p>
              Rank score = {scoreWeights.interfaceConfidence.toFixed(2)} interface confidence
              + {scoreWeights.epitopeContacts.toFixed(2)} epitope contacts
              + {scoreWeights.poseConsistency.toFixed(2)} pose consistency
              + {scoreWeights.specificity.toFixed(2)} specificity
              + {scoreWeights.developability.toFixed(2)} developability.
            </p>
          </div>
          <div className="candidate-table" role="table" aria-label="Ranked candidate table">
            <div className="candidate-row table-head" role="row">
              <span>Rank</span>
              <span>Candidate</span>
              <span>CDR3</span>
              <span>ipSAE</span>
              <span>ipTM</span>
              <span>Epi</span>
              <span>Score</span>
            </div>
            {rankedCandidates.map((candidate) => (
              <div className="candidate-row" role="row" key={candidate.id}>
                <span>{candidate.rank}</span>
                <strong>{candidate.id}</strong>
                <span>{candidate.cdr3Length} aa</span>
                <span>{candidate.ipSAE.toFixed(2)}</span>
                <span>{candidate.ipTM.toFixed(2)}</span>
                <span>{candidate.epitopeContactScore.toFixed(2)}</span>
                <span>{candidate.rankScore.toFixed(4)}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="scoring-section" aria-labelledby="scoring-heading">
          <div className="section-heading">
            <span className="label">Scoring model</span>
            <h2 id="scoring-heading">What the rank score means</h2>
            <p>
              The demo uses normalized model-style scores from 0.0 to 1.0, where higher is better.
              In the live workflow, <code>ipSAE</code> and <code>ipTM</code> come from complex-structure prediction
              outputs, then combine with epitope, consistency, specificity, and developability gates.
            </p>
          </div>

          <div className="scoring-grid" aria-label="Scoring terms">
            <article>
              <strong>ipSAE</strong>
              <p>Interface confidence derived from predicted aligned error around the binder-receptor interface. Higher means the interface is more confidently localized.</p>
            </article>
            <article>
              <strong>ipTM</strong>
              <p>Inter-chain TM-style confidence for the receptor:nanobody complex. Higher means the complex pose is more coherent.</p>
            </article>
            <article>
              <strong>Epitope contacts</strong>
              <p>How well the candidate contacts the intended LPAR1 ECL2 hotspot set instead of drifting to the wrong receptor face.</p>
            </article>
            <article>
              <strong>Pose consistency</strong>
              <p>Agreement across model seeds or verifier runs. A candidate should keep the same ECL2-centered pose.</p>
            </article>
            <article>
              <strong>Specificity</strong>
              <p>Margin against related GPCRs. Better candidates should score higher for LPAR1 than homolog counterscreens.</p>
            </article>
            <article>
              <strong>Developability</strong>
              <p>Sequence liability screen for VHH practicality: cysteines, glycosylation motifs, unstable motifs, solubility, and pI risk.</p>
            </article>
          </div>

          <div className="formula-panel">
            <div>
              <h3>Formula</h3>
              <pre>{`interface_confidence = 0.60 * ipSAE + 0.40 * ipTM

rank_score =
  0.35 * interface_confidence
  + 0.25 * epitope_contact_score
  + 0.15 * pose_consistency_score
  + 0.15 * specificity_score
  + 0.10 * developability_score`}</pre>
            </div>
            <div>
              <h3>Top candidate example</h3>
              <dl>
                <div>
                  <dt>Candidate</dt>
                  <dd>{rankedCandidates[0].id}</dd>
                </div>
                <div>
                  <dt>Interface confidence</dt>
                  <dd>{rankedCandidates[0].interfaceConfidence.toFixed(3)}</dd>
                </div>
                <div>
                  <dt>Epitope contacts</dt>
                  <dd>{rankedCandidates[0].epitopeContactScore.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>Pose consistency</dt>
                  <dd>{rankedCandidates[0].poseConsistencyScore.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>Specificity</dt>
                  <dd>{rankedCandidates[0].specificityScore.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>Developability</dt>
                  <dd>{rankedCandidates[0].developabilityScore.toFixed(3)}</dd>
                </div>
                <div>
                  <dt>Final rank score</dt>
                  <dd>{rankedCandidates[0].rankScore.toFixed(4)}</dd>
                </div>
              </dl>
            </div>
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
