"""Retornos e séries derivadas. Base de todo o resto.

Convenção do projeto: retornos SIMPLES para composição de carteira, retornos
LOG apenas onde a matemática exige (agregação temporal). Misturar os dois é
uma das fontes silenciosas de erro em sistemas quantitativos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def simple_returns(prices: pd.Series | pd.DataFrame, periods: int = 1) -> pd.Series | pd.DataFrame:
    """Retorno simples: P_t / P_{t-n} - 1."""
    return prices.pct_change(periods=periods, fill_method=None)


def log_returns(prices: pd.Series | pd.DataFrame, periods: int = 1) -> pd.Series | pd.DataFrame:
    return np.log(prices / prices.shift(periods))


def cumulative_return(returns: pd.Series) -> float:
    """Retorno total acumulado de uma série de retornos simples."""
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    return float((1.0 + clean).prod() - 1.0)


def equity_curve(returns: pd.Series, initial: float = 1.0) -> pd.Series:
    return initial * (1.0 + returns.fillna(0.0)).cumprod()


def total_return_between(prices: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Retorno entre duas datas usando os preços disponíveis <= cada data.

    Usa `asof` para não exigir que a data exata seja pregão — e nunca olha para
    frente.
    """
    series = prices.dropna()
    if series.empty:
        return float("nan")
    idx = series.index
    p0 = series.asof(pd.Timestamp(start))
    p1 = series.asof(pd.Timestamp(end))
    if pd.isna(p0) or pd.isna(p1) or p0 == 0 or pd.Timestamp(start) < idx[0]:
        return float("nan")
    return float(p1 / p0 - 1.0)


def annualize_return(total: float, n_periods: int, periods_per_year: int) -> float:
    """CAGR a partir de um retorno total e da duração em períodos."""
    if n_periods <= 0 or not np.isfinite(total) or total <= -1.0:
        return float("nan")
    years = n_periods / periods_per_year
    if years <= 0:
        return float("nan")
    return float((1.0 + total) ** (1.0 / years) - 1.0)


def annualize_volatility(returns: pd.Series, periods_per_year: int) -> float:
    clean = returns.dropna()
    if len(clean) < 2:
        return float("nan")
    return float(clean.std(ddof=1) * np.sqrt(periods_per_year))


def resample_returns(returns: pd.Series, rule: str) -> pd.Series:
    """Agrega retornos simples para outra frequência, compondo corretamente."""
    return (1.0 + returns.fillna(0.0)).resample(rule).prod() - 1.0
