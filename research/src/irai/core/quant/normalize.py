"""Normalização cross-sectional.

A regra que evita o vazamento mais comum de scoring quantitativo:
**normalizar entre empresas na MESMA data, nunca ao longo do tempo.**

Usar média e desvio da série inteira embute informação do futuro no z-score de
2015. O erro é silencioso: o backtest não quebra, só fica bom demais.

Usamos mediana e MAD em vez de média e desvio porque múltiplos financeiros têm
caudas grossas — um P/L de 900 destrói uma média.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MAD_TO_SIGMA = 1.4826  # torna o MAD comparável ao desvio-padrão sob normalidade


def winsorize(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """Corta caudas nos percentis da PRÓPRIA data (não da série histórica)."""
    clean = series.dropna()
    if len(clean) < 3:
        return series
    lo, hi = np.quantile(clean, [lower, upper])
    return series.clip(lower=lo, upper=hi)


def robust_zscore(series: pd.Series, clip: float | None = 3.0) -> pd.Series:
    """z robusto: (x - mediana) / (1.4826 * MAD).

    Se o MAD for zero (todos os valores iguais), devolve zeros em vez de
    infinito — dizer 'todos iguais' é mais honesto do que explodir.
    """
    clean = series.dropna()
    if len(clean) < 3:
        return pd.Series(np.nan, index=series.index)
    med = clean.median()
    mad = (clean - med).abs().median()
    if mad == 0 or not np.isfinite(mad):
        std = clean.std(ddof=1)
        if std == 0 or not np.isfinite(std):
            return pd.Series(0.0, index=series.index).where(series.notna())
        z = (series - clean.mean()) / std
    else:
        z = (series - med) / (MAD_TO_SIGMA * mad)
    if clip is not None:
        z = z.clip(-clip, clip)
    return z


def zscore(series: pd.Series, clip: float | None = 3.0) -> pd.Series:
    clean = series.dropna()
    if len(clean) < 3:
        return pd.Series(np.nan, index=series.index)
    std = clean.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return pd.Series(0.0, index=series.index).where(series.notna())
    z = (series - clean.mean()) / std
    return z.clip(-clip, clip) if clip is not None else z


def rank_score(series: pd.Series) -> pd.Series:
    """Percentil dentro do grupo, mapeado para [-1, 1].

    Alternativa imune a outliers; perde a informação de magnitude.
    """
    clean = series.dropna()
    if len(clean) < 2:
        return pd.Series(np.nan, index=series.index)
    pct = series.rank(pct=True, na_option="keep")
    return (pct - 0.5) * 2.0


NORMALIZERS = {
    "robust_z": robust_zscore,
    "z": zscore,
    "rank": rank_score,
}


def normalize_by_group(
    values: pd.Series,
    groups: pd.Series,
    method: str = "robust_z",
    winsorize_percentiles: tuple[float, float] | None = (0.01, 0.99),
    min_group_size: int = 5,
    clip: float | None = 3.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Normaliza dentro de cada grupo (setor), caindo para o universo inteiro
    quando o grupo é pequeno demais para ter estatística.

    Retorna (normalizado, grupo_efetivo, tamanho_do_grupo). O grupo efetivo é
    reportado porque um z-score contra 4 pares significa muito menos do que um
    z-score contra 40 — e o relatório precisa dizer isso.
    """
    if values.empty:
        empty = pd.Series(dtype=float)
        return empty, pd.Series(dtype=object), pd.Series(dtype=float)

    func = NORMALIZERS.get(method)
    if func is None:
        raise ValueError(f"Método de normalização desconhecido: {method!r}")

    groups = groups.reindex(values.index).fillna("UNKNOWN")
    counts = groups.map(groups.value_counts())
    effective_group = groups.where(counts >= min_group_size, "__ALL__")

    func_kwargs = {} if method == "rank" else {"clip": clip}

    def _normalized(chunk: pd.Series) -> pd.Series:
        if winsorize_percentiles:
            chunk = winsorize(chunk, *winsorize_percentiles)
        return func(chunk, **func_kwargs)

    out = pd.Series(np.nan, index=values.index, dtype=float)

    # Grupos grandes: cross-section dentro do próprio setor.
    big = effective_group != "__ALL__"
    if big.any():
        for _, idx in effective_group[big].groupby(effective_group[big]).groups.items():
            out.loc[idx] = _normalized(values.loc[idx])

    # Grupos pequenos: comparados contra o UNIVERSO INTEIRO, não entre si.
    # Comparar 3 bancos só com outros 3 bancos não é cross-section, é ruído.
    small_idx = effective_group.index[~big]
    if len(small_idx) > 0:
        out.loc[small_idx] = _normalized(values).loc[small_idx]

    sizes = effective_group.map(effective_group.value_counts()).astype(float)
    # Quem caiu no fallback foi comparado contra o universo inteiro: o tamanho
    # reportado precisa refletir isso, e não o punhado de pares do setor.
    sizes.loc[effective_group == "__ALL__"] = float(values.notna().sum())
    return out, effective_group, sizes
