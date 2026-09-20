# DATA_SOURCES.md

Levantamento de fontes de dados para a V1 do Investment Research AI.
Última revisão: **2026-09-20**.

> **Aviso de verificação.** Preços e limites de API mudam com frequência e foram
> coletados de páginas públicas dos fornecedores e de comparativos de terceiros
> em setembro de 2026. Antes de assinar qualquer plano, confirme na página oficial.
> Os campos marcados com ⚠️ não puderam ser verificados de dentro do ambiente de
> desenvolvimento (a política de egresso desta sessão bloqueia os hosts).
> Toda linha com ⚠️ deve ser tratada como "a confirmar", não como fato.

---

## 1. Critérios de escolha

Ordem de prioridade adotada (e o porquê):

| # | Critério | Por que vem antes de "popularidade" |
|---|---|---|
| 1 | **Existe carimbo de data de publicação?** | Sem a data em que o dado ficou público, não há backtest honesto. Ver `docs/LOOKAHEAD_BIAS.md`. |
| 2 | **Licença permite uso e armazenamento?** | Muita API gratuita proíbe cache/redistribuição. Armazenamos localmente — isso é cache. |
| 3 | **Cobre empresas descontinuadas (delistadas)?** | Sem isso, todo backtest tem viés de sobrevivência e fica otimista demais. |
| 4 | **Histórico suficiente (10 anos)?** | Requisito explícito do backtest de 10 anos. |
| 5 | **Custo** | Preferimos gratuito na V1, desde que 1–4 sejam aceitáveis. |
| 6 | **Estabilidade da API** | Endpoint não oficial quebra sem aviso. |

**Popularidade não entrou na lista.** `yfinance` é a biblioteca mais popular do
mercado e falha nos critérios 1, 3 e 6 — usamos assim mesmo na V1, mas com o
custo documentado e isolado atrás de uma interface trocável.

---

## 2. Resumo da decisão para a V1

| Camada | Escolha V1 | Escolha V2 (quando houver orçamento) |
|---|---|---|
| Preços BR (B3) | `yfinance` (sufixo `.SA`) | Dados oficiais B3 / EODHD / brapi Pro |
| Preços US | `yfinance` ou Stooq (CSV) | Tiingo / Polygon / Nasdaq Data Link |
| Fundamentos BR | **CVM Dados Abertos** (DFP/ITR, com `DT_RECEB`) | CVM + normalização comercial |
| Fundamentos US | **SEC EDGAR XBRL** (`companyfacts`, com campo `filed`) | SEC + Sharadar SF1 (point-in-time nativo) |
| Benchmarks | `^BVSP` (Ibovespa), `^GSPC` / `SPY` (S&P 500) | Índices com retorno total (IBXX TR, SP500TR) |
| Setores | `yfinance` (`sector`) na V1, com override manual em `config/sectors_override.yaml` | GICS licenciado |
| Câmbio / juros | BCB SGS (Selic, CDI, USD/BRL), FRED (DGS10, DFF) | idem |

**Racional da escolha híbrida:** os preços vêm do provedor mais barato e fácil;
os **fundamentos vêm da fonte primária do regulador**, porque é a única que
carrega a data de entrega do documento — o dado sem o qual o backtest mente.

---

## 3. Fichas das fontes

### 3.1 yfinance (Yahoo Finance não oficial)

| Campo | Valor |
|---|---|
| **Fonte** | Yahoo Finance, via biblioteca `yfinance` (v1.7.0 em 2026-09) |
| **Dados** | OHLCV diário/intradiário, dividendos, splits, market cap, P/E, P/B, ROE, margens, receita, lucro, EBITDA, dívida, fluxo de caixa, balanços (4–8 trimestres), setor/indústria |
| **API** | Biblioteca Python; endpoints `query1/query2.finance.yahoo.com` **não oficiais** |
| **Custo** | Grátis |
| **Cobertura BR** | Sim, tickers `PETR4.SA`, `VALE3.SA`, etc. |
| **Limitações** | ⚠️ Sem limite documentado; throttling e bloqueio por IP (pior em IP de cloud). Sem data de publicação nos fundamentos. Histórico de balanços curto (tipicamente 4 anos anuais / 5 trimestres). Sem empresas delistadas. Preços ajustados são revisados retroativamente. Quebra quando a Yahoo muda o site. Desde 2025 usa `curl_cffi`, o que causa falhas atrás de proxies corporativos. |
| **Licença** | ⚠️ Sem licença de redistribuição. Os Yahoo Terms of Service restringem uso comercial e redistribuição. **Uso pessoal/pesquisa apenas.** |
| **Atualização** | EOD; cotação com atraso |
| **Confiabilidade** | Preços: boa para EOD. Fundamentos: **média-baixa** — sem PIT, sem histórico longo, ocasionais erros de sinal e de unidade. |
| **Veredito** | ✅ preços na V1. ❌ fundamentos como fonte única de verdade para backtest. |

