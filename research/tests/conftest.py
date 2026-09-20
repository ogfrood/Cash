from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from irai.config import load_settings  # noqa: E402
from irai.core.db.database import Database  # noqa: E402
from irai.core.db.repository import PITPolicy, Repository  # noqa: E402
from irai.core.providers.synthetic import SyntheticConfig, SyntheticProvider  # noqa: E402
from irai.markets.stocks.fundamentals.derive import derive_for_tickers  # noqa: E402


@pytest.fixture
def settings():
    return load_settings(ROOT / "config" / "settings.yaml")


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def repo(db):
    return Repository(db, PITPolicy(allow_estimated=False))


@pytest.fixture
def synthetic_provider():
    return SyntheticProvider(SyntheticConfig(
        n_companies=12, start="2018-01-01", end="2022-12-31", seed=42,
    ))


@pytest.fixture
def loaded_repo(repo, synthetic_provider):
    """Repositório com um universo sintético pequeno já ingerido."""
    info = synthetic_provider.fetch_company_info()
    repo.upsert_companies(info.rows)
    repo.upsert_prices(synthetic_provider.fetch_prices().frame, source="synthetic")
    repo.upsert_prices(synthetic_provider.fetch_benchmark().frame, source="synthetic")
    repo.upsert_financials(synthetic_provider.fetch_financials().rows)
    tickers = info.frame["ticker"].tolist()
    derive_for_tickers(repo, tickers, source="synthetic")
    for snap in pd.date_range("2018-01-01", "2022-12-31", freq="QE"):
        repo.upsert_universe_snapshot(
            snap.strftime("%Y-%m-%d"), "US", "config", tickers, source="synthetic"
        )
    return repo
