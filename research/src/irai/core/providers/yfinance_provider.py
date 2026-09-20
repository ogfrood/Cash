"""Provedor yfinance — preços e demonstrações reais do Yahoo Finance.

⚠️ LEIA ANTES DE CONFIAR NO QUE SAI DAQUI

O Yahoo **não informa a data em que cada balanço foi publicado**. Sem essa
data, não existe backtest honesto (ver docs/LOOKAHEAD_BIAS.md). Então:

- toda linha de demonstração entra com `publication_date` ESTIMADA por lag
  conservador e marcada com `publication_date_is_estimated = 1`;
- o **backtest descarta** essas linhas por padrão;
- a **análise da data de hoje** pode usá-las, porque analisar o presente não
  é simular uma decisão passada — não há futuro para vazar.

Essa distinção é a diferença entre "posso olhar isto hoje" e "posso testar
isto no passado". As duas coisas não são a mesma.

Outras limitações que valem dinheiro: endpoints não oficiais que quebram sem
aviso, throttling por IP (pior em IP de nuvem), histórico curto de balanços
(tipicamente 4–5 trimestres), nenhuma empresa delistada, e preços ajustados
revisados retroativamente. Ver DATA_SOURCES.md §3.1.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

from irai.core.providers.base import DataProvider, FetchResult, ProviderCapabilities
from irai.core.providers.registry import register
from irai.markets.stocks.fundamentals import line_items as LI

# Nomes do Yahoo -> nome canônico interno. A primeira variante encontrada vence.
# A lista é longa de propósito: o Yahoo renomeia linhas entre setores e entre
# versões, e uma linha não mapeada vira métrica ausente lá na frente.
INCOME_MAP: dict[str, tuple[str, ...]] = {
    LI.REVENUE: ("Total Revenue", "Operating Revenue", "Revenue"),
    LI.COST_OF_REVENUE: ("Cost Of Revenue", "Cost of Revenue"),
    LI.GROSS_PROFIT: ("Gross Profit",),
    LI.OPERATING_INCOME: ("Operating Income", "Total Operating Income As Reported",
                          "EBIT"),
    LI.EBITDA: ("EBITDA", "Normalized EBITDA"),
    LI.DEPRECIATION_AMORTIZATION: (
        "Reconciled Depreciation",
        "Depreciation And Amortization In Income Statement",
        "Depreciation Amortization Depletion Income Statement",
    ),
    LI.INTEREST_EXPENSE: ("Interest Expense", "Net Interest Income",
                          "Interest Expense Non Operating"),
    LI.PRETAX_INCOME: ("Pretax Income", "Income Before Tax"),
    LI.INCOME_TAX: ("Tax Provision", "Income Tax Expense"),
    LI.NET_INCOME: ("Net Income", "Net Income Common Stockholders",
                    "Net Income From Continuing Operation Net Minority Interest"),
    LI.EPS_DILUTED: ("Diluted EPS", "Basic EPS"),
    LI.SHARES_DILUTED: ("Diluted Average Shares", "Basic Average Shares"),
}
BALANCE_MAP: dict[str, tuple[str, ...]] = {
    LI.TOTAL_ASSETS: ("Total Assets",),
    LI.CURRENT_ASSETS: ("Current Assets", "Total Current Assets"),
    LI.CASH_AND_EQUIVALENTS: ("Cash And Cash Equivalents",
                              "Cash Cash Equivalents And Short Term Investments",
                              "Cash And Cash Equivalents At Carrying Value"),
    LI.TOTAL_LIABILITIES: ("Total Liabilities Net Minority Interest",
                           "Total Liabilities"),
    LI.CURRENT_LIABILITIES: ("Current Liabilities", "Total Current Liabilities"),
    LI.TOTAL_DEBT: ("Total Debt", "Long Term Debt And Capital Lease Obligation"),
    LI.TOTAL_EQUITY: ("Stockholders Equity", "Total Equity Gross Minority Interest",
                      "Common Stock Equity"),
    LI.SHARES_OUTSTANDING: ("Ordinary Shares Number", "Share Issued"),
}
CASHFLOW_MAP: dict[str, tuple[str, ...]] = {
    LI.OPERATING_CASH_FLOW: ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
    LI.CAPEX: ("Capital Expenditure", "Purchase Of PPE"),
    LI.DIVIDENDS_PAID: ("Cash Dividends Paid", "Common Stock Dividend Paid"),
    LI.BUYBACKS: ("Repurchase Of Capital Stock",),
}
STATEMENTS = (
    ("income", INCOME_MAP),
    ("balance", BALANCE_MAP),
    ("cashflow", CASHFLOW_MAP),
)


class YFinanceProvider(DataProvider):
    def __init__(
        self,
        market: str = "US",
        publication_lag_days: int | None = None,
        request_delay_seconds: float = 0.4,
        max_retries: int = 3,
    ) -> None:
        self.market = market
        # Lag conservador: prazo regulatório com folga. BR trimestral 60 dias
        # (ITR tem 45 de prazo), US 45 (10-Q tem 40–45).
        self.publication_lag_days = publication_lag_days or (60 if market == "BR" else 45)
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="yfinance",
            prices=True, fundamentals=True, dividends=True, splits=True, company_info=True,
            provides_real_publication_dates=False,
            covers_delisted=False,
            markets=("BR", "US"),
            notes=("Sem data de publicação: fundamentos entram com data ESTIMADA e são "
                   "descartados pelo backtest por padrão. Endpoint não oficial."),
            license_note="Yahoo ToS — uso pessoal/pesquisa. Sem redistribuição.",
        )

    # ------------------------------------------------------------- interno
    @staticmethod
    def _yf() -> Any:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "yfinance não instalado. Rode: pip install yfinance"
            ) from exc
        return yf

    def _retry(self, fn: Any, label: str, warnings: list[str]) -> Any:
        delay = self.request_delay_seconds
        for attempt in range(self.max_retries):
            try:
                return fn()
            except Exception as exc:  # pragma: no cover - depende de rede
                if attempt == self.max_retries - 1:
                    warnings.append(f"{label}: {type(exc).__name__}: {exc}")
                    return None
                time.sleep(delay)
                delay *= 2
        return None

    # -------------------------------------------------------------- preços
    def fetch_prices(self, tickers: list[str], start: str, end: str) -> FetchResult:
        yf = self._yf()
        warnings: list[str] = []
        frames: list[pd.DataFrame] = []

        for ticker in tickers:
            hist = self._retry(
                lambda t=ticker: yf.Ticker(t).history(
                    start=start, end=end, auto_adjust=False, actions=True
                ),
                f"preços {ticker}", warnings,
            )
            if hist is None or hist.empty:
                warnings.append(f"{ticker}: sem histórico de preços no período.")
                continue
            df = hist.reset_index()
            date_col = "Date" if "Date" in df.columns else df.columns[0]
            adj = "Adj Close" if "Adj Close" in df.columns else "Close"
            frames.append(pd.DataFrame({
                "ticker": ticker,
                "date": pd.to_datetime(df[date_col]).dt.tz_localize(None),
                "open": df.get("Open"),
                "high": df.get("High"),
                "low": df.get("Low"),
                "close": df["Close"],
                "adj_close": df[adj],
                "volume": df.get("Volume"),
                "currency": None,
            }))
            time.sleep(self.request_delay_seconds)

        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return FetchResult(frame=frame, warnings=warnings)

    # ------------------------------------------------------------ cadastro
    def fetch_company_info(self, tickers: list[str]) -> FetchResult:
        yf = self._yf()
        warnings: list[str] = []
        rows: list[dict[str, Any]] = []

        for ticker in tickers:
            info = self._retry(lambda t=ticker: yf.Ticker(t).info,
                               f"cadastro {ticker}", warnings)
            if not info:
                rows.append({"ticker": ticker, "market": self.market, "source": "yfinance"})
                continue
            rows.append({
                "ticker": ticker,
                "market": self.market,
                "name": info.get("longName") or info.get("shortName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "currency": info.get("currency"),
                "country": info.get("country"),
                "source": "yfinance",
            })
            time.sleep(self.request_delay_seconds)

        return FetchResult(frame=pd.DataFrame(rows), rows=rows, warnings=warnings)

    # --------------------------------------------------------- balanços
    def fetch_financials(self, tickers: list[str]) -> FetchResult:
        yf = self._yf()
        warnings: list[str] = []
        rows: list[dict[str, Any]] = []

        for ticker in tickers:
            handle = yf.Ticker(ticker)
            statements = {
                "income": self._retry(lambda h=handle: h.quarterly_income_stmt,
                                      f"DRE {ticker}", warnings),
                "balance": self._retry(lambda h=handle: h.quarterly_balance_sheet,
                                       f"balanço {ticker}", warnings),
                "cashflow": self._retry(lambda h=handle: h.quarterly_cashflow,
                                        f"DFC {ticker}", warnings),
            }
            got = 0
            for statement, mapping in STATEMENTS:
                df = statements.get(statement)
                if df is None or getattr(df, "empty", True):
                    continue
                got += len(self._rows_from_statement(ticker, statement, mapping, df, rows))
            if got == 0:
                warnings.append(f"{ticker}: nenhuma linha de demonstração reconhecida.")
            time.sleep(self.request_delay_seconds)

        if rows:
            warnings.append(
                f"{len(rows)} linhas com data de publicação ESTIMADA "
                f"(fim do período + {self.publication_lag_days} dias). "
                f"O backtest as descarta por padrão."
            )
        return FetchResult(rows=rows, frame=pd.DataFrame(rows), warnings=warnings)

    def _rows_from_statement(
        self, ticker: str, statement: str, mapping: dict[str, tuple[str, ...]],
        df: pd.DataFrame, sink: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Converte o DataFrame do Yahoo (linhas = contas, colunas = períodos)."""
        produced: list[dict[str, Any]] = []
        index = {str(i).strip(): i for i in df.index}

        for canonical, aliases in mapping.items():
            source_row = next((index[a] for a in aliases if a in index), None)
            if source_row is None:
                continue
            for period in df.columns:
                value = df.at[source_row, period]
                if pd.isna(value):
                    continue
                period_end = pd.Timestamp(period).tz_localize(None)
                publication = period_end + pd.Timedelta(days=self.publication_lag_days)
                row = {
                    "ticker": ticker,
                    "statement": statement,
                    "line_item": canonical,
                    "period_end": period_end.strftime("%Y-%m-%d"),
                    "period_type": "Q",
                    "fiscal_year": int(period_end.year),
                    "fiscal_period": f"Q{period_end.quarter}",
                    "value": float(value),
                    "unit": "unit",
                    "currency": None,
                    "publication_date": publication.strftime("%Y-%m-%d"),
                    # A linha que impede este dado de mentir num backtest.
                    "publication_date_is_estimated": 1,
                    "version": 1,
                    "original_tag": str(source_row),
                    "document_id": None,
                    "source": "yfinance",
                }
                produced.append(row)
                sink.append(row)
        return produced


register("yfinance", YFinanceProvider)
