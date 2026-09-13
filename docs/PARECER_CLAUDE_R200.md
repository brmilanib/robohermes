# Parecer independente — Hermes R200

Revisor: Claude · Data: 2026-09-13 · Escopo: dossiê, fonte MQL5 v2.00, auditoria de código
e os quatro CSVs agregados da rodada R200.

Este parecer segue o roteiro do §12 do dossiê e responde às 8 perguntas prioritárias do §10.
Não executei ordens, não recompilei, não rodei backtest novo e não alterei o fonte de
referência. Onde cito função e linha, uso os módulos em `projeto_fonte/src/`.

---

## 0. Resumo executivo

1. **Os números batem e o código é causalmente sólido.** Reproduzi aritmeticamente os
   totais e a classificação de meses a partir dos CSVs. Na leitura estática, **não encontrei
   antecipação de preço futuro (look-ahead)** no detector de pivôs nem na rota de entrada.
   Isso confirma o parecer da auditoria interna.

2. **A conclusão da rodada está correta: a Referência (Caso 1) domina.** As duas variantes de
   pivô aumentaram o número de operações, **reduziram** o lucro e **pioraram** a consistência
   mensal. Isso não é um detalhe — é a evidência empírica de que **adicionar entradas para
   "preencher" meses fracos piorou o sistema.** Guarde essa lição.

3. **O objetivo declarado ("aumentar lucro com mais consistência mensal", meta aspiracional de
   nenhum mês negativo) está mal-endereçado pelo caminho que tende a ser tentado.** O risco
   real deste robô não são os meses negativos — é (a) **drawdown/alavancagem** e (b)
   **dependência de regime**. Enquanto isso não for tratado, mais filtros de entrada só
   ajustam ruído.

4. **~79% de todo o lucro do Caso 1 saiu de 2025–2026** (US$ 161,5 mil de US$ 204,9 mil),
   coincidindo com a alta histórica do ouro e a expansão de volatilidade. Com **lote fixo**,
   o robô transforma o nível/volatilidade do ouro em P&L. Isso é uma **aposta de regime
   alavancada**, não um edge estável comprovado.

5. **A maior alavanca disponível já está no seu código, desligada:** o dimensionamento por
   risco (% do patrimônio). Ativá-lo como **Caso 4 isolado** ataca o drawdown de frente sem
   tocar na lógica de entrada. É a experiência de maior valor e menor custo (ver
   `PLANO_EXPERIMENTOS.md`).

---

## 1. Reprodução dos números e leitura de resultados (roteiro §12.1)

**Fonte:** `dados_originais/comparacao(7).csv`, `analise/Meses_R200.csv`,
`Resultados_Anuais_R200.csv`.

| Métrica (56 meses completos: 01/2022–08/2026) | Caso 1 Referência | Caso 2 Continuidade | Caso 3 Início |
| --- | --- | --- | --- |
| Lucro líquido USD | **204.912,54** | 191.523,99 | 169.116,06 |
| Operações | 261 | 299 | 342 |
| Fator de lucro (ciclos) | **2,01** | 1,80 | 1,59 |
| Acerto | 26,05% | 25,42% | 24,56% |
| **DD relativo** | 42,76% | 43,58% | **36,85%** |
| **DD máximo em dinheiro** | **29.778** | 34.411 | **55.534** |
| Meses completos negativos | **17** | 22 | 18 (19 c/ set/26 parcial) |
| Swap acumulado USD | −17.866 | −19.738 | −21.182 |
| Risco máx. de um único trade | 14,62% | 16,98% | 12,21% |
| Máx. perdas consecutivas | 13 | 10 | 12 |
| R líquido médio por trade | +0,486 | +0,449 | +0,402 |

- **A soma dos meses concilia com o total** (tolerância de centavos, como o dossiê declara).
  Setembro/2026 é parcial (último tick 11/09/2026) e só o Caso 3 registrou operação nesse
  intervalo (−7.502,29), o que leva o Caso 3 de 18 para 19 meses negativos observados.
- **Cuidado com o DD do Caso 3.** Ele tem o menor DD **relativo** (36,85%) e o **maior** DD
  **em dinheiro** (US$ 55.534). São estatísticas diferentes, medidas em instantes diferentes;
  o menor percentual **não** significa menos risco. (Detalhe em §4.)
