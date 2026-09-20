-- Investment Research AI — schema
--
-- Três invariantes que valem para o banco inteiro:
--
--   1. Todo fato carrega `source`. Sem fonte, o dado não entra.
--   2. Todo fato datável carrega DUAS datas: quando o dado passou a valer
--      (`period_end` / `date`) e quando ele ficou PÚBLICO (`publication_date`).
--      `ingested_at` é auditoria e nunca entra em filtro de backtest.
--   3. Nada é apagado. Reapresentação vira nova `version`; modelo velho
--      continua no banco.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- universo

CREATE TABLE IF NOT EXISTS companies (
    ticker            TEXT PRIMARY KEY,
    market            TEXT NOT NULL,              -- BR | US | ...
    name              TEXT,
    sector            TEXT,
    industry          TEXT,
    currency          TEXT,
    country           TEXT,
    cnpj              TEXT,                       -- BR
    cvm_code          TEXT,                       -- BR
    cik               TEXT,                       -- US
    listed_date       TEXT,
    delisted_date     TEXT,                       -- NULL = ainda listada
    is_active         INTEGER NOT NULL DEFAULT 1,
    source            TEXT NOT NULL,
    ingested_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_companies_market ON companies(market, is_active);
CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(market, sector);

-- Composição do universo EM CADA DATA. É o que impede viés de sobrevivência:
-- o backtest de 2015 usa a lista registrada para 2015, não a lista de hoje.
CREATE TABLE IF NOT EXISTS universe_snapshots (
    snapshot_date     TEXT NOT NULL,
    market            TEXT NOT NULL,
    universe_name     TEXT NOT NULL,              -- ex.: 'ibovespa', 'sp500', 'config'
    ticker            TEXT NOT NULL,
    weight            REAL,                       -- peso no índice, quando aplicável
    source            TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, market, universe_name, ticker)
);
CREATE INDEX IF NOT EXISTS idx_universe_lookup
    ON universe_snapshots(market, universe_name, snapshot_date);

-- ----------------------------------------------------------------- preços

CREATE TABLE IF NOT EXISTS prices (
    ticker            TEXT NOT NULL,
    date              TEXT NOT NULL,
    open              REAL,
    high              REAL,
    low               REAL,
    close             REAL,                       -- preço bruto, como negociado
    adj_close         REAL,                       -- ajustado por proventos e splits
    volume            REAL,
    currency          TEXT,
    source            TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    PRIMARY KEY (ticker, date, source)
);
CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices(ticker, date);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);

CREATE TABLE IF NOT EXISTS dividends (
    ticker            TEXT NOT NULL,
    ex_date           TEXT NOT NULL,
    payment_date      TEXT,
    declared_date     TEXT,                       -- quando virou público
    amount            REAL NOT NULL,
    currency          TEXT,
    kind              TEXT,                       -- dividend | jcp | special
    source            TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    PRIMARY KEY (ticker, ex_date, kind, source)
);

CREATE TABLE IF NOT EXISTS splits (
    ticker            TEXT NOT NULL,
    date              TEXT NOT NULL,
    ratio             REAL NOT NULL,              -- 2.0 = desdobramento 2:1
    source            TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    PRIMARY KEY (ticker, date, source)
);

-- ------------------------------------------------------------ fundamentos

-- Linhas BRUTAS de demonstração financeira, como vieram do documento.
-- Nada é calculado aqui. Reapresentação entra como nova `version`.
CREATE TABLE IF NOT EXISTS financials (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                   TEXT NOT NULL,
    statement                TEXT NOT NULL,       -- income | balance | cashflow
    line_item                TEXT NOT NULL,       -- nome canônico interno
    period_end               TEXT NOT NULL,
    period_start             TEXT,
    period_type              TEXT NOT NULL,       -- Q | A | TTM
    fiscal_year              INTEGER,
    fiscal_period            TEXT,                -- Q1..Q4 | FY
    value                    REAL,
    unit                     TEXT,
    currency                 TEXT,
    publication_date         TEXT NOT NULL,       -- quando ficou público
    publication_date_is_estimated INTEGER NOT NULL DEFAULT 0,
    version                  INTEGER NOT NULL DEFAULT 1,
    original_tag             TEXT,                -- tag XBRL / CD_CONTA de origem
    document_id              TEXT,                -- accession number / id CVM
    source                   TEXT NOT NULL,
    ingested_at              TEXT NOT NULL,
    UNIQUE (ticker, statement, line_item, period_end, period_type, version, source)
);
CREATE INDEX IF NOT EXISTS idx_financials_pit
    ON financials(ticker, line_item, publication_date, period_end);

