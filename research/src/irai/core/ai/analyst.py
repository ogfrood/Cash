"""Camada de interpretação: orquestra evidência → relatório → autocrítica.

Dois modos, e o sistema funciona nos dois:

- **Com LLM** (`ANTHROPIC_API_KEY` presente): Claude escreve o texto a partir
  do pacote de evidências e passa pelos guardrails. Se for bloqueado, o
  relatório determinístico assume — o sistema nunca fica sem saída.
- **Sem LLM**: gerador determinístico monta o relatório direto do pacote.
  Menos fluente, igualmente rastreável, e reproduzível byte a byte.

O relatório, a autocrítica, o hash da evidência e o veredito do guardrail são
gravados em `ai_reports`. Nada de IA neste sistema é efêmero.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from irai.core.ai import guardrails, prompts
from irai.core.ai.evidence import EvidencePacket
from irai.core.db.database import utcnow
from irai.core.db.repository import Repository


@dataclass
class ResearchReport:
    report_id: str
    ticker: str
    market: str
    as_of: str
    model_version: str
    llm_model: str | None
    evidence_hash: str
    report_markdown: str
    self_critique_markdown: str
    guardrail: guardrails.GuardrailReport
    fallback_used: bool = False
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts = [
            self.report_markdown,
            "",
            "---",
            "",
            "## Autocrítica — por que esta leitura pode estar errada",
            "",
            self.self_critique_markdown,
            "",
            "---",
            "",
            f"_Evidência: `{self.evidence_hash[:16]}` · modelo de score: "
            f"`{self.model_version}` · redação: "
            f"`{self.llm_model or 'gerador determinístico (sem LLM)'}` · "
            f"{self.guardrail.summary()}_",
        ]
        return "\n".join(parts)


class ResearchAnalyst:
    def __init__(self, repo: Repository, settings: Any) -> None:
        self.repo = repo
        self.settings = settings
        self.ai_cfg = settings.ai if hasattr(settings, "ai") else {}

    # ------------------------------------------------------------- pública
    def write(
        self, packet: EvidencePacket, model_version: str, persist: bool = True
    ) -> ResearchReport:
        evidence_values = packet.numeric_values()
        evidence_json = packet.to_json()
        llm_model = None
        fallback = False
        notes: list[str] = []

        text = None
        critique = None
        client = self._client()
        if client is not None:
            llm_model = self.ai_cfg.get("model", "claude-opus-5")
            try:
                text = self._call(client, llm_model, prompts.SYSTEM_ANALYST,
                                  prompts.user_prompt(evidence_json, packet.ticker, packet.as_of))
                critique = self._call(client, llm_model, prompts.SYSTEM_CRITIC,
                                      prompts.critique_prompt(evidence_json, text))
            except Exception as exc:  # pragma: no cover - depende de rede
                notes.append(f"LLM indisponível ({type(exc).__name__}): {exc}")
                text = critique = None

        block = bool(self.ai_cfg.get("block_on_guardrail_violation", True))
        if text is not None:
            report_guard = guardrails.check(text, evidence_values, block_on_error=block)
            if report_guard.status == "blocked":
                notes.append(
                    "Saída do LLM bloqueada pelos guardrails; usando gerador determinístico. "
                    + report_guard.summary()
                )
                text = critique = None

        if text is None:
            fallback = True
            llm_model = None
            text = deterministic_report(packet)
            critique = deterministic_critique(packet)

        guard = guardrails.check(text + "\n" + (critique or ""), evidence_values,
                                 block_on_error=block)

        report = ResearchReport(
            report_id=f"AIR-{uuid.uuid4().hex[:10]}",
            ticker=packet.ticker, market=packet.market, as_of=packet.as_of,
            model_version=model_version, llm_model=llm_model,
            evidence_hash=packet.hash, report_markdown=text,
            self_critique_markdown=critique or "", guardrail=guard,
            fallback_used=fallback, notes=notes,
        )
        if persist:
            self._persist(report, evidence_json)
        return report

    # ------------------------------------------------------------ internos
    def _client(self) -> Any:
        if not self.ai_cfg.get("enabled", True):
            return None
        key_env = self.ai_cfg.get("api_key_env", "ANTHROPIC_API_KEY")
        if not os.environ.get(key_env):
            return None
        try:
            import anthropic
        except ImportError:
            return None
        return anthropic.Anthropic(api_key=os.environ[key_env])

    def _call(self, client: Any, model: str, system: str, user: str) -> str:
        response = client.messages.create(
            model=model,
            max_tokens=int(self.ai_cfg.get("max_tokens", 2000)),
            temperature=float(self.ai_cfg.get("temperature", 0.0)),
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    def _persist(self, report: ResearchReport, evidence_json: str) -> None:
        self.repo.db.execute(
            """
            INSERT INTO ai_reports (report_id, created_at, ticker, market, as_of_date,
                                    model_version, llm_model, evidence_hash, evidence_json,
                                    report_markdown, self_critique_markdown,
                                    guardrail_status, guardrail_detail)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (report.report_id, utcnow(), report.ticker, report.market, report.as_of,
             report.model_version, report.llm_model, report.evidence_hash, evidence_json,
             report.report_markdown, report.self_critique_markdown,
             report.guardrail.status, report.guardrail.summary()),
        )


