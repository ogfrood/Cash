# MODEL_METHODOLOGY.md

Metodologia do modelo de scoring. Este documento existe para que qualquer
número produzido pelo sistema possa ser reproduzido e contestado.

**Versão do modelo:** `stock-v1.0.0`
**Config:** `config/scoring_v1.yaml` (versão `v1.0.0`)
**Reprodutibilidade:** o SHA-256 do arquivo de configuração é gravado em cada
score e em cada previsão. Mesma config + mesmo banco = mesmo número, sempre.

---

## 1. O que o score é — e o que ele não é

O score é uma **ordenação relativa** de empresas dentro de um universo, numa
data, segundo critérios declarados.

Ele **não** é:

- estimativa de retorno futuro;
- probabilidade de alta;
- preço justo;
- recomendação.

Ele não tem unidade econômica. Um score de 1,2 não significa "12% ao ano".
Significa "esta empresa está 1,2 desvios robustos acima da mediana dos pares
no conjunto de critérios escolhidos". Se os critérios estiverem errados, o
score estará errado com precisão de três casas decimais.

---

## 2. Pipeline

```
fundamentos brutos (CVM/SEC)          preços (yfinance/B3)
        |                                     |
        v                                     v
  métricas derivadas                    fatores de mercado
  (herdam data de publicação)           (janela até as_of)
        |                                     |
        +------------------+------------------+
                           v
              painel de fatores em as_of
                           v
         winsorização (percentis da própria data)
                           v
         z robusto dentro do setor (mediana/MAD)
                           v
                 clip em ±3 desvios
                           v
      média ponderada por fator -> score do pilar
                           v
      média ponderada por pilar -> score total
```

---

## 3. Os fatores, um a um

Cada linha responde: **o que é**, **por que está aqui**, e **o que pode dar
errado**.

### 3.1 Quality (peso 1,0)

| Fator | Peso | Direção | Por que existe | O que pode dar errado |
|---|---|---|---|---|
| `roic` | 1,5 | + | Retorno sobre capital investido é a medida menos manipulável de vantagem competitiva. Peso maior que ROE porque não é inflado por alavancagem. | Depende da alíquota efetiva real; quando ela não é calculável, a métrica fica ausente em vez de estimada. Capital investido é sensível a intangíveis e arrendamentos. |
| `roe` | 1,0 | + | Retorno para o acionista. Usa patrimônio **médio**, não final. | Alavancagem infla ROE. Patrimônio negativo devolve ausência, não número. |
| `operating_margin` | 1,0 | + | Rentabilidade antes de estrutura de capital e impostos. | Varia estruturalmente por setor — daí a normalização setorial. |
| `gross_margin` | 0,5 | + | Poder de precificação. | Classificação de custos varia entre empresas. |
| `net_margin` | 0,5 | + | Resultado final. | Contaminada por itens não recorrentes e resultado financeiro. |

### 3.2 Growth (peso 1,0)

| Fator | Peso | Direção | Por que existe | O que pode dar errado |
|---|---|---|---|---|
| `revenue_growth_yoy` | 1,5 | + | Receita é a linha menos sujeita a escolha contábil. Peso maior por isso. | Crescimento por aquisição parece orgânico. Inflação alta infla receita nominal — relevante no Brasil. |
| `earnings_growth_yoy` | 1,0 | + | Crescimento que chega ao acionista. | Base pequena produz crescimento percentual absurdo. Base negativa devolve ausência. |
| `eps_growth_yoy` | 1,0 | + | Crescimento **por ação**: separa criação de valor de emissão de ações. | Recompra agressiva produz crescimento de LPA sem crescimento de negócio. |

Todos comparam **TTM contra TTM do ano anterior**, nunca trimestre contra
trimestre anterior — isso mediria sazonalidade.

### 3.3 Value (peso 1,0)

| Fator | Peso | Direção | Por que existe | O que pode dar errado |
|---|---|---|---|---|
| `ev_ebitda` | 1,5 | − | Neutro a estrutura de capital; o mais comparável entre empresas. | EBITDA ignora capex — enganoso em setores intensivos em capital. |
| `pe` | 1,0 | − | O múltiplo mais usado, logo o mais informativo sobre expectativa. | Inútil com lucro negativo (devolve ausência). Sensível a itens não recorrentes. |
| `price_to_fcf` | 1,0 | − | Caixa é mais difícil de maquiar que lucro. | FCF é volátil; um ano de capex alto distorce. |
| `pb` | 0,5 | − | Relevante para bancos e para ativos tangíveis. | Quase sem sentido para empresas de intangíveis. |