-- Métricas DERIVADAS (ROE, margens, múltiplos...). Herdam a data de publicação
-- do insumo mais recente usado no cálculo — nunca uma data melhor que essa.
CREATE TABLE IF NOT EXISTS fundamentals (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                   TEXT NOT NULL,
    metric                   TEXT NOT NULL,
    period_end               TEXT NOT NULL,
    period_type              TEXT NOT NULL,       -- Q | A | TTM | POINT
    value                    REAL,
    unit                     TEXT,
    currency                 TEXT,
    publication_date         TEXT NOT NULL,
    publication_date_is_estimated INTEGER NOT NULL DEFAULT 0,
    version                  INTEGER NOT NULL DEFAULT 1,
    inputs_json              TEXT,                -- insumos usados: rastreabilidade
    source                   TEXT NOT NULL,
    ingested_at              TEXT NOT NULL,
    UNIQUE (ticker, metric, period_end, period_type, version, source)
);
CREATE INDEX IF NOT EXISTS idx_fundamentals_pit
    ON fundamentals(ticker, metric, publication_date, period_end);

-- -------------------------------------------------------------- sinais

-- Valor de cada fator, por ticker e data de decisão. É o insumo do scoring
-- e a evidência que o relatório cita.
CREATE TABLE IF NOT EXISTS signals (
    as_of_date        TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    signal_name       TEXT NOT NULL,
    raw_value         REAL,
    normalized_value  REAL,                       -- z robusto dentro do grupo
    peer_group        TEXT,                       -- grupo usado na normalização
    peer_count        INTEGER,
    coverage_flag     TEXT,                       -- ok | missing | stale | estimated
    source            TEXT NOT NULL,
    config_hash       TEXT,
    ingested_at       TEXT NOT NULL,
    PRIMARY KEY (as_of_date, ticker, signal_name)
);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(as_of_date, signal_name);

CREATE TABLE IF NOT EXISTS scores (
    as_of_date        TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    model_version     TEXT NOT NULL,
    pillar            TEXT NOT NULL,              -- quality|growth|...|TOTAL
    value             REAL,
    coverage          REAL,                       -- fração de fatores disponíveis
    rank_in_universe  INTEGER,
    percentile        REAL,
    config_hash       TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    PRIMARY KEY (as_of_date, ticker, model_version, pillar)
);
CREATE INDEX IF NOT EXISTS idx_scores_lookup ON scores(as_of_date, model_version, pillar);

-- --------------------------------------------------------- versões de modelo

-- Nunca apagar linha desta tabela. É o que permite comparar v1.0 com v1.4
-- meses depois e saber exatamente o que mudou.
CREATE TABLE IF NOT EXISTS model_versions (
    model_version     TEXT PRIMARY KEY,           -- ex.: 'stock-v1.0.0'
    market            TEXT NOT NULL,
    family            TEXT NOT NULL,              -- scoring | ml | ensemble
    created_at        TEXT NOT NULL,
    config_hash       TEXT NOT NULL,
    config_json       TEXT NOT NULL,              -- cópia integral da config
    parent_version    TEXT,
    status            TEXT NOT NULL,              -- candidate | active | retired
    notes             TEXT
);