- **Comparação anual com a Selic (em BRL)** — `Resultados_Anuais_R200.csv` — mostra o robô
  batendo a Selic com folga **em todos os anos da amostra** (ex.: 2025, Caso 1: +146,5% BRL
  vs. Selic 14,3%). Isso é _in-sample_ e não deve ser lido como expectativa futura; serve
  apenas para dizer que, **nesta janela já vista**, o retorno excedeu o custo de oportunidade.

---

## 2. Auditoria de causalidade (roteiro §12.2)

Confirmo os pontos da auditoria interna e acrescento observações. Sem os registros
individuais (cycles/deals/events/bars), isto é **leitura estática do código**, não prova de
execução.

### 2.1 O que está correto (sem falha demonstrada)

- **Confirmação de pivô sem look-ahead.** Um extremo só é confirmado como pivô quando há duas
  barras fechadas de cada lado (`center = window[2]`), e fica disponível apenas na abertura
  seguinte (`available_time = next_open`). O "next_open" é só um horário — **não dá acesso ao
  OHLC da barra seguinte**. Ver `PivotCore.mqh:236-265` e o comentário `PivotCore.mqh:7-8`.
- **Rompimento avaliado antes de incorporar o novo pivô.** Em `HPStep`, a checagem de
  rompimento roda **no topo**, usando o estado anterior, e só depois a barra nova é
  adicionada/confirmada. A trava `known_at_open = pattern_available_time <= closed.time &&
  p2.available_time <= closed.time` garante que a referência (neckline P2) **já existia antes
  da abertura da barra de rompimento**. Ver `PivotCore.mqh:195-221`. Isto é causalmente
  correto.
- **Invalidação por F1 inclusive na barra de rompimento** (`closed.low <= p1.price →
  active_invalid`), e **no máximo um evento por padrão** (`active_invalid=true` após emitir).
  Ver `PivotCore.mqh:201-219`.
- **Somente barra fechada decide.** O EA age uma vez por nova barra M30 (`OnTick`
  `EA.mq5:501-503`) e lê apenas dados fechados em `ReadSignal`. Confere.
- **Prioridade BASE→PIVOT correta e sem fallback.** A rota extra só é considerada quando a
  original falha, e uma original que passa no setup mas falha no stop/margem/spread **não cai**
  para o pivô. Ver `PivotEntryCore.mqh:44-52` (`HPRouteEntry`) e `EA.mq5:519,536-538`.

### 2.2 Observações materiais (não são bugs, são hipóteses/limitações)

- **[A] O stop não é a geometria do pivô.** A rota de pivô detecta a estrutura F1–T–F2 (com
  F1 = invalidação geométrica), mas o **stop executado é o das 3 velas** (`min(Low[1..3]) −
  0,20 ATR`), não o F1. Ver `EA.mq5:384` (`H1Levels(...,.20,1.0,2.5,5.0,...)`) e a nota da
  auditoria A07. **Consequência:** a "estrutura" que justifica a entrada **não é a que
  protege** o trade. Geometria e stop são duas hipóteses distintas — e hoje estão
  desalinhadas. Isso é testável (ver Experimento 3 alternativo em `PLANO_EXPERIMENTOS.md`),
  mas **não** mexendo em stops retroativamente para salvar perdas conhecidas.
- **[B] Uma rejeição consome a oportunidade da barra.** `lastBar` é avançado **antes** de ler
  indicador e enviar ordem (`EA.mq5:503`); em G_STOP/G_SPREAD/G_REJECTED não há nova tentativa
  na mesma barra. A rodada teve 0 `G_NO_DATA` e 8/11/13 `G_REJECTED`, com último retcode
  **10018 (mercado fechado)**. É pequeno, mas parte das "oportunidades perdidas" é
  **execução/horário**, não qualidade de sinal. Só o `events.csv` separa as causas.
- **[C] Custo de ocupação altíssimo.** `G_POSITION = 10.394` no Caso 1 (`comparacao(7).csv`):
  é o nº de vezes que um sinal foi bloqueado por já haver posição aberta (`EA.mq5:532-533`).
  Muitos são o mesmo sinal persistindo por várias barras, então **não** são 10 mil
  oportunidades distintas — mas indica que a regra de **uma posição por vez** com **alvo
  longo (5R)** é o filtro mais restritivo depois do setup-base. Isso é central para a pergunta
  §10.5 e para entender por que **adicionar entradas (pivôs) canibalizou** as entradas BASE.

