"""Fundamentos derivados e valuation."""

from __future__ import annotations

import pandas as pd
import pytest

from irai.markets.stocks.fundamentals import line_items as LI
from irai.markets.stocks.fundamentals.metrics import FundamentalsCalculator
from irai.markets.stocks.valuation.multiples import compute_multiples, read_multiple


def _financials(rows):
    return pd.DataFrame([
        {
            "ticker": "AAA", "statement": "income", "line_item": item,
            "period_end": period, "period_type": "Q", "value": value,
            "publication_date": pub, "publication_date_is_estimated": 0,
            "version": 1, "source": "test",
        }
        for item, period, value, pub in rows
    ])


def test_ttm_soma_fluxo_e_nao_soma_estoque():
    """Somar quatro trimestres de patrimônio líquido daria ROE 4x errado."""
    periods = ["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31"]
    pubs = ["2023-05-15", "2023-08-14", "2023-11-14", "2024-03-15"]
    rows = [(LI.REVENUE, p, 100.0, d) for p, d in zip(periods, pubs, strict=True)]
    rows += [(LI.TOTAL_EQUITY, p, 1000.0, d) for p, d in zip(periods, pubs, strict=True)]
    df = _financials(rows)
    df.loc[df["line_item"] == LI.TOTAL_EQUITY, "statement"] = "balance"

    calc = FundamentalsCalculator(df)
    receita, _ = calc.ttm(LI.REVENUE)
    patrimonio, _ = calc.ttm(LI.TOTAL_EQUITY)

    assert receita == pytest.approx(400.0), "receita é fluxo: soma"
    assert patrimonio == pytest.approx(1000.0), "patrimônio é estoque: não soma"


def test_metrica_derivada_herda_publicacao_mais_recente():
    """Uma métrica não pode ser mais 'antiga' que o insumo mais novo."""
    periods = ["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31"]
    pubs = ["2023-05-15", "2023-08-14", "2023-11-14", "2024-03-15"]
    rows = [(LI.REVENUE, p, 100.0, d) for p, d in zip(periods, pubs, strict=True)]
    rows += [(LI.NET_INCOME, p, 10.0, d) for p, d in zip(periods, pubs, strict=True)]
    calc = FundamentalsCalculator(_financials(rows))

    resultados = {r.metric: r for r in calc.compute_all()}
    assert resultados["net_margin"].publication_date == "2024-03-15"


def test_metrica_derivada_registra_seus_insumos():
    periods = ["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31"]
    pubs = ["2023-05-15", "2023-08-14", "2023-11-14", "2024-03-15"]
    rows = [(LI.REVENUE, p, 100.0, d) for p, d in zip(periods, pubs, strict=True)]
    rows += [(LI.NET_INCOME, p, 10.0, d) for p, d in zip(periods, pubs, strict=True)]
    resultado = {r.metric: r for r in FundamentalsCalculator(_financials(rows)).compute_all()}
    componentes = resultado["net_margin"].inputs["components"]
    assert {c["line_item"] for c in componentes} == {LI.REVENUE, LI.NET_INCOME}


def test_crescimento_compara_ttm_contra_ttm_e_nao_trimestres_vizinhos():
    """Trimestre contra trimestre anterior mede sazonalidade, não crescimento."""
    periods = pd.date_range("2022-03-31", periods=8, freq="QE").strftime("%Y-%m-%d")
    pubs = (pd.date_range("2022-03-31", periods=8, freq="QE")
            + pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    # Sazonalidade forte, crescimento real de 10% a/a
    base = [100, 50, 120, 200]
    valores = base + [v * 1.1 for v in base]
    rows = [(LI.REVENUE, p, v, d)
            for p, v, d in zip(periods, valores, pubs, strict=True)]

    calc = FundamentalsCalculator(_financials(rows))
    crescimento, _ = calc._yoy_growth(LI.REVENUE)
    assert crescimento == pytest.approx(0.10, abs=1e-9)


def test_pe_com_lucro_negativo_nao_existe():
    """P/L negativo 'parece barato'. Devolvemos ausência em vez de armadilha."""
    m = compute_multiples(50.0, 1e9, {"eps_ttm": -2.0, "net_income_ttm": -2e9})
    assert m["pe"] is None


def test_yield_aceita_numerador_negativo():
    m = compute_multiples(50.0, 1e9, {"free_cash_flow": -5e9, "net_income_ttm": -2e9})
    assert m["fcf_yield"] < 0
    assert m["price_to_fcf"] is None


def test_peg_exige_crescimento_positivo():
    base = {"eps_ttm": 5.0, "net_income_ttm": 5e9}
    assert compute_multiples(60.0, 1e9, {**base, "earnings_growth_yoy": -0.2})["peg"] is None
    assert compute_multiples(60.0, 1e9, {**base, "earnings_growth_yoy": 0.12})["peg"] is not None


def test_enterprise_value_usa_divida_liquida():
    m = compute_multiples(10.0, 1e9, {"total_debt": 3e9, "cash": 1e9, "ebitda_ttm": 2e9})
    assert m["enterprise_value"] == pytest.approx(10e9 + 3e9 - 1e9)
    assert m["ev_ebitda"] == pytest.approx(6.0)


def test_leitura_de_multiplo_nao_rotula_barato_nem_caro():
    leitura = read_multiple("pe", 8.0, history=pd.Series([12.0] * 20),
                            peers=pd.Series([15.0] * 10), peer_group="Energy")
    texto = str(leitura.to_dict()).lower()
    assert "barat" not in texto and "car" not in texto.replace("percentile", "")
    assert leitura.vs_own_history == "below"
    assert leitura.vs_peers == "below"


def test_historico_curto_nao_produz_comparacao():
    leitura = read_multiple("pe", 8.0, history=pd.Series([12.0, 13.0]))
    assert leitura.vs_own_history == "insufficient_data"
    assert "insuficiente" in (leitura.note or "").lower()
