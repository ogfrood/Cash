"""Derivação de métricas a partir das linhas brutas de demonstração.

Executado uma vez por (ticker, data de publicação): para cada documento
publicado, recalculamos as métricas com **apenas o que era público naquele
momento**. O resultado é uma série histórica de métricas que reflete o que se
sabia em cada data, e não o que se sabe hoje.

É deliberadamente mais caro do que calcular uma vez com os dados atuais. O
custo é o preço de não mentir no backtest.
"""

from __future__ import annotations

from collections.abc import Iterable

from irai.core.db.repository import Repository
from irai.markets.stocks.fundamentals.metrics import FundamentalsCalculator


def derive_for_ticker(repo: Repository, ticker: str, source: str = "derived") -> int:
    """Calcula e grava as métricas derivadas de um ticker, período a período."""
    publications = repo.db.query(
        """
        SELECT DISTINCT publication_date FROM financials
        WHERE ticker = ? ORDER BY publication_date
        """,
        (ticker,),
    )
    total = 0
    for row in publications:
        as_of = row["publication_date"]
        # allow_estimated=True aqui de propósito: a decisão de usar ou não uma
        # data estimada é do CONSUMIDOR (o backtest), não do cálculo. A flag
        # é propagada para a métrica derivada e o filtro acontece na leitura.
        financials = repo.financials_as_of([ticker], as_of, allow_estimated=True)
        if financials.empty:
            continue
        results = FundamentalsCalculator(financials).compute_all()
        rows = [r.as_row(ticker, source=source) for r in results]
        total += repo.upsert_fundamentals(rows)
    return total


def derive_for_tickers(
    repo: Repository, tickers: Iterable[str], source: str = "derived"
) -> dict[str, int]:
    return {ticker: derive_for_ticker(repo, ticker, source) for ticker in tickers}
