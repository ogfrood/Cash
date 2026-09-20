"""Provedor sintético — dados fabricados, determinísticos, para teste e demo.

Existe por dois motivos:

1. **Testes não podem depender de rede.** Um teste que chama a Yahoo falha por
   motivos que nada têm a ver com o código.
2. **Demonstrar o encanamento sem enganar ninguém.** Todo dado gerado aqui
   carrega `source='synthetic'`, e qualquer backtest que o use sai com o
   carimbo DADOS SINTÉTICOS no relatório.

⚠️ AVISO QUE VALE PARA O PROJETO INTEIRO
Este gerador planta uma relação conhecida entre fundamentos e retorno futuro
(`signal_strength`). Isso torna o backtest sobre dados sintéticos **bom por
construção**. Ele prova que o encanamento funciona — não prova absolutamente
nada sobre o mercado real. Com `signal_strength=0.0` o gerador produz ruído
puro, que é o teste mais útil: se o sistema "acha" um sinal aí, há bug.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from irai.core.providers.base import DataProvider, FetchResult, ProviderCapabilities
from irai.core.providers.registry import register
from irai.markets.stocks.fundamentals import line_items as LI

SECTORS = ["Technology", "Financials", "Energy", "Healthcare", "Industrials",
           "Consumer", "Materials", "Utilities"]


@dataclass
class SyntheticConfig:
    n_companies: int = 40
    start: str = "2014-01-01"
    end: str = "2024-12-31"
    market: str = "US"
    seed: int = 20260920
    # Quanta relação existe entre a "qualidade" fabricada e o retorno futuro.
    # 0.0 = ruído puro. Ver aviso no topo do módulo.
    signal_strength: float = 0.35
    annual_drift: float = 0.07
    annual_vol: float = 0.28
    publication_lag_days: int = 45


class SyntheticProvider(DataProvider):
    """Gera empresas, preços diários e trimestres com data de publicação real."""

    def __init__(self, config: SyntheticConfig | None = None, **kwargs: object) -> None:
        if config is None:
            config = SyntheticConfig(**kwargs)  # type: ignore[arg-type]
        self.config = config
        self._rng = np.random.default_rng(config.seed)
        self._universe: pd.DataFrame | None = None
        self._prices: pd.DataFrame | None = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="synthetic",
            prices=True, fundamentals=True, dividends=True, company_info=True,
            provides_real_publication_dates=True,
            covers_delisted=True,
            markets=(self.config.market,),
            notes="DADOS FABRICADOS. Não representam nenhuma empresa real.",
            license_note="N/A — gerado localmente.",
        )

    # ------------------------------------------------------------- universo
    def _build_universe(self) -> pd.DataFrame:
        if self._universe is not None:
            return self._universe
        cfg = self.config
        rng = self._rng
        rows = []
        for i in range(cfg.n_companies):
            # "quality" é o fator latente que governa fundamentos e (se
            # signal_strength > 0) parte do retorno futuro.
            quality = float(rng.normal(0.0, 1.0))
            rows.append({
                "ticker": f"SYN{i:03d}",
                "market": cfg.market,
                "name": f"Synthetic Company {i:03d}",
                "sector": SECTORS[i % len(SECTORS)],
                "industry": f"{SECTORS[i % len(SECTORS)]} — subsetor {i % 3}",
                "currency": "USD" if cfg.market == "US" else "BRL",
                "country": "US" if cfg.market == "US" else "BR",
                "source": "synthetic",
                "_quality": quality,
                "_base_price": float(rng.uniform(8, 180)),
                "_shares": float(rng.uniform(2e8, 4e9)),
                "_base_revenue": float(rng.uniform(1e9, 6e10)),
                "_base_margin": float(np.clip(0.10 + 0.05 * quality + rng.normal(0, 0.03), 0.01, 0.45)),
            })
        self._universe = pd.DataFrame(rows)
        return self._universe

    def fetch_company_info(self, tickers: list[str] | None = None) -> FetchResult:
        uni = self._build_universe()
        cols = ["ticker", "market", "name", "sector", "industry", "currency", "country", "source"]
        df = uni[cols]
        if tickers:
            df = df[df["ticker"].isin(tickers)]
        return FetchResult(frame=df, rows=df.to_dict("records"),
                           warnings=["Cadastro sintético — empresas não existem."])

    # --------------------------------------------------------------- preços
    def fetch_prices(self, tickers: list[str] | None = None,
                     start: str | None = None, end: str | None = None) -> FetchResult:
        cfg = self.config
        uni = self._build_universe()
        dates = pd.bdate_range(start or cfg.start, end or cfg.end)
        n = len(dates)
        rng = np.random.default_rng(cfg.seed + 1)

        daily_drift = cfg.annual_drift / 252.0
        daily_vol = cfg.annual_vol / np.sqrt(252.0)
        # Fator de mercado comum: sem ele, todas as ações seriam independentes
        # e o beta do portfólio daria zero — irrealista e inútil para testar.
        market_factor = rng.normal(daily_drift * 0.6, daily_vol * 0.55, n)

        frames = []
        for _, row in uni.iterrows():
            idio = rng.normal(0.0, daily_vol * 0.8, n)
            # O efeito da "qualidade" entra com DEFASAGEM: a qualidade do
            # trimestre publicado influencia o retorno DOS MESES SEGUINTES.
            tilt = cfg.signal_strength * row["_quality"] * daily_drift
            beta_i = float(np.clip(rng.normal(1.0, 0.3), 0.2, 2.0))
            returns = beta_i * market_factor + idio + tilt
            price = row["_base_price"] * np.exp(np.cumsum(returns - 0.5 * np.var(returns)))
            volume = np.abs(rng.lognormal(np.log(row["_shares"] * 0.002), 0.6, n))
            frames.append(pd.DataFrame({
                "ticker": row["ticker"],
                "date": dates,
                "open": price * (1 + rng.normal(0, 0.002, n)),
                "high": price * (1 + np.abs(rng.normal(0, 0.006, n))),
                "low": price * (1 - np.abs(rng.normal(0, 0.006, n))),
                "close": price,
                "adj_close": price,
                "volume": volume,
                "currency": row["currency"],
            }))

        df = pd.concat(frames, ignore_index=True)
        if tickers:
            df = df[df["ticker"].isin(tickers)]
        self._prices = df
        return FetchResult(frame=df, warnings=["Preços sintéticos."])

    def fetch_benchmark(self, start: str | None = None, end: str | None = None) -> FetchResult:
        """Índice sintético equiponderado — o benchmark da demo."""
        prices = self._prices if self._prices is not None else self.fetch_prices().frame
        panel = prices.pivot_table(index="date", columns="ticker", values="adj_close")
        index_level = (panel / panel.iloc[0]).mean(axis=1) * 1000.0
        df = pd.DataFrame({
            "ticker": "^SYNX",
            "date": index_level.index,
            "open": index_level.values,
            "high": index_level.values,
            "low": index_level.values,
            "close": index_level.values,
            "adj_close": index_level.values,
            "volume": 0.0,
            "currency": "USD" if self.config.market == "US" else "BRL",
        })
        return FetchResult(frame=df, warnings=["Benchmark sintético equiponderado."])

    # ---------------------------------------------------------- fundamentos
    def fetch_financials(self, tickers: list[str] | None = None) -> FetchResult:
        """Trimestres com data de publicação REAL (fim do período + lag fixo).

        Esta é a diferença essencial em relação ao `yfinance`: aqui o carimbo
        de publicação existe, então o backtest não precisa descartar nada.
        """
        cfg = self.config
        uni = self._build_universe()
        rng = np.random.default_rng(cfg.seed + 2)
        quarters = pd.date_range(cfg.start, cfg.end, freq="QE")
        rows: list[dict] = []

        for _, comp in uni.iterrows():
            if tickers and comp["ticker"] not in tickers:
                continue
            revenue = comp["_base_revenue"]
            margin = comp["_base_margin"]
            equity = revenue * 0.8
            debt = revenue * float(rng.uniform(0.1, 0.9))
            cash = revenue * float(rng.uniform(0.05, 0.35))
            shares = comp["_shares"]
            growth_base = 0.01 + 0.012 * comp["_quality"]

            for q in quarters:
                growth = growth_base + float(rng.normal(0, 0.02))
                revenue *= (1.0 + growth)
                margin = float(np.clip(margin + rng.normal(0, 0.004), 0.01, 0.5))
                q_rev = revenue / 4.0
                gross = q_rev * float(np.clip(margin * 2.2, 0.05, 0.85))
                op = q_rev * margin
                da = q_rev * 0.05
                ebitda = op + da
                interest = debt * 0.06 / 4.0
                pretax = op - interest
                tax = max(pretax, 0.0) * 0.25
                net = pretax - tax
                ocf = net + da + float(rng.normal(0, q_rev * 0.02))
                capex = q_rev * float(rng.uniform(0.02, 0.09))
                equity += net * 0.6
                debt *= float(1.0 + rng.normal(-0.004 * comp["_quality"], 0.02))
                debt = max(debt, 0.0)
                cash += ocf - capex - net * 0.2
                shares *= float(1.0 + rng.normal(-0.0005 * comp["_quality"], 0.002))

                period_end = q.strftime("%Y-%m-%d")
                pub = (q + pd.Timedelta(days=cfg.publication_lag_days)).strftime("%Y-%m-%d")
                common = {
                    "ticker": comp["ticker"], "period_end": period_end, "period_type": "Q",
                    "period_start": (q - pd.offsets.QuarterBegin(startingMonth=1)).strftime("%Y-%m-%d"),
                    "fiscal_year": int(q.year), "fiscal_period": f"Q{q.quarter}",
                    "publication_date": pub, "publication_date_is_estimated": 0,
                    "currency": comp["currency"], "source": "synthetic", "unit": "unit",
                    "document_id": f"SYN-{comp['ticker']}-{period_end}",
                }
                for statement, item, value in (
                    ("income", LI.REVENUE, q_rev),
                    ("income", LI.GROSS_PROFIT, gross),
                    ("income", LI.OPERATING_INCOME, op),
                    ("income", LI.EBITDA, ebitda),
                    ("income", LI.DEPRECIATION_AMORTIZATION, da),
                    ("income", LI.INTEREST_EXPENSE, interest),
                    ("income", LI.PRETAX_INCOME, pretax),
                    ("income", LI.INCOME_TAX, tax),
                    ("income", LI.NET_INCOME, net),
                    ("income", LI.EPS_DILUTED, net / shares if shares else None),
                    ("balance", LI.TOTAL_EQUITY, equity),
                    ("balance", LI.TOTAL_ASSETS, equity + debt + cash),
                    ("balance", LI.TOTAL_DEBT, debt),
                    ("balance", LI.CASH_AND_EQUIVALENTS, cash),
                    ("balance", LI.CURRENT_ASSETS, cash + q_rev * 0.5),
                    ("balance", LI.CURRENT_LIABILITIES, q_rev * 0.4),
                    ("balance", LI.SHARES_OUTSTANDING, shares),
                    ("cashflow", LI.OPERATING_CASH_FLOW, ocf),
                    ("cashflow", LI.CAPEX, -capex),
                ):
                    rows.append({**common, "statement": statement,
                                 "line_item": item, "value": value})

        return FetchResult(rows=rows, frame=pd.DataFrame(rows),
                           warnings=["Demonstrações sintéticas com data de publicação fabricada."])


register("synthetic", SyntheticProvider)