# ---------------------------------------------------------------- fallback

def _fmt(value: Any, pct: bool = False, digits: int = 2) -> str:
    if value is None:
        return "Insufficient data"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{f * 100:.{digits}f}%" if pct else f"{f:.{digits}f}"


RATIO_METRICS = {"roe", "roic", "roa", "gross_margin", "operating_margin", "net_margin",
                 "ebitda_margin", "fcf_margin", "revenue_growth_yoy", "earnings_growth_yoy",
                 "eps_growth_yoy", "volatility_12m", "max_drawdown_12m", "momentum_1m",
                 "momentum_3m", "momentum_6m", "momentum_12m", "momentum_12_1",
                 "fcf_yield", "earnings_yield", "share_count_change_yoy"}


def deterministic_report(packet: EvidencePacket) -> str:
    """Relatório montado direto do pacote. Sem LLM, sem invenção."""
    data = packet.to_dict()
    metrics = data.get("calculated_metrics", {}) or {}
    scores = data.get("scores", {}) or {}
    explanation = data.get("score_explanation", {}) or {}
    valuation = data.get("valuation", {}) or {}
    company = data.get("company", {}) or {}
    prov = data.get("data_provenance", {}) or {}

    def metric(name: str) -> str:
        return _fmt(metrics.get(name), pct=name in RATIO_METRICS)

    lines = [
        f"# {packet.ticker} — pesquisa quantitativa",
        f"_Data de análise: {packet.as_of} · mercado: {packet.market}_",
        "",
        "> Relatório gerado pelo motor determinístico, sem modelo de linguagem.",
        "> Todos os números vêm do pacote de evidências e são rastreáveis à fonte.",
        "",
        "## 1. Negócio",
    ]
    if company.get("name"):
        lines.append(
            f"{company.get('name')} — setor {company.get('sector', 'Insufficient data')}, "
            f"indústria {company.get('industry', 'Insufficient data')}. "
            f"Fonte do cadastro: {company.get('source', 'Insufficient data')}."
        )
        lines.append("")
        lines.append(
            "Descrição qualitativa do negócio: **Insufficient data** — o motor "
            "determinístico não consulta fontes textuais."
        )
    else:
        lines.append("**Insufficient data** — cadastro da empresa ausente no pacote.")

    lines += [
        "",
        "## 2. Saúde financeira",
        f"- Dívida/patrimônio: {metric('debt_to_equity')}",
        f"- Dívida líquida/EBITDA: {metric('net_debt_ebitda')}",
        f"- Cobertura de juros: {metric('interest_coverage')}",
        f"- Liquidez corrente: {metric('current_ratio')}",
        f"- Margem de fluxo de caixa livre: {metric('fcf_margin')}",
        "",
        "## 3. Crescimento",
        f"- Receita (a/a): {metric('revenue_growth_yoy')}",
        f"- Lucro (a/a): {metric('earnings_growth_yoy')}",
        f"- LPA (a/a): {metric('eps_growth_yoy')}",
        f"- Variação na quantidade de ações (a/a): {metric('share_count_change_yoy')}",
        "",
        "## 4. Valuation",
    ]
    if isinstance(valuation, dict) and valuation.get("status") == "insufficient_data":
        lines.append("**Insufficient data**.")
    else:
        for name, reading in (valuation or {}).items():
            if not isinstance(reading, dict):
                continue
            value = reading.get("value")
            if value is None:
                lines.append(f"- {name}: Insufficient data")
                continue
            hist = reading.get("vs_own_history", "insufficient_data")
            peers = reading.get("vs_peers", "insufficient_data")
            lines.append(
                f"- {name}: {_fmt(value)} · vs. própria história: {hist} "
                f"(mediana {_fmt(reading.get('historical_median'))}, "
                f"n={reading.get('historical_n', 0)}) · vs. pares: {peers} "
                f"(mediana {_fmt(reading.get('peer_median'))}, "
                f"n={reading.get('peer_n', 0)})"
            )
        lines.append("")
        lines.append(
            "As palavras 'barato' e 'caro' não aparecem de propósito: a posição do "
            "múltiplo é um fato; a interpretação dela depende de por que ele está ali."
        )

    lines += [
        "",
        "## 5. Comportamento de mercado",
        f"- Momentum 12-1: {metric('momentum_12_1')}",
        f"- Momentum 6M: {metric('momentum_6m')} · 3M: {metric('momentum_3m')} "
        f"· 1M: {metric('momentum_1m')}",
        f"- Volatilidade 12M: {metric('volatility_12m')}",
        f"- Beta: {metric('beta')}",
        f"- Drawdown máximo 12M: {metric('max_drawdown_12m')}",
        f"- Tendência de volume: {metric('volume_trend')}",
        "",
        "## 6. Fluxo de capital",
        "**Insufficient data** — institutional ownership, fluxos de ETF/fundos e "
        "atividade de opções não têm fonte gratuita confiável nesta versão. "
        "Ver DATA_SOURCES.md.",
        "",
        "## 7. Notícias",
        "**Insufficient data** — ingestão de notícias entra na Fase 6.",
        "",
        "## 8. Catalisadores",
        "**Insufficient data** — catalisadores dependem de notícias e guidance, "
        "ainda não ingeridos.",
        "",
        "## 9. Riscos",
    ]
    negatives = explanation.get("top_negative") or []
    if negatives:
        lines.append("Fatores que mais pesaram contra a empresa no score:")
        for item in negatives[:4]:
            lines.append(
                f"- {item.get('factor')}: valor {_fmt(item.get('raw_value'), digits=3)}, "
                f"z {_fmt(item.get('z_score'))} dentro do grupo de pares"
            )
    else:
        lines.append("**Insufficient data**.")

    lines += ["", "## 10. Contexto histórico"]
    hist = data.get("historical_analogues")
    if isinstance(hist, dict) and hist.get("status") == "insufficient_data":
        lines.append("**Insufficient data** — sem amostra histórica suficiente na data.")
    elif isinstance(hist, list) and hist:
        for item in hist:
            lines.append(f"- {item.get('sentence', 'Insufficient data')}")
    else:
        lines.append("**Insufficient data**.")

    lines += ["", "## 11. Saída do modelo"]
    if scores:
        for pillar, value in scores.items():
            lines.append(f"- {pillar}: {_fmt(value)}")
        lines.append("")
        positives = explanation.get("top_positive") or []
        if positives:
            lines.append("Fatores que mais contribuíram positivamente:")
            for item in positives[:4]:
                lines.append(
                    f"- {item.get('factor')}: valor {_fmt(item.get('raw_value'), digits=3)}, "
                    f"z {_fmt(item.get('z_score'))}"
                )
        lines.append("")
        lines.append(
            f"Grupo de pares usado na normalização: {explanation.get('peer_group', 'n/d')} "
            f"com {_fmt(explanation.get('peer_count'), digits=0)} empresas."
        )
    else:
        lines.append("**Insufficient data**.")

    missing = explanation.get("missing_factors") or []
    lines += [
        "",
        "## 12. Incerteza",
        "- O score é uma ordenação relativa dentro do universo analisado nesta data. "
        "Não é estimativa de retorno e não tem unidade econômica.",
        f"- Fatores ausentes para esta empresa: "
        f"{', '.join(sorted(set(missing))[:10]) if missing else 'nenhum'}.",
        f"- Idade do fundamento mais recente: {metric('fundamental_age_days')} dias.",
        f"- Linhas de fundamento com data de publicação estimada: "
        f"{prov.get('n_fundamental_rows_estimated_publication', 'n/d')}.",
        "- Métricas de risco descrevem a janela passada. Não são previsão de risco futuro.",
        "- Limitações estruturais da V1: viés de sobrevivência no universo, ausência de "
        "dados de fluxo de capital, e preços ajustados retroativamente.",
    ]
    return "\n".join(lines)


