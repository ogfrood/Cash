"""Provedor yfinance — testado contra DataFrames no formato do Yahoo.

Sem rede: o que se testa aqui é a TRADUÇÃO (nomes do Yahoo para o plano de
contas canônico) e o carimbo de data de publicação estimada. A chamada de
rede em si só pode ser verificada na máquina do usuário.
"""

from __future__ import annotations

import pandas as pd
import pytest

from irai.core.providers.yfinance_provider import INCOME_MAP, YFinanceProvider
from irai.markets.stocks.fundamentals import line_items as LI


@pytest.fixture
def dre():
    """Formato do Yahoo: linhas = contas, colunas = fins de período."""
    return pd.DataFrame(
        {
            pd.Timestamp("2024-06-30"): [1000.0, 400.0, 150.0, 90.0],
            pd.Timestamp("2024-03-31"): [900.0, 360.0, 130.0, 80.0],
        },
        index=["Total Revenue", "Gross Profit", "Operating Income", "Net Income"],
    )


def test_traduz_nomes_do_yahoo_para_o_plano_canonico(dre):
    p = YFinanceProvider(market="US")
    sink = []
    p._rows_from_statement("AAPL", "income", INCOME_MAP, dre, sink)
    itens = {r["line_item"] for r in sink}
    assert itens == {LI.REVENUE, LI.GROSS_PROFIT, LI.OPERATING_INCOME, LI.NET_INCOME}


def test_data_de_publicacao_e_estimada_e_marcada(dre):
    """Sem esta marca, o backtest usaria dado que ninguém tinha na época."""
    p = YFinanceProvider(market="US")
    sink = []
    p._rows_from_statement("AAPL", "income", INCOME_MAP, dre, sink)
    for r in sink:
        assert r["publication_date_is_estimated"] == 1
    linha = next(r for r in sink
                 if r["line_item"] == LI.REVENUE and r["period_end"] == "2024-06-30")
    assert linha["publication_date"] == "2024-08-14"   # 30/06 + 45 dias


def test_lag_do_brasil_e_maior_que_o_dos_eua(dre):
    br, us = YFinanceProvider(market="BR"), YFinanceProvider(market="US")
    assert br.publication_lag_days == 60
    assert us.publication_lag_days == 45


def test_conta_ausente_nao_vira_zero(dre):
    """O Yahoo omite linhas conforme o setor. Ausente tem de ficar ausente."""
    p = YFinanceProvider(market="US")
    sink = []
    p._rows_from_statement("AAPL", "income", INCOME_MAP, dre, sink)
    assert not any(r["line_item"] == LI.EBITDA for r in sink)


def test_valores_nulos_sao_descartados(dre):
    dre.loc["Net Income", pd.Timestamp("2024-03-31")] = float("nan")
    p = YFinanceProvider(market="US")
    sink = []
    p._rows_from_statement("AAPL", "income", INCOME_MAP, dre, sink)
    nets = [r for r in sink if r["line_item"] == LI.NET_INCOME]
    assert len(nets) == 1 and nets[0]["period_end"] == "2024-06-30"


def test_alias_alternativo_e_reconhecido():
    df = pd.DataFrame(
        {pd.Timestamp("2024-06-30"): [500.0]},
        index=["Operating Revenue"],   # alias, não "Total Revenue"
    )
    p = YFinanceProvider(market="BR")
    sink = []
    p._rows_from_statement("PETR4.SA", "income", INCOME_MAP, df, sink)
    assert sink and sink[0]["line_item"] == LI.REVENUE
    assert sink[0]["original_tag"] == "Operating Revenue"


def test_capacidades_declaram_as_limitacoes_que_custam_dinheiro():
    caps = YFinanceProvider(market="BR").capabilities
    assert caps.provides_real_publication_dates is False
    assert caps.covers_delisted is False
    assert "não oficial" in caps.notes


def test_fundamento_estimado_e_invisivel_ao_backtest_mas_visivel_a_analise_corrente(repo, dre):
    """A distinção central: analisar hoje não é simular o passado."""
    from irai.core.db.repository import PITPolicy, Repository

    p = YFinanceProvider(market="US")
    sink = []
    p._rows_from_statement("AAPL", "income", INCOME_MAP, dre, sink)
    repo.upsert_financials(sink)

    estrito = Repository(repo.db, PITPolicy(allow_estimated=False))
    corrente = Repository(repo.db, PITPolicy(allow_estimated=True))

    assert estrito.financials_as_of(["AAPL"], "2025-01-01").empty
    assert not corrente.financials_as_of(["AAPL"], "2025-01-01").empty
