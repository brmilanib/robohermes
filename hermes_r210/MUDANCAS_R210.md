# Hermes R210 — o que mudou e por quê (para o ChatGPT e o proprietário)

Versão nova a partir do R200. **R200 (`../projeto_fonte/`) fica congelado** como
comparador auditado; o R210 acrescenta quatro casos novos **isolados**, reaproveitando o
motor de execução já validado. Trabalho a 4 mãos: o Claude escreveu esta versão; o ChatGPT
compila no MetaEditor, roda os backtests no MT5 e devolve os resultados.

> **Filosofia desta rodada (pedido do proprietário):** o robô **não pode ganhar só porque o
> ouro subiu**. Duas frentes: (1) **normalizar o risco** para o resultado deixar de ser uma
> aposta alavancada no preço do ouro; (2) testar uma estratégia de **ganhos menores e mais
> frequentes** — aproveitar a entrada de alto volume, pegar o nosso e sair.

---

## 1. O que é honesto afirmar sobre esta versão

- **Validado aqui (g++):** toda a lógica de decisão portável — roteamento dos casos, o
  `QHGate` do Caso 5, o `DDThrottleMultiplier` do Caso 6, o `WDUpdate`/`WDTradingCapital` do
  Caso 7, a propagação de `profile.be15`/alvo do Caso 8, o `EMACrossGate` do Caso 9 e o corpo de
  produção do `OpenCycle` — compila e passa em 12/12 testes unitários (`python3 verificar.py`).
  Os **cores auditados do R200 continuam byte-idênticos** (a verificação prova isso). O motor de
  breakeven do Caso 8 (`ManageProtection`/`MoveStops`/`PEArm`) **não é código novo** — é o mesmo
  motor do R200, já testado, só nunca configurado com `be15>0` em nenhum Caso até agora. O Caso 9
  é o primeiro desde o Caso 5 (Colheita Rápida) a introduzir uma condição de entrada
  **genuinamente nova** (`EMACrossCore.mqh`), em vez de só configurar um motor existente.
- **NÃO validado aqui:** rentabilidade. Não há MetaTrader neste ambiente — **nenhum backtest
  nativo foi executado por mim**. Todos os Casos 4-9 já rodaram no MT5 do proprietário — os
  Casos 4, 6 e 7 têm resultados reais que se sustentam (§3); os Casos 5, 8 e 9 também têm
  resultado real, mas foram **rejeitados** pelos critérios pré-registrados (§3.4, §3.5, §4).
- **Um passo que depende do ChatGPT:** o EA completo precisa ser **compilado no MetaEditor**.
  A cola de integração no EA (ex.: `ReadQuickHarvest`, o ramo do `OnTick`) segue os padrões do
  próprio projeto, mas não pôde ser compilada aqui. Se aparecer algum erro de compilação,
  me diga o texto do erro que eu corrijo.

**Nunca** apresente Caso 4 ou 5 como "melhoria" antes da validação fora da amostra (§7).

---

## 2. Os nove casos

| Caso | Nome | Entrada | Sizing | Alvo | Situação |
| --- | --- | --- | --- | --- | --- |
| 1 | HERMES_REFERENCIA | original (pullback+tendência) | **lote fixo 1,00** | 5R | **congelado R200** |
| 2 | HERMES_PIVO_CONTINUIDADE | original + pivô (com SMA200) | lote fixo 1,00 | 5R | congelado R200 |
| 3 | HERMES_PIVO_INICIO | original + pivô (sem SMA200) | lote fixo 1,00 | 5R | congelado R200 |
| 4 | **HERMES_RISCO_REF** | **igual ao Caso 1** | **risco % do patrimônio** | 5R | **novo — testado pelo proprietário** |
| 5 | **HERMES_COLHEITA_RAPIDA** | **surto de volume/range** | risco % do patrimônio | **curto (InpQHTargetR)** | **testado — REJEITADO (§4)** |
| 6 | **HERMES_DD_THROTTLE** | **igual ao Caso 1/4** | risco % **com freio por rebaixamento** | 5R | **novo — testado pelo proprietário (§3.2)** |
| 7 | **HERMES_SAQUE_LUCRO** | **igual ao Caso 1/4** | risco % **sobre capital com saque de lucro** | 5R | **novo — testado pelo proprietário (§3.3)** |
| 8 | **HERMES_BREAKEVEN_3R** | **igual ao Caso 1/4** | risco % do patrimônio | **3R + stop no breakeven em 1R** | **testado — REJEITADO (§3.4)** |
| 9 | **HERMES_CRUZAMENTO_EMA** | **igual ao Caso 1/4 + filtro EMA5/21** | risco % do patrimônio | 5R | **testado — REJEITADO (§3.5)** |

Selecione o caso pelo input `InpCase` (1..8) ou pelos presets em `presets/`.

---

## 3. Caso 4 — Referência com sizing por risco

**Por quê.** No R200 o lote é fixo em 1,00; o risco por trade varia de ~2% a ~15% do
patrimônio e o P&L em dólar vira função do nível/volatilidade do ouro. Dimensionar cada trade
a uma **fração fixa do patrimônio** (ex.: 1%) faz o **drawdown ser governado por você**, não
pelo regime do ouro. **As entradas são idênticas às do Caso 1** — muda só o tamanho.

**O motor já existia.** O caminho de risco (`DCRiskLot`, ramo `else` do `OpenCycle`, modo
`PERCENT_RISK` do `H1Volume`) já estava implementado e testado no R200; só rodava desligado.

**Mudanças (arquivos/linhas):**
- `src/PivotEntryCore.mqh` · `HPSelectProfile`: aceita `id` 1..5; para 4 e 5 faz
  `d.fixedLot=false` e garante `riskPercent` válido. Mantém todas as demais travas (5R,
  família 15, sem parcial/BE/adições).
- `src/PivotEntryCore.mqh` · `HPExtraGate`/`HPRouteEntry`: admitem id até 5; Casos 1, 4 e 5
  **não usam a rota de pivô** (base apenas), então Caso 4 = entradas idênticas ao Caso 1.
- `src/EA.mq5` · `OnInit`: novo input `InpRiskPercent` (0<x≤2); aplica `dc.riskPercent`
  quando `InpCase≥4`.
- `src/EA.mq5` · `OpenCycle`: para Casos 4/5 o teto de lote do `DCRiskLot` passa a ser o
  **volume máximo do símbolo** (o risco% e a margem% governam). Fixo (1–3) mantém `InpMaxLot`.

**Previsão falsificável.** DD relativo cai de ~43% para a faixa de ~10–15% (a 1% de risco);
retorno passa a **compor** (CAGR pode ficar menor — é esperado). **Rejeite** se o DD não cair
de forma material.

**Resultado real (backtest do proprietário, mesma janela do R200):**

| `InpRiskPercent` | Lucro líquido | DD relativo | Trades / acerto |
| --- | --- | --- | --- |
| 1% | 20.986 | 16,63% | 261 / 26,05% (idênticos ao Caso 1) |
| 2% | 76.920 | 30,22% (31,91% no capital líquido) | 261 / 26,05% |