def deterministic_critique(packet: EvidencePacket) -> str:
    data = packet.to_dict()
    metrics = data.get("calculated_metrics", {}) or {}
    explanation = data.get("score_explanation", {}) or {}
    prov = data.get("data_provenance", {}) or {}
    coverage = (explanation.get("coverage") or {}).get("total")

    contra: list[str] = []
    favor: list[str] = []

    for item in (explanation.get("top_positive") or [])[:3]:
        favor.append(f"{item.get('factor')} com z {_fmt(item.get('z_score'))} no grupo de pares")
    for item in (explanation.get("top_negative") or [])[:3]:
        contra.append(f"{item.get('factor')} com z {_fmt(item.get('z_score'))} no grupo de pares")

    lines = ["### Por que esta leitura pode estar errada", ""]

    peer_count = explanation.get("peer_count")
    if peer_count is not None and float(peer_count) < 10:
        lines.append(
            f"- **Grupo de pares pequeno.** A normalização usou "
            f"{_fmt(peer_count, digits=0)} empresas. Um z-score contra poucos pares "
            f"mede tanto a amostra quanto a empresa."
        )
    if coverage is not None and float(coverage) < 1.0:
        lines.append(
            f"- **Cobertura incompleta.** {_fmt(coverage, pct=True)} dos pilares tinham "
            f"dado suficiente. Os pesos foram renormalizados entre o que existe, o que "
            f"muda o significado do total."
        )
    age = metrics.get("fundamental_age_days")
    if age is not None and float(age) > 120:
        lines.append(
            f"- **Fundamento defasado.** O dado mais recente tem {_fmt(age, digits=0)} "
            f"dias. Entre a última publicação e hoje, o negócio pode ter mudado."
        )
    growth = metrics.get("revenue_growth_yoy")
    fcf_margin = metrics.get("fcf_margin")
    if growth is not None and fcf_margin is not None and float(growth) > 0 and float(fcf_margin) < 0:
        lines.append(
            "- **Preocupação contábil.** A receita cresce enquanto a margem de fluxo de "
            "caixa livre é negativa. Crescimento que consome caixa depende de "
            "financiamento externo."
        )
    debt = metrics.get("net_debt_ebitda")
    if debt is not None and float(debt) > 3.0:
        lines.append(
            f"- **Alavancagem.** Dívida líquida/EBITDA de {_fmt(debt)}. Em cenário de "
            f"juros altos ou queda de EBITDA, a estrutura de capital vira o problema "
            f"principal."
        )
    if prov.get("n_fundamental_rows_estimated_publication"):
        lines.append(
            "- **Datas de publicação estimadas.** Parte dos fundamentos entrou com data "
            "de publicação presumida por lag, não lida do documento."
        )

    lines += [
        "- **Viés de seleção do pesquisador.** Os fatores do score foram escolhidos "
        "conhecendo o passado do mercado. Nenhum código corrige isso; só o teste "
        "fora da amostra ao longo do tempo.",
        "- **Ausência de fluxo de capital e notícias.** Movimento de preço sem "
        "confirmação de fluxo é tratado aqui igual a movimento com confirmação, "
        "porque o dado de fluxo não existe nesta versão.",
        "",
        "**Argumentos a favor**",
    ]
    lines += [f"- {f}" for f in (favor or ["Insufficient data"])][:4]
    lines += ["", "**Argumentos contra**"]
    lines += [f"- {c}" for c in (contra or ["Insufficient data"])][:4]
    lines += [
        "",
        "**O que mudaria esta leitura:** uma publicação de resultado que altere a "
        "trajetória de margem ou de alavancagem; ou a constatação, no teste fora da "
        "amostra, de que o score não separa desempenho neste setor.",
    ]
    return "\n".join(lines)
