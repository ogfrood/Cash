"""Walk-forward com janela expansiva.

    calibrar 2010–2015  ->  testar 2016
    calibrar 2010–2016  ->  testar 2017
    calibrar 2010–2017  ->  testar 2018
    ...

O resultado que importa é a série concatenada dos períodos de TESTE — cada
um deles fora da amostra usada para escolher os parâmetros. O resultado do
período de calibração é mostrado ao lado, de propósito: a diferença entre os
dois é a medida honesta de quanto do desempenho veio de ajuste.

Duas defesas contra p-hacking embutidas:

1. `n_variants_tested` é contado e gravado. Testar 40 variantes e reportar a
   melhor não é a mesma coisa que testar uma.
2. `deflated_sharpe_ratio` ajusta o Sharpe pelo número de tentativas. Um
   Sharpe de 1,2 escolhido entre 40 candidatos vale menos que um Sharpe de
   0,9 escolhido entre 2.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from irai.config import MarketConfig
from irai.core.backtest.engine import BacktestConfig, BacktestEngine, BacktestResult
from irai.core.db.repository import Repository
from irai.core.quant.risk import risk_summary
from irai.core.scoring.engine import ScoringEngine


@dataclass
class Fold:
    index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    chosen_variant: str
    n_variants_tested: int
    train_metrics: dict[str, float]
    test_metrics: dict[str, float]
    test_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    test_benchmark_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


@dataclass
class WalkForwardResult:
    folds: list[Fold]
    combined_metrics: dict[str, float]
    combined_returns: pd.Series
    combined_benchmark_returns: pd.Series
    total_variants_tested: int
    selection_metric: str
    degradation: dict[str, float]
    warnings: list[str] = field(default_factory=list)

    def table(self) -> pd.DataFrame:
        rows = []
        for f in self.folds:
            rows.append({
                "fold": f.index,
                "calibração": f"{f.train_start[:7]}→{f.train_end[:7]}",
                "teste": f"{f.test_start[:7]}→{f.test_end[:7]}",
                "variante": f.chosen_variant,
                "ret_calib": f.train_metrics.get("total_return"),
                "ret_teste": f.test_metrics.get("total_return"),
                "sharpe_calib": f.train_metrics.get("sharpe"),
                "sharpe_teste": f.test_metrics.get("sharpe"),
                "dd_teste": f.test_metrics.get("max_drawdown"),
            })
        return pd.DataFrame(rows)

    def consistency(self) -> dict[str, float]:
        """Quantos períodos de teste foram positivos — e contra o benchmark.

        Consistência importa mais que média: um modelo que ganha muito em um
        ano e perde em cinco não é um modelo, é uma aposta que deu certo.
        """
        if not self.folds:
            return {}
        rets = [f.test_metrics.get("total_return", np.nan) for f in self.folds]
        exc = [f.test_metrics.get("excess_return", np.nan) for f in self.folds]
        rets = [r for r in rets if np.isfinite(r)]
        exc = [e for e in exc if np.isfinite(e)]
        return {
            "n_folds": float(len(self.folds)),
            "share_positive_return": float(np.mean([r > 0 for r in rets])) if rets else np.nan,
            "share_beat_benchmark": float(np.mean([e > 0 for e in exc])) if exc else np.nan,
            "worst_fold_return": float(min(rets)) if rets else np.nan,
            "best_fold_return": float(max(rets)) if rets else np.nan,
            "return_dispersion": float(np.std(rets, ddof=1)) if len(rets) > 1 else np.nan,
        }


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Probabilidade de o Sharpe observado ser maior que zero, descontando o
    fato de ele ter sido escolhido entre `n_trials` tentativas.

    Baseado em Bailey & López de Prado (2014). Serve para responder à pergunta
    que todo backtest esconde: "quantas ideias você testou antes desta?"
    """
    if n_trials < 1 or n_observations < 10 or not np.isfinite(observed_sharpe):
        return float("nan")
    euler = 0.5772156649
    if n_trials == 1:
        expected_max = 0.0
    else:
        z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
        z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
        expected_max = (1 - euler) * z1 + euler * z2
    denom = math.sqrt(
        max(1e-12, 1 - skew * observed_sharpe + (kurtosis - 1) / 4 * observed_sharpe**2)
    )
    numerator = (observed_sharpe - expected_max) * math.sqrt(n_observations - 1)
    return float(stats.norm.cdf(numerator / denom))