Direção negativa significa: **múltiplo mais baixo contribui positivamente para
o score**. Isso é a hipótese de valor, não um fato. Em regimes de crescimento,
ela custa dinheiro por anos seguidos.

### 3.4 Momentum (peso 1,0)

| Fator | Peso | Direção | Por que existe | O que pode dar errado |
|---|---|---|---|---|
| `momentum_12_1` | 1,5 | + | O efeito mais replicado da literatura: 12 meses excluindo o mês recente. | Sofre reversões brutais em viradas de mercado (crashes de momentum). |
| `momentum_6m` | 1,0 | + | Confirmação de médio prazo. | Correlacionado com 12-1; não é informação independente. |
| `momentum_3m` | 0,5 | + | Tendência recente. | Ruidoso. |
| `momentum_1m` | 0,5 | **−** | Reversão de curto prazo: o mês mais recente tende a reverter. | Efeito pequeno e sensível a custo de transação. |

O sinal negativo em `momentum_1m` é deliberado e é o motivo de `momentum_12_1`
existir separado de `momentum_12m`.

### 3.5 Financial Health (peso 1,0)

| Fator | Peso | Direção | Por que existe | O que pode dar errado |
|---|---|---|---|---|
| `net_debt_ebitda` | 1,5 | − | A medida mais direta de risco de solvência. | Sem sentido para bancos e seguradoras. EBITDA negativo devolve ausência. |
| `debt_to_equity` | 1,0 | − | Alavancagem estrutural. | Setorialmente muito diferente; patrimônio negativo quebra a leitura. |
| `fcf_margin` | 1,0 | + | Empresa que não gera caixa depende de terceiros para sobreviver a ciclo ruim. | Empresa em expansão legítima tem FCF negativo. |
| `current_ratio` | 0,5 | + | Liquidez de curto prazo. | Estoque elevado infla sem melhorar liquidez real. |

### 3.6 Risk (peso 1,0)

| Fator | Peso | Direção | Por que existe | O que pode dar errado |
|---|---|---|---|---|
| `volatility_12m` | 1,5 | − | Anomalia de baixa volatilidade: ativos menos voláteis historicamente entregaram retorno ajustado melhor. | Volatilidade passada é previsor fraco de volatilidade futura em quebras de regime. |
| `max_drawdown_12m` | 1,0 | − | Captura risco de cauda que o desvio-padrão não vê. | Uma única janela ruim domina a métrica. |
| `beta` | 0,5 | − | Sensibilidade ao mercado. | Instável; muda com a janela e com o benchmark escolhido. |

**Aviso que vale repetir:** este pilar mede risco **realizado no passado**. Ele
não prevê risco futuro. Chamá-lo de "Risk" é uma conveniência de nomenclatura.

---

## 4. Normalização

### 4.1 Por que z robusto e não z comum

Múltiplos financeiros têm caudas grossas. Um P/L de 900 numa amostra de 50
empresas move a média e o desvio o suficiente para achatar todo o resto. Usamos:

```
z = (x - mediana_grupo) / (1,4826 × MAD_grupo)
```

O fator 1,4826 torna o MAD comparável ao desvio-padrão sob normalidade.
Quando o MAD é zero (todos iguais), caímos para o z comum; se o desvio também
for zero, o grupo inteiro recebe zero — dizer "todos iguais" é mais honesto que
dividir por zero.

### 4.2 Winsorização

Percentis 1 e 99 **da própria data**. Nunca da série histórica — usar percentis
calculados com dados futuros é look-ahead.

### 4.3 Grupo de pares

Padrão: **setor**. Comparar a margem de um banco com a de uma mineradora não
informa nada.

Quando o setor tem menos de 5 empresas na data, a empresa é normalizada contra
**o universo inteiro**, e o relatório informa isso. O grupo efetivo e o número
de pares aparecem em toda saída, porque um z-score contra 4 pares e um z-score
contra 40 são coisas diferentes com o mesmo nome.

### 4.4 Clip

±3 desvios robustos. Limita o peso de um outlier remanescente sem descartá-lo.

---

## 5. Pesos: por que todos iguais

