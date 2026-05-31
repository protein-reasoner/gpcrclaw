# Real Model Execution Plan

The fake-worker path is now a proven execution harness, not the final model strategy. The real design path is RFantibody plus ESMFold2 on Google Batch A100 workers, with Boltz-2, Chai-1, ImmuneBuilder, and ThermoMPNN kept as downstream verifier/QC workers.

## Final Design Target

Primary cloud model workers:

```text
rfantibody-worker:
  upstream: RosettaCommons RFantibody/RFdiffusion
  role: structure-conditioned antibody or nanobody candidate generation
  image: us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/rfantibody-worker:latest

esmfold2-worker:
  upstream: Biohub ESMFold2
  role: fold generated candidates or target:candidate inputs and emit confidence metrics
  image: us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/esmfold2-worker:latest
```

Cloud submission entrypoints:

```bash
python3 scripts/run_rfantibody_batch.py --manifest examples/rfantibody/lpar1_generation_manifest.json --live
python3 scripts/run_esmfold2_batch.py --manifest examples/esmfold2/lpar1_nanobody_fold_manifest.json --live
```

Do not launch these blindly from docs. Build the images, set model/input paths, then submit through the scripts so assets are staged to Cloud Storage and job failures return nonzero.

## Current Proven Path

Validated cloud path:

```text
manifest.json in Cloud Storage
-> Google Batch GPU VM
-> Artifact Registry worker image
-> worker reads manifest
-> metrics/artifacts/logs written back to Cloud Storage
```

Verified jobs:

```text
L4 smoke: gpcrclaw-l4-smoke-20260531t002900 -> SUCCEEDED
A100 smoke: gpcrclaw-a100-smoke-20260531t003141 -> SUCCEEDED
A100 parallel 1: gpcrclaw-a100-parallel-1-20260531003434 -> SUCCEEDED
A100 parallel 2: gpcrclaw-a100-parallel-2-20260531003434 -> SUCCEEDED
```

Each successful job produced:

```text
artifacts.json
logs.txt
metrics.json
structures/LPAR1_NB_CLOUD_SMOKE_complex.pdb
```

## Primary Worker: RFantibody/RFdiffusion

RFantibody is the generation worker. It emits normalized candidate tables, FASTA files, optional structures, and downstream scoring manifests.

First live scope:

- Input: prepared receptor structure, epitope/hotspot constraints, framework/scaffold settings, and generation count.
- Output: generated candidates, FASTA files, optional extracted structures, and downstream verifier manifests.
- Metrics: `generation_rank`, `cdr3_length`, `sequence_length`, plus optional RFantibody score fields when present.
- GPU: standard A100 in `us-central1`.
- Batch shape: one generation wave per job, with `--gpu-count 1|2|4|8` available for valid A2 machine shapes.

The worker image is defined by `Dockerfile.rfantibody` and installs the RosettaCommons RFantibody repository. The Batch worker module is `gpcrclaw.workers.rfantibody`.

Build the image:

```bash
gcloud builds submit --config cloudbuild.rfantibody.yaml .
```

Submit a dry-run Batch job:

```bash
python3 scripts/run_rfantibody_batch.py --manifest examples/rfantibody/lpar1_generation_manifest.json
```

Submit live generation after `target.structure_path`, framework/scaffold inputs, and RFantibody commands/default paths are configured:

```bash
python3 scripts/run_rfantibody_batch.py \
  --manifest examples/rfantibody/lpar1_generation_manifest.json \
  --live
```

## Primary Worker: ESMFold2

ESMFold2 is the structure/confidence worker for generated candidates.

First live scope:

- Input: generated nanobody candidate sequence, optionally with target sequence for target:candidate folding.
- Output: ESMFold2 mmCIF structure, raw metrics JSON, logs, and contract metrics.
- Metrics: `mean_plddt`, `ptm`, `iptm`, `sequence_length`.
- GPU: standard A100 in `us-central1`.
- Batch shape: one candidate per job until runtime and output shape are known.