class WalkForwardRunner:
    """Executa o protocolo walk-forward.

    `variants` é a lista de configurações candidatas. Com uma única variante,
    não há seleção — e o walk-forward vira simplesmente um teste fora da
    amostra, que já é bem mais honesto que um backtest único.
    """

    def __init__(
        self,
        repo: Repository,
        market: MarketConfig,
        scoring_factory: Callable[[str], ScoringEngine],
        base_config: BacktestConfig,
    ) -> None:
        self.repo = repo
        self.market = market
        self.scoring_factory = scoring_factory
        self.base_config = base_config

    def run(
        self,
        start: str,
        end: str,
        train_years: int = 5,
        test_years: int = 1,
        variants: Sequence[dict[str, Any]] | None = None,
        selection_metric: str = "sharpe",
        model_version: str = "stock-v1.0.0",
    ) -> WalkForwardResult:
        variants = list(variants or [{"name": "baseline"}])
        folds: list[Fold] = []
        warnings: list[str] = []
        total_variants = 0

        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        first_test_start = start_ts + pd.DateOffset(years=train_years)
        if first_test_start >= end_ts:
            raise ValueError(
                f"Período curto demais: {train_years} anos de calibração não cabem "
                f"entre {start} e {end}."
            )

        fold_idx = 0
        test_start = first_test_start
        while test_start < end_ts:
            test_end = min(test_start + pd.DateOffset(years=test_years)
                           - pd.Timedelta(days=1), end_ts)
            train_start, train_end = start_ts, test_start - pd.Timedelta(days=1)

            best = None
            for variant in variants:
                total_variants += 1
                try:
                    train_result = self._backtest(variant, train_start, train_end, model_version)
                except ValueError as exc:
                    warnings.append(f"fold {fold_idx} variante {variant.get('name')}: {exc}")
                    continue
                score = train_result.metrics.get(selection_metric, float("-inf"))
                score = score if np.isfinite(score) else float("-inf")
                if best is None or score > best[0]:
                    best = (score, variant, train_result)

            if best is None:
                warnings.append(f"fold {fold_idx}: nenhuma variante rodou na calibração")
                test_start = test_start + pd.DateOffset(years=test_years)
                fold_idx += 1
                continue

            _, chosen, train_result = best
            try:
                test_result = self._backtest(chosen, test_start, test_end, model_version)
            except ValueError as exc:
                warnings.append(f"fold {fold_idx}: teste não rodou ({exc})")
                test_start = test_start + pd.DateOffset(years=test_years)
                fold_idx += 1
                continue

            folds.append(Fold(
                index=fold_idx,
                train_start=train_start.strftime("%Y-%m-%d"),
                train_end=train_end.strftime("%Y-%m-%d"),
                test_start=test_start.strftime("%Y-%m-%d"),
                test_end=test_end.strftime("%Y-%m-%d"),
                chosen_variant=str(chosen.get("name", "baseline")),
                n_variants_tested=len(variants),
                train_metrics=train_result.metrics,
                test_metrics=test_result.metrics,
                test_returns=test_result.returns,
                test_benchmark_returns=test_result.benchmark_returns,
            ))
            test_start = test_start + pd.DateOffset(years=test_years)
            fold_idx += 1

        combined = (
            pd.concat([f.test_returns for f in folds]).sort_index()
            if folds else pd.Series(dtype=float)
        )
        combined_bench = (
            pd.concat([f.test_benchmark_returns for f in folds]).sort_index()
            if folds else pd.Series(dtype=float)
        )
        combined = combined[~combined.index.duplicated(keep="first")]
        combined_bench = combined_bench[~combined_bench.index.duplicated(keep="first")]

        metrics = (
            risk_summary(combined, combined_bench if not combined_bench.dropna().empty else None,
                         self.market.risk_free_fallback_annual,
                         self.market.trading_days_per_year)
            if not combined.empty else {}
        )
        if metrics:
            metrics["deflated_sharpe_probability"] = deflated_sharpe_ratio(
                metrics.get("sharpe", float("nan")),
                n_trials=max(total_variants, 1),
                n_observations=len(combined),
                skew=float(stats.skew(combined.dropna())) if len(combined.dropna()) > 3 else 0.0,
                kurtosis=float(stats.kurtosis(combined.dropna(), fisher=False))
                if len(combined.dropna()) > 3 else 3.0,
            )
            metrics["n_variants_tested_total"] = float(total_variants)

        degradation = {}
        if folds:
            for key in ("total_return", "sharpe", "max_drawdown"):
                tr = [f.train_metrics.get(key, np.nan) for f in folds]
                te = [f.test_metrics.get(key, np.nan) for f in folds]
                tr = [v for v in tr if np.isfinite(v)]
                te = [v for v in te if np.isfinite(v)]
                if tr and te:
                    degradation[f"{key}_train_mean"] = float(np.mean(tr))
                    degradation[f"{key}_test_mean"] = float(np.mean(te))
                    degradation[f"{key}_drop"] = float(np.mean(tr) - np.mean(te))

        return WalkForwardResult(
            folds=folds, combined_metrics=metrics, combined_returns=combined,
            combined_benchmark_returns=combined_bench,
            total_variants_tested=total_variants, selection_metric=selection_metric,
            degradation=degradation, warnings=warnings,
        )

    def _backtest(
        self, variant: dict[str, Any], start: pd.Timestamp, end: pd.Timestamp, model_version: str
    ) -> BacktestResult:
        import dataclasses

        overrides = {k: v for k, v in variant.items()
                     if k != "name" and k != "scoring_config"}
        cfg = dataclasses.replace(
            self.base_config,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            **overrides,
        )
        scoring = self.scoring_factory(variant.get("scoring_config", ""))
        return BacktestEngine(self.repo, self.market, scoring, cfg).run(model_version)
