# Agent Pipeline

## Pipeline Overview

The campaign runner should execute a fixed workflow and preserve each step as an inspectable artifact.

```text
1. Brief Parser
2. Target Template Selector
3. ECL2 Localizer
4. Hotspot Deriver
5. Design Spec Compiler
6. Candidate Generator or Loader
7. Interface Scorer
8. Specificity Counter-Screener
9. Developability Checker
10. Ranker
11. Campaign Report Generator
```

Each module can be deterministic for the MVP. The important part is that each returns structured JSON plus a human-readable explanation.

## Shared Stage Contract

Each pipeline stage should return:

```typescript
type PipelineStage<TOutput> = {
  stage_id: string;
  label: string;
  status: "pending" | "running" | "done" | "warning" | "failed";
  output: TOutput;
  explanation: string;
  warnings?: string[];
};
```

The frontend can use this shared shape to render pipeline status, JSON previews, and stage explanations.

## 1. Brief Parser Agent

Purpose: turn a target selection or natural-language design brief into a structured campaign seed.

Input:

```typescript
type BriefParserInput = {
  target_id?: "LPAR1" | "MRGPRX2";
  pasted_brief?: string;
};
```

Output:

```json
{
  "campaign_id": "LPAR1_ECL2_CAMPAIGN",
  "target": "LPAR1",
  "gene": "LPAR1",
  "uniprot_id": "Q92633",
  "epitope": "ECL2",
  "ecl2_range": [188, 211],
  "primary_template": "7TD0",
  "counter_screen_targets": ["LPAR2", "LPAR3", "LPAR4", "LPAR5", "LPAR6"],
  "design_constraints": {
    "binder_format": "VHH",
    "cdr3_length_range": [10, 18],
    "precision_over_recall": true
  }
}
```

MVP behavior:

- If `target_id` is present, read from static target config.
- If pasted briefs are added later, parse with rules or an LLM call.

## 2. Target Template Agent

Purpose: choose the structure template used by the campaign.

Output:

```json
{
  "selected_template": "7TD0",
  "state": "active",
  "rationale": "Active-state LPAR1 template with ECL2 geometry appropriate for extracellular binder design.",
  "structure_file_url": "/structures/7TD0.pdb"
}
```

MVP behavior:

- Use the configured primary template.
- Show additional templates as context.
- If a PDB file is unavailable, keep the metadata and mark the structure file as optional.

## 3. ECL2 Localization Agent

Purpose: map the campaign epitope to a residue range and visualization selection.

Output:

```json
{
  "target": "LPAR1",
  "template": "7TD0",
  "ecl2_residue_range": [188, 211],
  "visualization_selection": "resi 188-211",
  "method": "configured approximate ECL2 range"
}
```

MVP behavior:

- Use configured residue ranges.
- Render a 2D schematic or highlighted range if 3D residue selection is not ready.

## 4. Hotspot Derivation Agent

Purpose: identify the residues that candidate binders should contact.

Output:

```json
{
  "target": "LPAR1",
  "epitope": "ECL2",
  "method": "demo-derived surface-exposed ECL2 residue approximation",
  "hotspot_residues": [
    {"residue": "R190", "exposure": 0.82, "role": "surface exposed ECL2 contact"},
    {"residue": "Y194", "exposure": 0.77, "role": "hydrophobic/aromatic surface"},
    {"residue": "D198", "exposure": 0.69, "role": "polar/charged contact"},
    {"residue": "K201", "exposure": 0.74, "role": "charged surface contact"},
    {"residue": "F205", "exposure": 0.63, "role": "surface aromatic contact"}
  ],
  "rationale": "Selected exposed residues within the ECL2 range to constrain nanobody binding to the intended epitope."
}
```

MVP behavior:

- Load hotspots from static target config or score metadata.
- Label them clearly as demo-derived if not calculated.

## 5. Design Specification Agent

Purpose: compile target, epitope, hotspots, and binder constraints into a formal design job.

Output:

```json
{
  "design_job_id": "LPAR1_ECL2_DESIGN_001",
  "target": "LPAR1",
  "template": "7TD0",
  "binder_format": "VHH",
  "scaffold": "camelid_nanobody",
  "cdr3_length_range": [10, 18],
  "hotspot_residues": ["R190", "Y194", "D198", "K201", "F205"],
  "allowed_contact_regions": ["ECL2", "TM4 flank", "TM5 flank"],
  "forbidden_contact_regions": ["orthosteric pocket", "intracellular face"],
  "num_candidates_to_generate": 20,
  "ranking_objective": "maximize ECL2-specific binding while minimizing cross-reactivity and developability risks"
}
```

This should be a major UI artifact. It proves the system compiled the brief into a concrete scientific job.

## 6. Candidate Generation Agent

Purpose: create or load candidate VHH records.

MVP behavior:

- Load static JSON candidates.
- Use 10 candidates for LPAR1.
- Use 8 candidates for MRGPRX2.
- Include pass, warning, cross-reactivity, and fail cases.
- Label candidates as `demo_generated` or `precomputed`.

