"""Interface de linha de comando do Investment Research AI."""

from __future__ import annotations

import argparse
import pathlib
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
    from irai.markets.stocks.fundamentals.derive import derive_for_tickers
    n_metrics = sum(derive_for_tickers(
        repo, info.frame["ticker"].tolist(), source="synthetic").values())
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

    from irai.core.models.registry import ModelRegistry

    registry = ModelRegistry(repo)
    model_version = "stock-v1.0.0"
    registry.ensure(model_version, market.code, scoring_cfg.config_hash, scoring_cfg.raw)
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
    print(C.rule("6. WALK-FORWARD — teste fora da amostra"))
    from irai.core.backtest.walkforward import WalkForwardRunner

    def scoring_factory(_: str) -> ScoringEngine:
        return ScoringEngine(scoring_cfg)

    variants = [
        {"name": "top5", "portfolio_size": 5},
        {"name": "top10", "portfolio_size": 10},
        {"name": "top10-trimestral", "portfolio_size": 10, "rebalance": "Q"},
    ]
    wf = WalkForwardRunner(repo, market, scoring_factory, bt_cfg).run(
        start=args.start, end=args.end, train_years=3, test_years=1,
        variants=variants, selection_metric="sharpe",
    )
    print(f"  protocolo ................ calibra 3 anos, testa 1, janela expansiva")
    print(f"  variantes por fold ....... {len(variants)}  "
          f"(total de backtests de calibração: {wf.total_variants_tested})")
    print()
    if wf.folds:
        tbl = wf.table().copy()
        for col in ("ret_calib", "ret_teste", "dd_teste"):
            tbl[col] = tbl[col].map(lambda v: C.fmt_pct(v))
        for col in ("sharpe_calib", "sharpe_teste"):
            tbl[col] = tbl[col].map(lambda v: C.fmt_num(v))
        print(C.table(tbl))
        print()
        cons = wf.consistency()
        print(f"  folds ..................... {int(cons.get('n_folds', 0))}")
        print(f"  folds com retorno positivo  {C.fmt_pct(cons.get('share_positive_return'))}")
        print(f"  folds que bateram o índice  {C.fmt_pct(cons.get('share_beat_benchmark'))}")
        print(f"  pior fold ................. {C.fmt_pct(cons.get('worst_fold_return'))}")
        print()
        if wf.degradation:
            print("  Degradação calibração -> teste (quanto do resultado era ajuste):")
            for key in ("total_return", "sharpe"):
                tr = wf.degradation.get(f"{key}_train_mean")
                te = wf.degradation.get(f"{key}_test_mean")
                if tr is None:
                    continue
                fmt = C.fmt_pct if key == "total_return" else C.fmt_num
                print(f"      {key:<16s} calibração {fmt(tr):>10s}  ->  teste {fmt(te):>10s}")
        print()
        dsr = wf.combined_metrics.get("deflated_sharpe_probability")
        print(f"  Sharpe combinado (só teste)  {C.fmt_num(wf.combined_metrics.get('sharpe'))}")
        print(f"  Deflated Sharpe P(>0) ...... {C.fmt_num(dsr, 4)}")
        print(f"      corrige pelo nº de variantes testadas ({wf.total_variants_tested}).")
        print("      Perto de 1 = o resultado sobrevive ao número de tentativas.")
        print("      Perto de 0 = você encontrou a melhor de N sorteios.")
    else:
        print("  Nenhum fold completo — período curto demais para o protocolo.")
    registry.record_experiment(
        model_version,
        description="walk-forward expansivo na demo sintética",
        n_variants_tested=wf.total_variants_tested,
        dataset_window=f"{args.start}..{args.end}",
        result={"combined_sharpe": wf.combined_metrics.get("sharpe")},
    )
    print(f"  variantes acumuladas ....... {registry.total_variants_tested(model_version)} "
          f"(gravado em model_experiments; alimenta o deflated Sharpe)")
    for w in wf.warnings[:3]:
        print(f"  aviso: {w}")

    print()
    print(C.rule("7. PREDICTION JOURNAL + avaliação"))
    n_pred, evaluation = _run_predictions(repo, market, engine, scoring_cfg, args)
    print(f"  previsões registradas .... {n_pred}")
    print(f"  resolvidas ............... {evaluation.n_resolved}")
    print(f"  amostra efetiva .......... {evaluation.effective_sample_size:.0f} blocos "
          f"independentes (de {evaluation.n_resolved} previsões brutas)")
    if evaluation.metrics:
        print()
        print(C.metrics_block(evaluation.metrics, [
            "base_rate_observed", "directional_accuracy", "brier_score",
            "brier_score_baseline_base_rate", "brier_skill_score", "mean_excess_return",
        ]))
    if evaluation.calibration:
        print()
        print("  Calibração — o que foi dito vs. o que aconteceu:")
        print(f"      {'faixa':<14s}{'n':>5s}{'previsto':>11s}{'observado':>11s}{'IC95%':>18s}")
        for b in evaluation.calibration:
            ci = f"{b.ci_low*100:.0f}–{b.ci_high*100:.0f}%"
            print(f"      {b.lower:.0%}–{b.upper:.0%}{b.n:>8d}"
                  f"{b.mean_predicted:>10.1%}{b.observed_frequency:>11.1%}{ci:>18s}")
    for w in evaluation.warnings:
        print(f"  aviso: {w}")

    print()
    print(C.rule("8. AI INTERPRETATION — relatório rastreável"))
    from irai.core.reporting.pipeline import analyze_company

    analysis = analyze_company(
        repo, market, engine, best, as_of, tickers, settings,
        model_version="stock-v1.0.0",
    )
    rep = analysis.report
    print(f"  empresa .................. {analysis.ticker}")
    print(f"  hash da evidência ........ {analysis.evidence_hash[:16]}")
    print(f"  redator .................. "
          f"{rep.llm_model or 'gerador determinístico (sem ANTHROPIC_API_KEY)'}")
    print(f"  guardrails ............... {rep.guardrail.status} "
          f"({rep.guardrail.checked_numbers} números conferidos contra a evidência)")
    for note in rep.notes[:2]:
        print(f"  nota: {note}")
    out_dir = settings.reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{analysis.ticker}_{as_of}.md"
    out_path.write_text(rep.render(), encoding="utf-8")
    print(f"  relatório gravado ........ {out_path}")
    print()
    preview = rep.report_markdown.splitlines()
    print("  " + "\n  ".join(preview[:14]))
    print("  ...")

    print()
    print(C.rule("Fase 1 completa", char="="))
    print("  DATA point-in-time -> QUANT ENGINE -> BACKTEST -> WALK-FORWARD")
    print("  -> PREDICTION JOURNAL -> CALIBRAÇÃO -> AI INTERPRETATION")
    print()
    print("  Lembrete: tudo acima roda sobre dados SINTÉTICOS. O número que")
    print("  importa não está aqui — está no track record que só existe depois")
    print("  de meses de previsões reais registradas e resolvidas.")
    return 0


