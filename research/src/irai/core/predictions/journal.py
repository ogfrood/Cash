"""Diário de previsões.

Uma previsão é gravada ANTES de o futuro acontecer e nunca mais é editada. O
resultado vai para uma tabela separada. Essa separação é o que torna o track
record confiável: não há caminho de código que permita "corrigir" o que o
sistema afirmou depois de saber o desfecho.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from irai.core.db.database import utcnow
from irai.core.db.repository import Repository

HORIZONS_DAYS = {"1M": 21, "3M": 63, "6M": 126, "12M": 252, "24M": 504}


@dataclass
class Prediction:
    """O que o sistema afirmou, com tudo que é preciso para cobrar depois."""

    ticker: str
    market: str
    as_of_date: str
    horizon_days: int
    model_version: str
    config_hash: str
    target: str = "excess_return"
    predicted_probability: float | None = None
    predicted_value: float | None = None
    uncertainty_low: float | None = None
    uncertainty_high: float | None = None
    base_rate: float | None = None
    sample_size: int | None = None
    effective_sample_size: float | None = None
    confidence: str = "low"
    features: dict[str, Any] = field(default_factory=dict)
    data_sources: list[str] = field(default_factory=list)
    market_regime: str | None = None
    score_total: float | None = None
    notes: str | None = None


class PredictionJournal:
    PREFIX = "STOCK"

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def next_id(self) -> str:
        row = self.repo.db.query_one("SELECT COUNT(*) AS n FROM model_predictions")
        return f"{self.PREFIX}-{int(row['n']) + 1:06d}"

    def record(self, prediction: Prediction) -> str:
        pid = self.next_id()
        self.repo.db.execute(
            """
            INSERT INTO model_predictions (
                prediction_id, created_at, as_of_date, ticker, market, model_version,
                horizon_days, target, predicted_probability, predicted_value,
                uncertainty_low, uncertainty_high, base_rate, sample_size,
                effective_sample_size, confidence, features_json, market_regime,
                data_sources_json, config_hash, score_total, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pid, utcnow(), prediction.as_of_date, prediction.ticker, prediction.market,
                prediction.model_version, prediction.horizon_days, prediction.target,
                prediction.predicted_probability, prediction.predicted_value,
                prediction.uncertainty_low, prediction.uncertainty_high,
                prediction.base_rate, prediction.sample_size,
                prediction.effective_sample_size, prediction.confidence,
                json.dumps(prediction.features, ensure_ascii=False, default=str),
                prediction.market_regime,
                json.dumps(prediction.data_sources, ensure_ascii=False),
                prediction.config_hash, prediction.score_total, prediction.notes,
            ),
        )
        return pid

    def record_many(self, predictions: list[Prediction]) -> list[str]:
        return [self.record(p) for p in predictions]

    def get(self, prediction_id: str) -> dict[str, Any] | None:
        row = self.repo.db.query_one(
            "SELECT * FROM model_predictions WHERE prediction_id = ?", (prediction_id,)
        )
        return dict(row) if row else None

    def list(
        self,
        model_version: str | None = None,
        ticker: str | None = None,
        resolved: bool | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        sql = """
            SELECT p.*, o.actual_return, o.benchmark_return, o.excess_return, o.outcome,
                   o.brier_component, o.absolute_error, o.status AS outcome_status,
                   o.resolution_date
            FROM model_predictions p
            LEFT JOIN prediction_outcomes o ON o.prediction_id = p.prediction_id
        """
        clauses, params = [], []
        if model_version:
            clauses.append("p.model_version = ?")
            params.append(model_version)
        if ticker:
            clauses.append("p.ticker = ?")
            params.append(ticker)
        if resolved is True:
            clauses.append("o.prediction_id IS NOT NULL")
        elif resolved is False:
            clauses.append("o.prediction_id IS NULL")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY p.as_of_date DESC, p.prediction_id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.repo.db.query(sql, params)
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

    def render(self, prediction_id: str) -> str:
        """Formato do item 11 do escopo: a ficha da previsão."""
        p = self.get(prediction_id)
        if p is None:
            return f"Previsão {prediction_id} não encontrada."
        outcome = self.repo.db.query_one(
            "SELECT * FROM prediction_outcomes WHERE prediction_id = ?", (prediction_id,)
        )
        features = json.loads(p["features_json"] or "{}")
        lines = [
            f"Prediction ID : {p['prediction_id']}",
            f"Ticker        : {p['ticker']} ({p['market']})",
            f"Date          : {p['as_of_date']}",
            f"Horizon       : {p['horizon_days']} pregões",
            f"Model         : {p['model_version']}  (config {p['config_hash'][:12]})",
            f"Target        : {p['target']}",
        ]
        if p["predicted_probability"] is not None:
            lines.append(
                f"Prediction    : P({p['target']} > 0) = {p['predicted_probability'] * 100:.1f}%"
            )
            if p["base_rate"] is not None:
                lines.append(
                    f"Base rate     : {p['base_rate'] * 100:.1f}%  "
                    f"(sem comparar com isto, a probabilidade não significa nada)"
                )
        lines.append(
            f"Sample        : n={p['sample_size']}, n efetivo={p['effective_sample_size']}"
        )
        lines.append(f"Confidence    : {p['confidence']}")
        lines.append(f"Market regime : {p['market_regime'] or '—'}")
        if features:
            top = list(features.items())[:8]
            lines.append("Features      : " + ", ".join(f"{k}={_fmt(v)}" for k, v in top))
        if outcome:
            lines += [
                "",
                f"Resolution    : {outcome['resolution_date']} ({outcome['status']})",
                f"Actual return : {_pct(outcome['actual_return'])}",
                f"Benchmark     : {_pct(outcome['benchmark_return'])}",
                f"Excess        : {_pct(outcome['excess_return'])}",
                f"Outcome       : {'positivo' if outcome['outcome'] else 'negativo'}",
                f"Brier comp.   : {_fmt(outcome['brier_component'])}",
            ]
        else:
            lines += ["", "Resolution    : pendente (horizonte ainda não venceu)"]
        return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _pct(value: Any) -> str:
    return "—" if value is None else f"{float(value) * 100:.2f}%"
