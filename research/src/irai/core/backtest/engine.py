"""Motor de backtest.

Hipóteses — todas explícitas, todas gravadas junto do resultado:

- Execução no FECHAMENTO do dia seguinte ao sinal (`execution_lag_days`).
  Decidir e executar no mesmo fechamento é look-ahead disfarçado de detalhe.
- Custo de transação e slippage aplicados sobre o valor negociado, nas duas
  pontas.
- Sem alavancagem, sem venda a descoberto, carteira apenas comprada.
- Dividendos entram via `adj_close` (retorno total), não como caixa. Isso
  superestima levemente o resultado de quem paga imposto sobre provento.
- Capacidade infinita: a ordem não move o preço. Falso para small caps.
- O universo de cada data vem de `universe_snapshots`; sem snapshot, o
  backtest FALHA em vez de usar a lista de hoje.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from irai.config import MarketConfig
from irai.core.db.repository import Repository
from irai.core.features.builder import FeatureBuilder
from irai.core.quant.risk import risk_summary
from irai.core.scoring.engine import ScoringEngine


@dataclass
class BacktestConfig:
    start: str
    end: str
    rebalance: str = "M"
    portfolio_size: int = 10
    weighting: str = "equal"
    initial_capital: float = 100_000.0
    transaction_cost_bps: float = 15.0
    slippage_bps: float = 10.0
    min_price: float = 1.0
    min_median_traded_value: float = 1_000_000.0
    min_names_to_trade: int = 3
    execution_lag_days: int = 1
    universe_name: str = "config"
    allow_static_universe: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class BacktestResult:
    backtest_id: str
    config: BacktestConfig
    market: str
    model_version: str
    config_hash: str
    equity: pd.Series
    benchmark_equity: pd.Series
    returns: pd.Series
    benchmark_returns: pd.Series
    holdings: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float]
    assumptions: dict[str, Any]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def summary_table(self) -> pd.DataFrame:
        keys = ["total_return", "cagr", "volatility", "sharpe", "sortino", "calmar",
                "max_drawdown", "win_rate", "benchmark_total_return", "benchmark_cagr",
                "excess_return", "beta", "alpha_annualized", "information_ratio",
                "turnover_annual", "n_trades"]
        return pd.DataFrame(
            [{"metric": k, "value": self.metrics.get(k)} for k in keys if k in self.metrics]
        )


class BacktestEngine:
    def __init__(
        self,
        repo: Repository,
        market: MarketConfig,
        scoring: ScoringEngine,
        config: BacktestConfig,
    ) -> None:
        self.repo = repo
        self.market = market
        self.scoring = scoring
        self.config = config
        self.builder = FeatureBuilder(repo, market)

    # ------------------------------------------------------------ execução
    def run(self, model_version: str = "stock-v1.0.0") -> BacktestResult:
        cfg = self.config
        universe_all = self._full_universe()
        if not universe_all:
            raise ValueError(
                "Universo vazio. Popule `universe_snapshots` antes de rodar o backtest "
                "(irai universe snapshot ...)."
            )

        calendar = self.repo.trading_dates(universe_all, cfg.start, cfg.end)
        if len(calendar) < 60:
            raise ValueError(
                f"Calendário insuficiente: {len(calendar)} pregões entre {cfg.start} e {cfg.end}."
            )
        calendar_index = pd.DatetimeIndex(calendar)
        rebalance_dates = self._rebalance_dates(calendar_index)

        prices = self.repo.price_panel(universe_all, start=cfg.start, end=cfg.end)
        prices = prices.reindex(calendar_index).ffill()
        bench_panel = self.repo.price_panel([self.market.benchmark], start=cfg.start, end=cfg.end)
        has_benchmark = not bench_panel.empty and self.market.benchmark in bench_panel
        bench = (
            bench_panel[self.market.benchmark].reindex(calendar_index).ffill()
            if has_benchmark else pd.Series(np.nan, index=calendar_index)
        )

        cash = cfg.initial_capital
        shares: dict[str, float] = {}
        equity_values: list[float] = []
        holdings_rows: list[dict[str, Any]] = []
        trades_rows: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        turnover_events: list[float] = []

        pending: dict[pd.Timestamp, list[dict[str, Any]]] = {}

        for i, date in enumerate(calendar_index):
            # 1) executa ordens agendadas para hoje (sinal de dias atrás)
            if date in pending:
                cash, shares, executed, turnover = self._execute(
                    pending.pop(date), prices.loc[date], cash, shares, date
                )
                trades_rows.extend(executed)
                if turnover is not None:
                    turnover_events.append(turnover)

            # 2) marca a carteira a mercado
            position_value = sum(
                qty * _price_of(prices, date, tkr) for tkr, qty in shares.items()
            )
            equity = cash + position_value
            equity_values.append(equity)
            for tkr, qty in shares.items():
                px = _price_of(prices, date, tkr)
                holdings_rows.append({
                    "date": date, "ticker": tkr, "quantity": qty, "price": px,
                    "value": qty * px, "weight": (qty * px / equity) if equity else np.nan,
                })

            # 3) gera sinal e agenda execução para d + lag
            if date in rebalance_dates and i + cfg.execution_lag_days < len(calendar_index):
                target, reason = self._target_portfolio(date)
                if target is None:
                    skipped.append({"date": str(date.date()), "reason": reason})
                else:
                    exec_date = calendar_index[i + cfg.execution_lag_days]
                    pending[exec_date] = target

        equity_series = pd.Series(equity_values, index=calendar_index, name="equity")
        returns = equity_series.pct_change(fill_method=None).fillna(0.0)
        bench_returns = bench.pct_change(fill_method=None).fillna(0.0) if has_benchmark \
            else pd.Series(np.nan, index=calendar_index)
        bench_equity = (
            cfg.initial_capital * (1 + bench_returns).cumprod() if has_benchmark
            else pd.Series(np.nan, index=calendar_index)
        )

        metrics = risk_summary(
            returns,
            bench_returns if has_benchmark else None,
            self.market.risk_free_fallback_annual,
            self.market.trading_days_per_year,
        )
        years = max(len(calendar_index) / self.market.trading_days_per_year, 1e-9)
        metrics["turnover_annual"] = float(np.sum(turnover_events) / years) if turnover_events else 0.0
        metrics["n_trades"] = float(len(trades_rows))
        metrics["n_rebalances"] = float(len(rebalance_dates))
        metrics["n_rebalances_skipped"] = float(len(skipped))
        metrics["total_costs"] = float(sum(t["cost"] for t in trades_rows))
        metrics["cost_drag_on_total_return"] = (
            float(metrics["total_costs"] / cfg.initial_capital) if cfg.initial_capital else np.nan
        )

        assumptions = {
            **cfg.to_dict(),
            "market": self.market.code,
            "benchmark": self.market.benchmark,
            "benchmark_available": bool(has_benchmark),
            "risk_free_annual": self.market.risk_free_fallback_annual,
            "trading_days_per_year": self.market.trading_days_per_year,
            "dividends": "incluídos via adj_close (retorno total, sem imposto)",
            "short_selling": False,
            "leverage": False,
            "market_impact": "não modelado — capacidade tratada como infinita",
            "universe_source": "universe_snapshots (point-in-time)",
            "data_sources": sorted({
                r["source"] for r in self.repo.db.query("SELECT DISTINCT source FROM prices")
            }),
        }

        return BacktestResult(
            backtest_id=f"BT-{uuid.uuid4().hex[:10]}",
            config=cfg, market=self.market.code, model_version=model_version,
            config_hash=self.scoring.config.config_hash,
            equity=equity_series, benchmark_equity=bench_equity,
            returns=returns, benchmark_returns=bench_returns,
            holdings=pd.DataFrame(holdings_rows), trades=pd.DataFrame(trades_rows),
            metrics=metrics, assumptions=assumptions,
            diagnostics={"skipped_rebalances": skipped,
                         "n_universe_all_time": len(universe_all)},
        )

    # ------------------------------------------------------------ internos
    def _full_universe(self) -> list[str]:
        rows = self.repo.db.query(
            """
            SELECT DISTINCT ticker FROM universe_snapshots
            WHERE market = ? AND universe_name = ? AND snapshot_date <= ?
            """,
            (self.market.code, self.config.universe_name, self.config.end),
        )
        return [r["ticker"] for r in rows]

    def _rebalance_dates(self, calendar: pd.DatetimeIndex) -> set[pd.Timestamp]:
        freq = {"M": "ME", "Q": "QE", "W": "W-FRI"}.get(self.config.rebalance, "ME")
        marks = pd.Series(1, index=calendar).resample(freq).last().index
        out = set()
        for mark in marks:
            eligible = calendar[calendar <= mark]
            if len(eligible):
                out.add(eligible[-1])
        return out

    def _target_portfolio(
        self, date: pd.Timestamp
    ) -> tuple[list[dict[str, Any]] | None, str]:
        cfg = self.config
        as_of = date.strftime("%Y-%m-%d")
        universe = self.repo.universe_as_of(self.market.code, cfg.universe_name, as_of)
        if not universe:
            return None, "sem snapshot de universo para a data"

        panel = self.builder.build(universe, as_of)
        if panel.frame.empty:
            return None, "painel de fatores vazio"

        # Filtros de negociabilidade ANTES do ranking: uma ação que não dá
        # para comprar não deveria nem entrar na disputa.
        frame = panel.frame
        eligible = frame.index[
            (frame["last_price"].fillna(0) >= cfg.min_price)
            & (frame["liquidity_median_traded_value"].fillna(0) >= cfg.min_median_traded_value)
        ]
        if len(eligible) < cfg.min_names_to_trade:
            return None, f"apenas {len(eligible)} ativos passaram nos filtros de liquidez"

        panel.frame = frame.loc[eligible]
        panel.sectors = panel.sectors.loc[eligible]
        result = self.scoring.score(panel)
        ranked = result.ranked("total")
        if len(ranked) < cfg.min_names_to_trade:
            return None, f"apenas {len(ranked)} ativos com score completo"

        selected = ranked.head(cfg.portfolio_size)
        if cfg.weighting == "score_proportional":
            raw = selected["total"] - selected["total"].min() + 1e-6
            weights = raw / raw.sum()
        else:
            weights = pd.Series(1.0 / len(selected), index=selected.index)

        return [
            {"ticker": t, "weight": float(w), "score": float(selected.loc[t, "total"]),
             "as_of": as_of}
            for t, w in weights.items()
        ], "ok"

    def _execute(
        self,
        target: list[dict[str, Any]],
        price_row: pd.Series,
        cash: float,
        shares: dict[str, float],
        date: pd.Timestamp,
    ) -> tuple[float, dict[str, float], list[dict[str, Any]], float | None]:
        cfg = self.config
        cost_rate = (cfg.transaction_cost_bps + cfg.slippage_bps) / 10_000.0

        equity = cash + sum(
            qty * float(price_row.get(t, np.nan) or np.nan) for t, qty in shares.items()
        )
        if not np.isfinite(equity) or equity <= 0:
            return cash, shares, [], None

        target_value = {t["ticker"]: t["weight"] * equity for t in target}
        scores = {t["ticker"]: t["score"] for t in target}
        trades: list[dict[str, Any]] = []
        traded_value = 0.0
        new_shares: dict[str, float] = {}

        for ticker in set(shares) | set(target_value):
            price = float(price_row.get(ticker, np.nan))
            if not np.isfinite(price) or price <= 0:
                # Sem preço de execução, mantemos a posição como está.
                if ticker in shares:
                    new_shares[ticker] = shares[ticker]
                continue
            current_qty = shares.get(ticker, 0.0)
            desired_qty = target_value.get(ticker, 0.0) / price
            delta = desired_qty - current_qty
            if abs(delta * price) < 1e-6:
                if desired_qty > 0:
                    new_shares[ticker] = desired_qty
                continue
            value = abs(delta * price)
            cost = value * cost_rate
            cash -= delta * price + cost
            traded_value += value
            trades.append({
                "date": date, "ticker": ticker,
                "action": "buy" if delta > 0 else "sell",
                "quantity": abs(delta), "price": price, "cost": cost,
                "reason": f"rebalance score={scores.get(ticker, float('nan')):.3f}"
                if ticker in scores else "saída do ranking",
            })
            if desired_qty > 0:
                new_shares[ticker] = desired_qty

        turnover = traded_value / equity if equity > 0 else None
        return cash, new_shares, trades, turnover


def _price_of(prices: pd.DataFrame, date: pd.Timestamp, ticker: str) -> float:
    try:
        value = float(prices.at[date, ticker])
    except (KeyError, ValueError, TypeError):
        return 0.0
    return value if np.isfinite(value) else 0.0


def persist_backtest(repo: Repository, result: BacktestResult) -> None:
    """Grava o backtest inteiro — inclusive as hipóteses — para auditoria."""
    from irai.core.db.database import utcnow

    now = utcnow()
    repo.db.execute(
        """
        INSERT INTO backtests (backtest_id, created_at, model_version, market, universe_name,
                               start_date, end_date, rebalance, portfolio_size, benchmark,
                               assumptions_json, metrics_json, config_hash, kind)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (result.backtest_id, now, result.model_version, result.market,
         result.config.universe_name, result.config.start, result.config.end,
         result.config.rebalance, result.config.portfolio_size,
         result.assumptions.get("benchmark"),
         json.dumps(result.assumptions, ensure_ascii=False, default=str),
         json.dumps(result.metrics, ensure_ascii=False, default=str),
         result.config_hash, "backtest"),
    )
    equity_rows = [
        (result.backtest_id, d.strftime("%Y-%m-%d"), float(v),
         float(result.benchmark_equity.get(d, np.nan)), None, None)
        for d, v in result.equity.items()
    ]
    repo.db.executemany(
        """INSERT OR REPLACE INTO backtest_equity
           (backtest_id, date, equity, benchmark_equity, drawdown, n_positions)
           VALUES (?,?,?,?,?,?)""",
        equity_rows,
    )
    if not result.trades.empty:
        repo.db.executemany(
            """INSERT INTO backtest_trades
               (backtest_id, date, ticker, action, quantity, price, cost, reason)
               VALUES (?,?,?,?,?,?,?,?)""",
            [(result.backtest_id, r.date.strftime("%Y-%m-%d"), r.ticker, r.action,
              float(r.quantity), float(r.price), float(r.cost), r.reason)
             for r in result.trades.itertuples(index=False)],
        )
