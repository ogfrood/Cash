"""Formatação de saída para terminal. Sem dependência externa."""

from __future__ import annotations

from typing import Any

import pandas as pd


def rule(title: str = "", width: int = 78, char: str = "─") -> str:
    if not title:
        return char * width
    pad = max(width - len(title) - 3, 0)
    return f"{char * 2} {title} {char * pad}"


def fmt_pct(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def fmt_num(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value):.{digits}f}"


def fmt_money(value: Any, currency: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    v = float(value)
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(v) >= div:
            return f"{currency}{v / div:,.2f}{unit}"
    return f"{currency}{v:,.2f}"


PERCENT_METRICS = {
    "total_return", "cagr", "volatility", "max_drawdown", "win_rate", "excess_return",
    "benchmark_total_return", "benchmark_cagr", "benchmark_volatility",
    "benchmark_max_drawdown", "alpha_annualized", "tracking_error", "var_95", "cvar_95",
    "cost_drag_on_total_return", "risk_free_annual_used", "turnover_annual",
}


def metrics_block(metrics: dict[str, Any], keys: list[str] | None = None) -> str:
    keys = keys or list(metrics)
    lines = []
    for key in keys:
        if key not in metrics:
            continue
        value = metrics[key]
        rendered = fmt_pct(value) if key in PERCENT_METRICS else fmt_num(value)
        lines.append(f"  {key:<34s} {rendered:>14s}")
    return "\n".join(lines)


def table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "  (vazio)"
    return df.head(max_rows).to_string(index=False)
