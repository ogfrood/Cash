"""Pacote de evidências — tudo que a IA tem permissão de ver.

A IA não consulta o banco, não chama função, não busca na internet. Ela recebe
este dicionário e nada mais. Consequências deliberadas:

- Se um número não está aqui, a IA não pode citá-lo. O guardrail verifica isso.
- O pacote é hasheado e gravado junto do relatório. Meses depois dá para
  reproduzir exatamente o que a IA sabia quando escreveu aquilo.
- Todo valor vem acompanhado de fonte, período e data de publicação. É o que
  transforma "o ROE é 18%" em "o ROE é 18%, calculado do balanço do 2T24
  publicado em 14/08/2024 pela fonte X".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from irai.config import sha256_of


def _clean(value: Any) -> Any:
    """Converte para JSON sem NaN/inf disfarçados de número."""
    if isinstance(value, bool) or isinstance(value, np.bool_):
        # antes de int: em Python, bool É int, e True viraria o número 1
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if not np.isfinite(f) else round(f, 6)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if value is None or isinstance(value, str):
        return value
    return str(value)


@dataclass
class EvidencePacket:
    ticker: str
    market: str
    as_of: str
    sections: dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, payload: Any) -> EvidencePacket:
        self.sections[name] = _clean(payload)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "market": self.market,
            "as_of": self.as_of,
            **self.sections,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @property
    def hash(self) -> str:
        return sha256_of(self.to_json())

    def numeric_values(self) -> list[float]:
        """Todos os números presentes no pacote — base da checagem anti-invenção."""
        out: list[float] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
            elif isinstance(node, (int, float)) and not isinstance(node, bool):
                f = float(node)
                if np.isfinite(f):
                    out.append(f)

        walk(self.to_dict())
        return out


def build_company_evidence(
    ticker: str,
    market: str,
    as_of: str,
    factors: dict[str, Any],
    scores: dict[str, Any],
    score_explanation: dict[str, Any],
    valuation: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    historical: list[dict[str, Any]] | None = None,
    provenance: dict[str, Any] | None = None,
    company: dict[str, Any] | None = None,
    news: list[dict[str, Any]] | None = None,
    macro: dict[str, Any] | None = None,
    model_output: dict[str, Any] | None = None,
) -> EvidencePacket:
    """Monta o pacote na ordem em que o relatório vai precisar dele.

    Seções ausentes entram explicitamente como 'insufficient_data' em vez de
    simplesmente sumirem — assim a IA sabe a diferença entre "não há dado" e
    "esqueci de olhar".
    """
    packet = EvidencePacket(ticker=ticker, market=market, as_of=as_of)
    packet.add("company", company or {"status": "insufficient_data"})
    packet.add("calculated_metrics", factors)
    packet.add("scores", scores)
    packet.add("score_explanation", score_explanation)
    packet.add("valuation", valuation or {"status": "insufficient_data"})
    packet.add("risk_metrics", risk or {"status": "insufficient_data"})
    packet.add("historical_analogues", historical or {"status": "insufficient_data"})
    packet.add("news", news or {"status": "insufficient_data",
                                "note": "Ingestão de notícias entra na Fase 6."})
    packet.add("macro", macro or {"status": "insufficient_data",
                                  "note": "Camada macro entra na Fase 5."})
    packet.add("capital_flow", {
        "status": "insufficient_data",
        "note": "Institutional ownership, fluxos de ETF e opções não têm fonte "
                "gratuita confiável. Ver DATA_SOURCES.md §B.1.",
    })
    packet.add("model_output", model_output or {"status": "insufficient_data"})
    packet.add("data_provenance", provenance or {})
    return packet
