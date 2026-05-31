from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .ids import short_id
from .models import ArtifactRef, Metric


def campaign_prefix(namespace: str, campaign_id: str) -> str:
    return f"campaigns/{namespace}/{campaign_id}"


def artifact_relative_path(namespace: str, campaign_id: str, *parts: str) -> str:
    clean_parts = [part.strip("/") for part in parts if part]
    return "/".join([campaign_prefix(namespace, campaign_id), *clean_parts])


def local_uri(path: Path) -> str:
    return f"local://{path.resolve()}"


def resolve_local_uri(uri: str) -> Path:
    if not uri.startswith("local://"):
        raise ValueError(f"Not a local artifact URI: {uri}")
    return Path(uri.removeprefix("local://"))


class LocalArtifactStore:
    def __init__(self, root: Path, namespace: str):
        self.root = root
        self.namespace = namespace

    def campaign_dir(self, campaign_id: str) -> Path:
        return self.root / campaign_prefix(self.namespace, campaign_id)

    def path_for(self, campaign_id: str, *parts: str) -> Path:
        return self.root / artifact_relative_path(self.namespace, campaign_id, *parts)

    def uri_for(self, campaign_id: str, *parts: str) -> str:
        return local_uri(self.path_for(campaign_id, *parts))

    def write_json(self, campaign_id: str, parts: tuple[str, ...], payload: dict[str, Any]) -> ArtifactRef:
        path = self.path_for(campaign_id, *parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return ArtifactRef(
            artifact_id=short_id("artifact"),
            kind=parts[-1].split(".")[0],
            uri=local_uri(path),
            mime_type="application/json",
        )

    def write_text(self, campaign_id: str, parts: tuple[str, ...], text: str, mime_type: str = "text/plain") -> ArtifactRef:
        path = self.path_for(campaign_id, *parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return ArtifactRef(
            artifact_id=short_id("artifact"),
            kind=parts[-1].split(".")[0],
            uri=local_uri(path),
            mime_type=mime_type,
        )

    def copy_file(self, campaign_id: str, source: Path, parts: tuple[str, ...], kind: str, mime_type: str) -> ArtifactRef:
        path = self.path_for(campaign_id, *parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
        return ArtifactRef(artifact_id=short_id("artifact"), kind=kind, uri=local_uri(path), mime_type=mime_type)


class ArtifactManifest:
    def __init__(self, store: LocalArtifactStore, campaign_id: str):
        self.store = store
        self.campaign_id = campaign_id
        self.path = store.path_for(campaign_id, "artifact_manifest.json")

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"campaign_id": self.campaign_id, "artifacts": [], "metrics": [], "events": []}
        return json.loads(self.path.read_text())

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def add_artifact(self, artifact: ArtifactRef) -> None:
        payload = self.load()
        payload["artifacts"].append(asdict(artifact))
        self.save(payload)

    def add_metric(self, metric: Metric) -> None:
        payload = self.load()
        payload["metrics"].append(asdict(metric))
        self.save(payload)

    def add_event(self, kind: str, detail: dict[str, Any]) -> None:
        payload = self.load()
        payload["events"].append({"kind": kind, "detail": detail})
        self.save(payload)

    def report_sources(self) -> list[dict[str, Any]]:
        payload = self.load()
        return [item for item in payload.get("artifacts", []) if item.get("status") == "available"]
