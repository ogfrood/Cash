"""Scoring, backtest e walk-forward."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from irai.config import load_settings
from irai.core.backtest.engine import BacktestConfig, BacktestEngine
from irai.core.backtest.walkforward import deflated_sharpe_ratio
from irai.core.features.builder import FeatureBuilder, FeaturePanel
from irai.core.scoring.engine import ScoringConfig, ScoringEngine


@pytest.fixture
def scoring():
    settings = load_settings()
    return ScoringEngine(ScoringConfig.load(settings.scoring_config_path()))


def _panel(frame: pd.DataFrame, sectors: dict[str, str]) -> FeaturePanel:
    return FeaturePanel(
        as_of=pd.Timestamp("2024-01-31"), market="US", frame=frame,
        sectors=pd.Series(sectors).reindex(frame.index),
    )


def test_config_de_scoring_e_hasheada(scoring):
    assert len(scoring.config.config_hash) == 64
    outra = ScoringConfig.load(load_settings().scoring_config_path())
    assert outra.config_hash == scoring.config.config_hash, "hash deve ser estável"


def test_fator_ausente_nao_vira_zero(scoring):
    """Zero num z-score significa 'na mediana do setor'. Ausente é ausente."""
    fatores = scoring.config.all_factor_names
    linhas = {}
    for i in range(8):
        linhas[f"T{i}"] = dict.fromkeys(fatores, float(i))
    frame = pd.DataFrame.from_dict(linhas, orient="index")
    frame.loc["T0", "roe"] = np.nan

    resultado = scoring.score(_panel(frame, dict.fromkeys(frame.index, "Tech")))

    assert np.isnan(resultado.normalized.loc["T0", "roe"])
    assert resultado.coverage.loc["T0", "quality"] < resultado.coverage.loc["T1", "quality"]


def test_cobertura_insuficiente_deixa_empresa_fora_do_ranking(scoring):
    fatores = scoring.config.all_factor_names
    linhas = {f"T{i}": dict.fromkeys(fatores, float(i)) for i in range(8)}
    frame = pd.DataFrame.from_dict(linhas, orient="index")
    # T0 perde quase tudo
    for fator in fatores[:-2]:
        frame.loc["T0", fator] = np.nan

    resultado = scoring.score(_panel(frame, dict.fromkeys(frame.index, "Tech")))

    assert np.isnan(resultado.scores.loc["T0", "total"])
    assert "T0" not in resultado.ranked("total").index


def test_direcao_negativa_inverte_a_contribuicao(scoring):
    """Múltiplo alto tem de piorar o pilar de valor, não melhorar."""
    fatores = scoring.config.all_factor_names
    linhas = {f"T{i}": dict.fromkeys(fatores, 1.0) for i in range(8)}
    frame = pd.DataFrame.from_dict(linhas, orient="index")
    frame["pe"] = [5, 6, 7, 8, 9, 10, 11, 100.0]

    resultado = scoring.score(_panel(frame, dict.fromkeys(frame.index, "Tech")))
    valor = resultado.scores["value"]

    assert valor.loc["T0"] > valor.loc["T7"], "P/L alto deveria reduzir o pilar de valor"


def test_explicacao_lista_contribuicoes_com_valor_bruto(scoring):
    fatores = scoring.config.all_factor_names
    linhas = {f"T{i}": dict.fromkeys(fatores, float(i)) for i in range(8)}
    frame = pd.DataFrame.from_dict(linhas, orient="index")
    resultado = scoring.score(_panel(frame, dict.fromkeys(frame.index, "Tech")))

    explicacao = resultado.explain("T7")
    assert explicacao["top_positive"]
    primeiro = explicacao["top_positive"][0]
    assert {"factor", "pillar", "raw_value", "z_score", "contribution"} <= set(primeiro)


def test_score_e_reproduzivel(scoring, loaded_repo):
    settings = load_settings()
    market = settings.market("US")
    tickers = loaded_repo.universe_as_of("US", "config", "2021-12-31")
    panel = FeatureBuilder(loaded_repo, market).build(tickers, "2021-12-31")

    a = scoring.score(panel).scores
    b = scoring.score(panel).scores
    pd.testing.assert_frame_equal(a, b)


# ------------------------------------------------------------------ backtest

def _backtest(repo, scoring, **overrides):
    settings = load_settings()
    import dataclasses

    market = dataclasses.replace(settings.market("US"), benchmark="^SYNX")
    cfg = BacktestConfig(
        start="2019-01-01", end="2022-12-31", portfolio_size=4,
        min_median_traded_value=0.0, min_price=0.0, **overrides,
    )
    return BacktestEngine(repo, market, scoring, cfg).run()


def test_backtest_roda_e_grava_hipoteses(loaded_repo, scoring):
    resultado = _backtest(loaded_repo, scoring)
    assert len(resultado.equity) > 200
    assert resultado.assumptions["execution_lag_days"] == 1
    assert resultado.assumptions["market_impact"].startswith("não modelado")
    assert "total_return" in resultado.metrics


def test_custo_maior_reduz_o_retorno(loaded_repo, scoring):
    barato = _backtest(loaded_repo, scoring, transaction_cost_bps=0.0, slippage_bps=0.0)
    caro = _backtest(loaded_repo, scoring, transaction_cost_bps=100.0, slippage_bps=100.0)
    assert caro.metrics["total_return"] < barato.metrics["total_return"]
    assert caro.metrics["total_costs"] > barato.metrics["total_costs"]


def test_execucao_acontece_depois_do_sinal(loaded_repo, scoring):
    """Toda ordem precisa ser executada em data POSTERIOR à data do sinal."""
    resultado = _backtest(loaded_repo, scoring)
    assert not resultado.trades.empty
    razoes = resultado.trades["reason"]
    assert razoes.str.contains("rebalance|saída").all()
    # nenhuma negociação no primeiro pregão do calendário (sinal ainda não existia)
    primeiro = resultado.equity.index[0]
    assert (resultado.trades["date"] > primeiro).all()


def test_universo_vazio_falha_em_vez_de_improvisar(repo, scoring):
    with pytest.raises(ValueError, match="Universo vazio"):
        _backtest(repo, scoring)


def test_deflated_sharpe_penaliza_muitas_tentativas():
    uma = deflated_sharpe_ratio(1.0, n_trials=1, n_observations=1000)
    muitas = deflated_sharpe_ratio(1.0, n_trials=200, n_observations=1000)
    assert uma > muitas
    assert muitas < 0.5, "Sharpe 1.0 escolhido entre 200 tentativas não é evidência"
