# Plano — Stock Market Intelligence Engine

Status: **proposta, aguardando confirmação.** Nada das Fases 1+ foi implementado.
Data: 2026-09-20.

---

## Parte A — Auditoria do que existe hoje

### A.1 O que eu encontrei no repositório (verificado, não presumido)

| Componente | Estado real | Onde |
|---|---|---|
| **Cash** — app de finanças pessoais | ✅ Implementado (Fase 1) | `src/` (Next.js 16, React 19, SQLite via Drizzle) |
| Schema Cash: `employers`, `shifts`, `payslips`, `buckets`, `debts`, `ledger_entries`… | ✅ 22 tabelas | `src/db/schema.ts` |
| **Engine de criptomoedas** | ❌ **Não existe.** Nenhuma linha de código. | — |
| Infraestrutura quantitativa compartilhada | ❌ **Não existe.** | — |
| Investment Research AI | 🟡 Iniciado nesta sessão: documentação e configuração apenas | `research/` |

Verificações feitas: `git log --all` (2 commits, ambas as branches no mesmo
ponto), busca por `crypto|bitcoin|btc` em todo o repo (só uma menção no README,
como intenção futura), `list_repos` da conta (**apenas `ogfrood/Cash`**),
`list_sessions` (apenas esta sessão e a do Cash).

> ⚠️ **Divergência de premissa.** O pedido diz "grande parte da infraestrutura
> quantitativa já existe ou foi planejada" e "não quero criar um sistema
> separado do de criptomoedas". Não há sistema de criptomoedas acessível a
> esta sessão. Se ele existe em outro repositório/conta, preciso do link — caso
> contrário, o que vou construir **é** o núcleo compartilhado, e o módulo de
> cripto virá depois plugado nele.

### A.2 O que existe em `research/` (feito nesta sessão, antes do seu upgrade)

- `DATA_SOURCES.md` — comparativo de 11 fontes (yfinance, CVM, SEC EDGAR, brapi,
  Alpha Vantage, FMP, EODHD, Tiingo, Stooq, B3, BCB/FRED) com custo, licença,
  limitação e veredito. Decisão: preços via yfinance, **fundamentos via fonte
  primária do regulador** (CVM `DT_RECEB` / SEC `filed`), porque só elas têm a
  data em que o dado ficou público.
- `docs/LOOKAHEAD_BIAS.md` — contrato point-in-time, as 4 formas de vazamento,
  a regra única de consulta, teste de envenenamento.
- `config/settings.yaml`, `config/scoring_v1.yaml`, `config/universe_{br,us}.yaml`.
- Estrutura de pastas.

**Nenhum código Python ainda.** Então o "não duplique" é fácil: não há o que
duplicar. O custo de mudar de rumo agora é ~zero.

### A.3 Restrição do ambiente de desenvolvimento

A política de egresso desta sessão bloqueia `finance.yahoo.com`, `sec.gov`,
`dados.cvm.gov.br`, `brapi.dev` e `stooq.com` (403 no CONNECT). Consequência
prática: **nesta sessão eu construo e testo com fixtures sintéticas
determinísticas; a ingestão real roda na sua máquina.** Isso não é um defeito do
design — é o motivo pelo qual a camada de provider é trocável e existe um
provider `fixture`.

---

## Parte B — As três coisas que vão dar errado se não decidirmos agora

### B.1 Metade das features pedidas não tem dado gratuito confiável

Isto não é pessimismo, é inventário. Sem resolver, essas seções viram
`"Insufficient data"` — que é o comportamento correto que você mesmo pediu, mas
é bom saber de antemão quanto da tela vai ficar vazia.

