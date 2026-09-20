"""Motor de scoring transparente.

Regras que tornam o score auditável:

- Nenhum peso está no código. Todos vêm do YAML, e o hash do YAML acompanha
  cada score gravado. Dois anos depois dá para saber exatamente qual peso
  produziu qual número.
- Fator ausente não vira zero. Zero, num z-score, significa "na mediana do
  setor" — afirmação forte sobre uma empresa da qual não se sabe nada. Fator
  ausente reduz a COBERTURA e os pesos são renormalizados entre o que existe.
- Abaixo do mínimo de cobertura, o pilar (ou a empresa inteira) fica sem score.
  É melhor não pontuar do que pontuar com metade da informação.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from irai.config import sha256_of
from irai.core.features.builder import FeaturePanel
from irai.core.quant.normalize import normalize_by_group


@dataclass(frozen=True)
class FactorSpec:
    name: str
    weight: float
    direction: int   # +1 = maior é melhor, -1 = menor é melhor


@dataclass(frozen=True)
class PillarSpec:
    name: str
    weight: float
    rationale: str
    factors: tuple[FactorSpec, ...]


@dataclass(frozen=True)
class ScoringConfig:
    version: str
    description: str
    method: str
    winsorize_percentiles: tuple[float, float]
    peer_group: str
    min_peers: int
    clip_z: float
    min_pillar_coverage: float
    min_total_coverage: float
    pillars: tuple[PillarSpec, ...]
    config_hash: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def all_factor_names(self) -> list[str]:
        return [f.name for p in self.pillars for f in p.factors]

    @classmethod
    def load(cls, path: Path | str) -> ScoringConfig:
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
        norm = raw.get("normalization", {})
        pillars = []
        for name, spec in raw["pillars"].items():
            factors = tuple(
                FactorSpec(name=fname, weight=float(f.get("weight", 1.0)),
                           direction=int(f.get("direction", 1)))
                for fname, f in spec["factors"].items()
            )
            pillars.append(PillarSpec(
                name=name, weight=float(spec.get("weight", 1.0)),
                rationale=spec.get("rationale", ""), factors=factors,
            ))
        return cls(
            version=raw["version"],
            description=raw.get("description", ""),
            method=norm.get("method", "robust_z"),
            winsorize_percentiles=tuple(norm.get("winsorize_percentiles", [0.01, 0.99])),
            peer_group=norm.get("peer_group", "sector"),
            min_peers=int(norm.get("min_peers", 5)),
            clip_z=float(norm.get("clip_z", 3.0)),
            min_pillar_coverage=float(raw.get("min_pillar_coverage", 0.5)),
            min_total_coverage=float(raw.get("min_total_coverage", 0.6)),
            pillars=tuple(pillars),
            config_hash=sha256_of(text),
            raw=raw,
        )


@dataclass
class ScoringResult:
    as_of: pd.Timestamp
    config_version: str
    config_hash: str
    scores: pd.DataFrame          # index=ticker, colunas=pilares + 'total'
    coverage: pd.DataFrame        # cobertura por pilar
    normalized: pd.DataFrame      # z de cada fator (a evidência citável)
    raw_factors: pd.DataFrame     # valor bruto de cada fator
    peer_groups: pd.Series
    peer_sizes: pd.Series
    missing_factors: dict[str, list[str]]

    def ranked(self, column: str = "total") -> pd.DataFrame:
        df = self.scores.dropna(subset=[column]).sort_values(column, ascending=False)
        out = df.copy()
        out["rank"] = np.arange(1, len(out) + 1)
        out["percentile"] = out[column].rank(pct=True) * 100.0
        return out

    def explain(self, ticker: str, top_n: int = 5) -> dict[str, Any]:
        """Por que este ticker recebeu este score.

        Devolve os fatores que mais empurraram para cima e para baixo. É o que
        alimenta a frase "a empresa apareceu por causa de X e Y" — e o que
        impede a IA de inventar a explicação.
        """
        if ticker not in self.normalized.index:
            return {"ticker": ticker, "status": "insufficient_data"}
        z = self.normalized.loc[ticker].dropna()
        contributions = []
        for pillar in self._pillar_specs():
            for factor in pillar.factors:
                if factor.name in z.index:
                    contributions.append({
                        "factor": factor.name,
                        "pillar": pillar.name,
                        "raw_value": _safe_float(self.raw_factors.loc[ticker].get(factor.name)),
                        "z_score": float(z[factor.name]),
                        "direction": factor.direction,
                        "contribution": float(z[factor.name] * factor.direction * factor.weight),
                    })
        contributions.sort(key=lambda c: c["contribution"], reverse=True)
        return {
            "ticker": ticker,
            "peer_group": self.peer_groups.get(ticker),
            "peer_count": _safe_float(self.peer_sizes.get(ticker)),
            "scores": {k: _safe_float(v) for k, v in self.scores.loc[ticker].items()},
            "coverage": {k: _safe_float(v) for k, v in self.coverage.loc[ticker].items()},
            "top_positive": contributions[:top_n],
            "top_negative": contributions[-top_n:][::-1],
            "missing_factors": self.missing_factors.get(ticker, []),
        }

    def _pillar_specs(self) -> tuple[PillarSpec, ...]:
        return getattr(self, "_specs", ())


class ScoringEngine:
    def __init__(self, config: ScoringConfig) -> None:
        self.config = config

    def score(self, panel: FeaturePanel) -> ScoringResult:
        cfg = self.config
        frame = panel.frame
        if frame.empty:
            empty = pd.DataFrame()
            return ScoringResult(panel.as_of, cfg.version, cfg.config_hash, empty, empty,
                                 empty, empty, pd.Series(dtype=object), pd.Series(dtype=float), {})

        groups = panel.sectors if cfg.peer_group == "sector" else pd.Series(
            "__ALL__", index=frame.index
        )

        normalized = pd.DataFrame(index=frame.index, dtype=float)
        peer_group_used: pd.Series | None = None
        peer_size_used: pd.Series | None = None

        for factor_name in cfg.all_factor_names:
            if factor_name not in frame.columns:
                normalized[factor_name] = np.nan
                continue
            z, grp, size = normalize_by_group(
                frame[factor_name], groups, method=cfg.method,
                winsorize_percentiles=cfg.winsorize_percentiles,
                min_group_size=cfg.min_peers, clip=cfg.clip_z,
            )
            normalized[factor_name] = z
            if peer_group_used is None:
                peer_group_used, peer_size_used = grp, size

        scores = pd.DataFrame(index=frame.index, dtype=float)
        coverage = pd.DataFrame(index=frame.index, dtype=float)
        missing: dict[str, list[str]] = {t: [] for t in frame.index}

        for pillar in cfg.pillars:
            weights = np.array([f.weight for f in pillar.factors], dtype=float)
            directions = np.array([f.direction for f in pillar.factors], dtype=float)
            names = [f.name for f in pillar.factors]
            block = normalized.reindex(columns=names)

            signed = block.mul(directions, axis=1)
            available = block.notna()
            weight_matrix = available.mul(weights, axis=1)
            weight_sum = weight_matrix.sum(axis=1)
            weighted = (signed.fillna(0.0) * weight_matrix).sum(axis=1)

            cov = available.mul(weights, axis=1).sum(axis=1) / weights.sum()
            pillar_score = weighted.divide(weight_sum.replace(0.0, np.nan))
            # Cobertura insuficiente => sem score. Não estimamos o que falta.
            pillar_score = pillar_score.where(cov >= cfg.min_pillar_coverage)

            scores[pillar.name] = pillar_score
            coverage[pillar.name] = cov
            for ticker in frame.index:
                absent = [n for n in names if not available.loc[ticker, n]]
                missing[ticker].extend(absent)

        pillar_weights = pd.Series({p.name: p.weight for p in cfg.pillars})
        pillar_available = scores.notna()
        total_weight = pillar_available.mul(pillar_weights, axis=1).sum(axis=1)
        total = (scores.fillna(0.0) * pillar_available.mul(pillar_weights, axis=1)).sum(axis=1)
        total = total.divide(total_weight.replace(0.0, np.nan))

        total_coverage = pillar_available.mul(pillar_weights, axis=1).sum(axis=1) / pillar_weights.sum()
        scores["total"] = total.where(total_coverage >= cfg.min_total_coverage)
        coverage["total"] = total_coverage

        result = ScoringResult(
            as_of=panel.as_of, config_version=cfg.version, config_hash=cfg.config_hash,
            scores=scores, coverage=coverage, normalized=normalized,
            raw_factors=frame, peer_groups=peer_group_used if peer_group_used is not None
            else pd.Series("__ALL__", index=frame.index),
            peer_sizes=peer_size_used if peer_size_used is not None
            else pd.Series(float(len(frame)), index=frame.index),
            missing_factors=missing,
        )
        result._specs = cfg.pillars  # type: ignore[attr-defined]
        return result


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else f
