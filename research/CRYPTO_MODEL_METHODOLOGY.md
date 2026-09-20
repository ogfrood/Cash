# CRYPTO_MODEL_METHODOLOGY.md

Metodologia do CryptoModel. Documento irmão de `MODEL_METHODOLOGY.md`, e
deliberadamente **separado** dele.

**Versão:** `crypto-v1.0.0` · **Config:** `config/crypto_scoring_v1.yaml`
**Reprodutibilidade:** o SHA-256 da config acompanha cada score e cada previsão.

---

## 0. Por que um modelo separado

| | Ações | Cripto |
|---|---|---|
| Calendário | 252 pregões | **365 dias, 24/7** |
| Demonstração financeira auditada | Sim, com data de publicação | **Não existe** |
| Análogo de receita | Receita contábil | Taxas e receita de protocolo (DefiLlama) |
| Histórico útil | 20+ anos, vários regimes | 4–15 anos, **2 a 3 ciclos** |
| Benchmark | Ibovespa, S&P 500 | BTC e índice de market cap total |
| Custo por rodada | ~25 bps | **~55 bps** (taxa de exchange + slippage de altcoin) |
| Correlação interna | Moderada | **0,7–0,9 com BTC** |
| Mortalidade de ativos | Baixa | **Altíssima** |

Usar o mesmo modelo nos dois mercados seria elegante e errado. O **núcleo** é
compartilhado (banco point-in-time, quant, backtest, previsões, calibração,
IA); o **modelo** não.

Anualizar volatilidade de cripto com 252 em vez de 365 a subestima em ~24%.
Detalhe pequeno, erro grande.

---

## 1. Variáveis — fonte, cálculo, peso, limitação, frequência

Legenda de direção: `+1` maior é melhor no score; `−1` menor é melhor.

### Market Momentum (peso do pilar 1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `momentum_90d_7d` | CoinGecko / Binance | Retorno de t−90d a t−7d | 1,5 | +1 | Reversões de momentum em cripto são mais violentas que em ações | Diária |
| `momentum_30d` | idem | Retorno de 30 dias | 1,0 | +1 | Correlacionado com o anterior; não é informação independente | Diária |
| `momentum_7d` | idem | Retorno de 7 dias | 0,5 | **−1** | Reversão de curtíssimo prazo; efeito pequeno e comido por custo | Diária |

A exclusão dos 7 dias recentes no fator principal tem o mesmo motivo do 12-1
em ações: separar tendência de reversão.

### Liquidity (1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `trusted_volume_usd_median_30d` | Binance/Coinbase/Kraken + DEX on-chain | Mediana de 30 dias do volume em exchanges de referência | 1,5 | +1 | **Wash trading** infla volume agregado; por isso não usamos o total da CoinGecko | Diária |
| `volume_to_marketcap` | CoinGecko | Volume 24h ÷ market cap | 1,0 | +1 | Market cap depende de supply auto-reportado | Diária |
| `bid_ask_spread_bps` | Binance order book | Spread médio do topo do livro | 1,0 | −1 | Só das exchanges amostradas | Horária |

### Capital Flow (1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `volume_trend_30d` | Binance | Volume médio 30d ÷ 180d − 1 | 1,5 | +1 | Confunde interesse com especulação de alavancagem | Diária |
| `open_interest_change_30d` | Binance Futures | Variação do open interest | 1,0 | +1 | Só perpétuos das exchanges cobertas | Horária |
| `funding_rate_mean_7d` | Binance Futures | Média do funding de 7 dias | 1,0 | **−1** | **Direção negativa é deliberada:** funding muito positivo é alavancagem comprada esticada, ou seja, risco de liquidação — não confirmação | 8 em 8 horas |
| `etf_net_flow_30d` | Farside Investors | Fluxo líquido acumulado | 0,5 | +1 | Só BTC e ETH; nulo para o resto | Diária |

**Este é o pilar que implementa sua regra de separar PRICE UP de CAPITAL
CONFIRMATION.** Alta de preço entra em Market Momentum; confirmação por
capital entra aqui. Os dois aparecem separados no relatório, nunca somados
numa conclusão só.

### Network Activity (1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `active_addresses_change_30d` | Dune / CoinMetrics | Variação de 30 dias | 1,5 | +1 | **Endereços ativos não são comparáveis entre chains.** Por isso usamos VARIAÇÃO, normalizada dentro da categoria — nunca o nível absoluto | Diária |
| `transaction_count_change_30d` | Dune / Blockchair | Variação de 30 dias | 1,0 | +1 | Inflável por spam barato em chains de taxa baixa | Diária |
| `tvl_change_30d` | DefiLlama | Variação de 30 dias | 1,0 | +1 | TVL sobe quando o preço do colateral sobe, sem entrada nova de capital | Diária |