Confirma a previsão: **mesmas entradas, drawdown 2,6× menor que o Caso 1** (42,76%) a 1% de
risco. O lucro em dólar é menor que o Caso 1 (204.912) **de propósito** — o Caso 1 chegava a
arriscar 14,6% da conta num único trade (13 perdas seguidas observadas); aquele resultado
inclui alavancagem que teria risco real de ruína numa ordem diferente dos trades.

### 3.1 Ajuste: teto de risco liberado até 5% (antes era travado em 2%)

O `DCRiskLot` original (usado pelos Casos 1–3) **recusa** (`G_RISK`, volume 0) qualquer
`riskPercent > 2%` — é uma proteção de fábrica do motor herdado. Para o proprietário poder
**medir a fronteira risco×retorno** conscientemente, os Casos 4/5 agora usam um cálculo próprio
(mesma fórmula do `DCRiskLot`, sem esse teto) que aceita `InpRiskPercent` até **5%**. Acima de
2% o EA imprime um aviso no log (`Print`), mas não bloqueia — é uma escolha deliberada, não
um "vale tudo" silencioso. **Os Casos 1–3 continuam recusando >2% exatamente como antes**
(prova disso em `tests/test_entry.cpp`, que testa os dois comportamentos lado a lado).

**Preset novo:** `presets/CASO_04_RISCO_2a5pct.set` — varre `InpRiskPercent` em {2, 3, 4, 5}
num único teste de otimização (Caso 4, entradas idênticas ao Caso 1). Use-o para desenhar a
curva DD×retorno e escolher o seu ponto de equilíbrio — **não** para "achar o risco que dá
mais lucro" (isso é ajuste na amostra, o mesmo erro do R200 com os pivôs).

> **⚠️ Risco de ruína cresce rápido acima de 2–3%.** O sistema já teve 13 perdas seguidas.
> A 5% de risco por trade, 13 perdas seguidas somam uma perda composta de
> `1 − (0,95)^13 ≈ 49%` do patrimônio **só nessa sequência** — e o histórico não garante que a
> próxima pior sequência não será mais longa. Trate os valores de 3–5% como **medição da
> fronteira**, não como recomendação de uso.

**Resultado real do sweep 2/3/4/5% (backtest do proprietário, `CASO_04_RISCO_2a5pct.set`,
mesma janela, 261 trades em todos):**

| Risco | Lucro líquido | Fator de Lucro | DD máximo | Fator de Recuperação |
| --- | --- | --- | --- | --- |
| 2% | 76.920 | 1,64 | 25,38% | 3,87 |
| 3% | 189.539 | 1,58 | 26,91% | 2,65 |
| 4% | 493.187 | 1,52 | 38,50% | 1,95 |
| 5% | 1.126.465 | 1,46 | 45,84% | 1,51 |

O lucro cresce muito mais rápido que o risco (2%→5% é só 2,5× o risco, mas ~14,6× o lucro —
composição geométrica do sizing por %), só que o Fator de Lucro e o Fator de Recuperação
**pioram a cada degrau**. A 5%, o DD máximo já é 66% do lucro final (1/1,51); a 2%, é 26%
(1/3,87). Isso **não é ajustável dentro da própria fórmula do Caso 4** — é a mesma composição
geométrica operando nos dois sentidos (lucro e dor). Ver §3.2 para o mecanismo que ataca isso.

### 3.2 Caso 6 — Caso 4 + freio de risco por rebaixamento

**Por quê.** O proprietário pediu: dá pra manter o lucro alto do risco 5% reduzindo o
drawdown? Não existe ajuste dentro da fórmula do Caso 4 que faça isso — sizing fixo-fracionário
tem essa forma para um edge fixo, ponto. O que existe é um mecanismo **diferente**: reduzir o
risco% **efetivo** quando o patrimônio está em rebaixamento contra o maior pico já visto, e
restaurar o risco cheio assim que um novo pico é feito. Isolado como **Caso 6**, comparado
contra o Caso 4 no mesmo risco-base (5%) — nunca substituindo o Caso 4.

**Mecanismo (`src/DDThrottleCore.mqh`, função pura `DDThrottleMultiplier`):**
- Rebaixamento até `InpDDBand1` (padrão 15%) do pico: risco cheio (multiplicador 1,0).
- Entre `InpDDBand1` e `InpDDBand2` (padrão 25%): risco × `InpDDMult1` (padrão 0,50).
- Acima de `InpDDBand2`: risco × `InpDDMult2` (padrão 0,25).
- Patrimônio faz novo pico → volta a 1,0 imediatamente (o pico é reavaliado a cada tick em
  `TrackEquity()`, `ddPeakEquity`).
- Dados ou configuração inválidos (bandas fora de ordem, multiplicadores fora de `(0,1]` ou
  crescentes com o rebaixamento) devolvem multiplicador **0** — chão de segurança, nunca
  amplia risco por engano de configuração.

**Só muda o volume — nenhuma entrada/saída é alterada.** `HPSelectProfile`/`HPRouteEntry`
tratam o Caso 6 exatamente como o Caso 4 (mesma rota, `HP_DISABLED`, sem pivô); o multiplicador
entra **só** dentro do cálculo de `sizingRiskBudget` em `OpenCycle`, e só quando `InpCase==6` —
o Caso 4 fica **imune** a `ddPeakEquity` (testado explicitamente em `tests/test_entry.cpp`).

**Preset:** `presets/CASO_06_HERMES_DD_THROTTLE.set` — `InpCase=6`, `InpRiskPercent=5.0` (mesmo
risco-base do pior DD do sweep acima), bandas/multiplicadores nos padrões. Compare o relatório
desse preset diretamente contra a linha "5%" da tabela acima: mesmas entradas, mesmo risco
nominal, só o freio ligado.

**Previsão falsificável.** DD máximo cai de forma material frente aos 45,84% do Caso 4 puro a
5%, sem devolver todo o lucro adicional que o risco 5% trouxe sobre o risco 2%. **Rejeite** a
hipótese se o freio não reduzir o DD, ou se reduzir o lucro de volta a algo próximo do que o
próprio risco 2% já entregava sozinho (nesse caso o freio não valeu o mecanismo extra — seria
mais simples só usar 2% direto).

**Bandas e multiplicadores são a primeira hipótese, não um resultado provado.** Assim como o
Caso 5, isso precisa validação fora da amostra antes de qualquer conclusão (§7). Se o primeiro
teste não convencer, ajustar as bandas é experimento novo — uma variável de cada vez, contra o
mesmo comparador (Caso 4 a 5%), nunca uma varredura cega de bandas×multiplicadores ao mesmo
tempo.

**Resultado real da tentativa 1 (`CASO_06_HERMES_DD_THROTTLE.set`, bandas 15%/25%, corte
50%/25%):** lucro 186.845 (devolveu 83% do lucro do Caso 4 @ 5% puro), DD do saldo caiu de
45,84% para 34,34%, mas o DD do **capital líquido** (equity, flutuante) ficou praticamente
igual (47,12%) — o freio só reduz o risco da *próxima* entrada, não encolhe uma posição já
aberta, então um trade que abre logo após um pico ainda pode afundar bastante antes de bater o
próprio stop. Pior: **o resultado ficou dominado pelo Caso 4 flat a 3%** (lucro quase igual,
189.539, com DD menor — 26,91% — e Fator de Recuperação melhor — 2,65 vs 2,25). Bandas cedo e
corte forte demais.

