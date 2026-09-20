# Crypto Intelligence — revisão antes de implementar

Resposta aos 8 pontos pedidos, antes de escrever código de cripto.
Data: 2026-09-20.

---

## 1. Componentes que já existem (e são reaproveitáveis)

A Fase 1 do motor de ações já entregou o núcleo. **Cerca de 80% do que a área
de cripto precisa já está pronto** — não como promessa, como código com testes.

| Componente | Onde | Reusa em cripto? |
|---|---|---|
| Banco point-in-time (24 tabelas), repositório com corte `publication_date <= as_of` | `core/db/` | ✅ Integral |
| Protocolo de provedores + registry + provedor sintético | `core/providers/` | ✅ Integral |
| Retornos, volatilidade, Sharpe, Sortino, Calmar, drawdown, VaR/CVaR, beta, alpha, IR | `core/quant/risk.py` | ✅ Integral |
| Momentum (incl. 12-1), médias móveis, volume relativo, força relativa | `core/quant/` | ✅ Integral |
| Normalização robusta cross-sectional por grupo | `core/quant/normalize.py` | ✅ Integral |
| Motor de scoring dirigido por YAML versionado e hasheado | `core/scoring/engine.py` | ✅ Integral — só muda o YAML |
| Backtest com D+1, custos, filtros de liquidez, hipóteses gravadas | `core/backtest/engine.py` | 🟡 Ajustar calendário 24/7 e custos |
| Walk-forward + deflated Sharpe + degradação calibração→teste | `core/backtest/walkforward.py` | ✅ Integral |
| Diário de previsões imutável + resolução ex-post | `core/predictions/journal.py` | ✅ Integral |
| Brier Skill Score, calibração com Wilson, amostra efetiva por blocos | `core/predictions/evaluation.py` | ✅ Integral |
| Frequências históricas condicionais (só observações já resolvidas) | `core/predictions/historical.py` | ✅ Integral |
| Registro imutável de versões de modelo + contagem de variantes | `core/models/registry.py` | ✅ Integral |
| Pacote de evidências hasheado, prompts, guardrails, autocrítica | `core/ai/` | ✅ Integral — só muda o vocabulário proibido |
| Relatório determinístico sem LLM | `core/ai/analyst.py` | 🟡 Novo template de 13 seções |

**Consequência:** a pergunta "Stocks e Crypto compartilham infraestrutura?" já
está respondida no código. `markets/crypto/` entra ao lado de
`markets/stocks/`, e o núcleo não muda.

O seu requisito **HUMAN OVERRIDE** (ver RAW DATA, MODEL OUTPUT e AI
INTERPRETATION separadamente) já é como o sistema funciona hoje: `raw_factors`,
`normalized`, `scores` e `ai_reports` são objetos distintos, e
`result.explain(ticker)` devolve a contribuição fator a fator.

E a **CRITICAL RULE** (nada publicado após a data da previsão entra nas
features) é a única regra que o projeto já trata como não negociável — há um
teste de envenenamento que quebra se alguém contornar a camada de repositório.

---

## 2. O que precisa ser criado

| Novo | Por que não dá para reusar |
|---|---|
| `markets/crypto/universe/` — universo dinâmico por market cap e liquidez, com snapshots | A lista muda toda semana e precisa incluir moedas mortas |
| `markets/crypto/ingest/` — CoinGecko, Binance, DefiLlama, GitHub, Deribit, Farside | Fontes completamente diferentes |
| `markets/crypto/onchain/` — endereços ativos, TVL, taxas, staking, supply, unlocks | Não existe análogo em ações |
| `markets/crypto/flow/` — funding, open interest, basis, fluxo de stablecoin, ETF | Não existe análogo em ações |
| `markets/crypto/tokenomics/` — supply circulante vs. total, inflação, cronograma de unlock, FDV | O "balanço" de um token |
| `markets/crypto/model/` — CryptoModel v1 com 11 pilares | Métricas diferentes, pesos diferentes |
| `config/crypto_scoring_v1.yaml` + `CRYPTO_MODEL_METHODOLOGY.md` | Documento próprio, como você pediu |
| `core/regime/` — detector **causal** de regime | Vale para os dois mercados; ainda não existe |
| `core/news/` — ingestão, deduplicação, classificação | Vale para os dois; ainda não existe |
| `core/macro/` — BCB, FRED, DXY, ouro, VIX | Vale para os dois; ainda não existe |
| `core/paper/` — paper trading | Vale para os dois; ainda não existe |
| Calendário 24/7 e custos de exchange no backtest | Ajuste no núcleo, não reescrita |

---

