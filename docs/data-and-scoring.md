# Data And Scoring

## Data Files

Recommended files:

```text
data/
  targets.json
  candidates/
    lpar1_candidates.json
    mrgprx2_candidates.json
  templates/
    lpar1_templates.json
    mrgprx2_templates.json
  mock_scores/
    lpar1_scores.json
    mrgprx2_scores.json
public/
  structures/
    7TD0.pdb
    7S8L.pdb
    predicted_complexes/
      LPAR1_NB_001_complex.pdb
      MRGPRX2_NB_001_complex.pdb
```

PDB files are optional for the MVP. If unavailable, keep structure links as placeholders and render a schematic structure view.

## Target Schema

```typescript
type TargetConfig = {
  target_id: "LPAR1" | "MRGPRX2";
  name: string;
  gene: string;
  uniprot_id: string;
  protein_class: string;
  length_aa: number;
  target_region: "ECL2";
  approx_ecl2_range: [number, number];
  primary_template: {
    pdb_id: string;
    state: "active" | "inactive";
    notes: string;
  };
  additional_templates: Array<{
    pdb_id: string;
    state: "active" | "inactive";
    notes?: string;
  }>;
  counter_screen_targets: Array<{
    gene: string;
    uniprot_id?: string;
  }>;
};
```

## Candidate Schema

```typescript
type NanobodyCandidate = {
  candidate_id: string;
  target: "LPAR1" | "MRGPRX2";
  sequence: string;
  cdr1: string;
  cdr2: string;
  cdr3: string;
  cdr3_length: number;
  source: "demo_generated" | "model_generated" | "precomputed";
  target_epitope: "ECL2";

  interface_score?: number;
  hotspot_contacts?: string[];
  clash_risk?: "low" | "medium" | "high";
  pose_confidence?: "low" | "medium" | "high";
  predicted_complex_file?: string;

  counter_scores?: Record<string, number>;
  specificity_margin?: number;
  specificity_status?: "pass" | "warning" | "fail";

  developability_status?: "pass" | "warning" | "fail";
  developability_flags?: {
    unpaired_cysteines: boolean;
    n_glycosylation_motif_in_cdr: boolean;
    deamidation_hotspot_in_cdr: boolean;
    isomerization_hotspot_in_cdr: boolean;
    met_trp_in_cdr: boolean;
    estimated_pI?: number;
    aggregation_risk?: "low" | "medium" | "high";
  };

  diversity_score?: number;
  final_score?: number;
  recommendation?: "advance_to_experimental_validation" | "hold_for_review" | "reject";
  why_selected?: string[];
  warnings?: string[];
};
```

## Candidate Dataset Shape

LPAR1 should have about 10 candidates:

- 3 strong pass candidates.
- 3 warning candidates.
- 2 cross-reactivity warning candidates.
- 2 developability fail candidates.

MRGPRX2 should have about 8 candidates:

- 2 strong pass candidates.
- 3 warning candidates.
- 2 fail candidates.
- 1 high-risk/high-reward candidate.

The data must not make every candidate pass. The demo needs visible filtering and tradeoffs.

## Specificity Score

Specificity score should be derived from the target score versus the strongest related-receptor score:

```typescript
const maxCounter = Math.max(...Object.values(candidate.counter_scores ?? { none: 0 }));
const specificityScore = Math.max(0, interfaceScore - maxCounter);
```

Suggested status:

```typescript
function specificityStatus(margin: number): "pass" | "warning" | "fail" {
  if (margin >= 0.25) return "pass";
  if (margin >= 0.08) return "warning";
  return "fail";
}
```

## Developability Checks

Apply regex checks primarily to concatenated CDRs:

```typescript
const cdrCombined = `${candidate.cdr1}${candidate.cdr2}${candidate.cdr3}`;

const nGlycoPattern = /N[^P][ST]/;
const deamidationPattern = /(NG|NS)/;
const isomerizationPattern = /(DG|DS)/;
const metTrpPattern = /[MW]/;
const cdrCysPattern = /C/;
```

Hydrophobicity/aggregation MVP:

```typescript
const hydrophobic = new Set(["A", "V", "I", "L", "M", "F", "W", "Y"]);
const hydrophobicFraction =
  candidate.cdr3.split("").filter((aa) => hydrophobic.has(aa)).length /
  Math.max(candidate.cdr3.length, 1);
```

Suggested aggregation risk:

```typescript
if (hydrophobicFraction > 0.55) return "high";
if (hydrophobicFraction > 0.45) return "medium";
return "low";
```

Developability score:

```text
pass = 1.00
warning = 0.65
fail = 0.20
```

## Ranking Function

Canonical MVP ranking:

```typescript
function rankCandidate(candidate: NanobodyCandidate, totalHotspots: number): NanobodyCandidate {
  const interfaceScore = candidate.interface_score ?? 0;

  const maxCounter = Math.max(...Object.values(candidate.counter_scores ?? { none: 0 }));
  const specificityScore = Math.max(0, interfaceScore - maxCounter);

  const developabilityScore =
    candidate.developability_status === "pass" ? 1 :
    candidate.developability_status === "warning" ? 0.65 :
    0.2;

  const hotspotCoverage =
    (candidate.hotspot_contacts?.length ?? 0) / Math.max(totalHotspots, 1);

  const diversityScore = candidate.diversity_score ?? 0.7;

  const finalScore =
    0.40 * interfaceScore +
    0.25 * specificityScore +
    0.20 * developabilityScore +
    0.10 * hotspotCoverage +
    0.05 * diversityScore;

  return {
    ...candidate,
    final_score: Number(finalScore.toFixed(3)),
    recommendation: finalScore > 0.75 && developabilityScore >= 0.65
      ? "advance_to_experimental_validation"
      : finalScore > 0.55
        ? "hold_for_review"
        : "reject"
  };
}
```

## Report Schema

```typescript
type CampaignReport = {
  campaign_summary: {
    campaign_id: string;
    target: "LPAR1" | "MRGPRX2";
    epitope: "ECL2";
    template: string;
    design_goal: string;
  };
  target_information: TargetConfig;
  template_selection: unknown;
  ecl2_hotspot_set: unknown;
  design_specification: unknown;
  top_candidates: NanobodyCandidate[];
  candidate_table: NanobodyCandidate[];
  specificity_review: unknown;
  developability_review: unknown;
  validation_plan: string[];
  limitations: string[];
};
```

Required report limitations:

- Computational prediction only.
- No wet-lab validation performed in the demo.
- Candidate structures and scores may be mocked or precomputed.
- Output is not a clinical or therapeutic claim.