---

## 3. O que os agregados permitem — e o que não (roteiro §12.3)

**Permitem concluir:**
- Totais, fator de lucro, acerto, DD relativo/dinheiro, swap, meses positivos/negativos,
  risco máximo por trade, sequência de perdas — tudo reconciliado.
- Que, **no agregado**, as variantes de pivô **pioraram** lucro e consistência.

**NÃO permitem concluir (exigem cycles/deals/events/bars individuais):**
- **Não** atribua a diferença de lucro entre casos aos pivôs isoladamente. Os fills por PIVOT
  foram 0/58/111, mas as entradas BASE caíram 261→241→231. A **ocupação** por um pivô mudou
  quais BASE aconteceram depois. A diferença é uma **mistura** de: pivôs (bons/ruins), BASE
  perdidas, BASE recuperadas e mudança na trajetória de saldo. (`comparacao(7).csv`:
  `hp_base_selected`, `hp_pivot_fills`; auditoria A05.)
- Qual a distribuição real de R dos vencedores: o TP em 5R **corta** a observação
  (`mean_winner_MFE_R = 5,00` é artefato do teto, não do mercado). Não dá para saber se
  vencedores iriam além de 5R sem uma rodada sem teto.
- PnL de qualquer gestão (BE, parcial, trailing): os "paths" de breakeven são **observacionais**
  e só existem para o Caso 1. Não são resultado financeiro de uma gestão executada.

---

## 4. Risco real: alavancagem, regime, custos (roteiro §12.4)

Esta seção é a mais importante para o objetivo do proprietário.

### 4.1 O lucro é uma aposta de regime alavancada

Lucro anual do Caso 1 (`Resultados_Anuais_R200.csv`):

| Ano | Lucro USD | Retorno s/ equity inicial do ano |
| --- | --- | --- |
| 2022 | 14.297,77 | +143,0% |
| 2023 | 7.688,73 | +31,6% |
| 2024 | 21.469,76 | +67,1% |
| 2025 | **94.825,68** | **+177,4%** |
| 2026* (8,5 meses) | **66.630,60** | +44,9% |

- **2025 + 2026 = 78,8% de todo o lucro.** **2024–2026 = 89,3%.** Os dois primeiros anos
  completos (2022–2023) somam só 10,7%.
- O **lote é fixo em 1,00** o tempo todo (`max_open_lots = 1,00`; sem reinvestimento). Logo o
  crescimento **não** é juros compostos — é o ouro subindo de ~US$ 1.800 para US$ 3.000+ e a
  volatilidade (ATR) expandindo. Um vencedor de 5R num lote de 1,00 vale muito mais em dólares
  em 2026 do que em 2022. **O robô converte o regime do ouro em P&L.**
- Traduzindo: o desempenho estelar é, em grande parte, **beta de um bull market histórico do
  ouro, com alavancagem alta**, e não um edge comprovadamente estável. Se o ouro entrar em
  range ou queda prolongada (o robô é **só compra**), o perfil muda radicalmente.

### 4.2 A alavancagem está alta demais para "renda", baixa demais para dormir

- **Risco de até 14,62% do saldo num único trade** (`max_stop_risk_percent`, Caso 1). Um lote
  de 1,00 de XAUUSD sobre US$ 10 mil é ordem de ~20x de alavancagem nocional.
- **Até 13 perdas consecutivas** (`max_consecutive_losses`). Com acerto de 26%, sequências
  longas de perda são **esperadas**, não anomalia.
- **DD relativo de 42,76%** e **maior DD mensal intramês de 32,05%** (`maximum_monthly_DD`).
  O primeiro mês da amostra (01/2022) perdeu **−26,52%** da conta.
- **Swap de −17.866** (Caso 1): carrego negativo por manter comprado ~28h em média (máx.
  ~526h). Num alvo de 5R que às vezes leva semanas, o swap corrói o R realizado.

O padrão do drawdown é revelador: **em % ele encolhe ao longo do tempo** (porque o lote fica
fixo enquanto a conta cresce), mas **em dinheiro ele explode** (US$ 25 mil de queda num único
mês em 02/2026). Ou seja, a "suavidade" recente do gráfico em % é **artefato do lote fixo +
conta grande**, não estabilização do edge.

