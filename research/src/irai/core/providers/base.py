"""Contrato dos provedores de dados.

Cada fonte (yfinance, CVM, SEC, fixtures) implementa esta interface. O resto
do sistema nunca importa um provedor concreto — pede ao registry. É o que
permite trocar `yfinance` por EODHD depois sem tocar em uma linha de sinal,
score ou backtest.

Todo provedor é obrigado a declarar se entrega data de publicação real
(`provides_real_publication_dates`). Quem não entrega, entrega dado que o
backtest vai descartar por padrão — e o usuário precisa saber disso ANTES de
rodar a ingestão, não depois de ver um resultado bom demais.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ProviderCapabilities:
    name: str
    prices: bool = False
    fundamentals: bool = False
    dividends: bool = False
    splits: bool = False
    company_info: bool = False
    provides_real_publication_dates: bool = False
    covers_delisted: bool = False
    markets: tuple[str, ...] = ()
    notes: str = ""
    license_note: str = ""

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "prices": self.prices,
            "fundamentals": self.fundamentals,
            "real_publication_dates": self.provides_real_publication_dates,
            "covers_delisted": self.covers_delisted,
            "markets": list(self.markets),
            "notes": self.notes,
            "license": self.license_note,
        }


@dataclass
class FetchResult:
    """Resultado de uma busca, com os problemas encontrados em vez de escondidos."""

    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class DataProvider(ABC):
    """Interface mínima. Métodos não suportados devolvem resultado vazio com
    aviso — nunca lançam, para que uma fonte incompleta não derrube a
    ingestão inteira."""

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    def fetch_prices(self, tickers: list[str], start: str, end: str) -> FetchResult:
        return FetchResult(warnings=[f"{self.capabilities.name} não fornece preços."])

    def fetch_company_info(self, tickers: list[str]) -> FetchResult:
        return FetchResult(warnings=[f"{self.capabilities.name} não fornece cadastro."])

    def fetch_financials(self, tickers: list[str]) -> FetchResult:
        return FetchResult(warnings=[f"{self.capabilities.name} não fornece demonstrações."])

    def fetch_dividends(self, tickers: list[str], start: str, end: str) -> FetchResult:
        return FetchResult(warnings=[f"{self.capabilities.name} não fornece proventos."])
