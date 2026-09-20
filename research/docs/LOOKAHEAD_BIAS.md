# Look-ahead bias — como o sistema se defende

> Este é o documento mais importante do projeto. Um backtest com look-ahead bias
> não é um backtest otimista: é ficção. Ele produz Sharpe 3 em cima de
> informação que ninguém tinha.

## 1. As quatro formas de vazamento

| # | Vazamento | Exemplo concreto | Defesa neste sistema |
|---|---|---|---|
| 1 | **Fundamento antes da publicação** | Balanço do 1T publicado em 15/05 usado numa decisão de 01/05 | `publication_date` obrigatório; filtro `publication_date <= as_of` |
| 2 | **Reapresentação** | Empresa republica o 1T em agosto corrigindo o lucro; o backtest de maio usa o número corrigido | Guardamos todas as versões (`version`); `as_of_fundamentals()` pega a **última versão publicada até a data**, não a última versão que existe |
| 3 | **Viés de sobrevivência** | O universo de 2015 é a lista de empresas que existem em 2026 | `universe_snapshots` por data; `companies.delisted_date`; `UniverseResolver` |
| 4 | **Sinal calculado com preço futuro** | Momentum de 12 meses que inclui o dia da decisão, ou z-score normalizado com média de toda a amostra | Sinais com `shift(1)`; normalização **cross-sectional na data**, nunca ao longo do tempo |

## 2. Contrato de dados point-in-time

Toda linha de fato financeiro (`financials`, `fundamentals`) carrega:

```
ticker              a que empresa se refere
period_end          fim do período contábil (ex.: 2024-03-31)
period_type         Q | A | TTM
publication_date    quando o dado ficou PÚBLICO   <-- a coluna que importa
publication_date_is_estimated  0 = data real do documento, 1 = estimada por lag
version             1, 2, 3… (reapresentações)
source              cvm_dfp | cvm_itr | sec_edgar | yfinance | fixture
ingested_at         quando ENTROU no nosso banco (auditoria, nunca usado em filtro)
metric, value, unit, currency
```

Dois carimbos distintos — `publication_date` e `ingested_at` — porque responder
"o dado era público?" é diferente de "eu já tinha o dado?".

## 3. A regra única de consulta

**Nenhum código de sinal lê a tabela de fundamentos diretamente.** Toda leitura
passa por:

```python
repo.fundamentals_as_of(ticker, as_of, metrics=[...])
```

que executa, em essência:

```sql
SELECT metric, value, period_end, publication_date, version, source
FROM fundamentals
WHERE ticker = :ticker
  AND publication_date <= :as_of          -- nada do futuro
  AND (:allow_estimated = 1 OR publication_date_is_estimated = 0)
ORDER BY period_end DESC, version DESC, publication_date DESC
```

e depois mantém, por `(metric, period_end)`, apenas a **maior versão cuja
publicação é anterior ou igual a `as_of`**.

Preços seguem a regra equivalente em `prices_as_of()`: `date <= as_of`, com a
decisão executada no **dia seguinte** (`execution_lag_days`, default 1).

## 4. Quando não existe a data real

`yfinance` não informa a data de publicação. Duas opções, e ambas são explícitas:

1. **Padrão (recomendado): recusar.** `allow_estimated_publication_dates: false`.
   O dado entra no banco, mas o backtest o ignora e o relatório informa quantas
   métricas foram descartadas.
2. **Estimar com lag conservador.** `publication_date = period_end + lag`, com
   lag por mercado e tipo de período em `config/settings.yaml`:

   | Mercado | Trimestral | Anual | Base |
   |---|---|---|---|
   | BR | 60 dias | 90 dias | Resolução CVM 80/22: ITR em até 45 dias, DFP em até 3 meses; usamos folga |
   | US | 45 dias | 75 dias | Prazos de 10-Q (40/45 dias) e 10-K (60/75/90 dias) por porte do filer |

   Toda linha assim fica com `publication_date_is_estimated = 1` e **aparece no
   relatório**. Um resultado que só funciona com estimativa ligada é um
   resultado suspeito.

## 5. Normalização sem vazamento

Z-scores são calculados **entre empresas, dentro da mesma data e do mesmo
setor** — nunca ao longo do tempo:

```
z(empresa, métrica, data) = (x - mediana_setor(data)) / (1.4826 * MAD_setor(data))
```

Usar média/desvio da série inteira (inclusive do futuro) é o erro silencioso mais
comum em scoring quantitativo. Ver `MODEL_METHODOLOGY.md §4`.

Winsorização também é feita por data (percentis 1/99 **daquela** data).

## 6. Como sabemos que a defesa funciona

Os testes em `tests/test_lookahead.py` incluem um **teste de envenenamento**:
gravamos um fundamento com `publication_date` no futuro e valor absurdo, e
verificamos que:

- `fundamentals_as_of` não o retorna;
- o score da data anterior não muda;
- o backtest produz exatamente os mesmos retornos com e sem a linha envenenada.

Se alguém futuramente burlar a camada de repositório, esse teste quebra.

## 7. O que continua sendo viés, mesmo com tudo isso

Honestidade sobre o que **não** está resolvido na V1:

- **Viés de sobrevivência residual**: sem fonte com delistadas, o universo
  histórico é aproximado. Ver `DATA_SOURCES.md §5.1`.
- **Ajuste retroativo de preços**: `adj_close` incorpora proventos conhecidos
  hoje. Aceitável para retorno total, errado para simular preço de tela.
- **Viés do pesquisador (o pior de todos)**: você escolheu indicadores e
  universo *sabendo* o que funcionou na última década. Nenhum código resolve
  isso. O walk-forward e o registro de previsões *fora da amostra*
  (`model_predictions`) existem por causa disso.
- **Liquidez**: o backtest assume execução no fechamento/abertura seguinte com
  custo fixo. Em small caps da B3, não é verdade.