The worker image is defined by `Dockerfile.esmfold2` and installs Biohub's ESM package from GitHub. The Batch worker module is `gpcrclaw.workers.esmfold2`.

Build the image:

```bash
gcloud builds submit --config cloudbuild.esmfold2.yaml .
```

Submit a dry-run Batch job:

```bash
python3 scripts/run_esmfold2_batch.py --manifest examples/esmfold2/lpar1_nanobody_fold_manifest.json
```

Submit live folding:

```bash
python3 scripts/run_esmfold2_batch.py \
  --manifest examples/esmfold2/lpar1_nanobody_fold_manifest.json \
  --live
```

## Required Gates

Before enabling live design waves:

1. Confirm RFantibody and ESMFold2 license/citation requirements.
2. Build and publish `rfantibody-worker` and `esmfold2-worker`.
3. Set GitHub OIDC publisher variables and Artifact Registry writer access.
4. Stage target structures/frameworks through the Batch submit scripts.
5. Keep generated outputs under `gs://gpcrclaw-artifacts/campaigns/alankrit/...`.
6. Parse real metrics into candidate provenance through `metrics.json` and `artifacts.json`.
7. Compare RFantibody generation outputs with ESMFold2 confidence before sending candidates to Boltz/Chai verifier waves.

## Secondary Worker: ThermoMPNN

ThermoMPNN is a downstream stability-risk worker. It does not score binding or complex confidence. It scores structure-aware single point mutations from a candidate PDB and returns predicted stability-change summaries.

First live scope:

- Input: candidate protein PDB and chain ID, usually a modeled nanobody chain.
- Optional input: point mutations to pull out of the full site-saturation scan.
- Output: ThermoMPNN CSV scan, summary JSON, logs, and contract metrics.
- Metrics: `min_ddg_pred`, `mean_ddg_pred`, `max_ddg_pred`, `stabilizing_fraction`, `destabilizing_fraction`, plus requested-mutation summaries when provided.
- GPU: standard A100 in `us-central1` for the first live run, matching the existing real-model gate.
- Batch shape: one candidate structure per job until path conventions and CSV parsing are proven.

The worker module is `gpcrclaw.workers.thermompnn`. It shells out to upstream ThermoMPNN `analysis/custom_inference.py` and parses `ThermoMPNN_inference_*.csv` into the shared worker contract.

Dry-run the wrapper locally:

```bash
PYTHONPATH=src python3 -m gpcrclaw.workers.thermompnn \
  --manifest examples/thermompnn/lpar1_nanobody_stability_manifest.json \
  --dry-run
```

Live ThermoMPNN remains gated on a dedicated image with the upstream repo, checkpoint, and candidate PDB staged in paths visible to the worker.

## Secondary Worker: ImmuneBuilder / NanoBodyBuilder2

ImmuneBuilder is the standalone nanobody structure-QC worker. It does not score receptor binding or model the antigen complex. It predicts the candidate VHH structure and turns NanoBodyBuilder2 ensemble variation into residue-level and CDR-loop QC artifacts.

First live scope:

- Input: one nanobody candidate sequence with optional `cdr1`, `cdr2`, `cdr3`, or explicit `cdr_ranges`.
- Output: refined nanobody PDB, optional ranked unrefined PDBs, residue error-estimate JSON, CDR loop QC JSON, logs, and contract metrics.
- Metrics: `mean_residue_error`, `max_residue_error`, `cdr1_mean_error`, `cdr2_mean_error`, `cdr3_mean_error`, `cdr_loop_quality_score`.
- GPU: standard A100 in `us-central1` for the first Batch path, although NanoBodyBuilder2 is lightweight enough that the longer-term worker can move to CPU execution once CPU Batch plumbing exists.
- Batch shape: one candidate sequence per job until CDR annotation and residue-error provenance are proven.

The worker module is `gpcrclaw.workers.immunebuilder`. It uses the NanoBodyBuilder2 Python API by default and can fall back to the installed `NanoBodyBuilder2` CLI with `worker_options.execution_mode: "cli"`.

