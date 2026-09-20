"""Guardrails da camada de IA — o que a IA não tem permissão de dizer."""

from __future__ import annotations

from irai.core.ai.evidence import EvidencePacket
from irai.core.ai.guardrails import check

EVIDENCE = [0.182, 12.4, 0.35, 20.0]


def test_afirmacao_de_alta_e_bloqueada():
    r = check("A ação vai subir nos próximos meses. Incerteza: alta.", EVIDENCE)
    assert r.status == "blocked"
    assert any(f.kind == "forbidden_language" for f in r.findings)


def test_recomendacao_e_preco_alvo_sao_bloqueados():
    for texto in ("Recomendo a compra do ativo.", "Preço-alvo de 12,4.",
                  "O papel está barato.", "Compre agora."):
        assert check(texto, EVIDENCE).status == "blocked", texto


def test_numero_fora_da_evidencia_e_bloqueado():
    r = check("O ROE é 18,2% e o P/L é 12,4. O EBITDA cresceu 47,3%. Incerteza: alta.",
              EVIDENCE)
    assert r.status == "blocked"
    assert 47.3 in r.unmatched_numbers


def test_texto_ancorado_na_evidencia_passa():
    r = check("O ROE é 18,2% e o P/L é 12,4, abaixo da mediana dos pares. "
              "Incerteza: amostra de 20 observações.", EVIDENCE)
    assert r.status == "pass", r.summary()


def test_data_nao_e_tratada_como_numero_inventado():
    """Sem isto, '2024-03-31' vira os números 3 e 31 e o relatório é acusado
    de inventar dados que nunca citou."""
    r = check("Data de análise: 2024-03-31. O P/L é 12,4. Incerteza: alta.", EVIDENCE)
    assert r.status == "pass", r.summary()


def test_inteiro_do_pacote_e_visivel_na_conferencia():
    """Inteiros estavam virando string na serialização e sumindo da checagem."""
    packet = EvidencePacket("AAA", "US", "2024-03-31")
    packet.add("valuation", {"pe": {"value": 12.4, "historical_n": 20}})
    assert 20.0 in packet.numeric_values()


def test_booleano_nao_vira_o_numero_um():
    packet = EvidencePacket("AAA", "US", "2024-03-31")
    packet.add("flags", {"estimated": True, "ok": False})
    assert packet.to_dict()["flags"]["estimated"] is True
    assert 1.0 not in packet.numeric_values()


def test_relatorio_sem_secao_de_incerteza_e_sinalizado():
    r = check("O ROE é 18,2%.", EVIDENCE)
    assert r.status == "flagged"
    assert any(f.kind == "missing_section" for f in r.findings)


def test_relatorio_deterministico_passa_nos_proprios_guardrails(loaded_repo, settings):
    """O gerador determinístico é o fallback do sistema. Se ele próprio é
    bloqueado, não existe fallback."""
    import dataclasses

    from irai.core.reporting.pipeline import analyze_company
    from irai.core.scoring.engine import ScoringConfig, ScoringEngine

    market = dataclasses.replace(settings.market("US"), benchmark="^SYNX")
    scoring = ScoringEngine(ScoringConfig.load(settings.scoring_config_path()))
    tickers = loaded_repo.universe_as_of("US", "config", "2022-09-30")

    analise = analyze_company(loaded_repo, market, scoring, tickers[0], "2022-09-30",
                              tickers, settings)

    assert analise.report.fallback_used, "sem chave de API, deve usar o determinístico"
    assert analise.report.guardrail.status == "pass", analise.report.guardrail.summary()


def test_numero_longo_nao_e_partido_em_fragmentos():
    """'1637.42' precisa ser lido como um número, não como '42'."""
    r = check("O PEG calculado é 1637.42. Incerteza: múltiplo sem significado "
              "econômico com crescimento próximo de zero.", [1637.42])
    assert r.status == "pass", r.summary()


def test_numeracao_de_secao_nao_conta_como_dado():
    texto = "## 11. Saída do modelo\n- total: 0,35\n\n## 12. Incerteza\n- amostra pequena."
    assert check(texto, [0.35]).status == "pass"
