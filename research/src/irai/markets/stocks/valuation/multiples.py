"""Motor de valuation: múltiplos, posição histórica e posição contra pares.

Princípio que o código respeita literalmente: **o sistema mostra onde o
múltiplo está; ele não diz "barato" ou "caro".** Essas duas palavras não
aparecem em nenhuma saída deste módulo. O que sai é: percentil histórico,
percentil contra pares, e a amostra usada para calcular cada um.

Um P/L no percentil 10 da própria história pode significar oportunidade ou
deterioração do negócio. O número não sabe a diferença — e nós também não.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class MultipleReading:
    """Uma leitura de múltiplo com todo o contexto necessário para interpretá-la."""

    metric: str
    value: float | None
    # posição contra a própria história
    historical_median: float | None = None
    historical_mean: float | None = None
    historical_percentile: float | None = None
    historical_n: int = 0
    historical_window: str | None = None
    # posição contra os pares
    peer_median: float | None = None
    peer_percentile: float | None = None
    peer_group: str | None = None
    peer_n: int = 0
    # interpretação EXPLÍCITA, nunca implícita
    vs_own_history: str = "insufficient_data"   # above | below | in_line | insufficient_data
    vs_peers: str = "insufficient_data"
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Distância da mediana, em fração, a partir da qual deixamos de chamar de
# "em linha". 15% é arbitrário — e por ser arbitrário, está aqui e não
# escondido no meio de um if.
IN_LINE_TOLERANCE = 0.15
MIN_HISTORICAL_OBS = 8
MIN_PEERS = 5


def _percentile_of(value: float, sample: pd.Series) -> float | None:
    clean = sample.dropna()
    if len(clean) < 3 or not np.isfinite(value):
        return None
    return float((clean < value).mean() * 100.0)


def _position(value: float | None, reference: float | None) -> str:
    if value is None or reference is None or not np.isfinite(value) or not np.isfinite(reference):
        return "insufficient_data"
    if reference == 0:
        return "insufficient_data"
    ratio = value / reference - 1.0
    if abs(ratio) <= IN_LINE_TOLERANCE:
        return "in_line"
    return "above" if ratio > 0 else "below"


def read_multiple(
    metric: str,
    current: float | None,
    history: pd.Series | None = None,
    peers: pd.Series | None = None,
    peer_group: str | None = None,
    historical_window: str | None = None,
) -> MultipleReading:
    """Monta a leitura completa de um múltiplo.

    `history` é a série do próprio ativo (valores conhecidos até a data de
    análise — o chamador é responsável por já ter aplicado o corte PIT).
    `peers` são os valores dos pares NA MESMA data.
    """
    reading = MultipleReading(metric=metric, value=current, peer_group=peer_group,
                              historical_window=historical_window)
    if current is None or not np.isfinite(current):
        reading.note = "Múltiplo indisponível para a data analisada."
        return reading

    if history is not None:
        clean = history.dropna()
        reading.historical_n = int(len(clean))
        if len(clean) >= MIN_HISTORICAL_OBS:
            reading.historical_median = float(clean.median())
            reading.historical_mean = float(clean.mean())
            reading.historical_percentile = _percentile_of(current, clean)
            reading.vs_own_history = _position(current, reading.historical_median)
        else:
            reading.note = (
                f"Histórico insuficiente: {len(clean)} observações, "
                f"mínimo {MIN_HISTORICAL_OBS}."
            )

    if peers is not None:
        clean_peers = peers.dropna()
        reading.peer_n = int(len(clean_peers))
        if len(clean_peers) >= MIN_PEERS:
            reading.peer_median = float(clean_peers.median())
            reading.peer_percentile = _percentile_of(current, clean_peers)
            reading.vs_peers = _position(current, reading.peer_median)

    return reading


def compute_multiples(
    price: float | None,
    shares_outstanding: float | None,
    fundamentals: dict[str, float | None],
) -> dict[str, float | None]:
    """Calcula os múltiplos da V1 a partir de preço e fundamentos TTM.

    Convenções declaradas (e não escondidas):
    - Denominador negativo devolve None, não um múltiplo negativo. P/L de -8
      não é "mais barato" que P/L 20; é uma empresa com prejuízo, e isso é
      informação diferente.
    - EV = market cap + dívida bruta - caixa.
    """
    out: dict[str, float | None] = {}
    if price is None or shares_outstanding in (None, 0) or not np.isfinite(price):
        return {k: None for k in
                ("market_cap", "pe", "pb", "ev_ebitda", "ev_revenue", "price_to_fcf",
                 "fcf_yield", "earnings_yield", "peg")}

    market_cap = price * shares_outstanding
    out["market_cap"] = market_cap

    def pos_div(num: float | None, den: float | None) -> float | None:
        if num is None or den is None or den <= 0 or not np.isfinite(den):
            return None
        val = num / den
        return float(val) if np.isfinite(val) else None

    eps = fundamentals.get("eps_ttm")
    net_income = fundamentals.get("net_income_ttm")
    equity = fundamentals.get("total_equity")
    ebitda = fundamentals.get("ebitda_ttm")
    revenue = fundamentals.get("revenue_ttm")
    fcf = fundamentals.get("free_cash_flow")
    debt = fundamentals.get("total_debt") or 0.0
    cash = fundamentals.get("cash") or 0.0

    out["pe"] = pos_div(price, eps) if eps is not None else pos_div(market_cap, net_income)
    out["pb"] = pos_div(market_cap, equity)

    enterprise_value = market_cap + debt - cash
    out["enterprise_value"] = enterprise_value
    out["ev_ebitda"] = pos_div(enterprise_value, ebitda) if enterprise_value > 0 else None
    out["ev_revenue"] = pos_div(enterprise_value, revenue) if enterprise_value > 0 else None
    out["price_to_fcf"] = pos_div(market_cap, fcf)

    # Yields são o inverso — e funcionam com numerador negativo, ao contrário
    # dos múltiplos. Por isso são calculados separadamente.
    out["fcf_yield"] = float(fcf / market_cap) if fcf is not None and market_cap > 0 else None
    out["earnings_yield"] = (
        float(net_income / market_cap) if net_income is not None and market_cap > 0 else None
    )

    # PEG: só faz sentido com P/L positivo E crescimento positivo. Fora disso,
    # o número existe matematicamente e não significa nada.
    growth = fundamentals.get("earnings_growth_yoy")
    pe = out["pe"]
    if pe is not None and growth is not None and growth > 0:
        out["peg"] = float(pe / (growth * 100.0))
    else:
        out["peg"] = None

    return out


def valuation_summary(
    current_multiples: dict[str, float | None],
    historical_multiples: pd.DataFrame | None,
    peer_multiples: pd.DataFrame | None,
    peer_group: str | None,
    historical_window: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Leitura completa de todos os múltiplos, pronta para relatório e IA."""
    metrics = ["pe", "pb", "ev_ebitda", "ev_revenue", "price_to_fcf",
               "fcf_yield", "earnings_yield", "peg"]
    summary: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        history = (
            historical_multiples[metric]
            if historical_multiples is not None and metric in historical_multiples
            else None
        )
        peers = (
            peer_multiples[metric]
            if peer_multiples is not None and metric in peer_multiples
            else None
        )
        summary[metric] = read_multiple(
            metric=metric,
            current=current_multiples.get(metric),
            history=history,
            peers=peers,
            peer_group=peer_group,
            historical_window=historical_window,
        ).to_dict()
    return summary