### 4.3 Por que isso condena a meta "sem meses negativos"

Com acerto de 26% e alvo de 5R, o sistema **vive de poucos trades grandes**. Meses sem um
vencedor grande são negativos por construção — e são **inevitáveis**. Tentar zerá-los com
filtros escolhidos na mesma amostra é ajustar ruído: foi exatamente o que as variantes de
pivô fizeram, e **pioraram** tudo. A meta correta não é "zero mês negativo"; é **"nenhum mês
(ou drawdown) capaz de me tirar do jogo"** — e isso se resolve com **tamanho de posição**,
não com mais entradas.

---

## 5. Respostas às 8 perguntas prioritárias (§10)

1. **A inspeção confirma os filtros ativos?** Sim. Caso 1 = EMA21>SMA50 e SMA50 subindo;
   Close>SMA200 e SMA200 subindo; ADX14≥20 e +DI>−DI; toque anterior na EMA em [2]/[3]/[4];
   vela gatilho altista com Close>EMA21 e Close>High[2]; Ask−EMA21≥0,5 ATR. Casos 2/3 acrescentam
   a rota de pivô F1–T–F2 (Caso 3 remove só as duas condições de SMA200). Bate com
   `XAU_H1_Core.mqh:18-52`, `EntryCore.mqh:55-90` e `PivotEntryCore.mqh:23-52`. **Divergência
   material:** o rótulo "Início" sugere captar reversões, mas a rota extra **ainda exige
   tendência local** (EMA21>SMA50 etc.) — não é detector de reversão (auditoria A07).
2. **Como separar o efeito dos 58/111 pivôs dos 20/30 BASE a menos?** **Não dá** com os
   agregados. Requer `cycles.csv` por caso, casando `signal_time` + `selected_entry_path` para
   classificar BASE-comum, BASE-exclusivo e PIVOT, e medir contribuição líquida **e** custo de
   ocupação. Até lá, não culpe (nem credite) o padrão isoladamente.
3. **O stop de 3 velas é coerente com a geometria F1–T–F2?** Não — são hipóteses distintas
   (§2.2[A]). Um teste limpo e **único**: na rota de pivô, comparar stop-3-velas vs. stop em
   F1 (−buffer), **fora da amostra**, sem escolher retroativamente o que salva perdas
   conhecidas. Ver Experimento 3 (alternativa) no plano.
4. **Ask≥EMA+0,5 ATR ajuda ou atrasa?** É um filtro de **momentum/extensão** (exige preço já
   esticado acima da EMA). Testável por comparação causal do parâmetro `InpMinEntryATR`
   (`EA.mq5:18,518`) em janelas cronológicas separadas — **sem** usar MFE/resultado futuro
   como entrada. É um lever pequeno; não prioritário.
5. **Há custo de ocupação excessivo com 5R?** Provavelmente sim (§2.2[C], `G_POSITION`=10.394).
   Faltam `events.csv`/`cycles.csv` para medir o resultado das BASE bloqueadas por posição
   aberta. Respeitando sua preferência por não fracionar alvos curtos, a resposta **não** é
   parcial; é medir a ocupação e, se for cara, tratá-la via **sizing** (posições menores,
   eventualmente mais de uma) num caso próprio — nunca como "correção".
6. **Existem regimes identificáveis e estáveis antes da entrada?** É a pergunta central e
   **ainda em aberto**. O lucro concentrado em 2024–2026 (§4.1) é o alerta. Boa notícia: o EA
   **já grava as variáveis de regime pré-entrada** por ciclo — `featureADX`, `featureADXChange`,
   `featureATR`, `featureDistance=(entry−EMA)/ATR`, `featureSlope=(SMA200−oldSMA200)/ATR`
   (`EA.mq5:474-475`). Isso viabiliza o Experimento 2 assim que os `cycles.csv` chegarem.
7. **O menor DD do Caso 3 justifica menos lucro e mais meses negativos?** **Não**, por nenhum
   objetivo pré-declarado razoável. E o "menor DD" é só **relativo**; em dinheiro o Caso 3 é o
   **pior** (US$ 55,5 mil). O Caso 1 domina.
