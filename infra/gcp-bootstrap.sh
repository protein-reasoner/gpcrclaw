#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-build-wgemini26sfo-2005}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-gpcrclaw-artifacts}"
REPO="${REPO:-gpcrclaw}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-gpcrclaw-batch-worker}"

gcloud config set project "${PROJECT_ID}"
gcloud services enable compute.googleapis.com batch.googleapis.com cloudbuild.googleapis.com storage.googleapis.com artifactregistry.googleapis.com

gcloud storage buckets create "gs://${BUCKET}" \
  --project "${PROJECT_ID}" \
  --location "${REGION}" \
  --uniform-bucket-level-access || true

gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="GPCRclaw model worker containers" || true

gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
  --display-name="GPCRclaw Batch Worker" || true

for role in roles/batch.jobsEditor roles/batch.agentReporter roles/logging.logWriter roles/storage.objectAdmin roles/artifactregistry.reader; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="${role}"
done