### 3.2 CVM — Portal de Dados Abertos (Brasil) — **fonte primária BR**

| Campo | Valor |
|---|---|
| **Fonte** | https://dados.cvm.gov.br (datasets `cia_aberta-doc-dfp`, `cia_aberta-doc-itr`, `cia_aberta-cad`, `cia_aberta-doc-fre`) |
| **Dados** | DRE, Balanço Patrimonial (ativo/passivo), DFC, DVA, DMPL — consolidado e individual; cadastro de companhias; composição de capital |
| **API** | Sem API REST: arquivos **ZIP/CSV anuais** por HTTP (`.../dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_2024.zip`) |
| **Custo** | Grátis |
| **⭐ Ponto crítico** | Os CSVs trazem **`DT_RECEB`** (data de recebimento pela CVM) e `VERSAO`. É a data em que o dado ficou público — exatamente o que o backtest precisa. |
| **Limitações** | Sem ticker (a chave é **CNPJ/CD_CVM**; precisa de mapa CNPJ→ticker). Encoding `latin-1`, separador `;`, decimal `,`. Contas em plano de contas padronizado (`CD_CONTA`), não em nomes amigáveis. Reapresentações geram novas versões — precisa de lógica de versão. Cobertura desde 2010 (ITR/DFP no formato atual). |
| **Licença** | Dado público — Lei de Acesso à Informação / política de dados abertos do governo federal. **Redistribuível com citação.** |
| **Atualização** | Semanal (inclui reapresentações) |
| **Confiabilidade** | **Alta** — é o documento oficial auditado |
| **Veredito** | ✅ **Fonte de verdade para fundamentos BR.** |

### 3.3 SEC EDGAR XBRL (EUA) — **fonte primária US**

| Campo | Valor |
|---|---|
| **Fonte** | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`, `companyconcept`, `frames`, `submissions`; `https://www.sec.gov/files/company_tickers.json` |
| **Dados** | Todo fato XBRL já reportado: receita, lucro, EPS, ativos, dívida, fluxo de caixa, ações em circulação — por período e por filing |
| **API** | REST JSON, sem chave |
| **Custo** | Grátis |
| **⭐ Ponto crítico** | Cada fato traz **`filed`** (data do protocolo), `start`, `end`, `fy`, `fp`, `form`, `accn`. PIT nativo e auditável. |
| **Limitações** | **10 req/s** e `User-Agent` obrigatório com contato válido (bloqueio caso contrário). Taxonomia us-GAAP heterogênea: a mesma linha muda de tag entre empresas (`Revenues` vs `RevenueFromContractWithCustomerExcludingAssessedTax`) — exige mapa de tags com fallback. Só quem reporta nos EUA. Sem preços. Sem market cap. |
| **Licença** | Domínio público (obra do governo dos EUA) |
| **Atualização** | Quase em tempo real (< 1 min após disseminação) |
| **Confiabilidade** | **Altíssima** |
| **Veredito** | ✅ **Fonte de verdade para fundamentos US.** |

### 3.4 brapi.dev (Brasil)

| Campo | Valor |
|---|---|
| **Fonte** | https://brapi.dev |
| **Dados** | Cotação, histórico, dividendos, módulos fundamentalistas, FIIs, listagem de ativos |
| **API** | REST JSON com token |
| **Custo** | ⚠️ Gratuito bastante limitado (poucos tickers sem token e cota baixa); planos Startup (~150 mil req/mês) e Pro (~500 mil req/mês, histórico completo, FIIs). Preço em BRL — confirmar em https://brapi.dev/pricing |
| **Limitações** | ⚠️ Cotação com atraso (≈15 min no Startup, ≈5 min no Pro). Histórico completo só no Pro. Tickers por chamada limitados por plano. Fundamentos derivados de terceiros, **sem data de publicação**. |
| **Licença** | Termos do serviço; uso conforme plano |
| **Atualização** | Intradiária com atraso |
| **Confiabilidade** | Boa para cotação BR; média para fundamentos (sem PIT) |
| **Veredito** | 🟡 Alternativa a `yfinance` para preços BR quando o Yahoo falhar; **não** resolve o problema de PIT. |

### 3.5 Alpha Vantage

