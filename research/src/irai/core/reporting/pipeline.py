"""Orquestração de alto nível: da data de análise ao relatório.

Um único lugar onde as camadas se encontram, para que CLI, API e dashboard
usem exatamente o mesmo caminho — e não existam duas definições de "análise".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from irai.config import MarketConfig
from irai.core.ai.analyst import ResearchAnalyst, ResearchReport
from irai.core.ai.evidence import build_company_evidence
from irai.core.db.repository import Repository
from irai.core.features.builder import FeatureBuilder
from irai.core.predictions.historical import ConditionalEstimate
from irai.core.scoring.engine import ScoringEngine, ScoringResult
from irai.markets.stocks.valuation.multiples import valuation_summary

VALUATION_METRICS = ["pe", "pb", "ev_ebitda", "ev_revenue", "price_to_fcf",
                     "fcf_yield", "earnings_yield", "peg"]


@dataclass
class CompanyAnalysis:
    ticker: str
    as_of: str
    market: str
    panel_row: pd.Series
    scoring: ScoringResult
    explanation: dict[str, Any]
    valuation: dict[str, Any]
    evidence_hash: str
    report: ResearchReport | None = None


def analyze_company(
    repo: Repository,
    market: MarketConfig,
    scoring: ScoringEngine,
    ticker: str,
    as_of: str,
    universe: list[str],
    settings: Any,
    model_version: str = "stock-v1.0.0",
    historical: list[ConditionalEstimate] | None = None,
    write_report: bool = True,
) -> CompanyAnalysis:
    """Análise completa de uma empresa numa data, com relatório rastreável."""
    if ticker not in universe:
        universe = [*universe, ticker]

    panel = FeatureBuilder(repo, market).build(universe, as_of)
    if panel.frame.empty or ticker not in panel.frame.index:
        raise ValueError(f"Sem dados suficientes para {ticker} em {as_of}.")

    result = scoring.score(panel)
    explanation = result.explain(ticker)
    row = panel.frame.loc[ticker]

    # Valuation: múltiplo atual vs. própria história vs. pares NA MESMA data.
    peers_frame = panel.frame.loc[panel.sectors[panel.sectors == panel.sectors[ticker]].index]
    peer_multiples = peers_frame[
        [c for c in VALUATION_METRICS if c in peers_frame.columns]
    ].drop(index=ticker, errors="ignore")
    historical_multiples = _historical_multiples(repo, market, scoring, ticker, as_of)

    current = {m: (float(row[m]) if m in row and pd.notna(row[m]) else None)
               for m in VALUATION_METRICS}
    valuation = valuation_summary(
        current, historical_multiples, peer_multiples,
        peer_group=str(panel.sectors[ticker]),
        historical_window="até 5 anos de trimestres conhecidos na data",
    )

    company_row = repo.companies(tickers=[ticker])
    company = company_row.iloc[0].to_dict() if not company_row.empty else {}

    scores_dict = {
        k: (None if pd.isna(v) else float(v)) for k, v in result.scores.loc[ticker].items()
    }
    risk_metrics = {
        k: (None if pd.isna(row.get(k)) else float(row[k]))
        for k in ("volatility_12m", "beta", "max_drawdown_12m", "distance_from_high_12m")
        if k in row
    }

    packet = build_company_evidence(
        ticker=ticker, market=market.code, as_of=as_of,
        factors={k: (None if pd.isna(v) else float(v)) for k, v in row.items()},
        scores=scores_dict,
        score_explanation=explanation,
        valuation=valuation,
        risk=risk_metrics,
        historical=[h.to_dict() | {"sentence": h.sentence()} for h in (historical or [])] or None,
        provenance=panel.provenance,
        company=company,
    )

    report = None
    if write_report:
        report = ResearchAnalyst(repo, settings).write(packet, model_version)

    return CompanyAnalysis(
        ticker=ticker, as_of=as_of, market=market.code, panel_row=row,
        scoring=result, explanation=explanation, valuation=valuation,
        evidence_hash=packet.hash, report=report,
    )


def _historical_multiples(
    repo: Repository, market: MarketConfig, scoring: ScoringEngine,
    ticker: str, as_of: str, n_quarters: int = 20,
) -> pd.DataFrame | None:
    """Série histórica de múltiplos da própria empresa, reconstruída com os
    dados que eram conhecidos em cada data passada.

    Recalcular o histórico com os números de hoje daria uma "média histórica"
    que ninguém poderia ter calculado na época.
    """
    history = repo.fundamentals_history_as_of(
        [ticker], as_of,
        metrics=["eps_ttm", "net_income_ttm", "ebitda_ttm", "revenue_ttm",
                 "free_cash_flow", "total_equity", "total_debt", "cash",
                 "shares_outstanding"],
    )
    if history.empty:
        return None

    wide = history.pivot_table(index="publication_date", columns="metric", values="value",
                               aggfunc="last").sort_index().tail(n_quarters)
    if wide.empty:
        return None

    prices = repo.price_panel([ticker], end=as_of)
    if prices.empty or ticker not in prices:
        return None
    px = prices[ticker].dropna()

    from irai.markets.stocks.valuation.multiples import compute_multiples

    rows = []
    for pub_date, values in wide.iterrows():
        price = px.asof(pd.Timestamp(pub_date))
        if pd.isna(price):
            continue
        fundamentals = {k: (float(v) if pd.notna(v) else None) for k, v in values.items()}
        shares = fundamentals.get("shares_outstanding")
        multiples = compute_multiples(float(price), shares, fundamentals)
        rows.append({"date": pub_date, **{m: multiples.get(m) for m in VALUATION_METRICS}})

    return pd.DataFrame(rows).set_index("date") if rows else None
