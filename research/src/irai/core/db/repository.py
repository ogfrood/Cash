"""Repositório point-in-time — o único caminho legítimo até os dados.

Nenhum módulo de sinal, score ou backtest lê as tabelas diretamente. Tudo
passa por aqui, porque é aqui que mora a regra que impede o sistema de
enxergar o futuro:

    publication_date <= as_of

Ver docs/LOOKAHEAD_BIAS.md §3. Se alguém contornar esta camada, o teste de
envenenamento em tests/test_lookahead.py quebra.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from irai.core.db.database import Database, utcnow


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def _as_list(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


@dataclass(frozen=True)
class PITPolicy:
    """Política de leitura point-in-time.

    `allow_estimated` liga o uso de fundamentos cuja data de publicação foi
    ESTIMADA por lag em vez de lida do documento. Padrão: desligado.
    """

    allow_estimated: bool = False

    @classmethod
    def from_settings(cls, settings: Any) -> PITPolicy:
        return cls(allow_estimated=settings.point_in_time.allow_estimated_publication_dates)


class Repository:
    def __init__(self, db: Database, policy: PITPolicy | None = None) -> None:
        self.db = db
        self.policy = policy or PITPolicy()

    # ================================================================ escrita

    def upsert_companies(self, rows: Iterable[dict[str, Any]]) -> int:
        now = utcnow()
        payload = [
            (
                r["ticker"], r["market"], r.get("name"), r.get("sector"), r.get("industry"),
                r.get("currency"), r.get("country"), r.get("cnpj"), r.get("cvm_code"),
                r.get("cik"), r.get("listed_date"), r.get("delisted_date"),
                1 if r.get("delisted_date") in (None, "") else 0,
                r["source"], now,
            )
            for r in rows
        ]
        if not payload:
            return 0
        self.db.executemany(
            """
            INSERT INTO companies (ticker, market, name, sector, industry, currency, country,
                                   cnpj, cvm_code, cik, listed_date, delisted_date, is_active,
                                   source, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=excluded.market, name=excluded.name, sector=excluded.sector,
                industry=excluded.industry, currency=excluded.currency,
                country=excluded.country, cnpj=excluded.cnpj, cvm_code=excluded.cvm_code,
                cik=excluded.cik, listed_date=excluded.listed_date,
                delisted_date=excluded.delisted_date, is_active=excluded.is_active,
                source=excluded.source, ingested_at=excluded.ingested_at
            """,
            payload,
        )
        return len(payload)

    def upsert_prices(self, frame: pd.DataFrame, source: str) -> int:
        """Grava OHLCV. `frame` precisa de ticker, date, close, adj_close, volume."""
        if frame.empty:
            return 0
        now = utcnow()
        required = {"ticker", "date", "close", "adj_close"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Colunas ausentes em upsert_prices: {sorted(missing)}")
        df = frame.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        for col in ("open", "high", "low", "volume", "currency"):
            if col not in df.columns:
                df[col] = None
        payload = [
            (
                row.ticker, row.date, row.open, row.high, row.low, row.close,
                row.adj_close, row.volume, row.currency, source, now,
            )
            for row in df.itertuples(index=False)
        ]
        self.db.executemany(
            """
            INSERT INTO prices (ticker, date, open, high, low, close, adj_close, volume,
                                currency, source, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker, date, source) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, adj_close=excluded.adj_close,
                volume=excluded.volume, ingested_at=excluded.ingested_at
            """,
            payload,
        )
        return len(payload)

    def upsert_financials(self, rows: Iterable[dict[str, Any]]) -> int:
        now = utcnow()
        payload = []
        for r in rows:
            self._require_publication(r)
            payload.append((
                r["ticker"], r["statement"], r["line_item"], str(r["period_end"]),
                r.get("period_start"), r["period_type"], r.get("fiscal_year"),
                r.get("fiscal_period"), r.get("value"), r.get("unit"), r.get("currency"),
                str(r["publication_date"]), int(bool(r.get("publication_date_is_estimated", 0))),
                int(r.get("version", 1)), r.get("original_tag"), r.get("document_id"),
                r["source"], now,
            ))
        if not payload:
            return 0
        self.db.executemany(
            """
            INSERT INTO financials (ticker, statement, line_item, period_end, period_start,
                                    period_type, fiscal_year, fiscal_period, value, unit,
                                    currency, publication_date, publication_date_is_estimated,
                                    version, original_tag, document_id, source, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker, statement, line_item, period_end, period_type, version, source)
            DO UPDATE SET value=excluded.value, publication_date=excluded.publication_date,
                          publication_date_is_estimated=excluded.publication_date_is_estimated,
                          ingested_at=excluded.ingested_at
            """,
            payload,
        )
        return len(payload)

    def upsert_fundamentals(self, rows: Iterable[dict[str, Any]]) -> int:
        now = utcnow()
        payload = []
        for r in rows:
            self._require_publication(r)
            inputs = r.get("inputs")
            payload.append((
                r["ticker"], r["metric"], str(r["period_end"]), r.get("period_type", "TTM"),
                r.get("value"), r.get("unit"), r.get("currency"),
                str(r["publication_date"]), int(bool(r.get("publication_date_is_estimated", 0))),
                int(r.get("version", 1)),
                json.dumps(inputs, ensure_ascii=False) if inputs is not None else None,
                r["source"], now,
            ))
        if not payload:
            return 0
        self.db.executemany(
            """
            INSERT INTO fundamentals (ticker, metric, period_end, period_type, value, unit,
                                      currency, publication_date,
                                      publication_date_is_estimated, version, inputs_json,
                                      source, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker, metric, period_end, period_type, version, source)
            DO UPDATE SET value=excluded.value, publication_date=excluded.publication_date,
                          publication_date_is_estimated=excluded.publication_date_is_estimated,
                          inputs_json=excluded.inputs_json, ingested_at=excluded.ingested_at
            """,
            payload,
        )
        return len(payload)

    def upsert_universe_snapshot(
        self, snapshot_date: str, market: str, universe_name: str,
        tickers: Iterable[str], source: str, weights: dict[str, float] | None = None,
    ) -> int:
        now = utcnow()
        weights = weights or {}
        payload = [
            (snapshot_date, market, universe_name, t, weights.get(t), source, now)
            for t in tickers
        ]
        if not payload:
            return 0
        self.db.executemany(
            """
            INSERT INTO universe_snapshots
                (snapshot_date, market, universe_name, ticker, weight, source, ingested_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(snapshot_date, market, universe_name, ticker)
            DO UPDATE SET weight=excluded.weight, ingested_at=excluded.ingested_at
            """,
            payload,
        )
        return len(payload)

    @staticmethod
    def _require_publication(row: dict[str, Any]) -> None:
        if not row.get("publication_date"):
            raise ValueError(
                f"Fato sem publication_date para {row.get('ticker')!r} "
                f"({row.get('metric') or row.get('line_item')!r}). "
                "Dado sem data de publicação não entra no banco — ver docs/LOOKAHEAD_BIAS.md."
            )

    # ================================================================= leitura

    def price_panel(
        self,
        tickers: Sequence[str],
        start: str | None = None,
        end: str | None = None,
        field: str = "adj_close",
    ) -> pd.DataFrame:
        """Painel largo (datas x tickers) do campo pedido.

        `end` é inclusivo e funciona como a fronteira point-in-time de preços:
        nada posterior a ele é retornado.
        """
        if not tickers:
            return pd.DataFrame()
        if field not in {"open", "high", "low", "close", "adj_close", "volume"}:
            raise ValueError(f"Campo de preço inválido: {field!r}")
        sql = f"SELECT ticker, date, {field} AS value FROM prices WHERE ticker IN ({_placeholders(len(tickers))})"  # noqa: S608
        params: list[Any] = list(tickers)
        if start:
            sql += " AND date >= ?"
            params.append(start)
        if end:
            sql += " AND date <= ?"
            params.append(end)
        rows = self.db.query(sql, params)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([dict(r) for r in rows])
        panel = df.pivot_table(index="date", columns="ticker", values="value", aggfunc="last")
        panel.index = pd.to_datetime(panel.index)
        return panel.sort_index()

    def fundamentals_as_of(
        self,
        tickers: Sequence[str],
        as_of: str,
        metrics: Sequence[str] | None = None,
        allow_estimated: bool | None = None,
    ) -> pd.DataFrame:
        """Último valor de cada métrica **que já era público** em `as_of`.

        Resolve reapresentação escolhendo, para cada (ticker, métrica), o
        período mais recente e, dentro dele, a maior versão publicada até
        `as_of` — e não a versão mais recente que existe hoje.
        """
        rows = self._fundamentals_rows(tickers, as_of, metrics, allow_estimated)
        if not rows:
            return pd.DataFrame(
                columns=["ticker", "metric", "value", "period_end", "period_type",
                         "publication_date", "publication_date_is_estimated", "version",
                         "source", "inputs_json"]
            )
        df = pd.DataFrame([dict(r) for r in rows])
        df = df.sort_values(
            ["ticker", "metric", "period_end", "version", "publication_date"],
            ascending=[True, True, False, False, False],
        )
        return df.drop_duplicates(subset=["ticker", "metric"], keep="first").reset_index(drop=True)

    def fundamentals_history_as_of(
        self,
        tickers: Sequence[str],
        as_of: str,
        metrics: Sequence[str] | None = None,
        allow_estimated: bool | None = None,
    ) -> pd.DataFrame:
        """Série histórica de cada métrica, com a versão vigente em `as_of`.

        É o insumo de 'múltiplo atual vs. média histórica': o histórico precisa
        ser o histórico **como era conhecido** naquela data.
        """
        rows = self._fundamentals_rows(tickers, as_of, metrics, allow_estimated)
        if not rows:
            return pd.DataFrame(
                columns=["ticker", "metric", "value", "period_end", "period_type",
                         "publication_date", "publication_date_is_estimated", "version",
                         "source", "inputs_json"]
            )
        df = pd.DataFrame([dict(r) for r in rows])
        df = df.sort_values(
            ["ticker", "metric", "period_end", "version", "publication_date"],
            ascending=[True, True, True, False, False],
        )
        return (
            df.drop_duplicates(subset=["ticker", "metric", "period_end"], keep="first")
            .reset_index(drop=True)
        )

    def _fundamentals_rows(
        self,
        tickers: Sequence[str],
        as_of: str,
        metrics: Sequence[str] | None,
        allow_estimated: bool | None,
    ) -> list[Any]:
        tickers = list(tickers)
        if not tickers:
            return []
        allow = self.policy.allow_estimated if allow_estimated is None else allow_estimated
        sql = f"""
            SELECT ticker, metric, value, period_end, period_type, publication_date,
                   publication_date_is_estimated, version, source, inputs_json
            FROM fundamentals
            WHERE ticker IN ({_placeholders(len(tickers))})
              AND publication_date <= ?
        """  # noqa: S608
        params: list[Any] = [*tickers, as_of]
        if not allow:
            sql += " AND publication_date_is_estimated = 0"
        if metrics:
            sql += f" AND metric IN ({_placeholders(len(metrics))})"
            params.extend(metrics)
        return self.db.query(sql, params)

    def financials_as_of(
        self,
        tickers: Sequence[str],
        as_of: str,
        line_items: Sequence[str] | None = None,
        period_type: str | None = None,
        allow_estimated: bool | None = None,
    ) -> pd.DataFrame:
        """Linhas brutas de demonstração conhecidas em `as_of`, uma por período."""
        tickers = list(tickers)
        if not tickers:
            return pd.DataFrame()
        allow = self.policy.allow_estimated if allow_estimated is None else allow_estimated
        sql = f"""
            SELECT ticker, statement, line_item, period_end, period_start, period_type,
                   fiscal_year, fiscal_period, value, unit, currency, publication_date,
                   publication_date_is_estimated, version, source
            FROM financials
            WHERE ticker IN ({_placeholders(len(tickers))})
              AND publication_date <= ?
        """  # noqa: S608
        params: list[Any] = [*tickers, as_of]
        if not allow:
            sql += " AND publication_date_is_estimated = 0"
        if line_items:
            sql += f" AND line_item IN ({_placeholders(len(line_items))})"
            params.extend(line_items)
        if period_type:
            sql += " AND period_type = ?"
            params.append(period_type)
        rows = self.db.query(sql, params)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([dict(r) for r in rows])
        df = df.sort_values(
            ["ticker", "line_item", "period_end", "version", "publication_date"],
            ascending=[True, True, True, False, False],
        )
        return (
            df.drop_duplicates(subset=["ticker", "line_item", "period_end", "period_type"],
                               keep="first")
            .reset_index(drop=True)
        )

    def universe_as_of(self, market: str, universe_name: str, as_of: str) -> list[str]:
        """Composição do universo registrada na data mais recente <= `as_of`.

        Sem snapshot anterior à data, retorna lista vazia — de propósito. Um
        backtest que silenciosamente cai para 'a lista de hoje' é um backtest
        com viés de sobrevivência disfarçado.
        """
        row = self.db.query_one(
            """
            SELECT MAX(snapshot_date) AS d FROM universe_snapshots
            WHERE market = ? AND universe_name = ? AND snapshot_date <= ?
            """,
            (market, universe_name, as_of),
        )
        if row is None or row["d"] is None:
            return []
        rows = self.db.query(
            """
            SELECT ticker FROM universe_snapshots
            WHERE market = ? AND universe_name = ? AND snapshot_date = ?
            ORDER BY ticker
            """,
            (market, universe_name, row["d"]),
        )
        return [r["ticker"] for r in rows]

    def companies(self, market: str | None = None, tickers: Sequence[str] | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM companies"
        params: list[Any] = []
        clauses = []
        if market:
            clauses.append("market = ?")
            params.append(market)
        if tickers:
            clauses.append(f"ticker IN ({_placeholders(len(tickers))})")
            params.extend(tickers)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        rows = self.db.query(sql, params)
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

    def sector_map(self, tickers: Sequence[str]) -> dict[str, str]:
        df = self.companies(tickers=tickers)
        if df.empty:
            return {}
        return {
            r["ticker"]: (r["sector"] or "UNKNOWN")
            for _, r in df.iterrows()
        }

    def trading_dates(self, tickers: Sequence[str], start: str, end: str) -> list[pd.Timestamp]:
        if not tickers:
            return []
        rows = self.db.query(
            f"""
            SELECT DISTINCT date FROM prices
            WHERE ticker IN ({_placeholders(len(tickers))}) AND date >= ? AND date <= ?
            ORDER BY date
            """,  # noqa: S608
            [*tickers, start, end],
        )
        return [pd.Timestamp(r["date"]) for r in rows]

    def data_span(self, tickers: Sequence[str]) -> tuple[str | None, str | None]:
        if not tickers:
            return (None, None)
        row = self.db.query_one(
            f"SELECT MIN(date) AS a, MAX(date) AS b FROM prices WHERE ticker IN ({_placeholders(len(tickers))})",  # noqa: S608
            list(tickers),
        )
        return (row["a"], row["b"]) if row else (None, None)

    # =========================================================== diagnóstico

    def coverage_report(self, tickers: Sequence[str], as_of: str) -> pd.DataFrame:
        """Quantas métricas cada ticker tem disponíveis em `as_of`, e quantas
        foram descartadas por terem data de publicação estimada.

        Existe para que o relatório possa dizer 'descartei 40% dos fundamentos'
        em vez de fingir cobertura total.
        """
        strict = self.fundamentals_as_of(tickers, as_of, allow_estimated=False)
        loose = self.fundamentals_as_of(tickers, as_of, allow_estimated=True)
        out = []
        for t in tickers:
            n_strict = 0 if strict.empty else int((strict["ticker"] == t).sum())
            n_loose = 0 if loose.empty else int((loose["ticker"] == t).sum())
            out.append({
                "ticker": t,
                "metrics_with_real_publication_date": n_strict,
                "metrics_including_estimated": n_loose,
                "discarded_as_estimated": n_loose - n_strict,
            })
        return pd.DataFrame(out)