| Feature pedida | Fonte realista | Veredito |
|---|---|---|
| Forward P/E, PEG, guidance, analyst revisions | Consenso de sell-side (Refinitiv/FactSet/Visible Alpha) | ❌ **Sem fonte gratuita.** Pago e caro (US$ milhares/ano). |
| Institutional ownership | SEC 13F | 🟡 Grátis, mas **trimestral com 45 dias de atraso**. Serve como contexto lento, nunca como sinal. Não existe para a B3. |
| Insider transactions | SEC Forms 3/4/5 | ✅ Grátis e com data de protocolo. BR: CVM formulário 44 (mensal, pior qualidade). |
| Short interest | FINRA/exchanges | 🟡 Grátis, quinzenal, com atraso. B3: aluguel de ações B3, arquivo diário. |
| ETF / fund flows | Provedores pagos | ❌ Sem fonte gratuita boa. |
| Options activity | OPRA | ❌ Caro. |
| Buybacks / share issuance | SEC 10-Q/10-K (shares outstanding) e CVM | ✅ Derivável dos balanços que já vamos ingerir. |
| News | RSS dos releases (IR), GDELT, Finnhub free | 🟡 Viável, cobertura BR irregular, sem histórico profundo para backtest. |
| Macro (juros, inflação, PMI, VIX, spreads) | BCB SGS, FRED, IBGE | ✅ Grátis e com bom histórico. |

**Consequência de design:** cada feature vira um *módulo opcional com estado de
disponibilidade*. O relatório mostra explicitamente "Capital flow: dados
indisponíveis para este mercado" em vez de inventar. E — importante — **nenhuma
dessas features entra no score ou no modelo até existir histórico suficiente
para backtest.** Notícia sem histórico é decoração, não sinal.

### B.2 "Historical analogues" é a feature mais perigosa do pedido

Buscar empresas com perfil parecido e olhar o que aconteceu depois é data mining
com aparência de ciência. Três armadilhas concretas:

1. **Amostra efetiva muito menor do que parece.** 500 empresas × 120 meses =
   60.000 observações, mas retornos de 12 meses se sobrepõem e empresas do mesmo
   setor se movem juntas. O n efetivo é mais próximo do **número de períodos
   independentes** (~10 para horizonte de 12M em 10 anos) do que de 60.000.
   Ignorar isso infla a significância em 5–10×.
   → Mitigação obrigatória: erros clusterizados por data, **block bootstrap**
   por blocos temporais, e o relatório mostra *n efetivo*, não só *n bruto*.
2. **Múltiplos testes.** Se o sistema permite fazer 200 perguntas do tipo
   "o que aconteceu quando…", ~10 delas parecerão significativas a 5% por puro
   acaso.
   → Mitigação: contador de consultas por sessão de pesquisa e correção
   (Benjamini-Hochberg) exibida ao lado do p-valor.
3. **Regime único.** "Historicamente" em 10 anos de ações quer dizer, na
   prática, um regime de juros e um ciclo. 
   → Mitigação: todo analogue é quebrado por sub-período e por regime, e se o
   sinal só existe em um sub-período, o relatório diz isso.

### B.3 Probabilidade sem base rate é teatro

"60% de probabilidade de retorno positivo em 6 meses" é aproximadamente a **taxa
base de qualquer ação** num mercado que sobe. Um modelo que cospe 60% para todo
mundo terá calibração perfeita e **zero skill**.

→ Por isso a métrica primária não é Brier, é **Brier Skill Score contra dois
baselines**: (a) a taxa base incondicional, (b) o benchmark. E a variável alvo
padrão é **retorno relativo ao benchmark** (excess return), não retorno absoluto
— assim a taxa base fica perto de 50% e a métrica tem significado.

---

## Parte C — Arquitetura proposta

### C.1 Núcleo compartilhado vs específico de mercado

