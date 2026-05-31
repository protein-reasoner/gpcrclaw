from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ConcurrencyLimits:
    standard_a100: int = 12
    preemptible_a100: int = 48
    l4: int = 8

    @classmethod
    def from_env(cls) -> "ConcurrencyLimits":
        return cls(
            standard_a100=int(os.getenv("GPCRCLAW_STANDARD_A100_LIMIT", "12")),
            preemptible_a100=int(os.getenv("GPCRCLAW_PREEMPTIBLE_A100_LIMIT", "48")),
            l4=int(os.getenv("GPCRCLAW_L4_LIMIT", "8")),
        )


@dataclass(frozen=True)
class GpcrClawConfig:
    namespace: str = "alankrit"
    project_id: str = "build-wgemini26sfo-2005"
    region: str = "us-central1"
    backend: str = "local-mock"
    state_root: Path = Path(".gpcrclaw/state")
    artifact_root: Path = Path(".gpcrclaw/artifacts")
    bucket: str = "gpcrclaw-artifacts"
    artifact_prefix: str = "campaigns/alankrit"
    container_image: str = "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/fake-worker:latest"
    boltz2_container_image: str = "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/boltz2-worker:latest"
    chai1_container_image: str = "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/chai1-worker:latest"
    immunebuilder_container_image: str = "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/immunebuilder-worker:latest"
    rfantibody_container_image: str = "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/rfantibody-worker:latest"
    esmfold2_container_image: str = "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/esmfold2-worker:latest"
    model_artifact_root: str = "gs://gpcrclaw-artifacts/models"
    service_account_email: str = "gpcrclaw-batch-worker@build-wgemini26sfo-2005.iam.gserviceaccount.com"
    accelerator_type: str = "A100"
    accelerator_count: int = 1
    timeout_minutes: int = 30
    max_retries: int = 1
    concurrency: ConcurrencyLimits = field(default_factory=ConcurrencyLimits)

    @classmethod
    def from_env(cls) -> "GpcrClawConfig":
        return cls(
            namespace=os.getenv("GPCRCLAW_NAMESPACE", "alankrit"),
            project_id=os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("GPCRCLAW_PROJECT_ID", "build-wgemini26sfo-2005")),
            region=os.getenv("GPCRCLAW_REGION", "us-central1"),
            backend=os.getenv("GPCRCLAW_BACKEND", "local-mock"),
            state_root=Path(os.getenv("GPCRCLAW_STATE_ROOT", ".gpcrclaw/state")),
            artifact_root=Path(os.getenv("GPCRCLAW_ARTIFACT_ROOT", ".gpcrclaw/artifacts")),
            bucket=os.getenv("GPCRCLAW_BUCKET", "gpcrclaw-artifacts"),
            artifact_prefix=os.getenv("GPCRCLAW_ARTIFACT_PREFIX", "campaigns/alankrit"),
            container_image=os.getenv(
                "GPCRCLAW_CONTAINER_IMAGE",
                "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/fake-worker:latest",
            ),
            boltz2_container_image=os.getenv(
                "GPCRCLAW_BOLTZ2_CONTAINER_IMAGE",
                "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/boltz2-worker:latest",
            ),
            chai1_container_image=os.getenv(
                "GPCRCLAW_CHAI1_CONTAINER_IMAGE",
                "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/chai1-worker:latest",
            ),
            immunebuilder_container_image=os.getenv(
                "GPCRCLAW_IMMUNEBUILDER_CONTAINER_IMAGE",
                "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/immunebuilder-worker:latest",
            ),
            rfantibody_container_image=os.getenv(
                "GPCRCLAW_RFANTIBODY_CONTAINER_IMAGE",
                "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/rfantibody-worker:latest",
            ),
            esmfold2_container_image=os.getenv(
                "GPCRCLAW_ESMFOLD2_CONTAINER_IMAGE",
                "us-central1-docker.pkg.dev/build-wgemini26sfo-2005/gpcrclaw/esmfold2-worker:latest",
            ),
            model_artifact_root=os.getenv("GPCRCLAW_MODEL_ARTIFACT_ROOT", "gs://gpcrclaw-artifacts/models"),
            service_account_email=os.getenv(
                "GPCRCLAW_SERVICE_ACCOUNT_EMAIL",
                "gpcrclaw-batch-worker@build-wgemini26sfo-2005.iam.gserviceaccount.com",
            ),
            accelerator_type=os.getenv("GPCRCLAW_ACCELERATOR_TYPE", "A100"),
            accelerator_count=int(os.getenv("GPCRCLAW_ACCELERATOR_COUNT", "1")),
            timeout_minutes=int(os.getenv("GPCRCLAW_TIMEOUT_MINUTES", "30")),
            max_retries=int(os.getenv("GPCRCLAW_MAX_RETRIES", "1")),
            concurrency=ConcurrencyLimits.from_env(),
        )

    def artifact_gs_root(self) -> str:
        return f"gs://{self.bucket}/{self.artifact_prefix}"