**Tentativa 2 (`CASO_06B_HERMES_DD_THROTTLE_SUAVE.set`):** mantém risco cheio por mais tempo
(`InpDDBand1=25`, não 15) e corta mais leve (`InpDDMult1=0.65`, não 0,50); só entra na banda
funda depois de 35% de DD (`InpDDBand2=35`, não 25), cortando pra 0,65→0,35 em vez de
0,50→0,25. Mesmo risco-base (5%) do Caso 4 e da tentativa 1 — única variável mudada é a forma
do freio.

**Resultado real da tentativa 2 (US$ 10.000):** lucro 337.353 (quase o dobro da tentativa 1),
DD estimado ~31% (contra 45,84%/56,68% do Caso 4 puro a 5% — dependendo de qual das duas
métricas de DD, ver nota abaixo), 22 meses negativos de 57. Melhor equilíbrio até agora entre
lucro e drawdown — mas **ainda é a segunda tentativa, não uma resposta final**; bandas e
multiplicadores continuam sendo a hipótese testada, não um resultado provado.

> **Nota sobre DD:** o `summary.csv` do Testador grava dois campos parecidos —
> `equity_percent_at_max_money_dd` (quanto sobrou do pico **no exato momento** do maior
> rebaixamento em **dinheiro**) e `equity_dd_relative_percent` (o pior rebaixamento **em
> porcentagem**, que pode ter acontecido num instante diferente, geralmente mais cedo, quando a
> conta ainda era menor). Este documento citava o primeiro por engano nas primeiras rodadas —
> o correto para "qual foi o pior tombo relativo" é sempre `equity_dd_relative_percent`. Os
> números do Caso 4 puro corrigidos: 2%→31,91%, 3%→43,90%, 4%→51,99%, 5%→**56,68%** (não
> 20,56/29,95/38,50/45,84% como constava antes).

### 3.3 Caso 7 — Caso 4 + saque de lucro (trava de ganho)

**Por quê.** No Caso 4 a 5%, o patrimônio chegou a um pico de ~US$ 1,36 milhão antes de um
único tombo devolver ~US$ 737 mil (54% daquele pico). Tecnicamente quase todo esse dinheiro em
risco era **lucro do próprio robô**, não capital original (só 0,7% do pico veio do depósito
inicial) — mas o motor de risco% não faz essa distinção: ele sempre arrisca a mesma fração do
patrimônio **atual**, para sempre, então o mesmo tombo proporcional se repete a cada novo pico,
com o lucro acumulado virando a nova base arriscada. Pedido do proprietário: sacar uma fração
do lucro a cada novo recorde, deixando só o resto compondo.

**Mecanismo (`src/WithdrawalCore.mqh`, funções puras `WDUpdate`/`WDTradingCapital`):**
- A cada novo recorde de **saldo realizado** (fechamento de trade — nunca patrimônio
  flutuante; saque só faz sentido sobre lucro já concretizado), uma fração do incremento
  (`InpWithdrawFraction`, padrão 50%) é contabilizada como "sacada".
- O saque nunca é desfeito: se o saldo cair depois, o total já sacado permanece.
- O capital usado para calcular o risco% (`sizingRiskBudget`) passa a ser
  `patrimônio − total sacado` (nunca negativo), em vez do patrimônio real puro.
- **A margem continua calculada sobre o patrimônio REAL da conta** — o saque só muda quanto se
  arrisca por trade, nunca a margem de fato disponível (nenhum dinheiro sai de verdade da conta
  do Testador; isso seria uma operação de saque real, fora do escopo testável aqui).
- Dados ou configuração inválidos (fração fora de `[0,1]`) — a atualização simplesmente não
  acontece; nunca amplia risco por engano.

**Só muda o volume — nenhuma entrada/saída é alterada**, mesma disciplina dos Casos 5/6:
`HPSelectProfile`/`HPRouteEntry` tratam o Caso 7 exatamente como o Caso 4 (mesma rota,
`HP_DISABLED`, sem pivô); o saque entra **só** dentro do cálculo de `sizingRiskBudget` em
`OpenCycle`, e só quando `InpCase==7` — os Casos 4/5/6 ficam **imunes** a `withdrawState`
(testado explicitamente em `tests/test_entry.cpp`).

**Preset:** `presets/CASO_07_HERMES_SAQUE_LUCRO.set` — `InpCase=7`, `InpRiskPercent=5.0`
(mesmo risco-base do Caso 4 puro que fez o US$ 1,1 milhão), `InpWithdrawFraction=0.50`.
Comparar diretamente contra a linha "5%" do Caso 4 puro (§3.1) — mesmas entradas, mesmo risco
nominal, só o saque ligado.

**Previsão falsificável.** O patrimônio de risco cresce mais devagar que o Caso 4 puro (metade
de cada novo recorde sai do sizing), então o **lucro total é menor** — isso é esperado e não é
"pior", é o preço da trava. O que importa medir: (1) o **capital sacado acumulado** (dinheiro
que teria saído da mesa, fora de risco, numa conta real) chega a superar o pico de patrimônio
que o Caso 4 puro atingiu? (2) o **drawdown relativo sobre o que ainda está em risco** melhora
de forma material? **Rejeite** a hipótese se o capital sacado acumulado for pequeno demais para
justificar o lucro menor, ou se o drawdown do que resta em risco não cair de forma clara.

**Diferença de filosofia frente ao Caso 6:** o freio (Caso 6) reduz risco **durante** um
rebaixamento, tentando evitar que ele fique tão fundo. O saque (Caso 7) não evita nenhum
rebaixamento — ele **tira dinheiro da mesa antes**, então mesmo um tombo de 56% sobre o capital
que restou em risco representa uma fatia menor da riqueza total do proprietário (parte já está
sacada, fora do alcance daquele tombo). São mecanismos complementares, não concorrentes — dá
pra imaginar um Caso futuro combinando os dois, mas só depois de entender cada um isolado.

**Resultado real (US$ 10.000, mesmo risco-base de 5% do Caso 4 puro):** lucro 186.878 (quase
idêntico à tentativa 1 do Caso 6 — coincidência de caminho, não sinal de nada). O
`equity_dd_relative_percent` reportado pelo Testador (48,10%) **não conta a história real**
aqui: como o Testador não sabe que uma parte do lucro "sairia" da mesa, a conta real fica com
100% do dinheiro, só em posições menores. Reconstruindo o saque mês a mês a partir do
`months.csv` (mesma fórmula do `WDUpdate`) e somando ao patrimônio restante na conta, o
**patrimônio total real chega a US$ 303.060** (30,3× o depósito) com um rebaixamento **real**
de só **≈ 29,4%** (setembro/2023) — o melhor de tudo testado até aqui, mas **só vale se o saque
for executado de verdade na vida real**; sem isso, a conta fica exposta aos 48,10% reportados,
sem nenhuma reserva em lugar nenhum. `negative_booked_months` ficou em 20/57 — empatado com o
Caso 4 puro em todos os níveis de risco, reforçando que sizing (incluindo o saque) não move
esse número.

### 3.4 Caso 8 — Caso 4 + breakeven em 1R + alvo 3R

