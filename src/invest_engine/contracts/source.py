"""Internal, versioned identity of *historical* market-data inputs.

E1 dataset packages and E5 event JSONL are not interchangeable byte formats.
This is a no-I/O provenance/value bridge, NOT an automatic replay converter,
streaming source, trading permission, or modification of legacy E5 digests.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal, Mapping

from invest_engine.data.datasets import DatasetManifest

HistoricalFormat = Literal["e1-normalized-parquet", "e5-canonical-jsonl"]
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class HistoricalSourceIdentity:
    """Stable source identity for a known binary representation and authority claim."""

    format: HistoricalFormat
    provider: str
    license_id: str
    content_sha256: str
    volume_unit: str
    dataset_id: str | None = None
    calendar_version: str | None = None
    adjustment: str | None = None
    completeness: str | None = None
    schema_version: str = "historical-source-identity-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "historical-source-identity-v1":
            raise ValueError("unsupported historical source reference version")
        if self.format not in ("e1-normalized-parquet", "e5-canonical-jsonl"):
            raise ValueError("unsupported historical representation")
        if not isinstance(self.content_sha256, str) or not SHA256.fullmatch(self.content_sha256):
            raise ValueError("invalid historical content checksum")
        for field in ("provider", "license_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("missing historical source identity field")
        if self.volume_unit not in ("SHARES", "TICK_COUNT", "UNKNOWN", "UNDECLARED"):
            raise ValueError("invalid historical volume unit")
        for name in ("dataset_id", "calendar_version", "adjustment", "completeness"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("invalid optional historical identity field")
        if self.format == "e1-normalized-parquet":
            if not all((self.dataset_id, self.calendar_version, self.adjustment, self.completeness)):
                raise ValueError("E1 package identity must pin its manifest fields")
        elif any((self.dataset_id, self.calendar_version, self.adjustment, self.completeness)):
            raise ValueError("E5 JSONL identity may not guess E1 package metadata")

    def portable_values(self) -> dict[str, str | None]:
        """Canonical JSON/CLI-compatible values with no live strategy/provider objects."""
        return {
            "schema_version": self.schema_version,
            "format": self.format,
            "provider": self.provider,
            "license_id": self.license_id,
            "content_sha256": self.content_sha256,
            "volume_unit": self.volume_unit,
            "dataset_id": self.dataset_id,
            "calendar_version": self.calendar_version,
            "adjustment": self.adjustment,
            "completeness": self.completeness,
        }

    @property
    def digest(self) -> str:
        data = json.dumps(
            self.portable_values(), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(data).hexdigest()


def from_e1_manifest(manifest: DatasetManifest) -> HistoricalSourceIdentity:
    """Describe E1 normalized Parquet. Does not load/check the stored package."""
    if not isinstance(manifest, DatasetManifest):
        raise TypeError("expected E1 DatasetManifest")
    return HistoricalSourceIdentity(
        format="e1-normalized-parquet",
        provider=manifest.spec.provider,
        license_id=manifest.spec.license_id,
        content_sha256=manifest.normalized_sha256,
        volume_unit="UNKNOWN",  # must resolve true units before economic replay
        dataset_id=manifest.spec.dataset_id,
        calendar_version=manifest.spec.calendar_version,
        adjustment=manifest.spec.adjustment.value,
        completeness=manifest.spec.completeness.value,
    )


def from_e5_dataset(dataset: Mapping[str, object]) -> HistoricalSourceIdentity:
    """Describe the existing e5-research-v1 dataset object, without opening files."""
    if not isinstance(dataset, Mapping):
        raise TypeError("E5 dataset must be a mapping")
    required = {"events_jsonl", "source", "license", "sha256"}
    if not required <= set(dataset) or set(dataset) - (required | {"volume_unit"}):
        raise ValueError("incorrect E5 dataset key set")
    path = dataset["events_jsonl"]
    if not isinstance(path, str) or not path.strip():
        raise ValueError("E5 source file reference missing")
    volume = dataset.get("volume_unit", "UNDECLARED")
    if not isinstance(volume, str) or volume not in {"SHARES", "TICK_COUNT", "UNDECLARED"}:
        raise ValueError("unsupported E5 volume unit")
    return HistoricalSourceIdentity(
        format="e5-canonical-jsonl",
        provider=dataset["source"],  # type: ignore[arg-type]
        license_id=dataset["license"],  # type: ignore[arg-type]
        content_sha256=dataset["sha256"],  # type: ignore[arg-type]
        volume_unit=volume,
    )
