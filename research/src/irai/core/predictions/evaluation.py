"""Avaliação ex-post: o que o sistema afirmou vs. o que aconteceu.

Três métricas que este módulo trata como obrigatórias, e o motivo:

- **Brier Skill Score contra a taxa base.** O Brier sozinho engana. Num mercado
  que sobe, dizer "65%" para todo mundo dá Brier decente e habilidade zero. O
  BSS mede o ganho sobre simplesmente chutar a frequência histórica.
- **Calibração por faixa.** Se o sistema diz 70%, aconteceu 70% das vezes? É o
  item 14 do escopo e é a única forma de saber se a probabilidade é uma
  probabilidade ou um número decorativo.
- **Amostra efetiva.** Previsões feitas na mesma data, sobre empresas do mesmo
  mercado, não são observações independentes. Contar 500 previsões como 500
  observações infla a confiança em várias vezes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from irai.core.db.database import utcnow
from irai.core.db.repository import Repository
from irai.core.quant.returns import total_return_between
from irai.core.quant.risk import max_drawdown
from irai.core.quant.returns import simple_returns


@dataclass
class CalibrationBin:
    lower: float
    upper: float
    n: int
    mean_predicted: float
    observed_frequency: float
    # Intervalo de Wilson: mais honesto que o normal quando n é pequeno,
    # e n quase sempre é pequeno aqui.
    ci_low: float
    ci_high: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class EvaluationReport:
    model_version: str
    n_predictions: int
    n_resolved: int
    effective_sample_size: float
    base_rate: float | None
    metrics: dict[str, float]
    calibration: list[CalibrationBin]
    breakdowns: dict[str, pd.DataFrame] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def calibration_frame(self) -> pd.DataFrame:
        return pd.DataFrame([b.to_dict() for b in self.calibration])


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (float(max(0.0, centre - margin)), float(min(1.0, centre + margin)))


def effective_sample_size(dates: pd.Series, horizon_days: int) -> float:
    """Número de observações realmente independentes.

    Duas fontes de dependência: previsões feitas no mesmo dia (mesmo choque de
    mercado) e horizontes que se sobrepõem no tempo. Contamos blocos de datas
    separados por pelo menos um horizonte — conservador e explicável.
    """
    if dates.empty:
        return 0.0
    unique = pd.to_datetime(pd.Series(dates.unique())).sort_values()
    blocks, last = 0, None
    for d in unique:
        if last is None or (d - last).days >= horizon_days:
            blocks += 1
            last = d
    return float(blocks)


class PredictionEvaluator:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    # ------------------------------------------------------------ resolução
    def resolve_pending(self, as_of: str, benchmark: str) -> dict[str, int]:
        """Preenche o desfecho de toda previsão cujo horizonte já venceu."""
        rows = self.repo.db.query(
            """
            SELECT p.* FROM model_predictions p
            LEFT JOIN prediction_outcomes o ON o.prediction_id = p.prediction_id
            WHERE o.prediction_id IS NULL
            """
        )
        resolved = insufficient = 0
        bench_panel = self.repo.price_panel([benchmark], end=as_of)
        bench = bench_panel[benchmark] if benchmark in bench_panel else pd.Series(dtype=float)

        for row in rows:
            start = pd.Timestamp(row["as_of_date"])
            # Horizonte em pregões, convertido para calendário com folga.
            end = start + pd.Timedelta(days=int(row["horizon_days"] * 365 / 252))
            if end > pd.Timestamp(as_of):
                continue

            px_panel = self.repo.price_panel([row["ticker"]], end=as_of)
            if row["ticker"] not in px_panel:
                self._write_outcome(row["prediction_id"], end, None, None, None, None,
                                    None, None, "insufficient_data")
                insufficient += 1
                continue
            px = px_panel[row["ticker"]].dropna()
            actual = total_return_between(px, start, end)
            bench_ret = total_return_between(bench, start, end) if not bench.empty else None
            if not np.isfinite(actual):
                self._write_outcome(row["prediction_id"], end, None, None, None, None,
                                    None, None, "insufficient_data")
                insufficient += 1
                continue

            excess = (actual - bench_ret) if bench_ret is not None and np.isfinite(bench_ret) else None
            target_value = excess if row["target"] == "excess_return" else actual
            if target_value is None:
                self._write_outcome(row["prediction_id"], end, actual, bench_ret, None,
                                    None, None, None, "insufficient_data")
                insufficient += 1
                continue

            outcome = 1 if target_value > 0 else 0
            prob = row["predicted_probability"]
            brier = (prob - outcome) ** 2 if prob is not None else None
            abs_err = (
                abs(row["predicted_value"] - target_value)
                if row["predicted_value"] is not None else None
            )
            window = px.loc[start:end]
            rets = simple_returns(window).dropna()
            realized_vol = (
                float(rets.std(ddof=1) * np.sqrt(252)) if len(rets) > 2 else None
            )
            realized_dd = float(max_drawdown(rets)) if len(rets) > 2 else None

            self._write_outcome(row["prediction_id"], end, actual, bench_ret, excess,
                                outcome, brier, abs_err, "resolved",
                                realized_vol, realized_dd)
            resolved += 1

        return {"resolved": resolved, "insufficient_data": insufficient,
                "still_pending": len(rows) - resolved - insufficient}

    def _write_outcome(
        self, prediction_id: str, resolution_date: pd.Timestamp,
        actual: float | None, bench: float | None, excess: float | None,
        outcome: int | None, brier: float | None, abs_err: float | None,
        status: str, realized_vol: float | None = None, realized_dd: float | None = None,
    ) -> None:
        self.repo.db.execute(
            """
            INSERT OR REPLACE INTO prediction_outcomes (
                prediction_id, evaluated_at, resolution_date, actual_return,
                benchmark_return, excess_return, realized_volatility,
                realized_max_drawdown, outcome, brier_component, absolute_error, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (prediction_id, utcnow(), resolution_date.strftime("%Y-%m-%d"), actual, bench,
             excess, realized_vol, realized_dd, outcome, brier, abs_err, status),
        )

    # ------------------------------------------------------------ avaliação
    def evaluate(
        self,
        model_version: str | None = None,
        horizon_days: int | None = None,
        n_bins: int = 5,
    ) -> EvaluationReport:
        sql = """
            SELECT p.*, o.actual_return, o.benchmark_return, o.excess_return, o.outcome,
                   o.brier_component, o.absolute_error, o.status
            FROM model_predictions p
            JOIN prediction_outcomes o ON o.prediction_id = p.prediction_id
            WHERE o.status = 'resolved'
        """
        params: list[Any] = []
        if model_version:
            sql += " AND p.model_version = ?"
            params.append(model_version)
        if horizon_days:
            sql += " AND p.horizon_days = ?"
            params.append(horizon_days)
        rows = self.repo.db.query(sql, params)

        total_row = self.repo.db.query_one(
            "SELECT COUNT(*) AS n FROM model_predictions"
            + (" WHERE model_version = ?" if model_version else ""),
            params[:1] if model_version else [],
        )
        n_total = int(total_row["n"]) if total_row else 0

        if not rows:
            return EvaluationReport(
                model_version=model_version or "(todos)", n_predictions=n_total,
                n_resolved=0, effective_sample_size=0.0, base_rate=None, metrics={},
                calibration=[],
                warnings=["Nenhuma previsão resolvida ainda. O track record começa vazio "
                          "— e isso é honesto."],
            )

        df = pd.DataFrame([dict(r) for r in rows])
        warnings: list[str] = []

        horizon = int(df["horizon_days"].median())
        n_eff = effective_sample_size(df["as_of_date"], horizon)
        base_rate = float(df["outcome"].mean())

        metrics: dict[str, float] = {
            "n_resolved": float(len(df)),
            "base_rate_observed": base_rate,
            "directional_accuracy": float(
                ((df["predicted_probability"] > 0.5) == (df["outcome"] == 1)).mean()
            ) if df["predicted_probability"].notna().any() else float("nan"),
            "mean_actual_return": float(df["actual_return"].mean()),
            "mean_excess_return": float(df["excess_return"].mean())
            if df["excess_return"].notna().any() else float("nan"),
        }

        if df["brier_component"].notna().any():
            brier = float(df["brier_component"].mean())
            # Baseline: prever sempre a taxa base observada.
            brier_base = float(((base_rate - df["outcome"]) ** 2).mean())
            metrics["brier_score"] = brier
            metrics["brier_score_baseline_base_rate"] = brier_base
            metrics["brier_skill_score"] = (
                float(1.0 - brier / brier_base) if brier_base > 0 else float("nan")
            )
            if metrics["brier_skill_score"] <= 0:
                warnings.append(
                    "Brier Skill Score <= 0: o modelo NÃO supera simplesmente chutar a "
                    "taxa base. Probabilidades sem habilidade demonstrada."
                )

        if df["absolute_error"].notna().any():
            metrics["mae"] = float(df["absolute_error"].mean())

        if n_eff < 20:
            warnings.append(
                f"Amostra efetiva de apenas {n_eff:.0f} blocos independentes "
                f"({len(df)} previsões brutas). Qualquer conclusão aqui é preliminar."
            )

        calibration = self._calibration(df, n_bins)
        breakdowns = self._breakdowns(df)

        return EvaluationReport(
            model_version=model_version or "(todos)", n_predictions=n_total,
            n_resolved=len(df), effective_sample_size=n_eff, base_rate=base_rate,
            metrics=metrics, calibration=calibration, breakdowns=breakdowns,
            warnings=warnings,
        )

    def _calibration(self, df: pd.DataFrame, n_bins: int) -> list[CalibrationBin]:
        sub = df.dropna(subset=["predicted_probability", "outcome"])
        if sub.empty:
            return []
        edges = np.linspace(0.0, 1.0, n_bins + 1)
        bins: list[CalibrationBin] = []
        for lo, hi in zip(edges[:-1], edges[1:], strict=True):
            mask = (sub["predicted_probability"] >= lo) & (
                sub["predicted_probability"] < hi if hi < 1.0
                else sub["predicted_probability"] <= hi
            )
            chunk = sub[mask]
            if chunk.empty:
                continue
            successes = int(chunk["outcome"].sum())
            ci_low, ci_high = wilson_interval(successes, len(chunk))
            bins.append(CalibrationBin(
                lower=float(lo), upper=float(hi), n=len(chunk),
                mean_predicted=float(chunk["predicted_probability"].mean()),
                observed_frequency=successes / len(chunk),
                ci_low=ci_low, ci_high=ci_high,
            ))
        return bins

    def _breakdowns(self, df: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """Onde o modelo funciona e onde falha — item 13 do escopo."""
        out: dict[str, pd.DataFrame] = {}
        sectors = self.repo.companies(tickers=df["ticker"].unique().tolist())
        if not sectors.empty:
            df = df.merge(sectors[["ticker", "sector"]], on="ticker", how="left")

        for key in ("market", "market_regime", "horizon_days", "sector", "model_version"):
            if key not in df.columns or df[key].isna().all():
                continue
            grouped = df.groupby(key, dropna=False).agg(
                n=("outcome", "size"),
                hit_rate=("outcome", "mean"),
                mean_excess=("excess_return", "mean"),
                brier=("brier_component", "mean"),
            ).reset_index()
            grouped["n_effective_warning"] = grouped["n"] < 20
            out[key] = grouped
        return out


def features_of(prediction_row: dict[str, Any]) -> dict[str, Any]:
    return json.loads(prediction_row.get("features_json") or "{}")