def _run_predictions(repo, market, engine, scoring_cfg, args):
    """Gera previsões históricas a partir de frequências condicionais, registra
    no diário e resolve as que já venceram.

    Cada previsão é feita com a amostra que existia NAQUELA data — nunca com a
    amostra completa. É a diferença entre track record e ilusão de retrospecto.
    """
    import pandas as pd

    from irai.core.features.builder import FeatureBuilder
    from irai.core.predictions.evaluation import PredictionEvaluator
    from irai.core.predictions.historical import HistoricalFrequencyEngine, build_observations
    from irai.core.predictions.journal import Prediction, PredictionJournal

    horizon = 126  # ~6 meses de pregões
    tickers = [r["ticker"] for r in repo.db.query(
        "SELECT DISTINCT ticker FROM universe_snapshots WHERE market = ?", (market.code,))]
    prices = repo.price_panel(tickers, start=args.start, end=args.end)
    bench_panel = repo.price_panel([market.benchmark], start=args.start, end=args.end)
    bench = bench_panel[market.benchmark] if market.benchmark in bench_panel else pd.Series(dtype=float)

    # Scores em datas semestrais: suficiente para a demo, e reduz sobreposição.
    dates = pd.date_range(args.start, args.end, freq="2QE")
    builder = FeatureBuilder(repo, market)
    scores_by_date = {}
    for d in dates:
        as_of = d.strftime("%Y-%m-%d")
        panel = builder.build(tickers, as_of)
        if panel.frame.empty:
            continue
        res = engine.score(panel)
        frame = res.scores.dropna(subset=["total"])
        if not frame.empty:
            scores_by_date[as_of] = frame

    observations = build_observations(scores_by_date, prices, bench, horizon,
                                      feature_columns=["total", "quality", "momentum"])
    if observations.empty:
        evaluator = PredictionEvaluator(repo)
        return 0, evaluator.evaluate()

    hist_engine = HistoricalFrequencyEngine(observations, horizon, target="excess_return")
    journal = PredictionJournal(repo)
    n = 0
    for as_of, frame in scores_by_date.items():
        for ticker in frame.index[:6]:
            score = float(frame.loc[ticker, "total"])
            est = hist_engine.estimate_by_quantile(as_of, "total", score, n_quantiles=4)
            if est.frequency_positive is None:
                continue
            journal.record(Prediction(
                ticker=ticker, market=market.code, as_of_date=as_of,
                horizon_days=horizon, model_version="stock-v1.0.0",
                config_hash=scoring_cfg.config_hash, target="excess_return",
                predicted_probability=est.frequency_positive,
                base_rate=est.base_rate, sample_size=est.sample_size,
                effective_sample_size=est.effective_sample_size,
                uncertainty_low=est.ci_low, uncertainty_high=est.ci_high,
                confidence=est.confidence,
                features={"score_total": score,
                          "quality": float(frame.loc[ticker, "quality"])
                          if "quality" in frame.columns and pd.notna(frame.loc[ticker, "quality"])
                          else None},
                data_sources=["synthetic"], market_regime="não classificado (Fase 4)",
                score_total=score, notes=est.condition,
            ))
            n += 1

    evaluator = PredictionEvaluator(repo)
    evaluator.resolve_pending(args.end, market.benchmark)
    return n, evaluator.evaluate(model_version="stock-v1.0.0")

