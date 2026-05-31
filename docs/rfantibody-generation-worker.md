# RFAntibody/RFdiffusion Generation Worker

The RFAntibody worker is the generation-side interface behind the same GPCRclaw worker contract used by fake-worker and Boltz-2:

```text
input/manifest.json
-> gpcrclaw.workers.rfantibody
-> output/metrics.json
-> output/artifacts.json
-> output/logs.txt
```

The worker does not change campaign orchestration or backend submission. A Google Batch request can use `worker_name: "rfantibody"`; the existing backend fallback resolves that to:

```text
python -m gpcrclaw.workers.rfantibody --manifest /mnt/disks/input/manifest.json
```

## Manifest Inputs

Required standard fields stay unchanged: `campaign_id`, `batch_id`, `job_id`, `worker_name`, `worker_version`, `evidence_mode`, `target`, `candidate`, `output_uri`, and `resources`.

Generation-specific options live under `worker_options.rfantibody`:

```json
{
  "num_candidates": 20,
  "candidate_prefix": "LPAR1_RFNB",
  "cdr3_length_range": [10, 18],
  "target_chain_id": "A",
  "binder_chain_id": "B",
  "hotspot_residues": ["R190", "Y194", "D198", "K201", "F205"],
  "commands": [["rfantibody-generate", "--out", "output/rfantibody_raw"]],
  "boltz2_options": {
    "target_chain_id": "A",
    "candidate_chain_id": "B",
    "use_msa_server": false
  }
}
```

For interface and plumbing checks, set `dry_run: true` or pass `--dry-run`. This emits deterministic, clearly labeled interface candidates without running RFAntibody/RFdiffusion.

## Outputs For Boltz-2

The worker normalizes generation output into files that the next Boltz-2 scoring wave can consume:

```text
output/
  metrics.json
  artifacts.json
  logs.txt
  work/
    constraints.json
    design_spec.json
  tables/
    generated_candidates.json
  sequences/
    candidates.fasta
    {candidate_id}.fasta
  structures/
    {candidate_id}_binder.pdb
  boltz2_manifests/
    {candidate_id}.json
```

Each `boltz2_manifests/{candidate_id}.json` is a standard Boltz-2 worker manifest with the generated sequence, CDR fields, structure path, target payload, and a candidate-specific output URI.

`metrics.json` contains one `candidates` array plus per-candidate metric records:

```json
[
  {"candidate_id": "LPAR1_RFNB_001", "name": "generation_rank", "value": 1},
  {"candidate_id": "LPAR1_RFNB_001", "name": "cdr3_length", "value": 14},
  {"candidate_id": "LPAR1_RFNB_001", "name": "sequence_length", "value": 132}
]
```

The registered generation schema is:

```text
tool: rfantibody
required_metrics: generation_rank, cdr3_length, sequence_length
artifact_kinds: generated_candidates, candidate_fasta, boltz2_manifest, worker_logs
```

## Running The Example

```bash
python -m gpcrclaw.workers.rfantibody \
  --manifest examples/rfantibody/lpar1_generation_manifest.json \
  --dry-run
```

This writes deterministic interface candidates under `.gpcrclaw/examples/rfantibody/output`. These are not real RFAntibody outputs and are labeled with source `rfantibody_interface_dry_run`.
