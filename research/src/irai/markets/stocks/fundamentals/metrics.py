"""Cálculo de métricas fundamentalistas a partir das linhas brutas.

Duas regras inegociáveis:

1. **Herança de data de publicação.** Uma métrica derivada não pode ser mais
   "antiga" que o insumo mais recente que a compôs. ROE calculado com um
   balanço publicado em 15/05 tem `publication_date = 15/05`, mesmo que o
   período termine em 31/03.
2. **Rastreabilidade.** Cada métrica grava, em `inputs_json`, quais linhas e
   quais períodos entraram no cálculo. É o que permite a IA citar a origem de
   um número em vez de afirmá-lo.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from irai.markets.stocks.fundamentals import line_items as LI


@dataclass
class MetricResult:
    metric: str
    value: float | None
    period_end: str
    period_type: str
    publication_date: str
    publication_date_is_estimated: bool
    inputs: dict[str, Any] = field(default_factory=dict)

    def as_row(self, ticker: str, source: str, currency: str | None = None) -> dict[str, Any]:
        return {
            "ticker": ticker,
            "metric": self.metric,
            "period_end": self.period_end,
            "period_type": self.period_type,
            "value": self.value,
            "currency": currency,
            "publication_date": self.publication_date,
            "publication_date_is_estimated": int(self.publication_date_is_estimated),
            "inputs": self.inputs,
            "source": source,
        }


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Divisão que devolve None em vez de explodir ou mentir.

    Denominador negativo em razões como P/L produz número sem significado
    econômico (patrimônio líquido negativo, lucro negativo). Devolvemos None e
    a métrica aparece como indisponível, em vez de como um múltiplo 'barato'.
    """
    if numerator is None or denominator is None:
        return None
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None
    if denominator == 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def _positive_only_div(numerator: float | None, denominator: float | None) -> float | None:
    """Para múltiplos onde denominador <= 0 torna o número interpretável ao
    contrário (P/L com lucro negativo 'parece' barato)."""
    if denominator is None or denominator <= 0:
        return None
    return _safe_div(numerator, denominator)


