"""Médias móveis, tendência de volume e distância de extremos.

Nada aqui é sinal de compra. São descrições do comportamento recente do preço
e do volume, usadas como insumo e como contexto no relatório.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def moving_average(prices: pd.Series, window: int) -> pd.Series:
    return prices.rolling(window=window, min_periods=max(2, window // 2)).mean()


def ma_distance(prices: pd.Series, as_of: pd.Timestamp, window: int) -> float:
    """Distância percentual entre o preço e sua média móvel, em `as_of`."""
    series = prices.loc[:pd.Timestamp(as_of)].dropna()
    if len(series) < max(2, window // 2):
        return float("nan")
    ma = series.rolling(window=window, min_periods=max(2, window // 2)).mean().iloc[-1]
    last = series.iloc[-1]
    if pd.isna(ma) or ma == 0:
        return float("nan")
    return float(last / ma - 1.0)


def ma_cross_state(prices: pd.Series, as_of: pd.Timestamp,
                   fast: int = 50, slow: int = 200) -> str:
    """Estado das médias: 'fast_above' | 'fast_below' | 'insufficient_data'."""
    series = prices.loc[:pd.Timestamp(as_of)].dropna()
    if len(series) < slow // 2:
        return "insufficient_data"
    f = series.rolling(fast, min_periods=fast // 2).mean().iloc[-1]
    s = series.rolling(slow, min_periods=slow // 2).mean().iloc[-1]
    if pd.isna(f) or pd.isna(s):
        return "insufficient_data"
    return "fast_above" if f > s else "fast_below"


def volume_trend(volume: pd.Series, as_of: pd.Timestamp,
                 short: int = 21, long: int = 252) -> float:
    """Volume médio curto / volume médio longo - 1.

    > 0 indica volume acima do normal da própria ação. É o insumo da separação
    entre movimento de preço e confirmação por fluxo.
    """
    series = volume.loc[:pd.Timestamp(as_of)].dropna()
    if len(series) < short:
        return float("nan")
    s = series.tail(short).mean()
    window_long = series.tail(long)
    if len(window_long) < short * 2 or window_long.mean() == 0:
        return float("nan")
    return float(s / window_long.mean() - 1.0)


def relative_volume(volume: pd.Series, as_of: pd.Timestamp, window: int = 63) -> float:
    """Volume do último dia contra a mediana da janela. Mediana, não média,
    porque um único dia de leilão distorce a média."""
    series = volume.loc[:pd.Timestamp(as_of)].dropna()
    if len(series) < 10:
        return float("nan")
    med = series.tail(window).median()
    if med == 0 or pd.isna(med):
        return float("nan")
    return float(series.iloc[-1] / med)


def median_traded_value(prices: pd.Series, volume: pd.Series, as_of: pd.Timestamp,
                        window: int = 63) -> float:
    """Mediana do volume financeiro negociado — o filtro de liquidez do backtest."""
    p = prices.loc[:pd.Timestamp(as_of)].dropna()
    v = volume.loc[:pd.Timestamp(as_of)].dropna()
    joined = pd.concat([p, v], axis=1, join="inner").dropna().tail(window)
    if joined.empty:
        return float("nan")
    return float((joined.iloc[:, 0] * joined.iloc[:, 1]).median())


def distance_from_high(prices: pd.Series, as_of: pd.Timestamp, window_days: int = 365) -> float:
    """Quanto o preço está abaixo da máxima da janela (valor <= 0)."""
    as_of = pd.Timestamp(as_of)
    series = prices.loc[as_of - pd.Timedelta(days=window_days):as_of].dropna()
    if series.empty:
        return float("nan")
    high = series.max()
    if high == 0 or pd.isna(high):
        return float("nan")
    return float(series.iloc[-1] / high - 1.0)


def rolling_correlation(a: pd.Series, b: pd.Series, window: int = 126) -> pd.Series:
    joined = pd.concat([a, b], axis=1, join="inner").dropna()
    if joined.empty:
        return pd.Series(dtype=float)
    return joined.iloc[:, 0].rolling(window, min_periods=window // 2).corr(joined.iloc[:, 1])


def realized_volatility(returns: pd.Series, as_of: pd.Timestamp,
                        window: int = 252, periods_per_year: int = 252) -> float:
    series = returns.loc[:pd.Timestamp(as_of)].dropna().tail(window)
    if len(series) < 20:
        return float("nan")
    return float(series.std(ddof=1) * np.sqrt(periods_per_year))
