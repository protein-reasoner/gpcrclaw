# ThermoMPNN Worker Plan

ThermoMPNN is the next scoring worker after Boltz-2. Its job is stability triage: given a candidate protein structure and chain, run site-saturation mutagenesis and summarize mutation-risk metrics through the same GPCRclaw worker contract.

Primary upstream reference: https://github.com/Kuhlman-Lab/ThermoMPNN

The official inference path is `analysis/custom_inference.py` with:

```bash
python analysis/custom_inference.py \
  --pdb candidate.pdb \
  --chain H \
  --model_path models/thermoMPNN_default.pt \
  --out_dir output
```

The script writes `ThermoMPNN_inference_<pdb>.csv` with `ddG_pred`, `position`, `wildtype`, `mutation`, and chain metadata. Negative `ddG_pred` values are treated as stabilizing; positive values are treated as destabilizing.

## Worker Contract

Worker module:

```text
gpcrclaw.workers.thermompnn
```

Manifest fields:

- `worker_name`: `thermompnn`
- `evidence_mode`: `live`
- `candidate.structure_path` or `candidate.pdb_path`: wildtype/candidate PDB path visible inside the worker container.
- `candidate.chain_id` or `worker_options.chain_id`: chain to score.
- `candidate.mutations` or `worker_options.mutations`: optional point mutations to summarize from the full ThermoMPNN scan. Each mutation may be `A10V` or an object with `wildtype`, `position`, and `mutation`.
- `worker_options.script_path`: optional path to upstream `custom_inference.py`; defaults to `/opt/ThermoMPNN/analysis/custom_inference.py`.
- `worker_options.model_path`: optional checkpoint path; if omitted, upstream ThermoMPNN can discover a checkpoint under its repo.

Contract outputs:

```text
metrics.json
artifacts.json
logs.txt
work/thermompnn_input.json
thermompnn/ThermoMPNN_inference_*.csv
thermompnn_summary.json
```

Required metrics:

- `min_ddg_pred`
- `mean_ddg_pred`
- `max_ddg_pred`
- `stabilizing_fraction`
- `destabilizing_fraction`

Optional requested-mutation metrics:

- `requested_mutation_count`
- `requested_mutation_mean_ddg_pred`
- `requested_mutation_max_ddg_pred`

Default thresholds:

- Stabilizing: `ddG_pred <= -0.5`
- Destabilizing: `ddG_pred >= 1.0`

## Gates

1. Keep the worker in dry-run mode until the ThermoMPNN repository, checkpoint, and candidate PDB paths are present in the image.
2. Confirm upstream MIT license and citation requirements.
3. Build a dedicated ThermoMPNN image with the upstream conda/mamba environment and `THERMOMPNN_REPO=/opt/ThermoMPNN`.
4. Run one dry-run Batch job that only writes `dry_run.json`, `logs.txt`, and `work/thermompnn_input.json`.
5. Run one live A100 job against a small candidate PDB and parse the generated CSV into GPCRclaw metrics.
6. Compare report labels so ThermoMPNN metrics are presented as stability-risk estimates, not binding, expression, or activity predictions.
