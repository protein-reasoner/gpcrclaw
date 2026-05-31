# GitHub OIDC For Worker Images

The `Build model worker images` workflow builds and pushes every model-worker image to Google Artifact Registry from GitHub Actions. It authenticates with GitHub OIDC and Google Workload Identity Federation, so the repository does not need a checked-in service-account key or a long-lived JSON credential.

## Required GitHub Variables

Define these as repository variables or on the `model-workers` environment:

```text
GCP_PROJECT_ID
GCP_REGION
GAR_REPOSITORY
GCP_WORKLOAD_IDENTITY_PROVIDER
GCP_SERVICE_ACCOUNT_EMAIL
```

For the current GCP setup, the values are expected to look like:

```text
GCP_PROJECT_ID=build-wgemini26sfo-2005
GCP_REGION=us-central1
GAR_REPOSITORY=gpcrclaw
GCP_WORKLOAD_IDENTITY_PROVIDER=projects/<project-number>/locations/global/workloadIdentityPools/<pool>/providers/<provider>
GCP_SERVICE_ACCOUNT_EMAIL=<service-account>@build-wgemini26sfo-2005.iam.gserviceaccount.com
```

The workflow uses those values to push:

```text
us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/fake-worker:<tag>
us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/boltz2-worker:<tag>
us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/chai1-worker:<tag>
us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/immunebuilder-worker:<tag>
```

Each image is tagged with both `sha-<commit-sha>` and `latest`.

The workflow uses the checked-in Dockerfiles directly:

```text
fake-worker -> Dockerfile.fake-worker
boltz2-worker -> Dockerfile.boltz2
chai1-worker -> Dockerfile.chai1
immunebuilder-worker -> Dockerfile.immunebuilder
```

## Required GitHub Secrets

No GitHub secret is required for the worker-image workflow when Workload Identity Federation is configured correctly. The service account and provider identifiers can be GitHub variables because they are not private keys.

If repository policy treats infrastructure identifiers as sensitive, store them as environment variables with restricted access rather than committing them. Do not add a Google service-account JSON key as a repository secret unless OIDC is unavailable.

## Google Cloud Permissions

The GitHub OIDC provider must allow tokens from this repository, and the configured service account must be allowed to impersonate through Workload Identity Federation. Grant the configured GitHub publisher service account `roles/iam.workloadIdentityUser` for the repository-bound Workload Identity principal.

The same configured service account must also be able to push images to the target Artifact Registry repository. Grant `roles/artifactregistry.writer` scoped to `projects/build-wgemini26sfo-2005/locations/us-central1/repositories/gpcrclaw` when possible. Project-level writer access also works, but is broader than necessary.

Do not point `GCP_SERVICE_ACCOUNT_EMAIL` at a Batch runtime service account that only has `roles/artifactregistry.reader`; image publishing will authenticate successfully and then fail at push time. Either use a dedicated publisher service account or grant writer access intentionally.

## Why `.env` Stays Local

`.env` files are for developer-local runtime settings, model tokens, license flags, and one-off machine configuration. They should not be read by GitHub Actions and should not be committed. CI uses GitHub variables, environment protection rules, OIDC, and Google IAM instead, which keeps deploy identity auditable and avoids copying local credentials into the repository.
