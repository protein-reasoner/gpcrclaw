# ImmuneBuilder / NanoBodyBuilder2 Worker

This worker runs NanoBodyBuilder2 through the existing GPCRclaw worker contract:

```text
manifest.json -> metrics.json + artifacts.json + logs.txt
```

## Scope

The worker predicts a standalone nanobody/VHH structure from one candidate sequence. It does not model the receptor-antigen complex and must not be interpreted as a binding score.

Primary outputs:

- Refined nanobody PDB from NanoBodyBuilder2.
- Optional ranked unrefined model PDBs when produced by `save_all`.
- Residue-level ensemble error estimates in JSON.
- CDR loop QC JSON with per-loop mean and max error estimates.
- Contract metrics for residue error, CDR1/CDR2/CDR3 error, and a bounded CDR loop quality score.

## Implementation Status

Dry-run mode and the wrapper/interface are implemented. Unit tests use fake predictor and fake CLI outputs, so they do not require the real external ImmuneBuilder package.

Live execution code paths are present for both the NanoBodyBuilder2 Python API and CLI fallback, but live NanoBodyBuilder2 execution has not been run or scientifically validated in this branch. Treat live mode as gated until the image is built, dependencies and weights are confirmed, and one real candidate run produces contract artifacts.

## Local Dry Run

```bash
PYTHONPATH=src python3 -m gpcrclaw.workers.immunebuilder \
  --manifest examples/immunebuilder/lpar1_nanobody_qc_manifest.json \
  --dry-run
```

The dry run writes:

```text
.gpcrclaw/immunebuilder-local/output/work/nanobody.fasta
.gpcrclaw/immunebuilder-local/output/work/immunebuilder_input.json
.gpcrclaw/immunebuilder-local/output/dry_run.json
.gpcrclaw/immunebuilder-local/output/logs.txt
```

## Live Local Run

Live local execution requires ImmuneBuilder plus its runtime dependencies:

```text
ImmuneBuilder
PyTorch
OpenMM
pdbfixer
ANARCI
```

Run with the Python API path:

```bash
PYTHONPATH=src python3 -m gpcrclaw.workers.immunebuilder \
  --manifest examples/immunebuilder/lpar1_nanobody_qc_manifest.json
```

Set `worker_options.dry_run` to `false` before live execution. The default execution mode is `api`, which uses `NanoBodyBuilder2().predict({"H": sequence})` and keeps residue error estimates directly from the prediction object.

Set `worker_options.execution_mode` to `cli` to execute the installed `NanoBodyBuilder2` command instead. CLI mode parses `error_estimates.npy` or PDB B-factors after prediction.

## Batch Run

Build the dedicated image:

```bash
gcloud builds submit --config cloudbuild.immunebuilder.yaml .
```

Submit a Batch dry run:

```bash
python3 scripts/run_immunebuilder_batch.py \
  --manifest examples/immunebuilder/lpar1_nanobody_qc_manifest.json
```

Submit a live Batch run after the image has been built and runtime licenses/citations are accepted:

```bash
python3 scripts/run_immunebuilder_batch.py \
  --manifest examples/immunebuilder/lpar1_nanobody_qc_manifest.json \
  --live
```

## Manifest Notes

Minimum candidate fields:

```json
{
  "candidate_id": "LPAR1_NB_001",
  "sequence": "EVQL..."
}
```

For reliable CDR loop QC, include either:

```json
{
  "cdr1": "GFTFSSYA",
  "cdr2": "AISGSGGSTYYADSVKG",
  "cdr3": "CARDRSTYW"
}
```

or explicit 1-based inclusive ranges:

```json
{
  "cdr_ranges": {
    "cdr1": [26, 33],
    "cdr2": [50, 66],
    "cdr3": [99, 107]
  }
}
```

If CDR ranges are missing, the worker may infer CDR3 from a terminal `C...WG` motif, but missing CDR1/CDR2 metrics are reported with whole-sequence means and warnings.

## Output Metrics

Required metrics registered in `MODEL_METRIC_SCHEMAS["immunebuilder"]`:

```text
mean_residue_error
max_residue_error
cdr1_mean_error
cdr2_mean_error
cdr3_mean_error
cdr_loop_quality_score
```

`mean_residue_error` and CDR metrics are in angstrom-like ensemble error-estimate units derived from NanoBodyBuilder2. `cdr_loop_quality_score` is `1 / (1 + mean CDR error)`, so higher is better and values remain bounded between 0 and 1.
