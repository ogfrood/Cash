"""Guardrails da camada de IA.

Três verificações, em ordem de severidade:

1. **Linguagem proibida.** O sistema não afirma que um ativo vai subir ou
   cair, não dá probabilidade sem amostra, não recomenda compra ou venda.
2. **Números inventados.** Todo número citado no texto precisa existir no
   pacote de evidências. É a defesa contra a falha mais perigosa de um LLM em
   contexto financeiro: o número plausível que ninguém calculou.
3. **Ausência de ressalvas.** Um relatório sem seção de incerteza é um
   relatório incompleto.

O guardrail não confia na boa vontade do prompt. O prompt pede; o guardrail
verifica.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Padrões que caracterizam afirmação preditiva ou recomendação.
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"\bvai\s+(subir|cair|disparar|despencar|valorizar|desvalorizar)\b",
     "afirmação de movimento futuro de preço"),
    (r"\bwill\s+(rise|fall|go up|go down|outperform|surge|crash)\b",
     "afirmação de movimento futuro de preço"),
    (r"\b(certamente|com certeza|garantid[oa]|sem dúvida|guaranteed|certain to)\b",
     "linguagem de certeza"),
    (r"\b(recomend[oa]|recomendamos|recommend)\s+(a\s+)?(compra|venda|buy|sell)",
     "recomendação de operação"),
    (r"\b(compre|venda|buy now|sell now|strong buy|strong sell)\b",
     "recomendação de operação"),
    (r"\bpre[çc]o[- ]alvo\b|\bprice target\b", "preço-alvo"),
    (r"\bdeve\s+(subir|cair)\b|\bshould\s+(rise|fall)\b",
     "afirmação de movimento futuro de preço"),
    (r"est[áa]\s+(muito\s+|bem\s+)?(barat[oa]|car[oa])\b",
     "rótulo de barato/caro sem qualificação — use 'acima/abaixo da mediana dos pares'"),
    (r"\b(oportunidade\s+de\s+compra|pechincha|bargain)\b",
     "juízo de valor sobre preço"),
    (r"\bundervalued\b|\bovervalued\b",
     "rótulo de barato/caro sem qualificação"),
]

REQUIRED_SECTIONS = ["incerteza", "uncertainty", "limita"]

# Tolerância para casar um número do texto com um número da evidência.
REL_TOLERANCE = 0.02
NUMBER_RE = re.compile(r"(?<![\w/])-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?(?![\w])")
# Números que qualquer texto pode conter sem precisar estar na evidência.
ALWAYS_ALLOWED = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0,
                  21.0, 50.0, 63.0, 100.0, 126.0, 200.0, 252.0}


@dataclass
class GuardrailFinding:
    kind: str           # forbidden_language | invented_number | missing_section
    severity: str       # error | warning
    detail: str
    excerpt: str | None = None


@dataclass
class GuardrailReport:
    status: str                      # pass | flagged | blocked
    findings: list[GuardrailFinding] = field(default_factory=list)
    checked_numbers: int = 0
    unmatched_numbers: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked_numbers": self.checked_numbers,
            "findings": [f.__dict__ for f in self.findings],
            "unmatched_numbers": self.unmatched_numbers,
        }

    def summary(self) -> str:
        if self.status == "pass":
            return f"Guardrails: OK ({self.checked_numbers} números conferidos)."
        lines = [f"Guardrails: {self.status.upper()}"]
        for f in self.findings:
            lines.append(f"  [{f.severity}] {f.kind}: {f.detail}")
            if f.excerpt:
                lines.append(f"      «{f.excerpt.strip()[:120]}»")
        return "\n".join(lines)


def _parse_number(token: str) -> float | None:
    raw = token.strip()
    # Heurística pt-BR/en: '1.234,56' -> 1234.56 ; '1,234.56' -> 1234.56
    if "," in raw and "." in raw:
        if raw.rindex(",") > raw.rindex("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _matches_evidence(value: float, evidence: list[float]) -> bool:
    if abs(value) in ALWAYS_ALLOWED:
        return True
    for candidate in evidence:
        for scaled in (candidate, candidate * 100.0, candidate / 100.0):
            if scaled == 0:
                if abs(value) < 1e-9:
                    return True
                continue
            if abs(value - scaled) <= abs(scaled) * REL_TOLERANCE:
                return True
            # Números arredondados pelo texto (ex.: 18,3 para 0.18276)
            if abs(round(value, 1) - round(scaled, 1)) < 1e-9:
                return True
    return False


def check(text: str, evidence_values: list[float], require_sections: bool = True,
          block_on_error: bool = True) -> GuardrailReport:
    findings: list[GuardrailFinding] = []
    lowered = text.lower()

    for pattern, description in FORBIDDEN_PATTERNS:
        for match in re.finditer(pattern, lowered, flags=re.IGNORECASE):
            start = max(0, match.start() - 60)
            findings.append(GuardrailFinding(
                kind="forbidden_language", severity="error", detail=description,
                excerpt=text[start:match.end() + 60],
            ))

    evidence_values = [v for v in evidence_values if np.isfinite(v)]
    unmatched: list[float] = []
    checked = 0
    for token in NUMBER_RE.findall(text):
        value = _parse_number(token)
        if value is None:
            continue
        checked += 1
        if not _matches_evidence(value, evidence_values):
            unmatched.append(value)
    if unmatched:
        findings.append(GuardrailFinding(
            kind="invented_number", severity="error",
            detail=(f"{len(unmatched)} número(s) citado(s) não constam do pacote de "
                    f"evidências: {unmatched[:8]}"),
        ))

    if require_sections and not any(s in lowered for s in REQUIRED_SECTIONS):
        findings.append(GuardrailFinding(
            kind="missing_section", severity="warning",
            detail="Relatório sem seção de incerteza/limitações.",
        ))

    has_error = any(f.severity == "error" for f in findings)
    if not findings:
        status = "pass"
    elif has_error and block_on_error:
        status = "blocked"
    else:
        status = "flagged"

    return GuardrailReport(status=status, findings=findings, checked_numbers=checked,
                           unmatched_numbers=unmatched)
