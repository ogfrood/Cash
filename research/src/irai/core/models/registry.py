"""Registro de versões de modelo.

Nenhuma linha desta tabela é apagada, nunca. É o que permite, dois anos
depois, olhar uma previsão de hoje e saber exatamente qual configuração a
produziu — e comparar `stock-v1.0.0` com `stock-v1.4.0` sobre o mesmo período.

Uma previsão não pode ser gravada sem uma versão registrada. A chave
estrangeira no banco garante isso mesmo se alguém esquecer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pandas as pd

from irai.core.db.database import utcnow
from irai.core.db.repository import Repository

STATUS_CANDIDATE = "candidate"
STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"


@dataclass
class ModelVersion:
    model_version: str
    market: str
    family: str
    config_hash: str
    config: dict[str, Any]
    parent_version: str | None = None
    status: str = STATUS_CANDIDATE
    notes: str | None = None


class ModelRegistry:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def register(self, version: ModelVersion, overwrite_config: bool = False) -> str:
        """Registra a versão. Idempotente.

        Se a versão já existe com OUTRO hash de configuração, é erro: mudou a
        config, então precisa de nova versão. Reescrever a config de uma versão
        publicada apagaria o rastro de tudo que ela já afirmou.
        """
        existing = self.get(version.model_version)
        if existing is not None:
            if existing["config_hash"] != version.config_hash and not overwrite_config:
                raise ValueError(
                    f"Versão {version.model_version!r} já existe com config_hash "
                    f"{existing['config_hash'][:12]}, mas foi passada "
                    f"{version.config_hash[:12]}. Mudou a configuração: crie uma nova "
                    f"versão em vez de reescrever a existente."
                )
            return version.model_version

        self.repo.db.execute(
            """
            INSERT INTO model_versions (model_version, market, family, created_at,
                                        config_hash, config_json, parent_version,
                                        status, notes)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (version.model_version, version.market, version.family, utcnow(),
             version.config_hash,
             json.dumps(version.config, ensure_ascii=False, default=str),
             version.parent_version, version.status, version.notes),
        )
        return version.model_version

    def ensure(self, model_version: str, market: str, config_hash: str,
               config: dict[str, Any], family: str = "scoring") -> str:
        """Registra se ainda não existe. Usado pelos pipelines."""
        return self.register(ModelVersion(
            model_version=model_version, market=market, family=family,
            config_hash=config_hash, config=config, status=STATUS_CANDIDATE,
            notes="Registrada automaticamente pelo pipeline.",
        ))

    def get(self, model_version: str) -> dict[str, Any] | None:
        row = self.repo.db.query_one(
            "SELECT * FROM model_versions WHERE model_version = ?", (model_version,)
        )
        return dict(row) if row else None

    def list(self, market: str | None = None) -> pd.DataFrame:
        sql = "SELECT model_version, market, family, created_at, config_hash, " \
              "parent_version, status, notes FROM model_versions"
        params: list[Any] = []
        if market:
            sql += " WHERE market = ?"
            params.append(market)
        sql += " ORDER BY created_at"
        rows = self.repo.db.query(sql, params)
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

    def promote(self, model_version: str) -> None:
        """Torna esta a versão ativa do mercado; a anterior vira 'retired'.

        A anterior NÃO é apagada — continua consultável, e as previsões que ela
        fez continuam apontando para ela.
        """
        version = self.get(model_version)
        if version is None:
            raise KeyError(f"Versão {model_version!r} não registrada.")
        with self.repo.db.transaction():
            self.repo.db.execute(
                "UPDATE model_versions SET status = ? WHERE market = ? AND status = ?",
                (STATUS_RETIRED, version["market"], STATUS_ACTIVE),
            )
            self.repo.db.execute(
                "UPDATE model_versions SET status = ? WHERE model_version = ?",
                (STATUS_ACTIVE, model_version),
            )

    def active(self, market: str) -> dict[str, Any] | None:
        row = self.repo.db.query_one(
            "SELECT * FROM model_versions WHERE market = ? AND status = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (market, STATUS_ACTIVE),
        )
        return dict(row) if row else None

    def record_experiment(
        self, model_version: str, description: str, n_variants_tested: int,
        dataset_window: str | None = None, result: dict[str, Any] | None = None,
    ) -> None:
        """Contabiliza quantas variantes foram testadas.

        Existe para alimentar o deflated Sharpe ratio: testar 40 ideias e
        reportar a melhor não é o mesmo que testar uma.
        """
        self.repo.db.execute(
            """
            INSERT INTO model_experiments (model_version, experiment_at, description,
                                           n_variants_tested, dataset_window, result_json)
            VALUES (?,?,?,?,?,?)
            """,
            (model_version, utcnow(), description, int(n_variants_tested), dataset_window,
             json.dumps(result or {}, ensure_ascii=False, default=str)),
        )

    def total_variants_tested(self, model_version: str) -> int:
        row = self.repo.db.query_one(
            "SELECT COALESCE(SUM(n_variants_tested), 0) AS n FROM model_experiments "
            "WHERE model_version = ?",
            (model_version,),
        )
        return int(row["n"]) if row else 0
