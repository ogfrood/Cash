"""Métricas de risco e de risco-retorno.

Todas medem o PASSADO da janela informada. Nenhuma delas prevê risco futuro —
e o relatório é obrigado a dizer isso (ver core/ai/guardrails.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from irai.core.quant.returns import annualize_return, annualize_volatility, cumulative_return


def max_drawdown(returns: pd.Series) -> float:
    """Maior queda de pico a vale, em fração (valor negativo)."""
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    curve = (1.0 + clean).cumprod()
    peak = curve.cummax()
    return float((curve / peak - 1.0).min())


def drawdown_series(returns: pd.Series) -> pd.Series:
    curve = (1.0 + returns.fillna(0.0)).cumprod()
    return curve / curve.cummax() - 1.0


def max_drawdown_duration(returns: pd.Series) -> int:
    """Nº de períodos entre o pico e a recuperação mais longa (ou até o fim)."""
    dd = drawdown_series(returns)
    if dd.empty:
        return 0
    longest = current = 0
    for value in dd:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def _excess(returns: pd.Series, risk_free_annual: float, periods_per_year: int) -> pd.Series:
    rf_period = (1.0 + risk_free_annual) ** (1.0 / periods_per_year) - 1.0
    return returns.dropna() - rf_period


def sharpe_ratio(returns: pd.Series, risk_free_annual: float, periods_per_year: int) -> float:
    """Sharpe anualizado.

    No Brasil isto importa mais do que parece: com CDI em dois dígitos, um
    Sharpe calculado contra risk-free zero fica inflado e sem significado.
    """
    ex = _excess(returns, risk_free_annual, periods_per_year)
    if len(ex) < 2:
        return float("nan")
    sd = ex.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return float("nan")
    return float(ex.mean() / sd * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, risk_free_annual: float, periods_per_year: int) -> float:
    """Sortino: penaliza apenas o desvio negativo."""
    ex = _excess(returns, risk_free_annual, periods_per_year)
    if len(ex) < 2:
        return float("nan")
    downside = ex[ex < 0]
    if downside.empty:
        return float("inf")
    dd = np.sqrt((downside**2).mean())
    if dd == 0:
        return float("nan")
    return float(ex.mean() / dd * np.sqrt(periods_per_year))


def calmar_ratio(returns: pd.Series, periods_per_year: int) -> float:
    total = cumulative_return(returns)
    cagr = annualize_return(total, len(returns.dropna()), periods_per_year)
    mdd = max_drawdown(returns)
    if not np.isfinite(mdd) or mdd == 0:
        return float("nan")
    return float(cagr / abs(mdd))


def beta(returns: pd.Series, benchmark: pd.Series) -> float:
    """Beta contra o benchmark, alinhando as datas em comum."""
    joined = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
    if len(joined) < 20:
        return float("nan")
    x = joined.iloc[:, 1]
    y = joined.iloc[:, 0]
    var = x.var(ddof=1)
    if var == 0 or not np.isfinite(var):
        return float("nan")
    return float(y.cov(x) / var)


def alpha_annualized(
    returns: pd.Series, benchmark: pd.Series, risk_free_annual: float, periods_per_year: int
) -> float:
    """Alpha de Jensen anualizado. Interpretação exige cuidado: é o resíduo de
    um modelo de um fator, não 'talento'."""
    b = beta(returns, benchmark)
    if not np.isfinite(b):
        return float("nan")
    joined = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
    rf_period = (1.0 + risk_free_annual) ** (1.0 / periods_per_year) - 1.0
    r = joined.iloc[:, 0].mean()
    m = joined.iloc[:, 1].mean()
    per_period_alpha = (r - rf_period) - b * (m - rf_period)
    return float((1.0 + per_period_alpha) ** periods_per_year - 1.0)


def tracking_error(returns: pd.Series, benchmark: pd.Series, periods_per_year: int) -> float:
    joined = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
    if len(joined) < 2:
        return float("nan")
    diff = joined.iloc[:, 0] - joined.iloc[:, 1]
    return float(diff.std(ddof=1) * np.sqrt(periods_per_year))


def information_ratio(returns: pd.Series, benchmark: pd.Series, periods_per_year: int) -> float:
    te = tracking_error(returns, benchmark, periods_per_year)
    if not np.isfinite(te) or te == 0:
        return float("nan")
    joined = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
    diff = joined.iloc[:, 0] - joined.iloc[:, 1]
    return float(diff.mean() * periods_per_year / te)


def win_rate(returns: pd.Series) -> float:
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    return float((clean > 0).mean())


def value_at_risk(returns: pd.Series, level: float = 0.05) -> float:
    """VaR histórico. Não é o pior caso — é o quantil da amostra observada."""
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    return float(np.quantile(clean, level))


def conditional_value_at_risk(returns: pd.Series, level: float = 0.05) -> float:
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    var = np.quantile(clean, level)
    tail = clean[clean <= var]
    return float(tail.mean()) if not tail.empty else float("nan")


def risk_summary(
    returns: pd.Series,
    benchmark: pd.Series | None,
    risk_free_annual: float,
    periods_per_year: int,
) -> dict[str, float]:
    """Pacote completo de métricas — o mesmo dicionário usado por backtest,
    paper trading e relatório, para não existirem duas definições de Sharpe."""
    total = cumulative_return(returns)
    n = len(returns.dropna())
    out: dict[str, float] = {
        "total_return": total,
        "cagr": annualize_return(total, n, periods_per_year),
        "volatility": annualize_volatility(returns, periods_per_year),
        "sharpe": sharpe_ratio(returns, risk_free_annual, periods_per_year),
        "sortino": sortino_ratio(returns, risk_free_annual, periods_per_year),
        "calmar": calmar_ratio(returns, periods_per_year),
        "max_drawdown": max_drawdown(returns),
        "max_drawdown_duration_periods": float(max_drawdown_duration(returns)),
        "win_rate": win_rate(returns),
        "var_95": value_at_risk(returns, 0.05),
        "cvar_95": conditional_value_at_risk(returns, 0.05),
        "n_periods": float(n),
        "risk_free_annual_used": float(risk_free_annual),
    }
    if benchmark is not None and not benchmark.dropna().empty:
        bench_total = cumulative_return(benchmark)
        out.update({
            "benchmark_total_return": bench_total,
            "benchmark_cagr": annualize_return(bench_total, len(benchmark.dropna()), periods_per_year),
            "benchmark_volatility": annualize_volatility(benchmark, periods_per_year),
            "benchmark_max_drawdown": max_drawdown(benchmark),
            "excess_return": total - bench_total,
            "beta": beta(returns, benchmark),
            "alpha_annualized": alpha_annualized(returns, benchmark, risk_free_annual, periods_per_year),
            "tracking_error": tracking_error(returns, benchmark, periods_per_year),
            "information_ratio": information_ratio(returns, benchmark, periods_per_year),
        })
    return out
