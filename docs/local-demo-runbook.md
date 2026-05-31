# GPCRclaw Local Demo Runbook

## Demo Goal

Show one complete LPAR1 nanobody campaign flow without relying on cloud GPU availability:

```text
LPAR1 ECL2 target constraints
-> local RFantibody-interface candidate artifacts
-> validation failure
-> retry/regeneration
-> ranked top candidates
```

## Setup

```bash
npm run dev -- --port 3000
```

Open:

```text
http://localhost:3000
```

## Talk Track

1. GPCRclaw starts from a structure-conditioned design brief, not a sequence-only prompt.
2. This demo target is `LPAR1`, using template `7TD0`, focused on ECL2 residues `188-211`.
3. The campaign compiles target, hotspot, VHH, and CDR3 constraints into an inspectable job.
4. Click `Run local loop`.
5. The loop moves through generation, validation, a failed candidate, retry/regeneration, and final ranked candidates.
6. Open `Demo Campaign` to show the ranked candidate table with CDR3 length, `ipSAE`, `ipTM`, epitope-contact score, and final rank score.
7. State the boundary clearly: this is local artifact-backed demo evidence, not live experimental or clinical validation.

## Scoring

The local demo uses the same shape as the intended full scoring rule:

```text
interface_confidence = 0.60 * ipSAE + 0.40 * ipTM

rank_score =
  0.35 * interface_confidence
  + 0.25 * epitope_contact_score
  + 0.15 * pose_consistency_score
  + 0.15 * specificity_score
  + 0.10 * developability_score
```

`ipSAE` and `ipTM` are normalized to `0.0-1.0` in the demo table, where higher is better. The epitope-contact score represents how many intended LPAR1 ECL2 hotspots are contacted.

## Showable Artifacts

```text
.gpcrclaw/examples/rfantibody/output/tables/generated_candidates.json
.gpcrclaw/examples/rfantibody/output/sequences/candidates.fasta
.gpcrclaw/examples/rfantibody/output/structures/LPAR1_RFNB_001_binder.pdb
.gpcrclaw/examples/rfantibody/output/reports/ranked_designs.csv
.gpcrclaw/examples/rfantibody/output/reports/campaign_report.json
```

## Backup Line

The live cloud path is separate from this demo. The local path is intentionally used here so the product story remains reliable even when GPU capacity or worker image dependencies are still being fixed.