def _load_universe(path):
    import yaml

    raw = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))
    return raw["market"], raw.get("name", path), raw["tickers"]


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingere dados REAIS de mercado. Roda na sua máquina, não no container."""
    from irai.core.providers.registry import get_provider
    from irai.markets.stocks.fundamentals.derive import derive_for_tickers

    repo, settings = _open(args)
    market_code, universe_label, tickers = _load_universe(args.universe)
    market = settings.market(market_code)
    provider = get_provider(args.provider, market=market_code)
    caps = provider.capabilities

    end = args.end or pd.Timestamp.today().strftime("%Y-%m-%d")
    start = args.start or (pd.Timestamp(end) - pd.DateOffset(years=args.years)).strftime("%Y-%m-%d")

    print(C.rule(f"Ingestão · {universe_label}"))
    print(f"  mercado .................. {market.name}")
    print(f"  provedor ................. {caps.name}")
    print(f"  período .................. {start} a {end}")
    print(f"  ativos ................... {len(tickers)}")
    if not caps.provides_real_publication_dates:
        print()
        print("  AVISO: este provedor NÃO informa a data de publicação dos balanços.")
        print("  Os fundamentos entram com data estimada e o BACKTEST OS DESCARTA.")
        print("  Para análise da data de hoje eles servem; para testar o passado, não.")
    print()

    info = provider.fetch_company_info(tickers)
    n = repo.upsert_companies(info.rows)
    print(f"  cadastro ................. {n} empresas")
    for w in info.warnings[:3]:
        print(f"      aviso: {w}")

    prices = provider.fetch_prices(tickers, start, end)
    n = repo.upsert_prices(prices.frame, source=caps.name) if not prices.frame.empty else 0
    print(f"  preços ................... {n:,} linhas")
    for w in prices.warnings[:3]:
        print(f"      aviso: {w}")

    bench = provider.fetch_prices([market.benchmark], start, end)
    if not bench.frame.empty:
        repo.upsert_prices(bench.frame, source=caps.name)
        print(f"  benchmark ................ {market.benchmark} ({len(bench.frame):,} pregões)")
    else:
        print(f"  benchmark ................ FALHOU ({market.benchmark}) — beta e alpha ficarão vazios")

    fins = provider.fetch_financials(tickers)
    n = repo.upsert_financials(fins.rows)
    print(f"  linhas de balanço ........ {n:,}")
    for w in fins.warnings[:3]:
        print(f"      aviso: {w}")

    derived = derive_for_tickers(repo, tickers, source=f"derived:{caps.name}")
    print(f"  métricas derivadas ....... {sum(derived.values()):,}")

    today = pd.Timestamp(end).strftime("%Y-%m-%d")
    repo.upsert_universe_snapshot(today, market_code, args.universe_name, tickers,
                                  source=caps.name)
    print(f"  snapshot do universo ..... {today} ({args.universe_name})")
    print()
    print(f"  Banco: {repo.db.path}")
    print(f"  Próximo passo: irai rank --market {market_code}")
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    """Lista de empresas que merecem pesquisa — NÃO é lista de compra."""
    from irai.core.db.repository import PITPolicy, Repository
    from irai.core.features.builder import FeatureBuilder
    from irai.core.scoring.engine import ScoringConfig, ScoringEngine

    repo, settings = _open(args)
    market = settings.market(args.market)
    as_of = args.as_of or pd.Timestamp.today().strftime("%Y-%m-%d")

    tickers = repo.universe_as_of(args.market, args.universe_name, as_of)
    if not tickers:
        print(f"Sem snapshot de universo para {args.market} em {as_of}.")
        print("Rode primeiro: irai ingest --universe config/universe_br.yaml")
        return 1

    # Analisar HOJE não é simular o passado: não há futuro para vazar. Por isso
    # a data estimada de publicação é aceitável aqui e proibida no backtest.
    days_old = (pd.Timestamp.today() - pd.Timestamp(as_of)).days
    is_current = days_old <= args.current_window_days
    policy = PITPolicy(allow_estimated=is_current and not args.strict)
    repo = Repository(repo.db, policy)

    scoring_cfg = ScoringConfig.load(settings.scoring_config_path())
    engine = ScoringEngine(scoring_cfg)
    panel = FeatureBuilder(repo, market).build(tickers, as_of)
    if panel.frame.empty:
        print("Painel de fatores vazio — sem preços suficientes no banco.")
        return 1
    result = engine.score(panel)
    ranked = result.ranked("total")

    print(C.rule("Companies Worth Further Research", char="="))
    print(f"  mercado .................. {market.name}")
    print(f"  data de análise .......... {as_of}" + ("  (análise corrente)" if is_current else ""))
    print(f"  modelo ................... {scoring_cfg.version} · config {scoring_cfg.config_hash[:12]}")
    print(f"  pontuadas ................ {len(ranked)} de {len(tickers)}")
    print(f"  datas de publicação ...... "
          f"{'estimadas, aceitas nesta análise corrente' if policy.allow_estimated else 'apenas reais'}")
    print()
    print("  ISTO NÃO É UMA LISTA DE COMPRA. É uma ordenação relativa segundo")
    print("  critérios declarados em MODEL_METHODOLOGY.md. Não estima retorno,")
    print("  não indica preço justo e não substitui a leitura dos documentos.")
    print()

    if ranked.empty:
        print("  Nenhuma empresa atingiu a cobertura mínima de fatores.")
        print("  Provável causa: poucos trimestres de balanço no banco.")
        return 1

    cols = [p.name for p in scoring_cfg.active_pillars]
    table = ranked.head(args.top)[cols + ["total"]].round(2)
    table.insert(0, "ticker", table.index)
    sectors = repo.sector_map(list(table.index))
    table.insert(1, "setor", [(sectors.get(t) or "—")[:14] for t in table.index])
    print(C.table(table.reset_index(drop=True), max_rows=args.top))
    print()

    print(C.rule("Por que cada uma apareceu"))
    for ticker in ranked.index[:args.explain]:
        exp = result.explain(ticker)
        fatores = ", ".join(
            f"{c['factor']} (z {c['z_score']:+.1f})" for c in exp["top_positive"][:3]
        )
        contra = ", ".join(
            f"{c['factor']} (z {c['z_score']:+.1f})" for c in exp["top_negative"][:2]
        )
        cobertura = exp["coverage"].get("total")
        print(f"  {ticker}")
        print(f"      a favor : {fatores or '—'}")
        print(f"      contra  : {contra or '—'}")
        print(f"      pares   : {exp['peer_group']} ({int(exp['peer_count'] or 0)}) · "
              f"cobertura {C.fmt_pct(cobertura)}")
    print()
    print(C.rule("Antes de usar isto com dinheiro", char="="))
    print("  1. O modelo ainda NÃO demonstrou habilidade fora da amostra.")
    print("     Rode: irai backtest e irai walkforward --market " + args.market)
    print("  2. Se o walk-forward vier negativo, esta lista é ruído ordenado.")
    print("  3. Paper trading por pelo menos um trimestre antes de qualquer ordem.")
    return 0


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


    ing = sub.add_parser("ingest", help="Ingere dados REAIS de mercado (roda na sua máquina)")
    ing.add_argument("--universe", required=True, help="config/universe_br.yaml")
    ing.add_argument("--provider", default="yfinance")
    ing.add_argument("--universe-name", default="config")
    ing.add_argument("--years", type=int, default=6)
    ing.add_argument("--start", default=None)
    ing.add_argument("--end", default=None)
    ing.set_defaults(func=cmd_ingest)

    rk = sub.add_parser("rank", help="Empresas que merecem pesquisa (NÃO é lista de compra)")
    rk.add_argument("--market", default="BR")
    rk.add_argument("--universe-name", default="config")
    rk.add_argument("--as-of", default=None)
    rk.add_argument("--top", type=int, default=15)
    rk.add_argument("--explain", type=int, default=5)
    rk.add_argument("--strict", action="store_true",
                    help="Exige data de publicação real mesmo na análise corrente")
    rk.add_argument("--current-window-days", type=int, default=10)
    rk.set_defaults(func=cmd_rank)

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