-- Contador de variantes testadas. Existe para calcular deflated Sharpe e
-- lembrar que testar 200 ideias no mesmo dado tem custo estatístico.
CREATE TABLE IF NOT EXISTS model_experiments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version     TEXT NOT NULL,
    experiment_at     TEXT NOT NULL,
    description       TEXT,
    n_variants_tested INTEGER NOT NULL DEFAULT 1,
    dataset_window    TEXT,
    result_json       TEXT,
    FOREIGN KEY (model_version) REFERENCES model_versions(model_version)
);

-- ------------------------------------------------------------- previsões

-- O diário de previsões. Toda afirmação do sistema vira linha aqui ANTES de
-- o futuro acontecer; o resultado é preenchido depois, sem poder editar a
-- previsão original.
CREATE TABLE IF NOT EXISTS model_predictions (
    prediction_id     TEXT PRIMARY KEY,           -- STOCK-000123
    created_at        TEXT NOT NULL,
    as_of_date        TEXT NOT NULL,              -- data da informação usada
    ticker            TEXT NOT NULL,
    market            TEXT NOT NULL,
    model_version     TEXT NOT NULL,
    horizon_days      INTEGER NOT NULL,
    target            TEXT NOT NULL,              -- excess_return | absolute_return
    -- O que o sistema afirmou:
    predicted_probability REAL,                   -- P(alvo > 0) na amostra histórica
    predicted_value   REAL,                       -- estimativa pontual, quando houver
    uncertainty_low   REAL,
    uncertainty_high  REAL,
    base_rate         REAL,                       -- taxa base da amostra: sem isto,
                                                  -- probabilidade não significa nada
    sample_size       INTEGER,
    effective_sample_size REAL,                   -- corrigida por sobreposição
    confidence        TEXT,                       -- low | medium | high
    -- Contexto reproduzível:
    features_json     TEXT NOT NULL,
    market_regime     TEXT,
    data_sources_json TEXT NOT NULL,
    config_hash       TEXT NOT NULL,
    score_total       REAL,
    notes             TEXT,
    FOREIGN KEY (model_version) REFERENCES model_versions(model_version)
);
CREATE INDEX IF NOT EXISTS idx_pred_lookup
    ON model_predictions(model_version, as_of_date, horizon_days);
CREATE INDEX IF NOT EXISTS idx_pred_ticker ON model_predictions(ticker, as_of_date);

-- Resultado observado. Tabela separada de propósito: previsão é imutável,
-- resultado chega meses depois.
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    prediction_id     TEXT PRIMARY KEY,
    evaluated_at      TEXT NOT NULL,
    resolution_date   TEXT NOT NULL,
    actual_return     REAL,
    benchmark_return  REAL,
    excess_return     REAL,
    realized_volatility REAL,
    realized_max_drawdown REAL,
    outcome           INTEGER,                    -- 1 = alvo positivo, 0 = não
    brier_component   REAL,                       -- (p - outcome)^2
    absolute_error    REAL,
    status            TEXT NOT NULL,              -- resolved | insufficient_data
    FOREIGN KEY (prediction_id) REFERENCES model_predictions(prediction_id)
);

-- ----------------------------------------------------------- backtesting

CREATE TABLE IF NOT EXISTS backtests (
    backtest_id       TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    model_version     TEXT NOT NULL,
    market            TEXT NOT NULL,
    universe_name     TEXT NOT NULL,
    start_date        TEXT NOT NULL,
    end_date          TEXT NOT NULL,
    rebalance         TEXT NOT NULL,
    portfolio_size    INTEGER NOT NULL,
    benchmark         TEXT,
    assumptions_json  TEXT NOT NULL,              -- TODAS as hipóteses, explícitas
    metrics_json      TEXT NOT NULL,
    config_hash       TEXT NOT NULL,
    kind              TEXT NOT NULL DEFAULT 'backtest'  -- backtest | walkforward_fold
);