```
research/src/investment_research/
├── core/                      ← COMPARTILHADO (stocks, crypto, futuro FX)
│   ├── db/                    schema PIT, migrations, repositório
│   ├── providers/             protocolo de provider + registry + fixture
│   ├── validation/            checagens de qualidade, quarentena de dados ruins
│   ├── quant/                 retornos, vol, beta, drawdown, MAs, z-scores robustos
│   ├── features/              pipeline de feature engineering com carimbo PIT
│   ├── backtest/              engine, custos, portfólio, métricas, walk-forward
│   ├── predictions/           registry, journal, avaliação, calibração
│   ├── models/                registry de versões de modelo (nunca apaga)
│   ├── regime/                detector causal de regime (sem suavização futura)
│   ├── macro/                 séries macro + relação com setores
│   ├── news/                  ingestão, deduplicação, classificação
│   ├── ai/                    evidence packet, prompts, guardrails, self-critique
│   ├── paper/                 paper trading
│   └── reporting/             relatórios e export
│
└── markets/
    ├── stocks/                ← ESPECÍFICO
    │   ├── universe/          B3, NYSE, Nasdaq; snapshots históricos
    │   ├── ingest/            CVM, SEC EDGAR, yfinance, B3
    │   ├── fundamentals/      normalização de plano de contas e tags XBRL
    │   ├── valuation/         múltiplos, DCF, DCF reverso, peers
    │   ├── flow/              13F, insiders, short interest, buybacks
    │   ├── discovery/         detector de mudança relevante
    │   └── model/             StockModel vN
    └── crypto/                ← ESPECÍFICO (Fase 10)
        └── …                  on-chain, funding, 24/7, sem fundamentos
```

**O que compartilha e por quê:** tudo que é matemática de série temporal,
persistência PIT, backtest, avaliação de previsão, calibração e a camada de IA.
São idênticos entre mercados.

**O que NÃO deve ser compartilhado, e é onde a maioria dos projetos erra:**

| Aspecto | Ações | Cripto | Por quê não dá para unificar |
|---|---|---|---|
| Calendário | 252 pregões/ano, feriados por país | 24/7/365 | Anualização, janelas móveis e alinhamento de datas mudam |
| Fundamentos | Balanço trimestral auditado com data de publicação | Não existem | O contrato PIT inteiro perde sentido |
| Histórico útil | 20+ anos, vários regimes | ~10 anos, essencialmente um ciclo de adoção | Qualquer "historicamente" em cripto é frágil |
| Benchmark | Ibovespa, S&P 500 | BTC ou índice de mercado total | Excess return muda de significado |
| Custos/liquidez | Corretagem + spread + impacto | Taxas de exchange, funding, slippage assimétrico | Modelo de custo diferente |
| Setores/peers | GICS, comparáveis reais | Categorias arbitrárias (L1, DeFi…) | Normalização cross-sectional por setor não transporta |

### C.2 Fluxo (o mesmo do seu item 20, com dois portões a mais)

```
DATA → DATA VALIDATION → PIT STORE → FEATURE ENGINEERING
   → QUANT ENGINE → SCORING/MODEL → BACKTEST → WALK-FORWARD
   → [PORTÃO 1: robustez]  → PREDICTION ENGINE → PREDICTION JOURNAL
   → OUTCOME → MODEL EVALUATION + CALIBRATION
   → [PORTÃO 2: holdout selado] → CANDIDATE MODEL → NEW VERSION
   → PAPER TRADING → DASHBOARD / AI RESEARCH LAYER
```

**Portão 1 — robustez.** Um modelo só passa se: sobrevive a walk-forward em
todos os sub-períodos, mantém sinal com custos dobrados, não depende de mais de
20% do resultado vir de um único ano, e não piora com pequenas perturbações de
parâmetro. Maior retorno histórico **não** é critério.

**Portão 2 — holdout selado.** O item 12 do seu pedido (continuous learning) tem
um furo: se você re-roda o walk-forward a cada erro, cada iteração gasta graus de
liberdade e você acaba fazendo overfitting *através do tempo*. Proposta:
um período final (ex.: os 18 meses mais recentes) fica **selado**, registrado em
`docs/SEALED_HOLDOUT.md`, e só pode ser aberto **uma vez por versão maior de
modelo**. O sistema conta e registra quantas variantes foram testadas
(`model_experiments.n_variants_tested`) e aplica *deflated Sharpe ratio* usando
esse número. É a única defesa real contra p-hacking pessoal.

