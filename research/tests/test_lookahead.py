"""Testes de look-ahead bias — os mais importantes do projeto.

Se qualquer um destes falhar, nenhum resultado do sistema vale nada.
"""

from __future__ import annotations

import pandas as pd
import pytest

from irai.core.db.repository import PITPolicy, Repository


def _fact(ticker, metric, period_end, value, publication_date, version=1, estimated=0):
    return {
        "ticker": ticker, "metric": metric, "period_end": period_end, "value": value,
        "publication_date": publication_date, "version": version,
        "publication_date_is_estimated": estimated, "source": "test",
        "period_type": "TTM",
    }


def test_fundamento_nao_publicado_e_invisivel(repo):
    """O caso do enunciado: balanço publicado em 15/05 não existe em 01/05."""
    repo.upsert_fundamentals([_fact("AAA", "roe", "2024-03-31", 0.25, "2024-05-15")])

    antes = repo.fundamentals_as_of(["AAA"], "2024-05-01")
    depois = repo.fundamentals_as_of(["AAA"], "2024-05-15")

    assert antes.empty, "dado apareceu antes da data de publicação"
    assert len(depois) == 1
    assert depois.iloc[0]["value"] == pytest.approx(0.25)


def test_reapresentacao_usa_versao_vigente_na_data(repo):
    """Reapresentação em agosto não pode alterar o que se sabia em junho."""
    repo.upsert_fundamentals([
        _fact("AAA", "roe", "2024-03-31", 0.25, "2024-05-15", version=1),
        _fact("AAA", "roe", "2024-03-31", 0.11, "2024-08-10", version=2),
    ])

    junho = repo.fundamentals_as_of(["AAA"], "2024-06-30")
    setembro = repo.fundamentals_as_of(["AAA"], "2024-09-30")

    assert junho.iloc[0]["value"] == pytest.approx(0.25)
    assert junho.iloc[0]["version"] == 1
    assert setembro.iloc[0]["value"] == pytest.approx(0.11)
    assert setembro.iloc[0]["version"] == 2


def test_data_estimada_e_descartada_por_padrao(repo):
    repo.upsert_fundamentals([
        _fact("AAA", "roe", "2024-03-31", 0.25, "2024-05-15", estimated=1),
    ])
    assert repo.fundamentals_as_of(["AAA"], "2024-12-31").empty

    permissivo = Repository(repo.db, PITPolicy(allow_estimated=True))
    assert len(permissivo.fundamentals_as_of(["AAA"], "2024-12-31")) == 1


def test_fato_sem_data_de_publicacao_e_rejeitado(repo):
    with pytest.raises(ValueError, match="publication_date"):
        repo.upsert_fundamentals([{
            "ticker": "AAA", "metric": "roe", "period_end": "2024-03-31",
            "value": 0.25, "source": "test",
        }])


def test_envenenamento_nao_contamina_o_passado(loaded_repo):
    """Teste de envenenamento.

    Injeta um fundamento absurdo com data de publicação no futuro e verifica
    que nada muda para uma data anterior. Se alguém contornar o repositório e
    ler a tabela direto, este teste quebra.
    """
    from irai.config import load_settings
    from irai.core.features.builder import FeatureBuilder

    settings = load_settings()
    market = settings.market("US")
    tickers = loaded_repo.universe_as_of("US", "config", "2021-06-30")
    as_of = "2021-06-30"

    antes = FeatureBuilder(loaded_repo, market).build(tickers, as_of).frame.copy()

    loaded_repo.upsert_fundamentals([
        _fact(tickers[0], "roe", "2022-12-31", 999.0, "2023-03-01"),
        _fact(tickers[0], "roic", "2022-12-31", 999.0, "2023-03-01"),
        _fact(tickers[0], "net_margin", "2022-12-31", 999.0, "2023-03-01"),
    ])

    depois = FeatureBuilder(loaded_repo, market).build(tickers, as_of).frame

    pd.testing.assert_frame_equal(antes, depois)


def test_precos_futuros_nao_entram_no_painel(loaded_repo):
    tickers = loaded_repo.universe_as_of("US", "config", "2020-06-30")
    panel = loaded_repo.price_panel(tickers, end="2020-06-30")
    assert panel.index.max() <= pd.Timestamp("2020-06-30")


def test_universo_sem_snapshot_nao_cai_para_lista_de_hoje(repo):
    """Cair silenciosamente para 'todos os tickers de hoje' seria viés de
    sobrevivência disfarçado de conveniência."""
    repo.upsert_companies([
        {"ticker": "AAA", "market": "US", "source": "test"},
        {"ticker": "BBB", "market": "US", "source": "test"},
    ])
    repo.upsert_universe_snapshot("2020-06-30", "US", "config", ["AAA"], source="test")

    assert repo.universe_as_of("US", "config", "2019-01-01") == []
    assert repo.universe_as_of("US", "config", "2020-12-31") == ["AAA"]
