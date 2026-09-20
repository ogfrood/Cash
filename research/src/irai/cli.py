"""Interface de linha de comando do Investment Research AI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from irai.config import get_settings, load_settings
from irai.core.db.database import Database
from irai.core.db.repository import PITPolicy, Repository
from irai.core.reporting import console as C


def _open(args: argparse.Namespace) -> tuple[Repository, object]:
    settings = load_settings() if args.config is None else load_settings(args.config)
    db_path = Path(args.db) if args.db else settings.database_path
    db = Database(db_path)
    repo = Repository(db, PITPolicy.from_settings(settings))
    return repo, settings


# ------------------------------------------------------------------ comandos

def cmd_init_db(args: argparse.Namespace) -> int:
    repo, settings = _open(args)
    tables = repo.db.query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    print(C.rule("Banco inicializado"))
    print(f"  arquivo : {repo.db.path}")
    print(f"  tabelas : {len(tables)}")
    print("  " + ", ".join(t["name"] for t in tables if not t["name"].startswith("sqlite_")))
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    from irai.core.providers.registry import available, get_provider

    print(C.rule("Provedores registrados"))
    for name in available():
        try:
            caps = get_provider(name).capabilities
        except Exception as exc:  # pragma: no cover
            print(f"  {name:<14s} indisponível ({exc})")
            continue
        flags = []
        if caps.prices:
            flags.append("preços")
        if caps.fundamentals:
            flags.append("fundamentos")
        pit = "SIM" if caps.provides_real_publication_dates else "NÃO"
        delisted = "SIM" if caps.covers_delisted else "NÃO"
        print(f"  {name:<14s} {', '.join(flags):<24s} data de publicação real: {pit:<4s} "
              f"delistadas: {delisted}")
        if caps.notes:
            print(f"  {'':<14s} {caps.notes}")
    print()
    print("  Comparativo completo das fontes: DATA_SOURCES.md")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Roda o pipeline inteiro sobre dados SINTÉTICOS."""
    from irai.core.backtest.engine import BacktestConfig, BacktestEngine, persist_backtest
    from irai.core.providers.synthetic import SyntheticConfig, SyntheticProvider
    from irai.core.scoring.engine import ScoringConfig, ScoringEngine

    import dataclasses

    repo, settings = _open(args)
    # O benchmark real (^GSPC) não existe no conjunto sintético; a demo usa o
    # índice equiponderado gerado junto com as empresas.
    market = dataclasses.replace(
        settings.market("US"), benchmark="^SYNX", benchmark_name="Índice sintético"
    )

    print(C.rule("AVISO", char="="))
    print("  Esta demonstração usa DADOS SINTÉTICOS gerados localmente.")
    print("  As empresas não existem. O gerador planta uma relação conhecida")
    print(f"  entre fundamentos e retorno futuro (signal_strength={args.signal}).")
    print("  O resultado prova que o encanamento funciona — NÃO prova nada")
    print("  sobre o mercado real. Para ruído puro, rode com --signal 0.")
    print()

    provider = SyntheticProvider(SyntheticConfig(
        n_companies=args.companies, start=args.start, end=args.end,
        market="US", signal_strength=args.signal,
    ))

    print(C.rule("1. DATA — ingestão"))
    info = provider.fetch_company_info()
    n = repo.upsert_companies(info.rows)
    print(f"  empresas ................. {n}")

    prices = provider.fetch_prices().frame
    n = repo.upsert_prices(prices, source="synthetic")
    print(f"  preços (linhas) .......... {n:,}")

    bench = provider.fetch_benchmark().frame
    repo.upsert_prices(bench, source="synthetic")
    print(f"  benchmark ................ {bench['ticker'].iloc[0]} ({len(bench):,} pregões)")

    fin = provider.fetch_financials()
    n = repo.upsert_financials(fin.rows)
    print(f"  linhas de balanço ........ {n:,} (com data de publicação real)")

    print()
    print(C.rule("2. DATA — cálculo de fundamentos derivados (point-in-time)"))
    n_metrics = _derive_fundamentals(repo, info.frame["ticker"].tolist())
    print(f"  métricas derivadas ....... {n_metrics:,}")
    print("  cada métrica herda a data de publicação do insumo mais recente")

    print()
    print(C.rule("3. Universo com snapshots históricos"))
    tickers = info.frame["ticker"].tolist()
    snapshots = pd.date_range(args.start, args.end, freq="QE")
    for snap in snapshots:
        repo.upsert_universe_snapshot(
            snap.strftime("%Y-%m-%d"), "US", "config", tickers, source="synthetic"
        )
    print(f"  snapshots gravados ....... {len(snapshots)} (trimestrais)")
    print("  o backtest usa a composição registrada em cada data, não a de hoje")

    print()
    print(C.rule("4. QUANT ENGINE — scoring numa data"))
    scoring_cfg = ScoringConfig.load(settings.scoring_config_path())
    engine = ScoringEngine(scoring_cfg)
    from irai.core.features.builder import FeatureBuilder

    as_of = args.as_of or (pd.Timestamp(args.end) - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    panel = FeatureBuilder(repo, market).build(tickers, as_of)
    result = engine.score(panel)
    ranked = result.ranked("total")
    print(f"  data de análise .......... {as_of}")
    print(f"  config de scoring ........ {scoring_cfg.version} (hash {scoring_cfg.config_hash[:12]})")
    print(f"  empresas pontuadas ....... {len(ranked)} de {len(tickers)}")
    print(f"  cobertura mediana ........ {C.fmt_pct(result.coverage['total'].median())}")
    print()
    cols = ["quality", "growth", "value", "momentum", "financial_health", "risk", "total"]
    top = ranked.head(8)[cols].round(2)
    top.insert(0, "ticker", top.index)
    print(C.table(top.reset_index(drop=True)))

    print()
    print(C.rule("   Por que a primeira da lista apareceu"))
    best = ranked.index[0]
    explanation = result.explain(best)
    print(f"  {best} — grupo de pares: {explanation['peer_group']} "
          f"({int(explanation['peer_count'] or 0)} empresas)")
    for c in explanation["top_positive"][:4]:
        print(f"    + {c['factor']:<24s} valor={C.fmt_num(c['raw_value'], 3):>10s}  "
              f"z={c['z_score']:+.2f}  contribuição={c['contribution']:+.2f}")
    for c in explanation["top_negative"][:2]:
        print(f"    - {c['factor']:<24s} valor={C.fmt_num(c['raw_value'], 3):>10s}  "
              f"z={c['z_score']:+.2f}  contribuição={c['contribution']:+.2f}")
    if explanation["missing_factors"]:
        print(f"    ! fatores ausentes: {', '.join(sorted(set(explanation['missing_factors']))[:6])}")

    print()
    print(C.rule("5. BACKTESTING"))
    bt_cfg = BacktestConfig(
        start=args.start, end=args.end,
        rebalance=settings.backtest["rebalance"],
        portfolio_size=min(args.portfolio, args.companies // 3),
        initial_capital=settings.backtest["initial_capital"],
        transaction_cost_bps=settings.backtest["transaction_cost_bps"],
        slippage_bps=settings.backtest["slippage_bps"],
        min_price=settings.backtest["min_price"],
        min_median_traded_value=settings.backtest["min_median_dollar_volume"],
        execution_lag_days=settings.point_in_time.execution_lag_days,
    )
    bt = BacktestEngine(repo, market, engine, bt_cfg).run()
    persist_backtest(repo, bt)
    print(f"  período .................. {bt_cfg.start} a {bt_cfg.end}")
    print(f"  rebalance ................ {bt_cfg.rebalance}, {bt_cfg.portfolio_size} posições, "
          f"execução em D+{bt_cfg.execution_lag_days}")
    print(f"  custo total .............. {bt_cfg.transaction_cost_bps + bt_cfg.slippage_bps:.0f} bps por ponta")
    print()
    print(C.metrics_block(bt.metrics, [
        "total_return", "cagr", "volatility", "sharpe", "sortino", "max_drawdown",
        "win_rate", "benchmark_total_return", "benchmark_cagr", "excess_return",
        "beta", "alpha_annualized", "information_ratio", "turnover_annual",
        "n_trades", "total_costs", "n_rebalances_skipped",
    ]))
    print()
    print(f"  backtest_id .............. {bt.backtest_id} (gravado no banco com todas as hipóteses)")
    skipped = bt.diagnostics.get("skipped_rebalances", [])
    if skipped:
        reasons: dict[str, int] = {}
        for s_ in skipped:
            reasons[s_["reason"]] = reasons.get(s_["reason"], 0) + 1
        print(f"  rebalances pulados ....... {len(skipped)} "
              f"(primeiro: {skipped[0]['date']}, último: {skipped[-1]['date']})")
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"      {count:>3d}x  {reason}")
        print("      ficar em caixa quando não há sinal é comportamento, não falha")

    print()
    print(C.rule("Estado da Fase 1", char="="))
    print("  Pronto  : DATA point-in-time, QUANT ENGINE, SCORING, BACKTEST")
    print("  A seguir: walk-forward, prediction journal, calibração, camada de IA")
    return 0


def _derive_fundamentals(repo: Repository, tickers: list[str]) -> int:
    """Calcula métricas derivadas para cada trimestre, com PIT preservado."""
    from irai.markets.stocks.fundamentals.metrics import FundamentalsCalculator

    total = 0
    for ticker in tickers:
        raw_all = repo.db.query(
            """SELECT DISTINCT period_end, publication_date FROM financials
               WHERE ticker = ? ORDER BY period_end""",
            (ticker,),
        )
        for row in raw_all:
            as_of = row["publication_date"]
            fins = repo.financials_as_of([ticker], as_of)
            if fins.empty:
                continue
            calc = FundamentalsCalculator(fins)
            results = calc.compute_all()
            rows = [r.as_row(ticker, source="synthetic") for r in results]
            total += repo.upsert_fundamentals(rows)
    return total


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="irai",
        description="Investment Research AI — motor de pesquisa quantitativa. "
                    "Não prevê o mercado; mede e registra.",
    )
    parser.add_argument("--db", help="Caminho do banco (sobrescreve settings.yaml)")
    parser.add_argument("--config", help="Caminho do settings.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Cria/atualiza o banco").set_defaults(func=cmd_init_db)
    sub.add_parser("sources", help="Lista provedores e suas limitações").set_defaults(func=cmd_sources)

    demo = sub.add_parser("demo", help="Pipeline completo sobre dados sintéticos")
    demo.add_argument("--companies", type=int, default=40)
    demo.add_argument("--start", default="2016-01-01")
    demo.add_argument("--end", default="2024-12-31")
    demo.add_argument("--as-of", default=None)
    demo.add_argument("--portfolio", type=int, default=10)
    demo.add_argument("--signal", type=float, default=0.35,
                      help="Força do sinal plantado nos dados sintéticos (0 = ruído puro)")
    demo.set_defaults(func=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nInterrompido.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