**Por quê.** Depois de confirmar, com dados reais de 3 mecanismos de sizing diferentes (Casos
4, 6, 7), que **nenhum ajuste de tamanho de posição move `negative_booked_months`** (ficou
sempre entre 20 e 25, nunca melhor que os 17 do Caso 1 original) — pedido do proprietário: virar
a chave e mexer na **gestão do trade em si**, não mais no tamanho. Dois ajustes juntos: mover o
stop para o preço de entrada assim que o trade atinge 1R de lucro flutuante (perdas que já
estavam indo bem viram ~0 em vez de -1R cheio) e reduzir o alvo de 5R para 3R (mais fácil de
alcançar, deveria subir a taxa de acerto).

**O motor já existia — de novo.** `Execution.mqh` (congelado, auditado) já tem
`ManageProtection()`/`MoveStops()`/`PEArm()` prontos e testados (`test_execution.cpp` já cobria
"confirmed half+BE"); o próprio R200 original já tinha uma tabela de gatilhos candidatos
pré-calculados (`PEThreshold`: 1,0R / 1,5R / 2,0R / 2,5R / 3,0R) para essa exata pergunta — só
nunca foi configurada com um valor diferente de zero em nenhum Caso. Não foi escrita nenhuma
lógica nova de proteção; só uma configuração (`profile.be15=InpBETriggerR`) que faltava.

**Mudanças (arquivos/linhas):**
- `src/EA.mq5` · novos inputs `InpBETriggerR` (padrão 1,0R) e `InpBETargetR` (padrão 3,0R).
- `src/EA.mq5` · `OnInit`: `profile.be15=InpBETriggerR` logo após `HPSelectProfile`, só quando
  `InpCase==8` (mesmo padrão de `dc.riskPercent=InpRiskPercent` para os Casos 4+). Validação:
  `0 < InpBETriggerR < InpBETargetR <= 10`.
- `src/EA.mq5` · `OpenCycle`: `reward=InpBETargetR` (em vez do 5,0 fixo) quando `InpCase==8`.
- `src/PivotEntryCore.mqh`: roteamento aceita `id` até 8, mesmas entradas do Caso 1 (`HP_DISABLED`).

**Só muda a proteção/alvo — nenhuma entrada é alterada**, mesma disciplina dos Casos 5/6/7.
Casos 4/6/7 ficam **imunes**: `profile.be15` nunca é sobrescrito para eles, então
`cycles[n].beTrigger` continua em zero (testado explicitamente em `tests/test_entry.cpp`).

**Preset:** `presets/CASO_08_HERMES_BREAKEVEN_3R.set` — `InpCase=8`, `InpRiskPercent=5.0`
(mesma base do Caso 4 puro que fez o US$ 1,1 milhão), `InpBETriggerR=1.0`, `InpBETargetR=3.0`.
Comparar diretamente contra a linha "5%" do Caso 4 puro (§3.1) — mesma entrada, mesmo risco
nominal, só a proteção/alvo mudados.

**Previsão falsificável.** A taxa de acerto (`cycle_win_percent`) deve subir em relação aos
26,05% de todos os Casos anteriores (alvo mais fácil de alcançar). O `average_net_R_initial`
pode cair um pouco (alvo menor limita o R máximo por trade), mas menos perdas cheias (viram
breakeven) deveria compensar — o teste real é se **`negative_booked_months` cai** de forma
material. **Rejeite** a hipótese se a taxa de acerto não subir, ou se subir mas
`negative_booked_months` não melhorar (sinal de que o alvo menor cortou ganhadores sem
realmente evitar meses ruins).

**Se quiser isolar as duas mudanças** (saber quanto vem do breakeven sozinho vs do alvo menor
sozinho): rode de novo com `InpBETargetR=5.0` (mantém alvo original, só o breakeven ativo) —
compara contra este resultado e contra o Caso 4 puro, uma variável de cada vez.

**Resultado real — tentativa 1, breakeven 1R + alvo 3R (`CASO_08_HERMES_BREAKEVEN_3R.set`,
US$ 10.000):**

| Métrica | Caso 4 @ 5% (sem BE, alvo 5R) | Caso 8, BE 1R + alvo 3R |
| --- | --- | --- |
| Lucro líquido | 1.126.465 | 121.313 |
| Fator de Lucro | 1,46 | 1,46 |
| Trades | 261 | 340 |
| Taxa de acerto | 26,05% | **22,35%** |
| `equity_dd_relative_percent` | 56,68% | 44,97% |
| `negative_booked_months` | 20/57 | **23/57** |
| Perdas seguidas (máx.) | 13 | 12 |

**Hipótese REJEITADA pelos dois critérios pré-registrados.** A taxa de acerto **caiu** (não
subiu) e `negative_booked_months` **piorou** (23 > 20). O DD relativo até melhorou de verdade
(56,68%→44,97%), mas custou **89% do lucro** — muito mais caro que o Caso 6 ou o Caso 7 pagaram
por uma redução de DD parecida.

**A comparação não é tão "isolada" quanto parecia.** O sistema abre só uma posição por vez
(trava `active<0` em `ManageProtection`). Ciclos mais curtos (alvo 3R + saídas antecipadas no
breakeven) liberam essa trava mais cedo, deixando o EA aceitar sinais que no Caso 4 ficariam
bloqueados por `G_POSITION` (posição já ativa) — por isso os trades subiram de 261 para 340. Não
é o mesmo grupo de 261 trades com proteção extra; é uma **população diferente**, com quase 80
ciclos adicionais que só existem porque o giro ficou mais rápido. Mudar a gestão de saída também
muda quais entradas são aceitas depois — um efeito colateral que os Casos 6/7 (só mudam tamanho,
não duração) não tinham.

**O "0x0" quase não aconteceu.** O gatilho armou em 185/340 ciclos (54%) e confirmou o stop em
184 — o mecanismo funcionou certinho — mas dos 108 ciclos que depois voltaram e bateram o stop
no breakeven, só **5** fecharam em zero exato; o resto fechou como perda pequena (spread/swap
corroem a saída "no preço de entrada" o suficiente pra não zerar). E mais da metade dos
perdedores (151/259) nunca chegou perto do gatilho de 1R (MFE médio dos perdedores = 0,90R) —
nenhum ajuste de breakeven com gatilho ≥1R protegeria essa maioria.

**Resultado real — tentativa 2 (isolamento), breakeven 1R + alvo ORIGINAL 5R
(`InpBETargetR=5.0`, mesmo preset, US$ 10.000):**

| Métrica | Caso 4 @ 5% (sem BE) | Caso 8, BE 1R + alvo 3R | Caso 8, BE 1R + alvo 5R (isolado) |
| --- | --- | --- | --- |
| Lucro líquido | 1.126.465 | 121.313 | 295.147 |
| Fator de Lucro | 1,46 | 1,46 | 1,60 |
| Trades | 261 | 340 | 297 |
| Taxa de acerto | 26,05% | 22,35% | **15,82%** |
| `equity_dd_relative_percent` | 56,68% | 44,97% | **63,91%** |
| `negative_booked_months` | 20/57 | 23/57 | **28/57** |
| Perdas seguidas (máx.) | 13 | 12 | **24** |