### Fundamentals (1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `fees_30d_usd` | DefiLlama | Taxas pagas pelos usuários em 30 dias | 1,5 | +1 | Nem todo protocolo tem adaptador; cobertura desigual | Diária |
| `revenue_30d_usd` | DefiLlama | Parcela capturada pelo protocolo | 1,0 | +1 | Definição varia entre protocolos | Diária |
| `fees_growth_qoq` | DefiLlama | Taxas 90d vs. 90d anteriores | 1,5 | +1 | **Série revisada retroativamente** — ver §3 | Diária |

É o análogo mais honesto de "fundamento" em cripto: dinheiro que usuários
efetivamente pagaram para usar a rede.

### Developer Activity (1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `active_contributors_90d` | GitHub API | Contribuidores distintos em 90 dias | 1,5 | +1 | Trabalho fora do GitHub não aparece; repositórios privados também não | Semanal |
| `commits_90d` | GitHub API | Commits em 90 dias | 0,5 | +1 | **Manipulável**: commits são baratos. Por isso pesa menos | Semanal |
| `contributors_change_180d` | GitHub API | Variação de contribuidores | 1,0 | +1 | Ruidoso em projetos pequenos | Semanal |

### Adoption (1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `stablecoin_supply_on_chain_change_90d` | DefiLlama Stablecoins | Variação do supply na chain | 1,0 | +1 | Só para L1/L2, não para tokens de aplicação | Diária |
| `dex_volume_change_90d` | DefiLlama | Variação do volume de DEX | 1,0 | +1 | Inclui volume de arbitragem e MEV | Diária |

### Valuation (1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `marketcap_to_fees_ttm` | CoinGecko + DefiLlama | Market cap ÷ taxas de 12 meses | 1,5 | −1 | Sem sentido para protocolo sem taxa; devolve ausência | Diária |
| `marketcap_to_tvl` | CoinGecko + DefiLlama | Market cap ÷ TVL | 1,0 | −1 | Só faz sentido para DeFi e L1 | Diária |
| `fdv_to_marketcap` | CoinGecko | FDV ÷ market cap | 1,5 | −1 | **Sinaliza diluição futura.** Razão > 3 significa que a maior parte do supply ainda vai chegar ao mercado | Diária |

**Regra explícita (item 3 do seu pedido, aplicada aqui também):** o sistema
mostra a posição do múltiplo — acima ou abaixo da própria mediana histórica,
acima ou abaixo da mediana dos pares — e **não** o converte em "barato" ou
"caro". O guardrail bloqueia essas duas palavras na saída.

### Catalysts (1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `upcoming_unlock_pct_supply_90d` | TokenUnlocks / docs | % do supply destravando em 90 dias | 1,5 | **−1** | Cobertura irregular; muitos projetos sem dado estruturado | Semanal |
| `supply_inflation_annual` | CoinGecko / tokenomics | Emissão anual ÷ supply circulante | 1,0 | −1 | Modelos de emissão variam muito | Semanal |

Unlock grande à frente é catalisador **negativo**: é oferta nova chegando.
Tratá-lo como "evento positivo" seria o tipo de erro que só aparece no
prejuízo.

### Risk (1,0)

| Variável | Fonte | Cálculo | Peso | Dir | Limitação | Atualização |
|---|---|---|---|---|---|---|
| `volatility_90d` | Preço | Desvio dos retornos diários × √365 | 1,5 | −1 | Mede o passado; não prevê risco futuro | Diária |
| `max_drawdown_90d` | Preço | Maior queda pico-vale | 1,0 | −1 | Uma janela ruim domina | Diária |
| `beta_to_btc` | Preço | Covariância com BTC ÷ variância de BTC | 0,5 | −1 | Instável; muda de regime | Diária |
| `top10_holder_share` | Explorers on-chain | Fração do supply nos 10 maiores endereços | 1,0 | −1 | Confunde exchange, ponte e custodiante com detentor real | Semanal |

### News / Sentiment (1,0) — **DESLIGADO na v1**

| Variável | Fonte | Peso | Dir | Por que está desligado |
|---|---|---|---|---|
| `news_sentiment_mean_30d` | Classificador sobre RSS | 1,0 | +1 | Sem histórico suficiente para backtest |
| `news_volume_change_30d` | idem | 0,5 | +1 | idem |

O pilar existe na estrutura com `enabled: false`. As notícias são **coletadas,
classificadas, armazenadas e mostradas no relatório** desde o início — mas não
entram no score enquanto não houver histórico para validar. Fator sem
validação dentro do score é decoração.

E, como você determinou: **sentimento é classificação de modelo, não fato.**
Toda saída carrega fonte, classificador e nível de confiança.

---

## 2. Normalização

Igual ao modelo de ações em método (z robusto com mediana/MAD, cross-section
na data, nunca ao longo do tempo), com dois ajustes:

1. **Winsorização em 5%/95%** em vez de 1%/99%. As caudas em cripto são muito
   mais grossas; cortar menos deixa um único outlier dominar o cross-section.