Dry-run the wrapper locally:

```bash
PYTHONPATH=src python3 -m gpcrclaw.workers.immunebuilder \
  --manifest examples/immunebuilder/lpar1_nanobody_qc_manifest.json \
  --dry-run
```

Submit an ImmuneBuilder Batch worker dry run:

```bash
python3 scripts/run_immunebuilder_batch.py \
  --manifest examples/immunebuilder/lpar1_nanobody_qc_manifest.json
```

Submit a live ImmuneBuilder run after accepting runtime dependencies, citations, and model-weight download behavior:

```bash
python3 scripts/run_immunebuilder_batch.py \
  --manifest examples/immunebuilder/lpar1_nanobody_qc_manifest.json \
  --live
```

## Chai-1 Secondary Verifier

Chai-1 is staged as an ensemble verifier for receptor:nanobody complexes, not as the primary generation path. The worker keeps the same manifest-to-artifacts contract as the other GPU workers:

```text
python -m gpcrclaw.workers.chai1 --manifest input/manifest.json
```

The upstream project is `chaidiscovery/chai-lab`. Its official entrypoint is `chai-lab fold input.fasta output_folder`, with Python API support through `chai_lab.chai1.run_inference`. As of the checked upstream docs, Chai-1 requires Linux, Python 3.10+, CUDA GPU hardware with bfloat16 support, and the code plus model weights are Apache-2.0 licensed for academic and commercial use.

Normalized outputs:

```text
work/chai1_input.fasta
chai1/pred.model_idx_*.cif
chai1/scores.model_idx_*.npz
chai1_summary.json
metrics.json
artifacts.json
logs.txt
```

Contract metrics are `aggregate_score`, `iptm`, `ptm`, and `complex_plddt`. `aggregate_score`, `iptm`, and `ptm` come from Chai score NPZ files. `complex_plddt` is the mean pLDDT written by Chai into CIF B-factors. Optional `has_inter_chain_clashes` is preserved when present.

Dry-run the wrapper locally:

```bash
PYTHONPATH=src python3 -m gpcrclaw.workers.chai1 \
  --manifest examples/chai1/lpar1_nanobody_verifier_manifest.json \
  --dry-run
```

Submit a Chai-1 Batch dry run:

```bash
python3 scripts/run_chai1_batch.py --manifest examples/chai1/lpar1_nanobody_verifier_manifest.json
```

Submit a live Chai-1 verifier only after accepting the MSA/template privacy behavior:

```bash
python3 scripts/run_chai1_batch.py \
  --manifest examples/chai1/lpar1_nanobody_verifier_manifest.json \
  --live \
  --use-msa-server \
  --use-templates-server
```

Without those server flags, the worker uses Chai-1's no-MSA/no-template path. That is better for private plumbing checks but should be labeled as a lower-confidence verifier run.

## RFantibody/RFdiffusion Output Contract

The RFantibody worker now has a real cloud image and preserves the manifest/output contract while normalizing generated candidate artifacts for later scoring waves.

Entrypoint:

```bash
python3 -m gpcrclaw.workers.rfantibody --manifest input/manifest.json
```

Normalized outputs:

```text
tables/generated_candidates.json
sequences/candidates.fasta
sequences/{candidate_id}.fasta
structures/{candidate_id}_binder.pdb
boltz2_manifests/{candidate_id}.json
metrics.json
artifacts.json
logs.txt
```

Each generated candidate records `candidate_id`, target, sequence, CDR fields, CDR3 length, source, target epitope, and paths to its FASTA, structure, and Boltz-2 manifest. Required generation metrics are `generation_rank`, `cdr3_length`, and `sequence_length`.

For plumbing checks, use the dry-run path:

```bash
python3 -m gpcrclaw.workers.rfantibody \
  --manifest examples/rfantibody/lpar1_generation_manifest.json \
  --dry-run
```

Dry-run candidates are labeled `rfantibody_interface_dry_run`; they are suitable for validating orchestration and downstream Boltz-2 manifest creation, not for scientific interpretation.