## 3. Fontes de dados necessárias

| Necessidade | Fonte primária | Fonte secundária |
|---|---|---|
| Preço/volume/market cap | CoinGecko | Binance klines, Coinbase |
| OHLCV de alta resolução | Binance API pública | Coinbase, Kraken |
| Funding, open interest, basis | Binance Futures público | Coinglass (freemium) |
| Opções (IV, skew) | **Deribit API pública** | — |
| TVL, taxas, receita de protocolo | **DefiLlama** | Token Terminal (pago) |
| Fluxo de stablecoin | DefiLlama Stablecoins | — |
| Atividade on-chain | Dune (free tier, SQL) | Blockchair, CoinMetrics Community |
| Atividade de desenvolvedores | **GitHub API** (commits, contribuidores) | Electric Capital (dataset aberto) |
| Supply e unlocks | CoinGecko + docs do projeto | TokenUnlocks |
| Fluxo de ETF (BTC/ETH) | Farside Investors (HTML público) | — |
| Notícias | RSS dos protocolos, CoinDesk/TheBlock RSS, GDELT | CryptoPanic (freemium) |
| Regulação | RSS da SEC, CVM, ESMA | — |
| Macro | FRED, BCB SGS | — |
| Benchmark | BTC e índice de market cap total (CoinGecko `global`) | — |

---

## 4. APIs gratuitas (suficientes para a V1)

| API | O que dá | Limite | Observação |
|---|---|---|---|
| **CoinGecko Demo** | Preço, volume, market cap, supply, histórico, categorias | ⚠️ ~100 req/min, teto ~10 mil/mês; o público sem chave é bem menor (5–15 req/min) | Base do universo dinâmico |
| **Binance público** | Klines, book, trades, funding, open interest; WebSocket | ⚠️ Sistema de peso, ~6.000 de peso/min em endpoints públicos | **Não precisa de chave para dados públicos** |
| **DefiLlama** | TVL, taxas, receita, stablecoins, volume de DEX, bridges — 400+ chains, 6.000+ protocolos | ⚠️ Sem limite declarado para tráfego normal | **A melhor fonte gratuita de "fundamento" cripto** |
| **Deribit público** | Opções: IV, skew, open interest | Generoso | Opções em cripto são grátis; em ações, caríssimas |
| **GitHub REST** | Commits, contribuidores, issues por repositório | 5.000 req/h autenticado | Proxy de atividade de desenvolvimento |
| **Dune** free | SQL sobre dados on-chain indexados | Créditos por compute | Ótimo para métricas sob medida |
| **CoinMetrics Community** | Métricas on-chain de ~10 ativos grandes | Diário | Qualidade alta, cobertura estreita |
| **Farside Investors** | Fluxo diário dos ETFs de BTC e ETH | HTML, sem API | Raspagem simples e legítima |
| **FRED / BCB SGS** | Juros, DXY, inflação | Grátis | Camada macro |

**Veredito:** para a V1 de cripto, **R$ 0 cobre mais do que cobria em ações.**
DefiLlama sozinho entrega algo que em ações custaria caro: receita e taxas
reais de protocolo, com histórico.

---

## 5. APIs pagas (e quando valem)

| API | Preço aproximado (2026) | O que destrava | Vale quando |
|---|---|---|---|
| Glassnode | ⚠️ ~US$ 49/mês anual (API leve, 14 dias, 50 chamadas/dia) até ~US$ 999/mês (API completa, 15+ anos) | Métricas on-chain profundas: SOPR, MVRV, idade das moedas, coortes | Só depois de o modelo provar valor com métricas simples |
| Coinglass | ⚠️ US$ 29–699/mês | Funding e open interest agregados de todas as exchanges | Se o fluxo de derivativos virar fator relevante |
| DefiLlama Pro / API | ⚠️ ~US$ 41/mês (Pro) / ~US$ 250/mês (API de alto volume) | Limites maiores; os dados em si são gratuitos | Só se o volume de requisições exigir |
| Dune pago | Por créditos | Consultas mais rápidas e pesadas | Quando a query gratuita não couber |
| Messari | ⚠️ Enterprise sob consulta (tiers antigos descontinuados em 2026) | Dados normalizados e research | Provavelmente nunca, para este caso |
| Token Terminal | Pago | Métricas financeiras padronizadas de protocolos | DefiLlama cobre o essencial de graça |
| Santiment | Pago | Social e on-chain, cadência de 10 min a diária | Se sentimento virar fator medido, não decorativo |
| Nansen | Pago (caro) | Rotulagem de carteiras, "whale activity" de verdade | É o único jeito de fazer whale tracking sério |