**O isolamento piora ainda mais — o breakeven sozinho é o pior dos três, não um meio-termo.**
Tirando o alvo curto da equação (voltando a 5R), a taxa de acerto cai ainda mais (15,82%, a mais
baixa de toda a família de casos), o DD relativo **passa a ser pior que o próprio Caso 4 sem
proteção nenhuma** (63,91% > 56,68%), a sequência de perdas quase dobra (24 contra 13) e
`negative_booked_months` vai a 28/57 — o pior número já medido neste projeto. Isso mostra que
**mover o stop para breakeven, isolado, não é neutro aqui — é prejudicial**: com um alvo distante
(5R), o preço tem mais tempo/espaço para passar de 1R e depois cair de volta, transformando
trades que teriam sido ganhadores em saídas no breakeven — e o corte de alguns perdedores
completos não compensa a perda de ganhadores nem a ampliação da sequência de perdas e do DD.

**Conclusão do Caso 8: as duas variantes testadas (BE+3R e BE isolado) estão REJEITADAS.** Nem
juntar breakeven com alvo curto, nem usar o breakeven sozinho, cumpriu qualquer um dos dois
critérios pré-registrados. Combinado com os Casos 4/6/7 (nenhum mecanismo de **sizing** move
`negative_booked_months`) e agora os dois mecanismos de **gestão do trade** testados aqui (ambos
pioram esse número), a conclusão empírica até aqui é que os 20/57 meses negativos parecem ser
uma característica estrutural das **entradas** do sistema (baixa frequência, ~4,6 trades/mês,
26% de acerto nativo) — não algo resolvível só ajustando tamanho de posição ou proteção de stop.
Próximo passo é decisão do proprietário: aceitar os 20 meses negativos como característica do
sistema, ou arriscar mudar a própria lógica de entrada (descongelando o comparador, o que exige
disciplina extra) — o Caso 5 (Colheita Rápida), a primeira ideia desta rodada que mudava a
**entrada** em vez da saída ou do tamanho, também rodou nativamente e também foi **rejeitado**
(§4): piorou ainda mais esse número (32/57). O Caso 9 (§3.5), pedido em seguida, tenta a mesma
frente por outro ângulo — filtrar as entradas do Caso 1/4 em vez de substituí-las — mas ainda não
tem backtest nativo.

### 3.5 Caso 9 — Caso 4 + filtro de cruzamento EMA5/21

**Por quê.** Pedido do proprietário, depois de ver que os 20 meses negativos resistiram a 3
mecanismos de sizing e 2 de gestão de trade: tentar melhorar a **qualidade da entrada** em si,
exigindo uma confirmação extra de momentum de curto prazo — um cruzamento recente da EMA5 acima
(compra) ou abaixo (venda) da EMA21 — além de tudo que a entrada original do Caso 1/4 já exige.

**Diferente dos Casos 6/7/8, isto é lógica genuinamente nova**, não um motor dormente do R200
sendo configurado. `EMACrossCore.mqh` é uma função pura nova (`EMACrossGate`), testada
isoladamente (`tests/test_ema_cross.cpp`) — a mesma disciplina do Caso 5 (`QuickHarvestCore.mqh`).

**Mecanismo.** Na barra de sinal fechada, com o lado (compra/venda) já decidido pela entrada
original: a EMA5 precisa estar do lado certo da EMA21 **agora** (>21 na compra, <21 na venda) **e**
ter estado do lado oposto em alguma das `InpEMACrossLookback` barras fechadas anteriores (padrão
3) — ou seja, o cruzamento aconteceu de fato dentro da janela, não é só um alinhamento antigo e
estático (o que não seria um "cruzamento"). Só **filtra** o lado que a entrada original já
escolheu — nunca decide o lado sozinho, nunca abre posição sem a entrada original também ter
disparado.

**Mudanças (arquivos/linhas):**
- `src/EMACrossCore.mqh` (**novo**): `EMACrossGate(side, ema5[], ema21[], n, sideOut)`, pura,
  testada em `tests/test_ema_cross.cpp` (compra, venda, alinhamento antigo sem cruzar, desalinhado
  agora, borda da janela, toque exato, lado/janela/dados inválidos).
- `src/EA.mq5`: novo input `InpEMACrossLookback` (padrão 3); novo handle `hEMA5` (EMA de 5
  períodos, só criado quando `InpCase==9`); `ReadEMACross` lê EMA5/EMA21 das últimas
  `lookback+1` barras fechadas; no `OnTick`, logo após a entrada original decidir `side`/`setup`,
  se `InpCase==9` e a entrada original já teria disparado (`setup==0`), o resultado do
  `EMACrossGate` pode **vetar** esse sinal (nunca inverter o lado nem criar um novo).
- `src/PivotEntryCore.mqh`: roteamento aceita `id` até 9, mesma entrada/rota do Caso 1/4
  (`HP_DISABLED`, sem pivô) — o filtro EMA não faz parte do roteamento, é uma camada extra no
  `OnTick`, fora do escopo do `HPRouteEntry`.
- Corrigido de passagem (não é um bug do Caso 9, mas apareceu ao mexer nestas linhas): o
  `target_value`/`target_R` exportados em `parameters.txt` e as colunas equivalentes em
  `bars.csv` estavam hardcoded em "5" mesmo para o Caso 8 (alvo real 3R) — `EA.mq5` não é
  arquivo congelado, então corrigi para refletir o alvo nominal real de cada Caso. **Não** mexi
  no mesmo problema em `summary.csv` (`nominal_target_R`/`target_value` via `Reports.mqh`, que
  É congelado) — ver §5, item 4, ainda pendente de resposta do proprietário.

**Só filtra — nenhuma entrada nova é criada, nenhuma saída é alterada.** `HPSelectProfile`/
`HPRouteEntry` tratam o Caso 9 exatamente como o Caso 4 (mesma rota, `HP_DISABLED`, sem pivô);
dentro do `OpenCycle`, o Caso 9 é **idêntico** ao Caso 4 em tudo (sizing, alvo 5R, sem breakeven)
— testado explicitamente em `tests/test_entry.cpp`. O filtro só decide, no `OnTick`, **se** aquele
sinal chega a `OpenCycle` — nunca o que acontece depois que chega.

**Preset:** `presets/CASO_09_HERMES_CRUZAMENTO_EMA.set` — `InpCase=9`, resto nos padrões
compartilhados (`InpRiskPercent=1.0`, igual ao `CASO_04_HERMES_RISCO_REF.set`) — comparação
direta contra o Caso 4 no seu preset mais simples, risco-base baixo, focada em **qualidade da
entrada**, não em composição/risco.

**Previsão falsificável.** Menos trades que o Caso 4 (o filtro só remove sinais, nunca adiciona).
Se o filtro realmente separa sinais melhores dos piores, a taxa de acerto e/ou o
`average_net_R_initial` devem subir, e — o teste que importa — `negative_booked_months` deve cair
de forma material frente aos 19-20/57 do resto da família. **Rejeite** se `negative_booked_months`
não melhorar, ou se o número de trades cair tanto (por ex. abaixo de ~80-100 em 57 meses) que a
amostra fique pequena demais para qualquer conclusão.

**A janela de 3 barras é a primeira hipótese, não um resultado provado.** Se o primeiro teste não
convencer (poucos trades, ou sem melhora em `negative_booked_months`), ajustar
`InpEMACrossLookback` é experimento novo — uma variável de cada vez, contra o mesmo comparador
(Caso 4), nunca uma varredura cega de janelas.