Os seis pilares têm peso 1,0. **Não porque seja ótimo — porque não temos
evidência para outra coisa.**

O argumento: qualquer conjunto de pesos diferente teria sido escolhido olhando
o desempenho histórico da própria amostra que usamos para testar. Isso é
ajuste, e ajuste sem validação fora da amostra é overfitting com etapa extra.

Pesos iguais são a **hipótese nula honesta**. Eles só mudam quando:

1. o walk-forward mostrar, em múltiplos folds independentes, que outro conjunto
   é consistentemente melhor;
2. a mudança for registrada como nova versão (`v1.1.0`), com o modelo antigo
   preservado;
3. o número de variantes testadas for contabilizado e o Sharpe for deflacionado
   por ele (ver §7).

Dentro de cada pilar os pesos dos fatores **não** são iguais. Eles refletem
julgamento declarado — por exemplo, receita pesa mais que lucro porque é menos
manipulável. Esse julgamento é discutível; está escrito justamente para poder
ser discutido.

---

## 6. Dados ausentes

Nenhum fator ausente é preenchido. Nem com zero, nem com a média do setor.

- Fator ausente reduz a **cobertura** do pilar.
- Pilar com cobertura < 50% dos pesos → sem score.
- Empresa com cobertura de pilares < 60% → **sem score total**, fica fora do
  ranking.

O motivo: num z-score, zero significa "exatamente na mediana do setor". É uma
afirmação forte sobre uma empresa da qual não se sabe nada. Imputar é inventar
com boa educação.

---

## 7. Como o modelo pode ser mudado

```
previsão → desfecho → análise de erro → modelo candidato
   → backtest → walk-forward → calibração → comparação
   → PORTÃO → nova versão → paper trading → (eventual) uso real
```

**Portão de robustez.** Um candidato só substitui o vigente se:

- sobreviver ao walk-forward em **todos** os folds, não na média;
- manter sinal com **custos de transação dobrados**;
- não depender de um único ano para mais de 20% do resultado;
- não degradar com pequenas perturbações de parâmetro;
- ter **calibração** ao menos tão boa quanto a do vigente.

Maior retorno histórico **não** é critério de seleção. Nunca.

**Portão do holdout selado.** Os 18 meses mais recentes ficam selados e só são
abertos uma vez por versão maior. Cada abertura é registrada. Sem isso, a
repetição do ciclo acima vira overfitting distribuído no tempo — o erro mais
difícil de enxergar, porque cada passo individual parece rigoroso.

**Contagem de tentativas.** `model_experiments.n_variants_tested` acumula
quantas variantes foram testadas. O Sharpe reportado é acompanhado do
*deflated Sharpe ratio*, que responde à pergunta que todo backtest esconde:
quantas ideias você testou antes desta?

---

## 8. Vieses conhecidos que a metodologia NÃO elimina

| Viés | Efeito | Estado |
|---|---|---|
| Sobrevivência | Infla retorno do backtest | **Presente na V1.** Mitigado por `universe_snapshots`, resolvido só com fonte que cubra delistadas. |
| Pesquisador | Infla tudo | **Insolúvel por código.** Walk-forward e holdout selado reduzem; o registro de previsões fora da amostra é a única prova real. |
| Ajuste retroativo de preço | Pequeno | Presente; aceitável para retorno total. |
| Seleção de universo | Médio | Universos da V1 são listas montadas em 2026. |
| Regime único | Alto | 10 anos de dados cobrem poucos regimes de juros. Todo resultado é quebrado por sub-período. |
| Liquidez / impacto de mercado | Médio em small caps | Não modelado. Filtro de liquidez mitiga parcialmente. |
| Custo tributário | Pequeno a médio | Dividendos entram via `adj_close` sem imposto. |

---

## 9. Como contestar um número deste sistema

1. Pegue o `config_hash` gravado com o score.
2. Confirme que bate com o SHA-256 de `config/scoring_v1.yaml`.
3. Rode `irai explain --ticker X --as-of DATA`: sai a contribuição de cada
   fator, o valor bruto, o z, o grupo de pares e o tamanho do grupo.
4. Cada métrica fundamental carrega `inputs_json` com as linhas de balanço, os
   períodos e as datas de publicação usadas no cálculo.

Se algum desses passos não fechar, é bug — e vale mais reportá-lo do que
confiar no resultado.
