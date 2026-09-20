"""Testes do motor quantitativo contra valores calculáveis à mão."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from irai.core.quant import momentum as mom
from irai.core.quant import technical as tech
from irai.core.quant.normalize import normalize_by_group, robust_zscore, winsorize
from irai.core.quant.returns import (
    annualize_return,
    cumulative_return,
    simple_returns,
    total_return_between,
)
from irai.core.quant.risk import (
    beta,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
)


def test_retorno_acumulado_composto_corretamente():
    r = pd.Series([0.10, -0.10, 0.10])
    # 1.1 * 0.9 * 1.1 - 1 = 0.089
    assert cumulative_return(r) == pytest.approx(0.089, abs=1e-9)


def test_cagr_conhecido():
    # dobrar em 2 anos => 41,42% a.a.
    assert annualize_return(1.0, 504, 252) == pytest.approx(2 ** 0.5 - 1, abs=1e-9)


def test_max_drawdown_conhecido():
    # +100% e depois -50% volta ao ponto inicial: drawdown de -50%
    r = pd.Series([1.0, -0.5])
    assert max_drawdown(r) == pytest.approx(-0.5, abs=1e-9)


def test_sharpe_com_risk_free_zero_bate_formula():
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0.001, 0.01, 2520))
    esperado = r.mean() / r.std(ddof=1) * np.sqrt(252)
    assert sharpe_ratio(r, 0.0, 252) == pytest.approx(esperado, rel=1e-9)


def test_risk_free_alto_derruba_o_sharpe():
    """Com CDI em dois dígitos, o Sharpe brasileiro calculado contra zero mente."""
    rng = np.random.default_rng(2)
    r = pd.Series(rng.normal(0.0005, 0.01, 2520))
    assert sharpe_ratio(r, 0.0, 252) > sharpe_ratio(r, 0.12, 252)


def test_sortino_ignora_volatilidade_de_alta():
    subidas = pd.Series([0.05] * 100)
    assert sortino_ratio(subidas, 0.0, 252) == float("inf")


def test_beta_de_serie_identica_e_um():
    rng = np.random.default_rng(3)
    b = pd.Series(rng.normal(0, 0.01, 300))
    assert beta(b, b) == pytest.approx(1.0, abs=1e-9)
    assert beta(2 * b, b) == pytest.approx(2.0, abs=1e-9)


def test_win_rate():
    assert win_rate(pd.Series([1.0, -1.0, 1.0, 0.0])) == pytest.approx(0.5)


def test_momentum_12_1_exclui_o_mes_recente():
    """Uma queda apenas no último mês não pode aparecer no 12-1."""
    idx = pd.bdate_range("2023-01-02", periods=300)
    precos = pd.Series(np.linspace(100, 200, 300), index=idx)
    # Colapso severo apenas no último mês, para BAIXO do nível de 12 meses atrás.
    precos.iloc[-21:] = 50.0
    as_of = idx[-1]

    m12 = mom.momentum(precos, as_of, 365)
    m121 = mom.momentum(precos, as_of, 365, skip_days=30)

    assert m12 < 0, "momentum 12M deveria refletir o colapso"
    assert m121 > 0, "momentum 12-1 não deveria enxergar o último mês"


def test_total_return_between_usa_asof_e_nao_extrapola():
    idx = pd.bdate_range("2024-01-01", periods=10)
    precos = pd.Series(np.arange(100, 110, dtype=float), index=idx)
    # data anterior ao início da série => NaN, não extrapolação
    assert np.isnan(total_return_between(precos, "2023-01-01", idx[-1]))


def test_winsorize_usa_percentis_da_propria_amostra():
    s = pd.Series([1, 2, 3, 4, 5, 1000.0])
    w = winsorize(s, 0.0, 0.8)
    assert w.max() < 1000


def test_robust_z_resiste_a_outlier():
    s = pd.Series([10, 11, 12, 13, 10_000.0])
    z = robust_zscore(s, clip=3.0)
    assert z.iloc[-1] == 3.0, "outlier deveria ser cortado no clip"
    assert abs(z.iloc[:4]).max() < 3.0


def test_grupo_pequeno_cai_para_o_universo_inteiro():
    v = pd.Series({"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8.0})
    g = pd.Series({"a": "X", "b": "X", "c": "X", "d": "X", "e": "X",
                   "f": "Y", "g": "Y", "h": "Y"})
    _, grupo, tamanho = normalize_by_group(v, g, min_group_size=5)
    assert set(grupo.loc[["f", "g", "h"]]) == {"__ALL__"}
    assert tamanho.loc["f"] == 8.0, "fallback deve comparar contra o universo inteiro"


def test_volume_relativo_usa_mediana():
    idx = pd.bdate_range("2024-01-01", periods=100)
    vol = pd.Series([100.0] * 99 + [300.0], index=idx)
    assert tech.relative_volume(vol, idx[-1]) == pytest.approx(3.0)


def test_simple_returns_nao_preenche_buracos():
    s = pd.Series([100.0, np.nan, 110.0])
    r = simple_returns(s)
    assert np.isnan(r.iloc[1])