**Resultado real (backtest do proprietário, `CASO_09_HERMES_CRUZAMENTO_EMA.set`, US$ 10.000):**

| Métrica | Caso 1 (mesma entrada base) | Caso 9 |
| --- | --- | --- |
| Trades | 260 | **100** |
| Taxa de acerto | 25,38% | 27,00% |
| `average_net_R_initial` | 0,443 | **0,545** |
| Perdas seguidas (máx.) | 13 | **11** |
| Meses sem nenhum trade | 3/57 | **12/57** |
| `negative_booked_months` | 19/57 | **22/57** |
| Negativo entre meses **ativos** (com trade) | 19/54 = 35,2% | **22/45 = 48,9%** |

**Hipótese REJEITADA pelo critério pré-registrado.** `negative_booked_months` não caiu — **piorou**
(22 contra 19, e contra os ~20/57 do resto da família Caso 4/6/7). O número absoluto já bastaria
para rejeitar, mas o que importa entender é *por quê*: o filtro cortou 61% dos trades (260→100),
deixando **12 meses sem nenhuma operação** (contra só 3 no Caso 1). Nos 45 meses em que o Caso 9
realmente operou, **quase metade (48,9%) terminou negativa** — bem pior que a taxa do Caso 1 nos
seus 54 meses ativos (35,2%). O filtro não separou meses ruins de bons; piorou a proporção.

**O "engano" que esse resultado quase causou.** Olhado isoladamente pelo resumo nativo do
Testador (Fator de Lucro 1,77, DD relativo 13,39%, taxa de acerto 27%), o Caso 9 parece uma
melhoria sobre o Caso 4 a 1% (DD 16,63%) — e de fato, **as médias por trade melhoraram**:
`average_net_R_initial` subiu de 0,443 para 0,545, perdas seguidas caíram de 13 para 11. É
exatamente por isso que fixamos `negative_booked_months` como critério **antes** de rodar:
métricas agregadas por trade podem melhorar enquanto a consistência mês a mês piora — os trades
que sobraram do filtro ainda se agrupam nos mesmos períodos ruins, só que agora há menos trades
bons nos outros meses para compensar.

**Bate com a análise de trades em meses negativos vs. positivos** (do Caso 1, ver mensagem
anterior a este resultado): nenhuma feature estática de entrada (ADX, ATR, inclinação da SMA200,
distância) separava trade de mês bom de trade de mês ruim. Um filtro construído sobre outra
feature estática (cruzamento de EMA5/21) reproduziu exatamente esse padrão — melhora o trade
médio, não melhora (piora) a consistência mensal. Reforça a hipótese de que os meses negativos são
sequências de perdas correlacionadas no tempo, não trades individualmente identificáveis de
antemão pelas features hoje disponíveis.

Com isso, **6 mecanismos diferentes** já testados com dados reais (Caso 4 sizing, Caso 6 freio,
Caso 7 saque, Caso 8 breakeven×2, Caso 5 entrada nova, Caso 9 filtro de entrada) — nenhum reduziu
`negative_booked_months` abaixo do que o próprio Caso 1 (sem nenhuma modificação) já tinha.

---

## 4. Caso 5 — Colheita Rápida (a nova filosofia)

**Ideia.** Numa barra M30 de **alta participação** (surto de tick volume + barra ampla) dentro
de uma tendência curta de alta, entrar, mirar um **alvo pequeno em R** e **sair rápido**.
Objetivo: ganhos menores e mais frequentes, com **risco normalizado**, para não depender de um
movimento gigante do ouro.

**Regras exatas (tudo disponível no fechamento da barra de sinal, shift 1):**
1. Tendência curta: `EMA21 > SMA50` e `Close > EMA21`.
2. Força/direção: `ADX14 ≥ InpQHMinADX` e `+DI > −DI`.
3. Gatilho: barra de alta (`Close > Open`).
4. **Surto de volume:** `tick_volume[1] ≥ InpQHVolFactor × média(tick_volume, 20)`.
5. **Barra ampla:** `(High−Low)/ATR ≥ InpQHRangeFactor`.
6. **Fechou forte:** `(Close−Low)/(High−Low) ≥ InpQHMinCloseLoc`.
7. Impulso mínimo: `Ask − EMA21 ≥ InpMinEntryATR × ATR`.
8. **Guarda de custo (obrigatória):** `Ask − Bid ≤ InpQHMaxSpreadATR × ATR`.

**Stop e alvo:** stop estrutural das 3 velas (reaproveita `H1Levels`, o mesmo do R200); alvo
curto = `InpQHTargetR` × risco (padrão **1R**). Sizing por risco (`InpRiskPercent`).

**Mudanças (arquivos):**
- `src/QuickHarvestCore.mqh` (**novo**): função pura `QHGate(...)` com as 8 condições acima.
  Testada em `tests/test_quickharvest.cpp`.
- `src/EA.mq5`: `#include` do novo core; `ReadQuickHarvest` (lê tick volume das 21 barras);
  ramo do `OnTick` que roteia o Caso 5; alvo curto no `OpenCycle` via `InpQHTargetR`; novos
  inputs `InpQH*`; validação no `OnInit`.

**Parâmetros (inputs) e padrões:**
`InpQHTargetR=1.0`, `InpQHVolFactor=1.5`, `InpQHRangeFactor=1.0`, `InpQHMinCloseLoc=0.6`,
`InpQHMinADX=20`, `InpQHMaxSpreadATR=0.10`, `InpRiskPercent=1.0`. São os botões de pesquisa.

**Previsão falsificável.** Comparado ao Caso 1: acerto maior, tempo em posição menor, menos
dependência de tendência longa. **Rejeite** se, **com custos realistas**, a expectância por
trade for ≤ 0 ou o fator de lucro < 1,2.

**Resultado real (backtest do proprietário, mesmo preset, US$ 10.000, XAUUSD M30):**

| Métrica | Previsto | Real |
| --- | --- | --- |
| Taxa de acerto | maior que 26,05% | **50,80%** — confirmado |
| Tempo em posição | menor | **6,76h em média** — confirmado (dezenas/centenas de horas no resto da família) |
| Fator de Lucro (custos reais) | ≥ 1,2 para aceitar | **0,98** |
| Lucro líquido | — | **-357,58** (prejuízo) |
| `average_net_R_initial` | — | **0,00051** (expectância ≈ zero) |
| `negative_booked_months` | — | **32/57** — pior de toda a família testada |

**Hipótese REJEITADA, pelo próprio critério definido antes de rodar** (Fator de Lucro 0,98 <
1,2). Duas partes da previsão até se confirmaram — acerto bem maior, tempo em posição bem menor
— mas isso não bastou: **taxa de acerto não é a mesma coisa que sistema lucrativo**. O alvo
original de 5R só precisa de ~17% de acerto para empatar (1/(1+5)); o alvo curto de 1R precisa
de **50%** (1/(1+1)) só para ficar no zero a zero — e o filtro de surto de volume entregou
exatamente 50,80%, em cima da linha de empate, que os custos reais (sobretudo swap: -488 no
total) empurraram para o lado negativo.