Candidate output shape:

```json
{
  "candidate_id": "LPAR1_NB_001",
  "target": "LPAR1",
  "sequence": "EVQL...",
  "cdr1": "GFTFSSYA",
  "cdr2": "AISGSGGSTYYADSVKG",
  "cdr3": "ARGTYWDSRGLFDY",
  "cdr3_length": 14,
  "source": "demo_generated",
  "target_epitope": "ECL2"
}
```

## 7. Interface Scoring Agent

Purpose: score plausible ECL2 interface quality.

MVP behavior:

- Use deterministic mock scores from static data.
- Include hotspot contacts and clash risk.
- Mark scores as `demo oracle score` or `precomputed`.

Output:

```json
{
  "candidate_id": "LPAR1_NB_001",
  "target": "LPAR1",
  "template": "7TD0",
  "interface_score": 0.86,
  "hotspot_contacts": ["R190", "Y194", "D198", "K201"],
  "num_hotspot_contacts": 4,
  "clash_risk": "low",
  "pose_confidence": "high",
  "predicted_complex_file": "/structures/predicted_complexes/LPAR1_NB_001_complex.pdb",
  "explanation": "Candidate is predicted to contact multiple ECL2 hotspot residues with low clash risk."
}
```

## 8. Specificity Counter-Screen Agent

Purpose: estimate whether the binder prefers the target over related GPCRs.

MVP behavior:

- Use counter-target scores from mock score data.
- Calculate specificity margin as `target_score - max(counter_scores)`.
- Return `pass`, `warning`, or `fail`.

Example warning:

```json
{
  "candidate_id": "LPAR1_NB_006",
  "target_score": 0.74,
  "counter_scores": {
    "LPAR2": 0.68,
    "LPAR3": 0.62,
    "LPAR4": 0.25,
    "LPAR5": 0.33,
    "LPAR6": 0.41
  },
  "specificity_margin": 0.06,
  "specificity_status": "warning",
  "explanation": "Candidate may cross-react with LPAR2 and LPAR3; not ideal for a precision ECL2 campaign."
}
```

## 9. Developability Agent

Purpose: run sequence liability checks.

MVP checks:

- CDR cysteines.
- N-linked glycosylation motif in CDRs.
- Deamidation motifs in CDRs.
- Isomerization motifs in CDRs.
- Met/Trp in CDRs.
- Approximate pI.
- Hydrophobicity/aggregation warning.

Output:

```json
{
  "candidate_id": "LPAR1_NB_001",
  "developability_status": "pass",
  "flags": {
    "unpaired_cysteines": false,
    "n_glycosylation_motif_in_cdr": false,
    "deamidation_hotspot_in_cdr": false,
    "isomerization_hotspot_in_cdr": false,
    "met_trp_in_cdr": true,
    "estimated_pI": 7.8,
    "aggregation_risk": "low"
  },
  "warnings": ["Contains W in CDR3; monitor oxidation risk."]
}
```

## 10. Ranking Agent

Purpose: combine candidate evidence into a final rank.

Ranking weights:

```text
final_score =
  0.40 * interface_score
+ 0.25 * specificity_score
+ 0.20 * developability_score
+ 0.10 * hotspot_coverage_score
+ 0.05 * diversity_score
```

Output:

```json
{
  "rank": 1,
  "candidate_id": "LPAR1_NB_001",
  "final_score": 0.84,
  "interface_score": 0.86,
  "specificity_score": 0.51,
  "developability_status": "pass",
  "hotspot_coverage": "4/5",
  "recommendation": "advance_to_experimental_validation",
  "why_selected": [
    "Strong predicted ECL2 interface",
    "Contacts 4 of 5 selected hotspot residues",
    "Low predicted cross-reactivity against LPAR2-LPAR6",
    "Passes developability filters"
  ]
}
```

## 11. Campaign Report Agent

Purpose: generate both frontend JSON and readable report content.

Report sections:

- Campaign summary.
- Target information.
- Template selection.
- ECL2 region.
- Hotspot derivation.
- Design specification.
- Candidate table.
- Top-ranked candidate cards.
- Specificity counter-screen results.
- Developability flags.
- High-level validation plan.
- Limitations.

The report should be the final proof object of the app.

## Optional Real-Tool Validation Track

The first GPCRclaw build can keep the pipeline deterministic. The Biomni replay suggests an eventual validation track:

```text
Candidate Loader
-> Boltz-2 Complex Scorer
-> ThermoMPNN Stability Scorer
-> ImmuneBuilder Loop QC
-> Integrated Ranker
```

This track should run after candidate generation and before final ranking when precomputed or live tool outputs exist.

Design constraints:

- The ranker must tolerate missing expensive metrics.
- Tool outputs should be attached as evidence, not hidden behind a single score.
- Every metric should keep provenance: tool, job ID, input template, and whether it was live, precomputed, or demo-derived.
- The report should list skipped or failed batches because operational failures are part of a real scientific campaign.