2. **Grupo de pares = categoria** (L1, L2, DeFi, AI, Gaming, RWA, DePIN,
   Memecoin, Infraestrutura), mínimo de 6 pares. Abaixo disso, compara contra
   o universo inteiro e o relatório informa.

Cobertura mínima total de 50% (contra 60% em ações), porque dados on-chain
faltam com frequência. Mesmo assim, **fator ausente nunca vira zero.**

---

## 3. Point-in-time em cripto: o vazamento que quase ninguém trata

Preço tem carimbo de tempo confiável. **Dado on-chain agregado, não.**

- O **TVL histórico da DefiLlama muda depois**: quando um adaptador é
  corrigido ou um protocolo é adicionado, a série inteira é reescrita.
- O **market cap histórico da CoinGecko muda** quando o supply circulante é
  corrigido.
- Indexadores fazem *backfill*; reorgs alteram blocos recentes.

Consequência: **buscar "o histórico de TVL" hoje NÃO devolve o que se via
naquela época.** Um backtest construído assim usa informação que não existia.

**Defesa implementada:** armazenamos *vintages*. Todo dado on-chain e de
market cap entra com `publication_date = data da observação` e o sistema
**nunca** reconstrói série histórica a partir de uma busca de hoje. O histórico
é construído acumulando snapshots diários, a partir do dia em que a ingestão
começou. Isso significa que **o backtest de cripto só vai ter profundidade
real depois de meses coletando** — e é melhor assim do que ter profundidade
falsa agora.

Onde só existir a série revisada, o dado entra com
`publication_date_is_estimated = 1` e é **descartado por padrão** pelo
backtest, como qualquer fundamento sem data real.

---

## 4. Horizontes e por que 24h não decide nada

| Horizonte | Uso |
|---|---|
| 24h | **Registrado e calibrado, mas não decide.** Razão sinal/ruído péssima; custo por rodada (~55 bps) supera qualquer efeito plausível; é o horizonte que mais produz padrão falso |
| 7 dias | Mínimo para decisão |
| 30 dias | **Horizonte principal** |
| 90 dias | Horizonte secundário |

Alvo padrão das previsões: **retorno excedente sobre BTC**, não retorno
absoluto. Motivo: a taxa base de retorno absoluto positivo num ciclo de alta é
de 70%+, o que faz qualquer modelo parecer calibrado e não mede habilidade
nenhuma. Contra BTC, a taxa base fica perto de 50% e a métrica volta a ter
significado.

---

## 5. Pesos: por que todos iguais

Mesmo argumento do modelo de ações, e mais forte aqui.

A amostra efetiva de cripto é da ordem de **dezenas** de observações
independentes — não de dezenas de milhares (ver
`docs/CRYPTO_INTELLIGENCE_PLAN.md §7.1`). Com 30 fatores ativos e ~90
observações efetivas, qualquer otimização de peso encontra padrão no ruído.

Pesos iguais entre pilares. Dentro de cada pilar, os pesos refletem julgamento
declarado (contribuidores pesam mais que commits porque commits são
manipuláveis; taxas pesam mais que TVL porque TVL sobe com o preço do
colateral). Esse julgamento está escrito para poder ser contestado.

Pesos só mudam com: walk-forward favorável em **todos** os folds, nova versão
registrada, modelo anterior preservado, e deflated Sharpe recalculado com o
número de variantes testadas.

---

## 6. Limitações que este modelo não resolve

| Limitação | Efeito | Estado |
|---|---|---|
| Viés de sobrevivência | **Grande.** Tokens mortos somem das listas | Mitigado por snapshots de universo; nunca eliminado sem base histórica de mortos |
| Correlação com BTC | Reduz a diversificação real a quase nada | Alvo em retorno excedente sobre BTC; `beta_to_btc` no pilar de risco |
| Supply auto-reportado | Market cap e FDV pouco confiáveis | Guardamos os dois e sinalizamos `FDV/MC > 3` |
| Wash trading | Volume inflado | Só volume de exchanges de referência e DEX on-chain |
| Revisão retroativa | **Look-ahead silencioso** | Vintages, ver §3 |
| Poucos ciclos | Tudo é "dentro da amostra" de 2–3 ciclos | Resultados quebrados por ciclo; nunca reportar só a média |
| Métricas on-chain não comparáveis entre chains | Ranking sem sentido | Normalização por categoria e uso de variação, não de nível |
| Regulação e risco de exchange | Não modelável | Declarado no relatório como risco, sem número |

---

## 7. Como contestar um número deste modelo

Igual ao de ações:

1. `config_hash` do score confere com o SHA-256 de `config/crypto_scoring_v1.yaml`;
2. `irai explain --market CRYPTO --ticker SOL --as-of DATA` devolve a
   contribuição fator a fator, o valor bruto, o z, a categoria de pares e o
   tamanho do grupo;
3. cada métrica carrega `inputs_json` com fonte, endpoint e data de observação.

Se algum passo não fechar, é bug — e reportar vale mais do que confiar.