**O lado bom, real:** o pior mês individual nunca passou de 6,41% de DD
(`maximum_monthly_DD_percent`) — de longe o mais baixo de qualquer caso testado (Caso 4 a 1% já
tinha 16,63%) — e a sequência de perdas máxima caiu para 8 (era 13–24 no resto da família). O
problema não é risco de ruína — é que **56% dos meses (32/57) fecham no vermelho**, ainda que
cada um seja pequeno: perdas pequenas e frequentes demais para as vitórias pequenas compensarem,
empatando (e com custo, perdendo) no agregado.

**Nota sobre o `summary.csv`:** os campos `nominal_target_R` e `target_value` aparecem como "5"
mesmo aqui, apesar do alvo real configurado ser 1R — ver aviso 4 em §5. Não afeta nenhum outro
número deste resultado; o alvo realmente usado é confirmado por `mean_winner_MFE_R` = 1,01
(bem próximo de 1R, como configurado) e pelas checagens internas de reconciliação do próprio EA,
que vieram todas em zero.

---

## 5. AVISOS CRÍTICOS (leia antes de acreditar em qualquer resultado do Caso 5)

1. **CUSTO É TUDO num alvo curto.** Spread + comissão + slippage podem comer todo o edge. O
   backtest do R200 rodou com **comissão zero** e spread embutido — isso **superestima** um
   scalp. **Rode o Caso 5 com comissão e spread realistas da sua corretora**, senão o
   resultado é ficção. A guarda `InpQHMaxSpreadATR` ajuda, mas não substitui custos reais.
2. **"Volume" aqui é TICK VOLUME**, não volume real (XAUUSD CFD normalmente não tem volume
   real). Tick volume depende do **modo de modelagem** do Testador ("Every tick"/"real ticks").
   Rode com "Every tick based on real ticks" quando possível e registre o modo.
3. **"Ganhar todos os dias" não existe.** O objetivo alcançável é *mais consistência e menos
   dependência do ouro subir* — não zero perdas. Perdas e dias/meses negativos continuarão
   ocorrendo; a meta é que sejam **pequenos e controlados** (é o que o sizing por risco faz).
4. **Os campos `nominal_target_R` e `target_value` do `summary.csv` sempre mostram "5"**, mesmo
   nos Casos 5 (alvo real 1R) e 8 (alvo real 3R). É herança do R200: essas duas linhas, dentro do
   `Reports.mqh` **congelado**, calculam o alvo nominal a partir de `dc.targetMode` — um campo que
   nunca varia (fica sempre 0) em nenhum Caso do R210 — em vez de olhar `InpQHTargetR`/
   `InpBETargetR`. No R200 isso nunca foi um problema porque o alvo era sempre 5R mesmo. **Não
   afeta nenhum outro número do relatório** — lucro, DD, taxa de acerto, trades e
   `negative_booked_months` são todos calculados de outro jeito e conferidos automaticamente
   pelo próprio EA (os campos `*_reconcile_*` vêm em zero quando bate). Para confirmar o alvo
   realmente usado num backtest, olhe `mean_winner_MFE_R` — esse sim reflete o R real dos
   ganhadores (deu 1,01 no Caso 5, 3,02 no Caso 8). Corrigir essas duas linhas é simples e não
   mudaria nenhuma decisão de trade — mas exigiria tocar o único arquivo que provei, com um teste
   automatizado, permanecer byte-idêntico ao R200 durante todo o projeto. Prefiro perguntar antes
   de quebrar essa garantia; me avise se quiser que eu corrija.

---

## 6. Como compilar e rodar (MetaEditor + MT5)

1. `cd hermes_r210 && python3 build.py` → gera `Hermes_R210.mq5` (arquivo único) e os presets.
2. Copie `Hermes_R210.mq5` para `MQL5/Experts/` e **compile no MetaEditor** (F7). O EA exige
   Testador (`OnInit` bloqueia uso fora do Strategy Tester).
3. No Testador: XAUUSD, M30, período desejado, **modelagem por ticks reais**, **custos reais**.
4. Carregue um preset de `presets/` (ex.: `CASO_04_...`, `CASO_05_...`, `CASO_06_...`,
   `CASO_07_...`, `CASO_08_...`, `CASO_09_...`) ou ajuste `InpCase`.
5. Exporte os CSVs (bars/events + agregados) como no R200 para comparar.

Checagem local sem MT5: `python3 verificar.py` (compila e roda os 12 testes portáveis em g++ e
prova que os cores do R200 não foram tocados).

---

## 7. Protocolo de validação (obrigatório antes de qualquer conclusão)

1. **Caso 1 no R210 = Caso 1 no R200** (mesmo lucro/trades). Se divergir, pare e me avise.
2. **Caso 4 vs Caso 1** na mesma janela: comparar DD relativo, DD em dinheiro, fator de lucro
   e **desvio-padrão do retorno mensal**.
3. **Caso 5 com custos realistas**: expectância por trade e fator de lucro **após custos**.
4. **Caso 6 vs Caso 4 (mesmo risco-base, 5%)**: DD máximo precisa cair de forma material sem
   devolver o lucro a algo próximo do risco 2% sozinho (§3.2). Testar bandas/multiplicadores
   diferentes é experimento novo, um de cada vez — nunca uma varredura simultânea.
5. **Caso 7 vs Caso 4 (mesmo risco-base, 5%)**: o capital sacado acumulado precisa ser grande o
   suficiente para justificar o lucro menor, e o drawdown sobre o que resta em risco precisa
   melhorar de forma clara (§3.3).
6. **Caso 8 vs Caso 4 (mesmo risco-base, 5%)**: `cycle_win_percent` precisa subir de forma clara
   frente aos 26,05% históricos, e `negative_booked_months` precisa cair de forma material frente
   aos 20/57 medidos em todo o resto da família (Casos 4/6/7) — senão o alvo menor só trocou
   ganho por ganho, sem resolver o problema que motivou o caso (§3.4).
7. **Caso 9 vs Caso 4 (mesmo risco-base, 1%)**: menos trades (o filtro só remove sinais), e
   `negative_booked_months` precisa cair de forma material — senão o filtro só descartou sinais
   ao acaso, sem separar os bons dos ruins (§3.5).
8. **Fora da amostra:** walk-forward + uma janela final nunca usada na escolha + teste num
   período do ouro que **não** foi bull market (ex.: 2013–2019).
9. **Forward em DEMO** antes de qualquer real. Depois, micro-real com risco baixo.

Detalhe do raciocínio e das previsões em `../docs/PLANO_EXPERIMENTOS.md` e no parecer
`../docs/PARECER_CLAUDE_R200.md`.

---

## 8. Reinvestir 50% do lucro e aumentar o lote proporcionalmente — vale a pena?

