# ESMFold2 Worker

ESMFold2 is the second first-class design model in the Google Batch path. It folds generated nanobody candidates, or target/candidate pairs when `include_target` is enabled, and writes the same worker contract as the other GPU tools.

Entrypoint:

```text
python3 -m gpcrclaw.workers.esmfold2 --manifest /mnt/disks/input/manifest.json
```

Cloud image:

```text
us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/esmfold2-worker:latest
```

The image is defined in `Dockerfile.esmfold2`. It installs PyTorch CUDA wheels and Biohub's ESM package from `https://github.com/Biohub/esm.git`, then uses the local `ESMFold2Model` path rather than an API service.

## Manifest Options

ESMFold2-specific options live under `worker_options.esmfold2`:

```json
{
  "model_id": "biohub/ESMFold2",
  "candidate_chain_id": "B",
  "target_chain_id": "A",
  "include_target": false,
  "num_loops": 3,
  "num_sampling_steps": 50,
  "num_diffusion_samples": 1
}
```

Default mode folds the candidate sequence only. Set `include_target: true` to fold the target and candidate together when both sequences are present.

## Outputs

Normalized outputs:

```text
work/esmfold2_input.fasta
esmfold2/{candidate_id}_esmfold2.cif
esmfold2/esmfold2_metrics.json
metrics.json
artifacts.json
logs.txt
```

Contract metrics:

```text
mean_plddt
ptm
iptm
sequence_length
```

Contract artifacts:

```text
esmfold2_structure
raw_metrics
esmfold2_input
worker_logs
```

## Cloud Submission

Build the image:

```bash
gcloud builds submit --config cloudbuild.esmfold2.yaml .
```

Submit a dry-run Batch job without launching inference:

```bash
python3 scripts/run_esmfold2_batch.py --manifest examples/esmfold2/lpar1_nanobody_fold_manifest.json
```

Submit live inference when the image and model access are ready:

```bash
python3 scripts/run_esmfold2_batch.py \
  --manifest examples/esmfold2/lpar1_nanobody_fold_manifest.json \
  --live
```
