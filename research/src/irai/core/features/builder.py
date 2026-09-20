"""Construção do painel de fatores numa data de decisão.

Este é o ponto onde DATA vira QUANT. Entra o repositório point-in-time, sai um
DataFrame (ticker x fator) com tudo que se sabia em `as_of` — e nada além.

Três garantias que o módulo oferece:

1. Preços são lidos até `as_of` inclusive; fundamentos, até `as_of` na data de
   PUBLICAÇÃO. Os dois cortes são diferentes e ambos são aplicados.
2. Todo fator ausente fica como NaN e é contabilizado na cobertura. Nunca é
   preenchido com média, zero ou 'valor do setor' — imputação silenciosa é uma
   forma de inventar dado.
3. O painel carrega, junto, a proveniência: quantos fatores vieram de fonte com
   data de publicação real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from irai.config import MarketConfig
from irai.core.db.repository import Repository
from irai.core.quant import momentum as mom
from irai.core.quant import technical as tech
from irai.core.quant.returns import simple_returns
from irai.core.quant.risk import beta as beta_fn
from irai.core.quant.risk import max_drawdown
from irai.markets.stocks.valuation.multiples import compute_multiples

# Fundamentos lidos do banco e usados diretamente como fator.
FUNDAMENTAL_FACTORS = [
    "roe", "roic", "roa", "gross_margin", "operating_margin", "net_margin",
    "ebitda_margin", "fcf_margin", "revenue_growth_yoy", "earnings_growth_yoy",
    "eps_growth_yoy", "ebitda_growth_yoy", "debt_to_equity", "net_debt_ebitda",
    "current_ratio", "interest_coverage", "share_count_change_yoy",
]
# Fundamentos usados como insumo de valuation (não viram fator sozinhos).
VALUATION_INPUTS = [
    "eps_ttm", "net_income_ttm", "ebitda_ttm", "revenue_ttm", "free_cash_flow",
    "total_equity", "total_debt", "cash", "shares_outstanding",
]
MARKET_FACTORS = [
    "momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m", "momentum_12_1",
    "volatility_12m", "beta", "max_drawdown_12m", "ma_distance_50", "ma_distance_200",
    "volume_trend", "relative_volume", "distance_from_high_12m", "relative_strength_6m",
]
VALUATION_FACTORS = [
    "pe", "pb", "ev_ebitda", "ev_revenue", "price_to_fcf", "fcf_yield",
    "earnings_yield", "peg", "market_cap",
]

ALL_FACTORS = FUNDAMENTAL_FACTORS + MARKET_FACTORS + VALUATION_FACTORS


@dataclass
class FeaturePanel:
    """Painel de fatores + metadados de proveniência."""

    as_of: pd.Timestamp
    market: str
    frame: pd.DataFrame
    sectors: pd.Series
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def tickers(self) -> list[str]:
        return list(self.frame.index)

    def coverage(self) -> pd.Series:
        """Fração de fatores disponíveis por ticker."""
        if self.frame.empty:
            return pd.Series(dtype=float)
        return self.frame.notna().mean(axis=1)


class FeatureBuilder:
    def __init__(self, repo: Repository, market: MarketConfig) -> None:
        self.repo = repo
        self.market = market

    def build(
        self,
        tickers: list[str],
        as_of: str | pd.Timestamp,
        benchmark_ticker: str | None = None,
        price_lookback_days: int = 800,
    ) -> FeaturePanel:
        as_of_ts = pd.Timestamp(as_of)
        as_of_str = as_of_ts.strftime("%Y-%m-%d")
        start = (as_of_ts - pd.Timedelta(days=price_lookback_days)).strftime("%Y-%m-%d")
        benchmark_ticker = benchmark_ticker or self.market.benchmark

        prices = self.repo.price_panel(tickers, start=start, end=as_of_str, field="adj_close")
        volumes = self.repo.price_panel(tickers, start=start, end=as_of_str, field="volume")
        bench_panel = self.repo.price_panel([benchmark_ticker], start=start, end=as_of_str)
        bench = (
            bench_panel[benchmark_ticker]
            if not bench_panel.empty and benchmark_ticker in bench_panel
            else pd.Series(dtype=float)
        )

        fundamentals = self.repo.fundamentals_as_of(
            tickers, as_of_str, metrics=FUNDAMENTAL_FACTORS + VALUATION_INPUTS
        )
        fund_wide = (
            fundamentals.pivot_table(index="ticker", columns="metric", values="value",
                                     aggfunc="last")
            if not fundamentals.empty else pd.DataFrame(index=pd.Index([], name="ticker"))
        )

        rows: dict[str, dict[str, float]] = {}
        stale: dict[str, int] = {}
        for ticker in tickers:
            row: dict[str, float] = {}
            px = prices[ticker].dropna() if ticker in prices else pd.Series(dtype=float)
            vol = volumes[ticker].dropna() if ticker in volumes else pd.Series(dtype=float)

            row.update(self._market_factors(px, vol, bench, as_of_ts))
            fund_row = (
                fund_wide.loc[ticker].to_dict() if ticker in fund_wide.index else {}
            )
            for factor in FUNDAMENTAL_FACTORS:
                row[factor] = float(fund_row[factor]) if _present(fund_row.get(factor)) else np.nan

            last_price = float(px.iloc[-1]) if not px.empty else None
            shares = fund_row.get("shares_outstanding")
            multiples = compute_multiples(
                price=last_price,
                shares_outstanding=float(shares) if _present(shares) else None,
                fundamentals={k: (float(v) if _present(v) else None)
                              for k, v in fund_row.items()},
            )
            for factor in VALUATION_FACTORS:
                value = multiples.get(factor)
                row[factor] = float(value) if value is not None else np.nan

            # Idade do fundamento mais recente: um ROE de 14 meses atrás não é
            # o mesmo dado que um ROE de 2 meses atrás.
            if not fundamentals.empty and ticker in set(fundamentals["ticker"]):
                pubs = fundamentals.loc[fundamentals["ticker"] == ticker, "publication_date"]
                age = (as_of_ts - pd.Timestamp(max(pubs))).days
                row["fundamental_age_days"] = float(age)
                stale[ticker] = int(age)
            else:
                row["fundamental_age_days"] = np.nan

            row["liquidity_median_traded_value"] = tech.median_traded_value(px, vol, as_of_ts)
            row["last_price"] = last_price if last_price is not None else np.nan
            rows[ticker] = row

        frame = pd.DataFrame.from_dict(rows, orient="index")
        frame.index.name = "ticker"
        sectors = pd.Series(self.repo.sector_map(tickers)).reindex(frame.index).fillna("UNKNOWN")

        estimated = 0
        if not fundamentals.empty:
            estimated = int(fundamentals["publication_date_is_estimated"].sum())
        provenance = {
            "as_of": as_of_str,
            "market": self.market.code,
            "benchmark": benchmark_ticker,
            "n_tickers_requested": len(tickers),
            "n_tickers_with_prices": int(sum(1 for t in tickers if t in prices)),
            "n_fundamental_rows_used": 0 if fundamentals.empty else int(len(fundamentals)),
            "n_fundamental_rows_estimated_publication": estimated,
            "allow_estimated_publication_dates": self.repo.policy.allow_estimated,
            "median_fundamental_age_days": (
                float(np.median(list(stale.values()))) if stale else None
            ),
            "benchmark_available": not bench.empty,
        }
        return FeaturePanel(as_of=as_of_ts, market=self.market.code, frame=frame,
                            sectors=sectors, provenance=provenance)

    # ------------------------------------------------------------- internos
    def _market_factors(
        self, px: pd.Series, vol: pd.Series, bench: pd.Series, as_of: pd.Timestamp
    ) -> dict[str, float]:
        out: dict[str, float] = dict.fromkeys(MARKET_FACTORS, np.nan)
        if px.empty:
            return out
        out.update(mom.momentum_set(px, as_of))

        rets = simple_returns(px).dropna()
        out["volatility_12m"] = tech.realized_volatility(
            rets, as_of, window=self.market.trading_days_per_year,
            periods_per_year=self.market.trading_days_per_year,
        )
        out["max_drawdown_12m"] = max_drawdown(rets.tail(self.market.trading_days_per_year))
        out["ma_distance_50"] = tech.ma_distance(px, as_of, 50)
        out["ma_distance_200"] = tech.ma_distance(px, as_of, 200)
        out["volume_trend"] = tech.volume_trend(vol, as_of)
        out["relative_volume"] = tech.relative_volume(vol, as_of)
        out["distance_from_high_12m"] = tech.distance_from_high(px, as_of)

        if not bench.empty:
            bench_rets = simple_returns(bench).dropna()
            out["beta"] = beta_fn(rets.tail(self.market.trading_days_per_year),
                                  bench_rets.tail(self.market.trading_days_per_year))
            out["relative_strength_6m"] = mom.relative_strength(px, bench, as_of, 182)
        return out


def _present(value: Any) -> bool:
    return value is not None and not (isinstance(value, float) and np.isnan(value)) \
        and not pd.isna(value)