Pergunta do proprietário. Resposta curta: **o Caso 4 já reinveste** (é isso que "sizing por
risco" significa); a ideia de "reinvestir 50% e crescer o lote" é um mecanismo **diferente e
mais arriscado**, e ele **já existe, pronto, no motor** — só nunca foi ligado nos casos
Hermes. Não ativei nada sozinho; aqui está o raciocínio para decidir.

**O Caso 4 (risco %) já é reinvestimento.** `volume = (risco% × Equity) / perda-por-lote`. Se o
patrimônio dobra, o lote dobra — automaticamente, todo trade, sem outro mecanismo. É a forma
de reinvestimento matematicamente mais estudada em gestão de risco (fixed-fractional / aparentado
a Kelly): o risco **por trade** fica constante, medido pela distância do stop (ATR), não pelo
tamanho da conta sozinho.

**O que você descreveu é outra coisa: escalar o lote pelo LUCRO acumulado, não pelo risco do
trade.** Isso já está implementado — código legado, testado, **nunca ativado** em nenhum
Caso Hermes (`p.reinvest` é sempre `false` nos 9 casos R210):

- `src/ProtectCore.mqh:144` · `PEReinvestLot(base, deposit, balance, cap, step)` — usa
  **exatamente 50%** fixo: `efetivo = base × (1 + 0,5 × max(0, balance−deposit)/deposit)`.
- `src/EntryCore.mqh:45` · `EVOCapitalLot(base, deposit, balance, fraction, cap, step)` — a
  mesma ideia, com `fraction` configurável (0%, 50%, 75% ou 100% nos perfis legados).

**Por que eu NÃO ligaria isso junto com o Caso 4 (os dois ao mesmo tempo):**

1. **Dupla composição = risco real maior que o configurado.** No Caso 4, o risco por trade já
   cresce com o patrimônio (via `Equity`). Se você *também* multiplica o lote pelo lucro
   acumulado, está compondo **duas vezes** — o risco efetivo por trade sobe silenciosamente
   acima do `InpRiskPercent` que você escolheu, sem um número claro te avisando disso.
2. **Amplia exatamente onde o sistema é mais frágil.** O robô já teve **13 perdas seguidas**.
   Reinvestir sobre o pico de lucro significa que o lote fica **maior** logo depois de uma
   sequência boa — que é precisamente quando, estatisticamente, uma sequência ruim tem mais
   chance de vir a seguir (reversão à média). É compor exposição no pior momento relativo.
3. **Fica mais difícil de raciocinar sobre risco.** Com o Caso 4 sozinho, "quanto posso
   perder numa sequência de N perdas" é uma conta simples (`1-(1-risco%)^N`). Somando um
   segundo fator de crescimento por lucro acumulado, essa conta deixa de ser direta — você
   perde a legibilidade que é o ponto principal do sizing por risco.

**Minha recomendação:** fique com o Caso 4 (risco % puro) como o mecanismo de "reinvestimento".
Se mesmo assim você quiser **medir** a ideia do lucro-acumulado como hipótese separada — nunca
empilhada com o Caso 4 —, eu implemento um **Caso 10 isolado** (`PEReinvestLot`/`EVOCapitalLot`,
já testados no motor) com **sizing fixo simples** (sem risco%), seguindo o mesmo protocolo:
comparador preservado, previsão falsificável, validação fora da amostra. Me avise se quiser
que eu construa esse Caso 10.

> **Nota:** os números "Caso 6", "Caso 7", "Caso 8" e "Caso 9" citados em versões anteriores
> deste documento acabaram sendo usados para o freio de risco por rebaixamento (§3.2), o saque
> de lucro (§3.3), o breakeven+alvo 3R (§3.4) e o filtro de cruzamento EMA5/21 (§3.5), todos
> pedidos depois desta seção. Se a ideia de lucro-acumulado acima for implementada, ela vira
> **Caso 10** — os números dos casos nunca são reciclados depois de existirem presets/testes
> referenciando-os.

## 9. Mapa de mudanças

| Arquivo | Estado | O quê |
| --- | --- | --- |
| `src/XAU_H1_Core.mqh`, `ProtectCore`, `EntryCore`, `DonchianCore`, `HermesCore`, `Execution`, `PivotCore`, `PivotRuntime`, `Reports` | **byte-idêntico ao R200** | motor auditado, intocado (inclui o motor de breakeven do Caso 8 — só configuração nova, zero linhas mudadas) |
| `src/PivotEntryCore.mqh` | alterado | roteamento aceita Casos 4/5/6/7/8/9 (sizing por risco; Casos 8/9 usam a mesma rota do Caso 4) |
| `src/EA.mq5` | alterado | inputs novos, `ReadQuickHarvest`, ramo do Caso 5, freio do Caso 6, saque do Caso 7, `profile.be15`+alvo curto do Caso 8, `ReadEMACross`+filtro do Caso 9, validações; corrigido de passagem: `target_value`/`target_R` em `parameters.txt`/`bars.csv` (não em `Reports.mqh`, que é congelado) agora refletem o alvo real do Caso 5/8 em vez de sempre "5" |
| `src/QuickHarvestCore.mqh` | novo | decisão do Caso 5 (`QHGate`), pura e testada |
| `src/DDThrottleCore.mqh` | novo | freio do Caso 6 (`DDThrottleMultiplier`), pura e testada |
| `src/WithdrawalCore.mqh` | novo | saque do Caso 7 (`WDUpdate`/`WDTradingCapital`), pura e testada |
| `src/EMACrossCore.mqh` | **novo** | filtro do Caso 9 (`EMACrossGate`), pura e testada — lógica de entrada genuinamente nova, não configuração de motor existente |
| `tests/test_quickharvest.cpp` | novo | testa `QHGate` |
| `tests/test_dd_throttle.cpp` | novo | testa `DDThrottleMultiplier` (bandas, dados/config inválidos) |
| `tests/test_withdrawal.cpp` | novo | testa `WDUpdate`/`WDTradingCapital` (recordes, acúmulo, frações-limite, piso em zero) |
| `tests/test_ema_cross.cpp` | **novo** | testa `EMACrossGate` (compra/venda, alinhamento antigo sem cruzar, desalinhado agora, borda da janela, toque exato, lado/janela/dados inválidos) |
| `tests/test_entry.cpp` | atualizado | Caso 4 imune a `ddPeakEquity`/`withdrawState`/`profile.be15`; Casos 6/7 reduzem o risco corretamente; Caso 8 confirma alvo 3R (`tp=4042,8`) e `beTrigger` propagado; Caso 9 confirma `OpenCycle` idêntico ao Caso 4 (o filtro vive fora do `OpenCycle`, no `OnTick`) |
| `tests/test_pivot_entry.cpp` | atualizado | agora valida Casos 4/5/6/7/8/9 |
| `build.py`, `verificar.py` | adaptados | 9 casos, 12 presets; prova cores congelados (Caso 9 adiciona `EMACrossCore.mqh`; Caso 8 não adicionou `.mqh` — reusa `Execution.mqh` congelado) |
| `presets/CASO_04_*`, `CASO_05_*`, `CASO_06_*`, `CASO_06B_*`, `CASO_07_*`, `CASO_08_*`, `CASO_09_*`, `00_COMPARAR_9_CASOS` | novos | presets dos casos novos |

**Peço ao ChatGPT:** compilar no MetaEditor; confirmar que os Casos 1–3 reproduzem o R200;
rodar Caso 4 (risco 1%), Caso 5 (**com custos reais**), Caso 6 (risco 5% + freio), Caso 7
(risco 5% + saque), Caso 8 (risco 5% + breakeven em 1R + alvo 3R) e Caso 9 (risco 1% + filtro de
cruzamento EMA5/21), comparando os últimos quatro contra a linha "5%" da tabela em §3.1 ou contra
o `CASO_04_HERMES_RISCO_REF.set` (Caso 9, mesmo risco-base baixo); devolver os CSVs para eu
analisar regime, custo de ocupação e a fronteira risco×retorno.