---

## Parte D — Fases propostas

Cada fase entrega algo utilizável e testável. Sem fase ficar "80% pronta".

| Fase | Entrega | Cobre os itens |
|---|---|---|
| **1. Núcleo + Stocks V1** | DB PIT, providers, ingestão (CVM/SEC/yfinance/fixtures), validação, quant engine, scoring 6 pilares, backtest + walk-forward, prediction journal, camada de IA com guardrails + self-critique, CLI, testes | 2, 4 (parcial), 16, 17, 18, 20 |
| **2. Universo amplo + Discovery** | Ingestão em massa (SEC bulk, B3 COTAHIST), universo completo B3+NYSE+Nasdaq com snapshots históricos, **detector de mudança relevante** (aceleração de receita, melhora de margem, ROIC subindo, desalavancagem, volume anômalo, earnings surprise) | 1, 8 |
| **3. Valuation engine** | Múltiplos completos, histórico próprio, percentil vs pares, DCF e DCF reverso com premissas explícitas. Mostra posição, **não** rotula "barato/caro" | 3 |
| **4. Market behavior + Regime** | Relative strength, correlação, volume relativo, **detector causal de regime** (sem suavização futura) | 4, 7 (parcial) |
| **5. Macro engine** | BCB SGS + FRED, relação setor × ambiente macro com aviso anti-causalidade | 15 |
| **6. News intelligence** | Ingestão com data de publicação, categorização, sentimento **como dado, não como fato**, ligado à empresa e rastreável | 6 |
| **7. Capital flow** (condicional a dados) | 13F, insiders (Forms 3/4/5), short interest, buybacks. Separação explícita *price movement* × *capital confirmation* | 5 |
| **8. Historical analogues + Prediction engine** | Busca de análogos com n efetivo, block bootstrap e correção de múltiplos testes; previsões probabilísticas 1M/3M/6M/12M sobre **excess return**; Brier Skill Score vs base rate | 9, 10 |
| **9. Model registry + Avaliação contínua** | Versionamento imutável de modelos, performance por setor/mercado/regime/capitalização/horizonte, **curva de calibração obrigatória**, AI Track Record | 11, 12, 13, 14, 21 |
| **10. Paper trading + Dashboards** | Paper portfolio diário; páginas Daily Stock Intelligence, Stock Opportunities, Model Performance, AI Track Record | 7, 8, 19 |
| **11. Crypto plugado no núcleo** | Módulo `markets/crypto` reusando 100% do núcleo | 20 |

### Estimativa honesta
Fase 1 é grande (é o núcleo inteiro). Fases 2–6 são incrementais. Fases 8–9 são
as que exigem mais cuidado estatístico do que código. Fase 10 depende de 8–9
terem dado sinal.

**A fase que você não deve pular:** 9. Sem ela, o item 21 ("o objetivo é criar
uma IA cuja performance possa ser medida") não existe — e é o único item que
distingue este projeto de mais um screener bonito.

---

## Parte E — Decisões que preciso de você

1. **Existe engine de cripto?** Se sim, link do repositório. Se não, confirmo
   que construo o núcleo compartilhado agora e cripto entra na Fase 11.
2. **Orçamento de dados.** R$ 0 (aceitando "Insufficient data" em forward P/E,
   PEG, fluxos de ETF/fundos e opções) ou ~US$ 40–100/mês (EODHD/Sharadar,
   destrava universo com delistadas e fundamentos PIT prontos)?
3. **Sequência.** Fase 1 completa e validada antes de tudo, ou construir a
   largura primeiro (mais telas, menos validação)?
4. **Onde o código mora.** `research/` neste repositório (monorepo com o Cash)
   ou repositório separado?