CREATE TABLE IF NOT EXISTS backtest_equity (
    backtest_id       TEXT NOT NULL,
    date              TEXT NOT NULL,
    equity            REAL NOT NULL,
    benchmark_equity  REAL,
    drawdown          REAL,
    n_positions       INTEGER,
    PRIMARY KEY (backtest_id, date),
    FOREIGN KEY (backtest_id) REFERENCES backtests(backtest_id)
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_id       TEXT NOT NULL,
    date              TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    action            TEXT NOT NULL,              -- buy | sell
    quantity          REAL,
    price             REAL,
    cost              REAL,
    reason            TEXT,
    FOREIGN KEY (backtest_id) REFERENCES backtests(backtest_id)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    backtest_id       TEXT NOT NULL,
    date              TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    weight            REAL NOT NULL,
    quantity          REAL,
    price             REAL,
    value             REAL,
    score_total       REAL,
    PRIMARY KEY (backtest_id, date, ticker)
);

-- ------------------------------------------------------------ paper trading

CREATE TABLE IF NOT EXISTS paper_portfolios (
    portfolio_id      TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    market            TEXT NOT NULL,
    model_version     TEXT NOT NULL,
    initial_capital   REAL NOT NULL,
    benchmark         TEXT,
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS paper_positions (
    portfolio_id      TEXT NOT NULL,
    date              TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    quantity          REAL NOT NULL,
    entry_date        TEXT,
    entry_price       REAL,
    price             REAL,
    value             REAL,
    weight            REAL,
    reason            TEXT NOT NULL,              -- por que entrou; obrigatório
    model_version     TEXT NOT NULL,
    prediction_id     TEXT,
    PRIMARY KEY (portfolio_id, date, ticker),
    FOREIGN KEY (portfolio_id) REFERENCES paper_portfolios(portfolio_id)
);

-- -------------------------------------------------------------- macro/news

CREATE TABLE IF NOT EXISTS macro_series (
    series_id         TEXT NOT NULL,              -- BCB_SELIC, FRED_DGS10...
    date              TEXT NOT NULL,
    value             REAL,
    unit              TEXT,
    publication_date  TEXT,                       -- releases macro são revisados
    source            TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    PRIMARY KEY (series_id, date, source)
);

CREATE TABLE IF NOT EXISTS news (
    news_id           TEXT PRIMARY KEY,           -- hash(url + título)
    ticker            TEXT,
    market            TEXT,
    publication_date  TEXT NOT NULL,
    retrieved_at      TEXT NOT NULL,
    source            TEXT NOT NULL,
    url               TEXT NOT NULL,
    headline          TEXT NOT NULL,
    summary           TEXT,
    category          TEXT,                       -- earnings | guidance | m&a | ...
    sentiment         REAL,                       -- -1..1, OPINIÃO, não fato
    sentiment_model   TEXT,
    confidence        REAL,
    potential_impact  TEXT,
    is_classified_by_ai INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_news_ticker_date ON news(ticker, publication_date);

-- --------------------------------------------------- qualidade e relatórios

CREATE TABLE IF NOT EXISTS data_quality_issues (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at       TEXT NOT NULL,
    table_name        TEXT NOT NULL,
    ticker            TEXT,
    check_name        TEXT NOT NULL,
    severity          TEXT NOT NULL,              -- info | warning | error
    detail            TEXT,
    sample_json       TEXT,
    resolved          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ai_reports (
    report_id         TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    ticker            TEXT,
    market            TEXT,
    as_of_date        TEXT NOT NULL,
    model_version     TEXT NOT NULL,
    llm_model         TEXT,
    evidence_hash     TEXT NOT NULL,              -- hash do pacote de evidências
    evidence_json     TEXT NOT NULL,              -- os números que a IA recebeu
    report_markdown   TEXT NOT NULL,
    self_critique_markdown TEXT,
    guardrail_status  TEXT NOT NULL,              -- pass | flagged | blocked
    guardrail_detail  TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_reports_ticker ON ai_reports(ticker, as_of_date);

CREATE TABLE IF NOT EXISTS schema_meta (
    key               TEXT PRIMARY KEY,
    value             TEXT NOT NULL
);