| Campo | Valor |
|---|---|
| **Dados** | Ações, ETFs, FX, cripto, fundamentos normalizados, indicadores técnicos |
| **Custo** | ⚠️ Gratuito ~25 req/dia; pagos a partir de ~US$ 49,99/mês |
| **Limitações** | Cota gratuita inviabiliza varredura de universo (25 req/dia ≈ 25 tickers/dia). Fundamentos normalizados **sem data de publicação**. Cobertura BR fraca. |
| **Licença** | Termos do serviço; uso não comercial no plano gratuito |
| **Confiabilidade** | Boa |
| **Veredito** | ❌ V1 (cota inviável). 🟡 backup pago. |

### 3.6 Financial Modeling Prep (FMP)

| Campo | Valor |
|---|---|
| **Dados** | Fundamentos profundos, índices calculados, dados derivados do EDGAR, 30+ anos para large caps |
| **Custo** | ⚠️ A partir de ~US$ 22–59/mês |
| **Limitações** | Gratuito muito restrito. Dados derivados — erros de normalização já foram reportados pela comunidade. Data de publicação disponível em alguns endpoints (`acceptedDate`), não em todos. |
| **Licença** | Termos do serviço; redistribuição proibida |
| **Veredito** | 🟡 Boa opção V2 para US se quisermos evitar o trabalho de normalizar XBRL. |

### 3.7 EODHD (EOD Historical Data)

| Campo | Valor |
|---|---|
| **Dados** | ~60 bolsas globais (inclui B3), EOD longo, fundamentos, dividendos, splits, **dados de empresas delistadas** |
| **Custo** | ⚠️ Gratuito ~20 req/dia; planos pagos por faixa |
| **⭐ Ponto forte** | É das poucas fontes acessíveis que oferece **universo com delistadas** — mata o viés de sobrevivência. |
| **Limitações** | Fundamentos são normalizados por terceiros. Qualidade em BR precisa de auditoria amostral. |
| **Licença** | Termos do serviço; sem redistribuição |
| **Veredito** | 🟡 **Melhor candidato pago para V2**, precisamente por causa das delistadas. |

### 3.8 Tiingo

| Campo | Valor |
|---|---|
| **Dados** | EOD US limpo e ajustado, notícias, fundamentos US em planos pagos |
| **Custo** | ⚠️ A partir de ~US$ 30/mês (há tier gratuito para uso pessoal com limites) |
| **Limitações** | Cobertura internacional/BR limitada |
| **Veredito** | 🟡 Ótimo para preços US em V2; não cobre BR. |

### 3.9 Stooq

| Campo | Valor |
|---|---|
| **Dados** | CSV de OHLCV histórico, US e alguns mercados; índices |
| **API** | URL de CSV direto, sem chave |
| **Custo** | Grátis |
| **Limitações** | ⚠️ Sem garantia formal, sem fundamentos, ajustes inconsistentes, cobertura BR irregular |
| **Veredito** | 🟡 Plano B gratuito para preços US, e útil como *segunda fonte* para cruzar/validar preços. |

### 3.10 B3 (oficial)

| Campo | Valor |
|---|---|
| **Dados** | Séries históricas oficiais (arquivo `COTAHIST` anual, layout de posição fixa), composição e histórico dos índices (Ibovespa, IBrX), negociação |
| **Custo** | Arquivos históricos gratuitos; market data em tempo real é produto comercial caro |
| **⭐ Ponto forte** | **Composição histórica do Ibovespa** — permite reconstruir o universo sem viés de sobrevivência e benchmark correto. |
| **Limitações** | Layout legado trabalhoso; sem fundamentos; downloads manuais/semiautomáticos |
| **Licença** | Termos da B3; redistribuição restrita |
| **Veredito** | 🟡 V1.5: usar `COTAHIST` para validar preços e a carteira teórica do Ibovespa para montar o universo histórico. |

### 3.11 Banco Central (BCB SGS) e FRED

| Campo | Valor |
|---|---|
| **Dados** | BCB SGS: Selic, CDI, IPCA, USD/BRL (séries 11, 12, 433, 1). FRED: DGS10, DFF, CPI |
| **API** | REST JSON, sem chave (BCB); FRED exige chave gratuita |
| **Custo** | Grátis |
| **Uso aqui** | **Taxa livre de risco** para Sharpe/Sortino — sem isso o Sharpe brasileiro fica absurdo, porque o CDI já rende dois dígitos. |
| **Confiabilidade** | Alta (fonte oficial) |
| **Veredito** | ✅ V1. |

---

## 4. Comparativo direto