class FundamentalsCalculator:
    """Transforma um painel de linhas brutas em métricas, preservando PIT."""

    def __init__(self, financials: pd.DataFrame) -> None:
        """`financials` é a saída de Repository.financials_as_of para UM ticker."""
        self.raw = financials
        self._by_item: dict[str, pd.DataFrame] = {}
        if not financials.empty:
            for item, chunk in financials.groupby("line_item"):
                self._by_item[str(item)] = chunk.sort_values("period_end")

    # ------------------------------------------------------------- acesso
    def latest(self, item: str, period_type: str | None = None) -> tuple[float | None, dict[str, Any]]:
        """Último valor conhecido do item, com metadados de rastreabilidade."""
        chunk = self._by_item.get(item)
        if chunk is None or chunk.empty:
            return None, {}
        if period_type:
            chunk = chunk[chunk["period_type"] == period_type]
            if chunk.empty:
                return None, {}
        row = chunk.iloc[-1]
        meta = {
            "line_item": item,
            "period_end": row["period_end"],
            "period_type": row["period_type"],
            "publication_date": row["publication_date"],
            "estimated": bool(row["publication_date_is_estimated"]),
            "source": row["source"],
        }
        value = row["value"]
        return (None if pd.isna(value) else float(value)), meta

    def ttm(self, item: str, n_quarters: int = 4) -> tuple[float | None, dict[str, Any]]:
        """Soma dos últimos `n_quarters` trimestres para itens de FLUXO.

        Para itens de ESTOQUE, somar não faz sentido — devolvemos o último
        valor. Este é exatamente o erro que produz ROE de 4x o correto.
        """
        chunk = self._by_item.get(item)
        if chunk is None or chunk.empty:
            return None, {}
        if not LI.is_flow(item):
            return self.latest(item)
        q = chunk[chunk["period_type"] == "Q"].sort_values("period_end")
        if len(q) < n_quarters:
            annual = chunk[chunk["period_type"] == "A"]
            if not annual.empty:
                row = annual.iloc[-1]
                return (None if pd.isna(row["value"]) else float(row["value"])), {
                    "line_item": item, "period_end": row["period_end"], "period_type": "A",
                    "publication_date": row["publication_date"],
                    "estimated": bool(row["publication_date_is_estimated"]),
                    "source": row["source"], "note": "TTM indisponível; usado exercício anual",
                }
            return None, {}
        window = q.tail(n_quarters)
        if window["value"].isna().any():
            return None, {}
        return float(window["value"].sum()), {
            "line_item": item,
            "period_end": window.iloc[-1]["period_end"],
            "period_type": "TTM",
            "periods": list(window["period_end"]),
            # A publicação da métrica é a MAIS RECENTE das publicações usadas.
            "publication_date": max(window["publication_date"]),
            "estimated": bool(window["publication_date_is_estimated"].any()),
            "source": window.iloc[-1]["source"],
        }

    def average_stock(self, item: str, n_periods: int = 2) -> tuple[float | None, dict[str, Any]]:
        """Média de um item de estoque entre períodos.

        ROE correto usa patrimônio MÉDIO do período, não o patrimônio final —
        senão uma empresa que fez aumento de capital no fim do ano aparece com
        rentabilidade artificialmente baixa.
        """
        chunk = self._by_item.get(item)
        if chunk is None or chunk.empty:
            return None, {}
        window = chunk.sort_values("period_end").tail(n_periods)
        if window["value"].isna().any() or window.empty:
            return None, {}
        return float(window["value"].mean()), {
            "line_item": item,
            "period_end": window.iloc[-1]["period_end"],
            "periods": list(window["period_end"]),
            "publication_date": max(window["publication_date"]),
            "estimated": bool(window["publication_date_is_estimated"].any()),
            "source": window.iloc[-1]["source"],
            "note": f"média de {len(window)} períodos",
        }

    # ---------------------------------------------------------- derivadas
    def compute_all(self) -> list[MetricResult]:
        """Calcula o conjunto de métricas da V1."""
        if self.raw.empty:
            return []
        results: list[MetricResult] = []

        def emit(metric: str, value: float | None, metas: Sequence[dict[str, Any]],
                 unit: str | None = None) -> None:
            metas = [m for m in metas if m]
            if not metas:
                return
            pubs = [m["publication_date"] for m in metas if m.get("publication_date")]
            ends = [m["period_end"] for m in metas if m.get("period_end")]
            if not pubs or not ends:
                return
            # A métrica derivada nunca pode ser mais "antiga" que o insumo mais
            # recente: a publicação é o MÁXIMO das publicações usadas.
            pub = max(pubs)
            est = any(m.get("estimated") for m in metas)
            period_end = max(ends)
            results.append(MetricResult(
                metric=metric, value=value, period_end=period_end,
                period_type="TTM", publication_date=pub,
                publication_date_is_estimated=est,
                inputs={"unit": unit, "components": list(metas)},
            ))

        rev, m_rev = self.ttm(LI.REVENUE)
        gp, m_gp = self.ttm(LI.GROSS_PROFIT)
        op, m_op = self.ttm(LI.OPERATING_INCOME)
        ni, m_ni = self.ttm(LI.NET_INCOME)
        ebitda, m_eb = self.ttm(LI.EBITDA)
        ocf, m_ocf = self.ttm(LI.OPERATING_CASH_FLOW)
        capex, m_cx = self.ttm(LI.CAPEX)
        interest, m_int = self.ttm(LI.INTEREST_EXPENSE)

        equity, m_eq = self.average_stock(LI.TOTAL_EQUITY)
        assets, m_as = self.average_stock(LI.TOTAL_ASSETS)
        debt, m_dbt = self.latest(LI.TOTAL_DEBT)
        cash, m_csh = self.latest(LI.CASH_AND_EQUIVALENTS)
        cur_a, m_ca = self.latest(LI.CURRENT_ASSETS)
        cur_l, m_cl = self.latest(LI.CURRENT_LIABILITIES)

        # --- margens -----------------------------------------------------
        emit("gross_margin", _safe_div(gp, rev), [m_gp, m_rev], "ratio")
        emit("operating_margin", _safe_div(op, rev), [m_op, m_rev], "ratio")
        emit("net_margin", _safe_div(ni, rev), [m_ni, m_rev], "ratio")
        emit("ebitda_margin", _safe_div(ebitda, rev), [m_eb, m_rev], "ratio")

        # --- retorno sobre capital --------------------------------------
        emit("roe", _safe_div(ni, equity), [m_ni, m_eq], "ratio")
        emit("roa", _safe_div(ni, assets), [m_ni, m_as], "ratio")

        # ROIC = NOPAT / capital investido. Sem a alíquota efetiva real,
        # usamos 34% (BR) / 21% (US)? Não: usamos a alíquota implícita quando
        # disponível e, na falta dela, deixamos a métrica indisponível em vez
        # de inventar um número plausível.
        pretax, m_pt = self.ttm(LI.PRETAX_INCOME)
        tax, m_tx = self.ttm(LI.INCOME_TAX)
        effective_tax = _safe_div(tax, pretax)
        nopat = None
        if op is not None and effective_tax is not None and 0.0 <= effective_tax < 1.0:
            nopat = op * (1.0 - effective_tax)
        invested_capital = None
        if equity is not None and debt is not None:
            invested_capital = equity + debt - (cash or 0.0)
        emit("roic", _safe_div(nopat, invested_capital),
             [m_op, m_pt, m_tx, m_eq, m_dbt, m_csh], "ratio")
        emit("effective_tax_rate", effective_tax, [m_tx, m_pt], "ratio")

        # --- caixa -------------------------------------------------------
        fcf = None
        if ocf is not None and capex is not None:
            # Convenção: capex entra negativo no DFC. Normalizamos o sinal.
            fcf = ocf - abs(capex)
        emit("free_cash_flow", fcf, [m_ocf, m_cx], "currency")
        emit("fcf_margin", _safe_div(fcf, rev), [m_ocf, m_cx, m_rev], "ratio")

        # --- alavancagem -------------------------------------------------
        emit("debt_to_equity", _safe_div(debt, equity), [m_dbt, m_eq], "ratio")
        net_debt = None if debt is None else debt - (cash or 0.0)
        emit("net_debt", net_debt, [m_dbt, m_csh], "currency")
        emit("net_debt_ebitda", _safe_div(net_debt, ebitda) if (ebitda or 0) > 0 else None,
             [m_dbt, m_csh, m_eb], "ratio")
        emit("current_ratio", _safe_div(cur_a, cur_l), [m_ca, m_cl], "ratio")
        emit("interest_coverage",
             _safe_div(op, abs(interest)) if interest not in (None, 0) else None,
             [m_op, m_int], "ratio")

        # --- crescimento -------------------------------------------------
        for metric, item in (
            ("revenue_growth_yoy", LI.REVENUE),
            ("earnings_growth_yoy", LI.NET_INCOME),
            ("eps_growth_yoy", LI.EPS_DILUTED),
            ("ebitda_growth_yoy", LI.EBITDA),
        ):
            growth, metas = self._yoy_growth(item)
            emit(metric, growth, metas, "ratio")

        # --- diluição ----------------------------------------------------
        dilution, metas = self._yoy_growth(LI.SHARES_DILUTED)
        emit("share_count_change_yoy", dilution, metas, "ratio")

        # --- níveis absolutos (para o relatório e para valuation) --------
        emit("revenue_ttm", rev, [m_rev], "currency")
        emit("net_income_ttm", ni, [m_ni], "currency")
        emit("ebitda_ttm", ebitda, [m_eb], "currency")
        emit("eps_ttm", self.ttm(LI.EPS_DILUTED)[0], [self.ttm(LI.EPS_DILUTED)[1]], "currency")
        emit("total_equity", equity, [m_eq], "currency")
        emit("cash", cash, [m_csh], "currency")
        emit("total_debt", debt, [m_dbt], "currency")
        shares, m_sh = self.latest(LI.SHARES_OUTSTANDING)
        emit("shares_outstanding", shares, [m_sh], "count")

        return [r for r in results if r.value is not None]

    def _yoy_growth(self, item: str) -> tuple[float | None, list[dict[str, Any]]]:
        """Crescimento ano contra ano.

        Compara TTM atual com TTM de 4 trimestres atrás (ou exercício contra
        exercício). Nunca compara trimestre com trimestre anterior — isso
        mede sazonalidade, não crescimento.
        """
        chunk = self._by_item.get(item)
        if chunk is None or chunk.empty:
            return None, []
        if LI.is_flow(item) or item == LI.EPS_DILUTED:
            q = chunk[chunk["period_type"] == "Q"].sort_values("period_end")
            if len(q) >= 8 and not q.tail(8)["value"].isna().any():
                current = q.tail(4)["value"].sum()
                prior = q.tail(8).head(4)["value"].sum()
                if prior is None or prior == 0 or prior < 0:
                    return None, []
                meta = {
                    "line_item": item,
                    "period_end": q.iloc[-1]["period_end"],
                    "publication_date": q.tail(4)["publication_date"].max(),
                    "estimated": bool(q.tail(8)["publication_date_is_estimated"].any()),
                    "source": q.iloc[-1]["source"],
                    "note": "TTM atual vs TTM do ano anterior",
                    "periods": list(q.tail(8)["period_end"]),
                }
                return float(current / prior - 1.0), [meta]
        annual = chunk[chunk["period_type"] == "A"].sort_values("period_end")
        if len(annual) >= 2 and not annual.tail(2)["value"].isna().any():
            prior = float(annual.iloc[-2]["value"])
            current = float(annual.iloc[-1]["value"])
            if prior <= 0:
                return None, []
            meta = {
                "line_item": item,
                "period_end": annual.iloc[-1]["period_end"],
                "publication_date": annual.tail(2)["publication_date"].max(),
                "estimated": bool(annual.tail(2)["publication_date_is_estimated"].any()),
                "source": annual.iloc[-1]["source"],
                "note": "exercício vs exercício anterior",
                "periods": list(annual.tail(2)["period_end"]),
            }
            return float(current / prior - 1.0), [meta]
        return None, []
