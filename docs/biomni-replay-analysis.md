# Biomni Replay Analysis

Source reviewed: [Biomni shared replay](https://biomni.phylo.bio/replay/share_bdb5530d3bc94979aea75edb11e70681)

The shared replay is a completed Biomni session named `Nanobody CDR Design Expert`. It is not about LPAR1 or MRGPRX2 directly. It is a full in-silico nanobody campaign against inactive-state mu-opioid receptor, or MOR, and it contains useful detail about the kind of scientific workflow GPCRclaw should emulate.

The reusable lesson is the campaign machinery:

```text
target brief
-> structure/template selection
-> hotspot definition
-> target preparation
-> RFAntibody/RFdiffusion + ProteinMPNN generation
-> candidate triage
-> Boltz-2 complex scoring
-> ThermoMPNN stability scoring
-> ImmuneBuilder CDR loop QC
-> integrated ranking
-> report plus artifacts
```

The MOR-specific biology should not be copied directly into GPCRclaw's LPAR1/MRGPRX2 ECL2 scope.

## Conversation Spine

The user in the replay started as a drug discovery researcher focused on nanobody CDR sequence design and asked what Biomni could do for a nanobody design pipeline.

Biomni mapped the available toolchain:

- `RFAntibody`: primary de novo antibody/nanobody CDR design tool.
- `RFdiffusion`: backbone generation for CDR loop scaffolds.
- `ProteinMPNN`: fixed-backbone sequence design.
- `Boltz-2` and `Chai-1`: nanobody-antigen complex prediction.
- `ThermoMPNN`: mutation/stability scoring.
- `ImmuneBuilder` / `NanoBodyBuilder2`: nanobody structure and CDR-aware loop quality.
- `Foldseek`: structural similarity search.
- `ESMCFold2` / `AlphaFold v2`: sequence-to-structure prediction.

The user then specified a concrete campaign:

- Single-domain antibody / VHH / nanobody.
- Target: human mu-opioid receptor, gene `OPRM1`.
- Goal: extracellular antagonist nanobody for inactive MOR.
- Templates: `4DKL` and `8QOT`.
- CDR3 is important because it may need to occupy the orthosteric pocket.
- CDR3 length matters.
- Nanomolar potency is the aspiration, but the actual run remained computational.

The campaign moved from a broad plan to a concrete run, hit several compute/platform constraints, adapted the workflow, and produced final ranked candidates and artifacts.

## MOR Campaign Details

Final target setup:

```text
Campaign A: 4DKL inactive MOR, open orthosteric pocket after BF0 removal
Campaign B: 8QOT inactive MOR with NbE antagonist nanobody binding mode as reference
Binder: h-NbBCII10 humanized VHH framework
CDR3 length: 15-22 aa
Generation scale reached: 75 designs total
```

Important source-metadata caution:

- The replay text contains inconsistent structure resolution values.
- RCSB currently reports [`4DKL`](https://www.rcsb.org/structure/4DKL) at 2.80 Angstrom and [`8QOT`](https://www.rcsb.org/structure/8QOT) at 3.20 Angstrom.
- GPCRclaw should never hard-code structure metadata from a chat transcript without verifying it against RCSB/PDB metadata.

## Hotspot Specification

The MOR campaign used an explicit hotspot set rather than a vague "bind the receptor" objective.

User-specified MOR hotspots:

```text
TM3: D147, Y148, M151
TM5: K233, V234
TM6: W293, H297
TM7: I322, Y326
ECL2 lid: approximately 210-229
Numbering: human OPRM1 / UniProt P35372
```

The replay later contains a possible inconsistency where `V234` appears as `I234` in an assistant summary. Treat the user's `V234` instruction as the source until verified against the actual template chain.

Reusable principle for GPCRclaw:

- Require every campaign to compile an explicit hotspot set.
- Preserve residue numbering provenance.
- Track whether hotspots are user-specified, literature-derived, structure-derived, or demo-derived.
- Verify hotspots against each selected PDB chain before generation.

## Ligand Handling Lesson

The replay contains a useful correction.

At first, BF0, the small-molecule antagonist in `4DKL`, was retained as a pocket geometry reference. The user challenged this. Biomni then concluded BF0 should be removed because:

- Explicit hotspot residues already defined the epitope.
- BF0 physically occupies the deep pocket that CDR3 needs to enter.
- The nanobody is meant to replace or compete with the ligand, not co-bind with it.
- Keeping BF0 can push generative models to design around the ligand instead of into the intended pocket.

GPCRclaw implication:

- Do not keep bound ligands, peptides, G proteins, antibodies, or other partners by default.
- Strip non-target chains and ligands unless the design objective explicitly needs them.
- If a ligand is retained, the report must state why and how it affects design constraints.
- For LPAR1/MRGPRX2 ECL2 campaigns, native ligands should usually be metadata or visual context, not physical constraints in candidate generation.

## Actual Compute Pattern

The original plan attempted 100 designs per campaign through a full RFAntibody pipeline. That failed under an 8-hour HPC wall-time limit.

The adapted strategy:

```text
Generation:
  RFAntibody / RFdiffusion + ProteinMPNN
  15 designs per job
  batched by campaign

Scoring:
  Boltz-2 one complex per job
  ThermoMPNN in batches across all generated designs
  ImmuneBuilder only for top candidates
```

Observed platform constraints:

- 8-hour wall-time limit.
- 3 concurrent GPU job limit.
- Some jobs silently produced zero files.
- Some API submissions failed due payload size.
- Some submissions hit rate limits.
- Boltz-2 jobs needed `--use_msa_server` for protein sequence inputs.
- Long bundled jobs should be split into small restartable batches.

GPCRclaw implication:

- Model the campaign as resumable stages, not one monolithic run.
- Store batch IDs, job IDs, output file IDs, status, and error notes.
- Let partial campaigns still produce useful results.
- The UI should expose operational status, retries, skipped batches, and provenance.

## Final Scoring Stack

The replay's final ranking used these metrics:

```text
binding confidence: Boltz-2 ipTM
structural quality: Boltz-2 complex pLDDT
scaffold stability: ThermoMPNN mean ddG from SSM
CDR loop quality: ImmuneBuilder CDR3 error
sequence liabilities: motif-based penalty
```

Final composite formula from the report:

```text
composite =
  0.55 * ipTM
+ 0.15 * stability_norm
+ 0.15 * pLDDT_norm
+ 0.15 * IB_CDR3_norm

liability penalty:
  -0.02 per flag
```

Boltz-2 interpretation used in the report:

```text
ipTM > 0.8: high-confidence complex
0.5-0.8: moderate confidence
< 0.5: low confidence
```

GPCRclaw implication:

- Keep the existing simple MVP scoring formula for mock mode.
- Add a separate `structural_validation` scoring path for real or precomputed outputs.
- Candidate records should support both mock campaign scores and real tool-derived metrics.

## Final Top Candidates From The Replay

These are MOR-specific results. They should be used as examples of artifact shape, not as GPCRclaw candidates.

| Rank | Design | Campaign | CDR3 | ipTM | Boltz confidence | Note |
|---|---|---|---|---:|---:|---|
| 1 | `8qot_b1_9` | B_8QOT | `WAYSSYGEVLTEPSSYT` | 0.899 | 0.915 | Best CDR3 loop quality |
| 2 | `4dkl_b2_7` | A_4DKL | `WSTHSAGRDALDPSQYS` | 0.885 | 0.916 | DP motif at position 13 |
| 3 | `4dkl_b1_14` | A_4DKL | `IHESRFVLSKEYLLRPETYS` | 0.835 | 0.908 | Highest complex pLDDT |
| 4 | `8qot_b1_3` | B_8QOT | `LEYESPGFYSNLSLLDPSVYS` | 0.889 | 0.883 | Backup; lower pLDDT and higher CDR3 uncertainty |

Key final findings:

- The top 4 split evenly across the two structural campaigns.
- CDR3 length `17-20` looked strongest; the 15 aa candidate scored poorly.
- A `DP` motif was enriched in high-confidence candidates.
- All 75 designs had a narrow ThermoMPNN stability range, suggesting the framework was consistently stable.
- ImmuneBuilder CDR3 errors around `1.08-1.21` Angstrom were considered acceptable for de novo loops.

## Artifact Shape To Copy

The final replay produced:

- Markdown final report.
- Full ranking CSV for all 75 designs.
- Top-10 ranking CSV.
- Integrated scoring figure.
- Top-candidate profile figure.
- SSM heatmap.
- Design-space analysis figure.
- Prepared target PDBs.
- ImmuneBuilder PDBs for top candidates.

GPCRclaw should mirror this artifact model, even when using mock data:

```text
campaign_report.md
ranked_candidates.csv
candidate_metrics.json
target_preparation.json
pipeline_events.json
top_candidate_cards
structure artifacts or placeholders
```

## Data Fields GPCRclaw Should Add

The initial GPCRclaw candidate schema should be expanded to support Biomni-style evidence:

```typescript
type StructuralValidation = {
  generation_campaign?: string;
  generation_batch?: string;
  source_template?: string;
  job_ids?: string[];

  cdr3_aromatic_count?: number;
  cdr3_net_charge?: number;
  has_dp_motif?: boolean;
  dp_position?: number;

  boltz_iptm?: number;
  boltz_ptm?: number;
  boltz_confidence?: number;
  complex_plddt?: number;

  thermo_mean_ddg?: number;
  thermo_min_ddg?: number;
  thermo_stabilizing_mutations?: number;
  thermo_destabilizing_mutations?: number;

  immunebuilder_mean_error?: number;
  immunebuilder_cdr3_error?: number;
  immunebuilder_framework_error?: number;

  composite_score?: number;
};
```

Do not force every MVP candidate to have these fields. The schema should allow them as optional evidence when real or precomputed tool outputs exist.

## How This Changes GPCRclaw

The initial docs correctly describe a structured ECL2 campaign compiler. The replay adds a more concrete long-term pipeline:

1. `Mock mode`: use static candidates and deterministic scores for the hackathon UI.
2. `Precomputed mode`: load Biomni-like output CSV/JSON/PDB artifacts and render them as a completed campaign.
3. `Live mode`: submit real generation/scoring jobs in small batches and update the campaign as callbacks arrive.

For the current hackathon build, prioritize `mock mode` and `precomputed mode`. Live HPC orchestration is too much for a first GPCRclaw app unless the platform is already available.

## What Not To Copy Directly

Do not copy these MOR-specific assumptions into the LPAR1/MRGPRX2 app:

- Orthosteric pocket penetration as a default goal.
- CDR3 `DP` motif as a universal nanobody feature.
- MOR residue hotspots.
- MOR selectivity panel against KOR/DOR.
- The h-NbBCII10 framework as the only possible scaffold unless intentionally chosen.

For GPCRclaw's current brief, the default claim remains:

```text
ECL2-focused VHH candidate campaign for LPAR1 and MRGPRX2,
prioritizing extracellular ECL2 specificity and developability,
not clinical validation.
```