**Recomendação:** nenhum. Comece em R$ 0. O gargalo da V1 não é dado — é
amostra. Ver ponto 7.

---

## 6. Dados difíceis de obter (e o que fazer)

| Dado pedido | Dificuldade | Decisão |
|---|---|---|
| **Whale activity** | Alta. Exige rotulagem de carteiras (Nansen/Arkham). Heurísticas por tamanho de transação confundem exchange, bridge e custodiante com "baleia". | `Data unavailable` na V1. Melhor não ter do que ter errado. |
| **Exchange inflows/outflows** | Alta. Depende de conhecer os endereços das exchanges; listas públicas são incompletas e desatualizam. | Parcial via Dune para as maiores; marcado com aviso de cobertura. |
| **Fund flows (fora de ETF)** | Alta. Relatórios semanais agregados. | `Data unavailable`. |
| **Sentimento confiável** | Média-alta. Bots inflam X/Twitter; engajamento é comprável. | Implementar como **dado com fonte e confiança**, nunca como fato — exatamente como você pediu. E deixar de fora do score até haver histórico para backtest. |
| **Unlock schedules** | Média. Espalhados por documentação e contratos. | Ingerir onde houver dado estruturado; caso contrário `Data unavailable`. |
| **Market cap confiável** | **Média — e mais perigosa do que parece.** Supply circulante é auto-reportado e manipulável. Projetos de baixo float exibem market cap baixo com FDV altíssimo. | Guardar **market cap e FDV juntos**, e sinalizar quando `FDV/MC > 3`. |
| **Volume confiável** | **Média — e subestimada.** Wash trading infla volume em exchanges menores. | Usar volume de exchanges de referência + volume on-chain de DEX. Nunca o volume agregado bruto. |
| **Moedas mortas (viés de sobrevivência)** | **Alta, e é o maior problema de todos.** Listas atuais só mostram sobreviventes. Em cripto, a taxa de mortalidade é ordens de grandeza maior que em ações. | Snapshots de universo desde o primeiro dia + preservar tudo que já entrou no banco. É a única defesa disponível de graça. |

---

## 7. Onde está o maior risco de overfitting

Esta seção é a mais importante do documento.

### 7.1 A amostra efetiva de cripto é minúscula

Bitcoin tem ~15 anos. Altcoins relevantes têm 4–8. Nesse período houve talvez
**2 ou 3 ciclos** — e um único regime macro dominante de cada vez.

Pior: **altcoins correlacionam 0,7–0,9 com BTC.** Um painel com 100 moedas e
1.000 dias parece ter 100.000 observações. Na prática:

```
n efetivo ≈ (número de períodos independentes) × (número de fatores de risco independentes)
          ≈ (dias / horizonte)                  × (~1 a 2)
```

Para horizonte de 30 dias em 5 anos: **≈ 60 × 1,5 ≈ 90 observações efetivas**,
não 100.000. O módulo `effective_sample_size` já implementa a versão
conservadora disso, e o relatório é obrigado a mostrar os dois números.

### 7.2 O horizonte de 24h é o mais perigoso de todos

Você pediu 24h, 7d, 30d, 90d. Sobre 24h, meu contraponto:

- A razão sinal/ruído em 24h é péssima. A volatilidade diária de uma altcoin
  é de 4–8%; qualquer efeito real é de dezenas de pontos-base.
- Custos comem tudo: spread + taxa + slippage passam fácil de 20 bps por
  rodada, e 365 rodadas por ano custam mais que o sinal.
- É o horizonte com mais observações aparentes e, por isso, o que mais produz
  padrões falsos. É exatamente onde o overfitting se esconde.

**Recomendo implementar 24h como métrica observada (para calibração), mas não
como base de decisão.** O foco do modelo deve ser 30d e 90d.

### 7.3 Viés de sobrevivência é pior em cripto que em ações

Milhares de tokens morreram. Qualquer backtest montado sobre "as 100 maiores de
hoje" está medindo o desempenho de vencedores conhecidos. **O efeito é grande o
suficiente para transformar uma estratégia perdedora em vencedora.**

### 7.4 Revisão retroativa de dados on-chain

Este é o vazamento que quase ninguém trata: **o TVL histórico da DefiLlama muda
depois.** Quando um adaptador é corrigido ou um protocolo é adicionado, a série
histórica inteira é reescrita. O mesmo vale para market cap na CoinGecko quando
o supply circulante é corrigido.

Consequência: **puxar "o histórico de TVL" hoje não dá o que se via naquela
época.** A defesa é armazenar *vintages* — snapshots diários do que foi
observado no dia, com `observed_at` — e nunca reconstruir o histórico a partir
de uma busca de hoje. Vou implementar isso na camada de ingestão de cripto.

