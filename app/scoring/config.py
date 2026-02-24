from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List

import yaml

DEFAULT_SCORING_PATH = os.getenv("IDS_SCORING_CONFIG", "app/scoring/scoring.yaml")


@dataclass(frozen=True)
class SeverityBand:
    min_score: int
    severity: str


@dataclass(frozen=True)
class ScoringConfig:
    version: int
    baseline: int
    cap: int
    weights: Dict[str, int]
    thresholds: Dict[str, int]
    severity_bands: List[SeverityBand]
    path: str


def load_scoring_config(path: str | None = None) -> ScoringConfig:
    p = path or DEFAULT_SCORING_PATH
    with open(p, "r", encoding="utf-8") as f:
        raw: Dict[str, Any] = yaml.safe_load(f) or {}

    bands_raw = raw.get("severity_bands") or []
    bands = [
        SeverityBand(min_score=int(b["min_score"]), severity=str(b["severity"]))
        for b in bands_raw
    ]
    bands.sort(key=lambda x: x.min_score)

    return ScoringConfig(
        version=int(raw.get("version", 1)),
        baseline=int(raw.get("baseline", 0)),
        cap=int(raw.get("cap", 100)),
        weights={k: int(v) for k, v in (raw.get("weights") or {}).items()},
        thresholds={k: int(v) for k, v in (raw.get("thresholds") or {}).items()},
        severity_bands=bands,
        path=p,
    )


def severity_from_score(cfg: ScoringConfig, score: int) -> str:
    sev = "NONE"
    for b in cfg.severity_bands:
        if score >= b.min_score:
            sev = b.severity
    return sev
