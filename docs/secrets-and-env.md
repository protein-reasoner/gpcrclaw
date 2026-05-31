# Secrets And Environment

GPCRclaw uses environment variables for local configuration and GitHub/GCP secrets for anything sensitive.

## Local Files

Use `.env.example` as the template:

```bash
cp .env.example .env
```

Rules:

- Commit `.env.example`.
- Never commit `.env` or `.env.*`.
- Keep real tokens, license flags, service-account material, and model-provider credentials out of Git.
- Prefer `gcloud auth application-default login` locally instead of storing service-account JSON.

The CLI loads `.env` automatically before reading `GpcrClawConfig`.

## GitHub Secrets

Use GitHub repository or environment secrets for sensitive values:

```text
GCP_PROJECT_ID
GCP_REGION
GCP_WORKLOAD_IDENTITY_PROVIDER
GCP_SERVICE_ACCOUNT
GPCRCLAW_BUCKET
HUGGINGFACE_TOKEN
WANDB_API_KEY
BOLTZ2_LICENSE_ACCEPTED
```

Use GitHub variables for non-secret defaults:

```text
GPCRCLAW_NAMESPACE
GPCRCLAW_ARTIFACT_PREFIX
GPCRCLAW_STANDARD_A100_LIMIT
GPCRCLAW_PREEMPTIBLE_A100_LIMIT
GPCRCLAW_L4_LIMIT
```

Prefer GitHub OIDC / Workload Identity Federation for CI access to Google Cloud. Avoid long-lived service-account JSON keys unless there is no alternative.

## Model Secrets

Real model workers should receive only the secrets they actually need.

Boltz-2 expected first-pass inputs:

```text
GPCRCLAW_BOLTZ2_CONTAINER_IMAGE
GPCRCLAW_MODEL_ARTIFACT_ROOT
BOLTZ2_LICENSE_ACCEPTED
HUGGINGFACE_TOKEN
```

The placeholder Boltz-2 worker must remain non-secret and runnable without model weights. The live worker should fail fast if required model artifacts or license gates are missing.
