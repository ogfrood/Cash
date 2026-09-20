"""Carregamento e validação da configuração.

Regra do projeto: nenhum número que altere resultado de backtest fica no
código. Tudo vem de `config/*.yaml`, e o conteúdo é hasheado para que cada
previsão gravada possa ser reproduzida byte a byte.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def project_root() -> Path:
    """Raiz do projeto (a pasta que contém `config/`).

    Respeita ``IRAI_ROOT`` para permitir rodar a partir de qualquer diretório.
    """
    env = os.environ.get("IRAI_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "settings.yaml").exists():
            return parent
    # Fallback: dois níveis acima de src/irai/
    return here.parents[2]


def sha256_of(payload: str | bytes) -> str:
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(data).hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Configuração inválida (esperava mapeamento): {path}")
    return data


@dataclass(frozen=True)
class MarketConfig:
    """Parâmetros de um mercado. Nada aqui é compartilhado entre mercados.

    Calendário, benchmark e taxa livre de risco mudam por mercado — é por isso
    que ações e cripto não podem compartilhar este objeto.
    """

    code: str
    name: str
    currency: str
    ticker_suffix: str
    benchmark: str
    benchmark_name: str
    trading_days_per_year: int
    risk_free_fallback_annual: float
    risk_free_series: str | None = None

    @classmethod
    def from_dict(cls, code: str, raw: dict[str, Any]) -> MarketConfig:
        return cls(
            code=code,
            name=raw["name"],
            currency=raw["currency"],
            ticker_suffix=raw.get("ticker_suffix", ""),
            benchmark=raw["benchmark"],
            benchmark_name=raw["benchmark_name"],
            trading_days_per_year=int(raw.get("trading_days_per_year", 252)),
            risk_free_fallback_annual=float(raw.get("risk_free_fallback_annual", 0.0)),
            risk_free_series=raw.get("risk_free_series"),
        )


@dataclass(frozen=True)
class PointInTimeConfig:
    """Como o sistema se protege de look-ahead bias. Ver docs/LOOKAHEAD_BIAS.md."""

    allow_estimated_publication_dates: bool
    estimated_publication_lag_days: dict[str, dict[str, int]]
    execution_lag_days: int

    def lag_days(self, market: str, period_type: str) -> int:
        """Lag conservador entre fim do período e publicação presumida."""
        per_market = self.estimated_publication_lag_days.get(market)
        if not per_market:
            raise KeyError(
                f"Sem lag de publicação configurado para o mercado {market!r}. "
                "Adicione em config/settings.yaml -> point_in_time."
            )
        key = "A" if period_type.upper() in {"A", "FY", "ANNUAL"} else "Q"
        return int(per_market[key])


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]
    root: Path
    config_hash: str
    markets: dict[str, MarketConfig] = field(default_factory=dict)

    # -- acessores tipados ------------------------------------------------
    @property
    def point_in_time(self) -> PointInTimeConfig:
        pit = self.raw["point_in_time"]
        return PointInTimeConfig(
            allow_estimated_publication_dates=bool(pit["allow_estimated_publication_dates"]),
            estimated_publication_lag_days=pit["estimated_publication_lag_days"],
            execution_lag_days=int(pit.get("execution_lag_days", 1)),
        )

    @property
    def database_path(self) -> Path:
        return self.root / self.raw["database"]["path"]

    @property
    def backtest(self) -> dict[str, Any]:
        return self.raw["backtest"]

    @property
    def ingestion(self) -> dict[str, Any]:
        return self.raw["ingestion"]

    @property
    def ai(self) -> dict[str, Any]:
        return self.raw.get("ai", {})

    @property
    def reports_dir(self) -> Path:
        return self.root / self.raw.get("reports", {}).get("output_dir", "reports")

    def market(self, code: str) -> MarketConfig:
        try:
            return self.markets[code]
        except KeyError as exc:
            known = ", ".join(sorted(self.markets)) or "(nenhum)"
            raise KeyError(f"Mercado {code!r} não configurado. Conhecidos: {known}") from exc

    def scoring_config_path(self) -> Path:
        return self.root / self.raw["scoring"]["config_file"]


def load_settings(path: Path | str | None = None) -> Settings:
    root = project_root()
    settings_path = Path(path) if path else root / "config" / "settings.yaml"
    raw_text = settings_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    markets = {code: MarketConfig.from_dict(code, cfg) for code, cfg in raw["markets"].items()}
    return Settings(
        raw=raw,
        root=root,
        config_hash=sha256_of(raw_text),
        markets=markets,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