### 7.5 Muitos fatores, poucos dados

Você listou 11 categorias de score e dezenas de métricas. Com ~90 observações
efetivas, ajustar dezenas de pesos é garantia de overfitting.

**Proposta:** o CryptoModel v1 começa com **pesos iguais e poucos fatores por
pilar**, exatamente como o modelo de ações. Aumentar complexidade só depois que
o walk-forward mostrar que o simples funciona.

---

## 8. Como validar que o sistema realmente melhorou

Quatro provas, em ordem crescente de dificuldade. Nenhuma sozinha basta.

**Prova 1 — Fora da amostra, não na amostra.** Walk-forward já implementado.
A métrica que vale é a série concatenada dos períodos de teste. A demonstração
sintética que rodei hoje já mostra por que: retorno médio de **+92% na
calibração** virou **−3,7% no teste**, e o Sharpe caiu de 0,86 para −0,48.
Isso com dados que *têm* sinal plantado. O backtest único teria parecido ótimo.

**Prova 2 — Deflated Sharpe.** Já implementado. Corrige pelo número de
variantes testadas, registrado em `model_experiments`. Sharpe 1,0 escolhido
entre 200 tentativas devolve probabilidade < 0,5 de ser real.

**Prova 3 — Calibração, não acerto.** Já implementado. Você mesmo escreveu:
"uma previsão de 51% não deve ser tratada da mesma maneira que uma de 90%".
Por isso a métrica primária é **Brier Skill Score contra a taxa base**, e não
acurácia. Um modelo que acerta 70% num mercado que subiu 70% do tempo tem
habilidade zero — e o BSS mostra isso como zero.

**Prova 4 — Track record prospectivo.** A única prova que não dá para falsear.
Previsões gravadas hoje, resolvidas daqui a 30 e 90 dias, sem possibilidade de
edição. É por isso que o diário é uma tabela separada do desfecho.

**Critério de promoção de versão** (`v1.0` → `v1.1`), já codificado no portão
de robustez:

1. melhor em **todos** os folds do walk-forward, não na média;
2. mantém sinal com custo dobrado;
3. não depende de um único ano para >20% do resultado;
4. calibração igual ou melhor;
5. deflated Sharpe não piora após contabilizar as variantes testadas;
6. paper trading por no mínimo um trimestre antes de qualquer uso real.

**Se a v1.1 não passar em todos, a v1.0 continua ativa.** Exatamente como você
escreveu: "se não melhorar, manter a versão anterior."

---

## Nota de segurança — Binance MCP

Você adicionou `binance-mcp-server` apontando para
`https://agent.binance.com/mcp/agentic`. Registrei nesta sessão e ele responde
**"Needs authentication"**. Três observações:

1. Este container é efêmero — a configuração morre com ele. Para uso real,
   adicione na sua máquina.
2. Para **pesquisa**, você não precisa dele: a API pública da Binance dá
   klines, funding e open interest sem chave e sem autenticação.
3. O endpoint chama-se *agentic*. Um endpoint autenticado de exchange pode ter
   capacidade de **movimentar saldo**. Dar a um agente de pesquisa acesso a uma
   ferramenta que negocia contraria o princípio que você mesmo definiu — paper
   trading antes de dinheiro real. Minha recomendação: manter a ingestão de
   dados na API pública e deixar qualquer credencial de conta fora do sistema.

---

## Etapas propostas

| Etapa | Entrega |
|---|---|
| **C1** | Mercado CRYPTO no núcleo: calendário 24/7, custos de exchange, benchmark BTC + índice total; universo dinâmico com snapshots e vintages |
| **C2** | Ingestão: CoinGecko (preço/mcap/supply), Binance (OHLCV/funding/OI), DefiLlama (TVL/taxas/receita/stablecoins) |
| **C3** | `crypto_scoring_v1.yaml` + `CRYPTO_MODEL_METHODOLOGY.md` + CryptoModel v1 |
| **C4** | Capital flow e derivativos; separação explícita *price up* × *capital confirmation* |
| **C5** | On-chain e atividade de desenvolvedores (Dune, GitHub) |
| **C6** | Notícias e regulação, como dado com confiança declarada |
| **C7** | Backtest e walk-forward de cripto; horizontes 7d/30d/90d (24h só observado) |
| **C8** | Relatório de 13 seções + guardrails de vocabulário cripto |
| **C9** | Daily Intelligence, Crypto Opportunities, Model Performance |
| **C10** | Detector causal de regime, compartilhado com ações |