8. **Testes mínimos para distinguir (i) correção do código, (ii) reprodução do backtest e
   (iii) vantagem em dados novos?** (i) rodar os testes portáveis de `projeto_fonte/tests/` e
   registrar hash do EX5; (ii) reproduzir o Caso 1 com o mesmo histórico/preset e conferir os
   124 campos + 1.026 mensais já conciliados; (iii) **walk-forward + forward DEMO em janela
   nunca usada na escolha** (ver protocolo no plano). Só (iii) fala sobre o futuro.

---

## 6. Tabela evidência × impacto

| # | Achado | Tipo | Evidência | Impacto | O que fazer |
| --- | --- | --- | --- | --- | --- |
| E1 | Sem look-ahead no detector/rota | Confirmação | `PivotCore.mqh:195-265`; `PivotEntryCore.mqh:44-52` | Alta confiança na causalidade | Manter; registrar hash do EX5 |
| E2 | Pivôs pioraram lucro e consistência | Confirmação | `comparacao(7).csv` (204,9k vs 191,5k vs 169,1k; 17/22/18 meses) | Rejeita a hipótese das entradas extras | **Não ativar** Casos 2/3 |
| E3 | 79% do lucro em 2025–2026 | Risco de regime | `Resultados_Anuais_R200.csv` | Edge pode ser beta do ouro | Experimento 2 (regime) |
| E4 | Risco até 14,6%/trade; DD 42,8%; 13 perdas seguidas | Desenho financeiro | `comparacao(7).csv` | Alavancagem perigosa p/ conta real | **Experimento 1 (sizing)** |
| E5 | Motor de risco existe, desligado | Oportunidade | `EA.mq5:413-434`; `DonchianCore.mqh:62`; `XAU_H1_Core.mqh:70` | Alavanca barata sobre o DD | **Caso 4** |
| E6 | Stop ≠ geometria do pivô | Limitação/hipótese | `EA.mq5:384`; auditoria A07 | Estrutura não protege o trade | Experimento 3 (alternativa), OOS |
| E7 | Ocupação alta (`G_POSITION`=10.394) | Limitação | `EA.mq5:532-533` | BASE canibalizadas | Medir com cycles/events |
| E8 | TP 5R corta a observação de MFE | Limite de métrica | `mean_winner_MFE_R=5,00` | Não se sabe se 5R é ótimo | Rodada diagnóstica sem teto |
| E9 | Rejeições consomem a barra | Limitação operacional | `EA.mq5:503`; retcode 10018 | Pequena perda de oportunidade | Analisar `events.csv` |

---

## 7. Dados estritamente necessários para avançar

Os agregados já foram exauridos. Para qualquer decisão de estratégia com base empírica, são
necessários os **detalhes por caso** (o índice `dados_originais/arquivos_comparacao(3).csv`
aponta para as pastas exportadas no seu computador, ainda **não** anexadas):

1. **`cycles.csv`** de cada caso (com `signal_time`, `selected_entry_path`, `quoted_entry`,
   `entry`, `stop`, `target`, `initialRisk`, e as `feature*` de regime já gravadas) — separa
   PIVOT × BASE e habilita a análise de regime.
2. **`events.csv`** — separa rejeições por horário/causa (pergunta §10.4 e E9).
3. **`deals.csv`** — swap/comissão por trade e R realizado vs. nominal.
4. **Relatório nativo do MT5** (modelagem de ticks, qualidade do histórico, spread) + **hash
   do EX5** e do preset — sem isso, o backtest não é totalmente reproduzível nem auditável
   (auditoria A01/A02).

---

## 8. O que NÃO fazer (para não repetir o erro da R200)

- **Não** adicionar filtros de entrada escolhidos porque "removem" um mês ruim conhecido.
- **Não** otimizar parâmetros na janela 2022–2026 e chamar de melhoria.
- **Não** apresentar uma versão com sizing por risco como "correção" do Caso 1 — é **outro
  caso**, com outra natureza de risco (passa a compor), e precisa de validação própria.
- **Não** prometer (a si mesmo ou a terceiros) "sem meses negativos" ou "renda garantida".

O plano de experimentos, com regras exatas, previsões falsificáveis e protocolo de validação,
está em **`PLANO_EXPERIMENTOS.md`**.