| Fonte | Preços | Fundamentos | **Data de publicação** | **Delistadas** | BR | US | Custo V1 | Estabilidade |
|---|---|---|---|---|---|---|---|---|
| yfinance | ✅ | 🟡 curto | ❌ | ❌ | ✅ | ✅ | grátis | ⚠️ frágil |
| CVM Dados Abertos | ❌ | ✅ completo | ✅ `DT_RECEB` | ✅ (fica o histórico) | ✅ | ❌ | grátis | ✅ estável |
| SEC EDGAR XBRL | ❌ | ✅ completo | ✅ `filed` | ✅ | ❌ | ✅ | grátis | ✅ estável |
| brapi | ✅ | 🟡 | ❌ | ❌ | ✅ | 🟡 | ⚠️ pago p/ sério | 🟡 |
| Alpha Vantage | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | inviável | ✅ |
| FMP | ✅ | ✅ | 🟡 parcial | 🟡 | 🟡 | ✅ | pago | ✅ |
| EODHD | ✅ | ✅ | 🟡 | **✅** | ✅ | ✅ | pago | ✅ |
| Tiingo | ✅ | 🟡 US | ❌ | 🟡 | ❌ | ✅ | pago | ✅ |
| Stooq | ✅ | ❌ | — | ❌ | 🟡 | ✅ | grátis | 🟡 |
| B3 COTAHIST | ✅ | ❌ | — | **✅** | ✅ | ❌ | grátis | ✅ |
| BCB / FRED | — | — | — | — | ✅ | ✅ | grátis | ✅ |

---

## 5. O que a escolha da V1 nos custa (leia antes de confiar num backtest)

1. **Viés de sobrevivência.** O universo da V1 é montado a partir de tickers
   vivos hoje. Empresas que quebraram ou saíram da bolsa não aparecem, e elas
   são justamente as de retorno pior. **Isso infla o retorno do backtest.**
   Mitigação V1: `universe_snapshots` no banco, para que cada data use a
   composição registrada naquela data. Mitigação real: EODHD ou B3 COTAHIST.
2. **Fundamentos sem data de publicação no `yfinance`.** Por isso o sistema
   **recusa**, por padrão, usar fundamentos sem `publication_date` em backtest
   (`allow_estimated_publication_dates: false` em `config/settings.yaml`).
   Quando você liga a estimativa, cada linha fica marcada como estimada e o
   relatório avisa.
3. **Preços ajustados são revisados.** O `adj_close` de hoje para 2015 não é o
   que estava na tela em 2015. Para retorno total isso é aceitável; para
   simular ordens a preço exato, não é. Guardamos também o preço bruto.
4. **Sem dados de entrada/saída de índice.** O Ibovespa da V1 é uma série de
   preço, não a carteira histórica.
5. **Nenhuma fonte gratuita cobre bem *short interest*, ações em circulação
   diária ou revisões de analistas.** Não fingimos ter esses dados.

---

## 6. Recomendação de evolução

| Fase | Investimento | O que compra |
|---|---|---|
| V1 | R$ 0 | CVM + SEC + yfinance. Suficiente para provar ou derrubar a tese. |
| V1.5 | R$ 0 | B3 COTAHIST + carteira histórica do Ibovespa → universo BR sem viés de sobrevivência. |
| V2 | ~US$ 40–100/mês | EODHD (delistadas + global) ou Sharadar SF1 (PIT nativo US). Só vale **depois** que o walk-forward mostrar resultado estável. |

**Não assine nada antes do walk-forward ter dado sinal.** Pagar por dados é a
forma mais fácil de confundir custo com progresso.

---

## Fontes consultadas

- [brapi.dev — planos](https://brapi.dev/pricing) · [limites](https://brapi.dev/faq/tem-algum-limite) · [docs ações](https://brapi.dev/docs/acoes)
- [Portal Dados Abertos CVM — DFP](https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp) · [ITR](https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr)
- [SEC — EDGAR Application Programming Interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [yfinance CHANGELOG](https://github.com/ranaroussi/yfinance/blob/main/CHANGELOG.rst) · [New rate-limiting (issue #2128)](https://github.com/ranaroussi/yfinance/issues/2128)
- [Best Fundamentals APIs in 2026 — StockFit](https://developer.stockfit.io/blog/best-fundamentals-api)
- [Best Financial Data APIs in 2026 — nb-data](https://www.nb-data.com/p/best-financial-data-apis-in-2026)
- [Alpha Vantage — Best Stock Market APIs 2026](https://www.alphavantage.co/best_stock_market_api_review/)
- [Alternatives to Tiingo — Find My Moat](https://www.findmymoat.com/alternatives/tiingo)
