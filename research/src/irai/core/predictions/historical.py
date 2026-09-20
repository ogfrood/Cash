"""Frequências históricas condicionais — o "motor de previsão" do projeto.

O sistema nunca afirma o que vai acontecer. Ele responde a uma pergunta bem
mais modesta e verificável:

    "Na amostra disponível até esta data, empresas com características
     parecidas apresentaram retorno excedente positivo em X% das vezes,
     em n observações (n efetivo = m)."

Restrições que o código impõe por construção:

1. **Nada do futuro entra na amostra.** Uma observação só conta se o horizonte
   dela já tinha vencido ANTES da data de análise. Uma previsão feita em
   2020-01 não pode aprender com o que aconteceu em 2020-06.
2. **A taxa base vem junto.** Sem ela, "62%" parece informação e pode ser
   apenas o mercado subindo.
3. **A amostra efetiva vem junto.** 800 observações concentradas em 6 datas
   valem 6 observações, não 800.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from irai.core.predictions.evaluation import effective_sample_size, wilson_interval


@dataclass
class ConditionalEstimate:
    """Resposta a 'o que aconteceu historicamente em situações parecidas?'"""

    condition: str
    horizon_days: int
    target: str
    frequency_positive: float | None
    base_rate: float | None
    lift_vs_base_rate: float | None
    sample_size: int
    effective_sample_size: float
    ci_low: float | None
    ci_high: float | None
    median_outcome: float | None
    mean_outcome: float | None
    p25_outcome: float | None
    p75_outcome: float | None
    worst_outcome: float | None
    sample_start: str | None
    sample_end: str | None
    confidence: str
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sentence(self) -> str:
        """A frase que o sistema tem permissão de dizer. Note o que ela NÃO diz."""
        if self.frequency_positive is None:
            return (
                f"Insufficient data: amostra de {self.sample_size} observações não permite "
                f"estimar frequência para a condição '{self.condition}'."
            )
        return (
            f"Na amostra de {self.sample_start} a {self.sample_end}, empresas na condição "
            f"'{self.condition}' apresentaram {self.target} positivo em "
            f"{self.frequency_positive * 100:.1f}% dos casos no horizonte de "
            f"{self.horizon_days} pregões "
            f"(IC95% {self.ci_low * 100:.1f}–{self.ci_high * 100:.1f}%; "
            f"n={self.sample_size}, n efetivo={self.effective_sample_size:.0f}). "
            f"A taxa base da amostra inteira foi {self.base_rate * 100:.1f}%. "
            f"Isto descreve o passado da amostra; não é previsão."
        )


MIN_SAMPLE = 30
MIN_EFFECTIVE = 8


class HistoricalFrequencyEngine:
    """Constrói o conjunto histórico e responde consultas condicionais.

    `observations` precisa das colunas:
        as_of_date, ticker, outcome_value, resolution_date, + colunas de feature
    """

    def __init__(self, observations: pd.DataFrame, horizon_days: int,
                 target: str = "excess_return") -> None:
        self.horizon_days = horizon_days
        self.target = target
        required = {"as_of_date", "ticker", "outcome_value", "resolution_date"}
        missing = required - set(observations.columns)
        if missing and not observations.empty:
            raise ValueError(f"Colunas ausentes no conjunto histórico: {sorted(missing)}")
        self.observations = observations

    def available_at(self, as_of: str) -> pd.DataFrame:
        """Apenas observações cujo horizonte já tinha vencido em `as_of`.

        É aqui que o look-ahead morre. Sem este filtro, o 'histórico' incluiria
        desfechos que ainda não tinham acontecido.
        """
        if self.observations.empty:
            return self.observations
        return self.observations[
            pd.to_datetime(self.observations["resolution_date"]) <= pd.Timestamp(as_of)
        ]

    def estimate(
        self,
        as_of: str,
        mask: pd.Series | None = None,
        condition_label: str = "condição",
        extra_limitations: list[str] | None = None,
    ) -> ConditionalEstimate:
        sample = self.available_at(as_of)
        base_rate = (
            float((sample["outcome_value"] > 0).mean()) if not sample.empty else None
        )
        if mask is not None and not sample.empty:
            sample = sample[mask.reindex(sample.index).fillna(False)]

        limitations = list(extra_limitations or [])
        if sample.empty:
            return ConditionalEstimate(
                condition=condition_label, horizon_days=self.horizon_days,
                target=self.target, frequency_positive=None, base_rate=base_rate,
                lift_vs_base_rate=None, sample_size=0, effective_sample_size=0.0,
                ci_low=None, ci_high=None, median_outcome=None, mean_outcome=None,
                p25_outcome=None, p75_outcome=None, worst_outcome=None,
                sample_start=None, sample_end=None, confidence="none",
                limitations=[*limitations, "Nenhuma observação disponível na data."],
            )

        outcomes = sample["outcome_value"].dropna()
        n = int(len(outcomes))
        successes = int((outcomes > 0).sum())
        n_eff = effective_sample_size(sample["as_of_date"], self.horizon_days)
        ci_low, ci_high = wilson_interval(successes, n) if n else (None, None)
        freq = successes / n if n else None

        if n < MIN_SAMPLE:
            limitations.append(
                f"Amostra de {n} observações, abaixo do mínimo de {MIN_SAMPLE} adotado."
            )
        if n_eff < MIN_EFFECTIVE:
            limitations.append(
                f"Apenas {n_eff:.0f} blocos temporais independentes — as observações "
                f"se sobrepõem e não são independentes entre si."
            )
        span_years = (
            (pd.Timestamp(sample["as_of_date"].max()) - pd.Timestamp(sample["as_of_date"].min())).days
            / 365.25
        )
        if span_years < 5:
            limitations.append(
                f"A amostra cobre {span_years:.1f} anos — provavelmente um único regime "
                f"de mercado."
            )

        if n < MIN_SAMPLE or n_eff < MIN_EFFECTIVE:
            confidence = "low"
        elif n_eff < 20 or span_years < 8:
            confidence = "medium"
        else:
            confidence = "high"

        return ConditionalEstimate(
            condition=condition_label, horizon_days=self.horizon_days, target=self.target,
            frequency_positive=freq, base_rate=base_rate,
            lift_vs_base_rate=(freq - base_rate) if (freq is not None and base_rate is not None)
            else None,
            sample_size=n, effective_sample_size=n_eff, ci_low=ci_low, ci_high=ci_high,
            median_outcome=float(outcomes.median()), mean_outcome=float(outcomes.mean()),
            p25_outcome=float(outcomes.quantile(0.25)),
            p75_outcome=float(outcomes.quantile(0.75)),
            worst_outcome=float(outcomes.min()),
            sample_start=str(sample["as_of_date"].min()),
            sample_end=str(sample["as_of_date"].max()),
            confidence=confidence, limitations=limitations,
        )

    def estimate_by_quantile(
        self, as_of: str, column: str, value: float, n_quantiles: int = 5
    ) -> ConditionalEstimate:
        """Frequência condicional ao quantil em que o valor cai.

        Os cortes de quantil são calculados SOMENTE com a amostra disponível
        na data — recalcular os cortes com a série completa seria look-ahead.
        """
        sample = self.available_at(as_of)
        if sample.empty or column not in sample.columns:
            return self.estimate(as_of, condition_label=f"{column} indisponível")
        series = sample[column].dropna()
        if len(series) < n_quantiles * 10:
            return self.estimate(
                as_of, condition_label=f"{column}: amostra pequena demais para quantis",
                extra_limitations=[f"{len(series)} observações para {n_quantiles} faixas."],
            )
        edges = np.unique(np.quantile(series, np.linspace(0, 1, n_quantiles + 1)))
        bucket = int(np.clip(np.searchsorted(edges, value, side="right") - 1,
                             0, len(edges) - 2))
        lo, hi = edges[bucket], edges[bucket + 1]
        mask = (sample[column] >= lo) & (
            sample[column] <= hi if bucket == len(edges) - 2 else sample[column] < hi
        )
        label = f"{column} entre {lo:.3f} e {hi:.3f} (faixa {bucket + 1}/{n_quantiles})"
        return self.estimate(as_of, mask=mask, condition_label=label)


def build_observations(
    scores_by_date: dict[str, pd.DataFrame],
    price_panel: pd.DataFrame,
    benchmark: pd.Series,
    horizon_days: int,
    feature_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Monta o conjunto histórico a partir de scores passados e preços.

    `scores_by_date` mapeia data -> DataFrame indexado por ticker com as
    colunas de feature (inclusive 'total').
    """
    rows: list[dict[str, Any]] = []
    calendar = price_panel.index
    for as_of, frame in scores_by_date.items():
        as_of_ts = pd.Timestamp(as_of)
        future = calendar[calendar > as_of_ts]
        if len(future) <= horizon_days:
            continue
        resolution = future[horizon_days - 1]
        bench_ret = (
            float(benchmark.asof(resolution) / benchmark.asof(as_of_ts) - 1.0)
            if not benchmark.empty and benchmark.asof(as_of_ts) else np.nan
        )
        for ticker in frame.index:
            if ticker not in price_panel.columns:
                continue
            series = price_panel[ticker].dropna()
            p0, p1 = series.asof(as_of_ts), series.asof(resolution)
            if pd.isna(p0) or pd.isna(p1) or p0 == 0:
                continue
            asset_ret = float(p1 / p0 - 1.0)
            row = {
                "as_of_date": as_of_ts.strftime("%Y-%m-%d"),
                "resolution_date": resolution.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "asset_return": asset_ret,
                "benchmark_return": bench_ret,
                "outcome_value": asset_ret - bench_ret if np.isfinite(bench_ret) else np.nan,
            }
            for col in (feature_columns or list(frame.columns)):
                if col in frame.columns:
                    row[col] = frame.loc[ticker, col]
            rows.append(row)
    return pd.DataFrame(rows).dropna(subset=["outcome_value"])
