"""Momentum e força relativa.

Duas decisões que valem explicação:

1. **12-1 em vez de 12M puro.** A literatura de momentum (Jegadeesh & Titman e
   sucessores) exclui o mês mais recente porque ele carrega reversão de curto
   prazo. Usar 12M cheio mistura dois efeitos opostos.
2. **Tudo é calculado até `as_of` inclusive, e a execução acontece depois.**
   O lag de execução é aplicado pelo backtest, não aqui.
"""

from __future__ import annotations

import pandas as pd

from irai.core.quant.returns import total_return_between

# Aproximações em dias de calendário. Usamos `asof`, então não precisam ser
# exatas — precisam ser consistentes.
WINDOWS_DAYS = {
    "1m": 30,
    "3m": 91,
    "6m": 182,
    "12m": 365,
}


def momentum(prices: pd.Series, as_of: pd.Timestamp, lookback_days: int,
             skip_days: int = 0) -> float:
    """Retorno entre (as_of - lookback) e (as_of - skip)."""
    as_of = pd.Timestamp(as_of)
    start = as_of - pd.Timedelta(days=lookback_days)
    end = as_of - pd.Timedelta(days=skip_days)
    if end <= start:
        return float("nan")
    return total_return_between(prices, start, end)


def momentum_set(prices: pd.Series, as_of: pd.Timestamp) -> dict[str, float]:
    """Conjunto padrão de momentum usado pelo scoring."""
    return {
        "momentum_1m": momentum(prices, as_of, WINDOWS_DAYS["1m"]),
        "momentum_3m": momentum(prices, as_of, WINDOWS_DAYS["3m"]),
        "momentum_6m": momentum(prices, as_of, WINDOWS_DAYS["6m"]),
        "momentum_12m": momentum(prices, as_of, WINDOWS_DAYS["12m"]),
        # 12 meses excluindo o mês mais recente
        "momentum_12_1": momentum(prices, as_of, WINDOWS_DAYS["12m"], skip_days=WINDOWS_DAYS["1m"]),
    }


def relative_strength(prices: pd.Series, benchmark: pd.Series, as_of: pd.Timestamp,
                      lookback_days: int = 182) -> float:
    """Retorno do ativo menos retorno do benchmark na mesma janela.

    Força relativa é o que separa 'a ação subiu' de 'a ação subiu mais que o
    mercado'. Sem isto, todo backtest em bull market parece genial.
    """
    r = momentum(prices, as_of, lookback_days)
    b = momentum(benchmark, as_of, lookback_days)
    if pd.isna(r) or pd.isna(b):
        return float("nan")
    return float(r - b)
