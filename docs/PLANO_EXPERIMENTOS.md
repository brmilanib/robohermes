# Plano de experimentos — Hermes R200 → R210

Três experimentos, no máximo, como pede o §12.5 do dossiê: **novos, diferentes, isolados e
falsificáveis**. Cada um traz mecanismo, regras exatas, informação disponível **no momento da
entrada**, previsão falsificável e critério de rejeição. Nenhum deles é "filtro escolhido por
coincidir com meses negativos conhecidos".

**Regra de ouro:** o **Caso 1 (Referência) permanece intocado** como comparador. Cada
experimento muda **uma coisa** e vira um **caso próprio**. Nada é declarado "melhoria" antes de
passar na validação fora da amostra (§4).

Ordem de prioridade e porquê:

| Prioridade | Experimento | Ataca | Custo de implementação |
| --- | --- | --- | --- |
| **1** | Sizing por risco (Caso 4) | Drawdown / alavancagem (o risco real) | **Baixo** — motor já existe |
| 2 | Robustez de regime | Overfitting / dependência de 2024–2026 | Médio — precisa de `cycles.csv` |
| 3 | Diagnóstico de saída (MFE sem teto) | Saber se 5R é ótimo (potencial de lucro) | Médio — uma rodada diagnóstica |

---

## Experimento 1 — Dimensionamento por risco (Caso 4) · PRIORIDADE MÁXIMA

**Mecanismo.** Com lote fixo, o risco por trade varia de ~2% a ~15% do patrimônio e o P&L em
dólares vira função do nível/volatilidade do ouro (ver Parecer §4). Dimensionar cada trade a
uma **fração fixa do patrimônio** normaliza o risco: o drawdown passa a ser **governado por
você**, não pelo regime do ouro. **Não muda nenhuma regra de entrada, stop ou alvo.**

**Regras exatas.**
- Entradas, stop (3 velas −0,20 ATR, 1–2,5 ATR) e alvo (5R) **idênticos ao Caso 1**.
- Volume por trade = `floor( (risco% × Equity) / (perda_em_$_por_lote_no_stop) / passo ) ×
  passo`, respeitando mín./máx./margem nativa. **Sem** forçar mínimo, **sem** reduzir às
  cegas — exatamente como o motor já faz.
- Parâmetro primário **pré-declarado: risco = 1,0% do patrimônio por trade.** Grade mínima
  auxiliar só para sensibilidade: {0,5% ; 1,0% ; 2,0%} — com **1,0% declarado como o caso**,
  os outros dois apenas para desenhar a fronteira risco×retorno (não para "escolher o melhor
  a posteriori").

**Informação usada na entrada:** patrimônio atual, distância do stop (já calculada antes da
ordem), specs do contrato. Tudo causal; nenhum dado futuro.

**Previsão falsificável.** Em relação ao Caso 1, o Caso 4 (a 1%):
- reduz o **DD relativo** de ~43% para a faixa de ~10–15% (a 1% de risco, uma sequência de 13
  perdas ≈ −13%);
- reduz a **dispersão** do retorno mensal em % (meses ruins viram pequenos e controlados);
- o retorno passa a **compor** — o CAGR pode ficar **menor** que os +143%/ano _in-sample_, e
  **isso é esperado e desejável**.

**Critério de rejeição.** Rejeite o Caso 4 se, na **mesma** janela, o DD relativo **não** cair
de forma material **ou** a curva de patrimônio ficar mais errática (maior dispersão mensal). Se
cair o DD sem destruir o fator de lucro (que deve ficar ~2,0, pois as entradas são as mesmas),
o experimento **passa a fase 1** e vai para validação OOS (§4).

**Por que é o nº 1:** ataca o único problema que pode te tirar do jogo (drawdown/alavancagem),
reusa código já testado e é isolado. Detalhes de implementação na **§5** deste documento.

---

## Experimento 2 — Robustez de regime (medir antes de filtrar)

**Mecanismo.** O edge pode ser condicional ao regime (tendência/volatilidade do ouro). Em vez
de adicionar um filtro ajustado à história, **meça** se uma variável de regime **pré-entrada**
separa vencedores de perdedores **de forma estável em subperíodos disjuntos**.

**Regras exatas (é análise primeiro, filtro só depois).**
- Variáveis candidatas, **todas já gravadas por ciclo** em `EA.mq5:474-475`:
  `featureSlope=(SMA200−oldSMA200)/ATR` (inclinação do longo prazo normalizada),
  `featureADX`, `featureADXChange`, `featureDistance=(entry−EMA)/ATR`.
- Divida a amostra em **dois blocos cronológicos disjuntos**: A = 2022-01…2023-12, B =
  2024-01…2026-08. Em cada bloco, agrupe os trades do Caso 1 em quartis de cada variável e
  calcule o **R médio por quartil**.

**Informação usada na entrada:** todas as variáveis são conhecidas na barra de decisão.

**Previsão falsificável.** Se a variável for um regime real, o **ranking dos quartis por R
médio é o mesmo (monotônico) em A e em B**. Ex.: se "inclinação alta da SMA200" tem R médio
maior, isso vale nos dois blocos.

**Critério de rejeição.** Se o ranking **inverter** entre A e B (o que é bom em 2022–2023 é
ruim em 2024–2026), a variável **não** é regime estável — **proibido** transformá-la em filtro.
Só promova a filtro (num Caso próprio) a variável cujo ranking se mantém **e** que sobrevive à
validação OOS.

**Por que importa:** é o teste que distingue "edge" de "beta do bull market do ouro". Sem ele,
qualquer ganho novo é suspeito.

**Dado faltante:** `cycles.csv` por caso (com `feature*` e R realizado). É o insumo nº 1 da
lista do Parecer §7.

---

## Experimento 3 — Diagnóstico de saída (o teto de 5R esconde informação)

**Mecanismo.** Hoje `mean_winner_MFE_R = 5,00`: o TP em 5R **corta** a observação, então é
**impossível** saber se os vencedores iriam além. Antes de decidir qualquer coisa sobre saída,
é preciso **observar** a excursão favorável real (MFE) sem o teto.

**Regras exatas (rodada diagnóstica, não uma nova estratégia).**
- Caso diagnóstico = Caso 1 com **TP removido** (ou TP em 20R, efetivamente sem teto), saindo
  **apenas** por stop estrutural. Entradas idênticas. Objetivo: **registrar a distribuição de
  MFE em R** de todos os trades (vencedores e perdedores).
- Isto **não** é para operar — é para **medir**. Não escolha o alvo que maximiza o lucro
  passado.

**Informação usada na entrada:** nenhuma nova; é medição pós-fato do caminho do preço (MFE),
usada só para desenhar a decisão de saída, **nunca** como filtro de entrada.

**Previsão falsificável (para a decisão que vier depois).** Se a MFE dos vencedores se
concentrar bem acima de 5R, um **trailing por ATR** (ex.: armado em +2R, trilha de 3×ATR)
tende a aumentar o R médio dos vencedores **sem** aumentar o DD. Se a MFE se concentrar **em
torno de 5R**, o alvo atual já é adequado e **nada muda**.

**Critério de rejeição.** Qualquer alternativa de saída (trailing, alvo maior, ou o
**stop-em-F1** da §2.2[A] do Parecer) só é aceita se, **fora da amostra**, melhorar fator de
lucro **sem** piorar o DD. Caso contrário, mantém-se o 5R fixo.

**Observação sobre sua preferência:** você prefere não fracionar alvos curtos — respeitado.
Trailing e BE **não** são parciais; são regras de saída única. Ainda assim, cada um vira um
caso isolado e passa pela mesma validação.

---

## 4. Protocolo de validação (vale para TODOS os experimentos)

Um ganho na janela 2022–2026 **não prova nada** — ela já foi vista muitas vezes. A ordem é:

1. **Correção de código.** Rode os testes portáveis em `projeto_fonte/tests/`. Registre hash
   do `.mq5`, do `.ex5`, do preset e do relatório nativo. (Fecha auditoria A01/A02.)
2. **Reprodução.** Reproduza o Caso 1 (204.912,54 / 261 trades) no mesmo histórico/preset.
3. **Walk-forward.** Otimize (se houver algo a otimizar, como o risco% do Exp. 1) só em
   janelas passadas e valide na janela seguinte, andando no tempo. Reporte a **degradação**
   entre in-sample e out-of-sample.
4. **Hold-out cronológico.** Congele uma janela final (ex.: 2025-07…2026-08) que **nunca**
   entrou em nenhuma escolha e meça ali.
5. **Robustez cruzada.** Teste o mesmo EA em (a) outro período histórico do ouro (2013–2019,
   que **não** foi bull market), (b) opcionalmente outro ativo correlato. Se o edge só existe
   em 2020+, é regime, não edge.
6. **Forward em DEMO.** Rode em conta DEMO com dados ao vivo por semanas/meses **antes** de
   qualquer real. O EA hoje exige `MQL_TESTER` (`OnInit`) — para forward, isso precisa ser
   liberado conscientemente e com o hash registrado.
7. **Micro-real.** Só depois, capital pequeno, sizing por risco baixo, com o entendimento de
   que **drawdowns de 10–20% são normais**.

Uma mudança só é "melhoria confirmada" quando sobrevive a 3–6. Antes disso, é hipótese.

---

## 5. Especificação de implementação do Caso 4 (para o ChatGPT)

**Fato-chave:** o dimensionamento por risco **já está implementado e testado** no EA. Os casos
R200 apenas o mantêm desligado. Não é código novo de estratégia — é ativar um caminho
existente para um novo `InpCase`.

### 5.1 Onde o motor já vive

- `XAU_H1_Core.mqh:70-84` — `H1Volume(PERCENT_RISK, ...)`: modo de risco por orçamento.
- `DonchianCore.mqh:62` — `DCRiskLot(equity, free, used, riskPercent, marginPercent,
  lossPerLot, marginPerLot, min, max, step, hardLotCap)`: calcula o lote pelo orçamento de
  risco **e** de margem, com o teto `riskPercent ≤ 2,0`.
- `DonchianCore.mqh:4-14` — `DCProfile{ fixedLot, riskPercent, minimumStopATR }` e
  `DCSelectProfile`: para `id=1`, já produz `fixedLot=false, riskPercent=2.0`; para `id∈{2,3,4}`,
  `fixedLot=true`.
- `EA.mq5:406-445` — `OpenCycle`: o ramo `if(dc.fixedLot)` usa lote exato; o **`else`
  (linhas 413-434)** é o **caminho de risco completo**: `OrderCalcProfit`/`OrderCalcMargin`,
  `sizingRiskBudget=eq*dc.riskPercent/100`, revalidação de margem em tiers, sem forçar mínimo.

### 5.2 O gargalo que prende tudo em lote fixo

`PivotEntryCore.mqh:14-22` — `HPSelectProfile(id, ...)` chama **`DCSelectProfile(2, d,e,p)`**
para **todos** os casos R200. Como `id=2` → `fixedLot=true`, os três casos são lote fixo. É
por aqui que o Caso 4 entra.

### 5.3 Mudança proposta (mínima, isolada) — pontos exatos a tocar

O Caso 4 é "Referência (entradas do Caso 1) com sizing por risco". O truque é que o perfil de
risco **já existe**: `DCSelectProfile(1, ...)` produz `fixedLot=false, riskPercent=2.0,
targetMode=0` (5R), enquanto `DCSelectProfile(2, ...)` — usado hoje por **todos** os casos —
produz `fixedLot=true`. Então "ativar risco" = rotear o Caso 4 pelo perfil DC de id 1 e ajustar
o percentual. É preciso admitir `id==4` nas travas que hoje param em 3 e **relaxar o guard que
exige lote fixo**:

1. **`HPSelectProfile` (`PivotEntryCore.mqh:14-22`).**
   - Linha 16: `if(id<1 || id>3 || !DCSelectProfile(2,d,e,p))` → admitir `id==4` e, para ele,
     chamar `DCSelectProfile(1, ...)` (perfil de risco). Casos 1–3 continuam em `DCSelectProfile(2)`.
   - Linhas 19-21: o `return` **exige `d.fixedLot`**. Para o Caso 4, esse guard tem de aceitar
     `!d.fixedLot` (ex.: `((id==4 && !d.fixedLot) || (id!=4 && d.fixedLot))`). Manter todas as
     demais asserções (`targetMode==0`, `entryPolicy==0`, `family==15`, sem parcial/BE/add/reinvest).
2. **`HPExtraGate` (`PivotEntryCore.mqh:23-40`).**
   - Linha 27: `if(id<1 || id>3) return HP_INVALID_CASE;` → `id>4`.
   - Linha 28: `if(id==1) return HP_DISABLED;` → `if(id==1 || id==4) return HP_DISABLED;`
     (Caso 4 **não** usa rota de pivô — entradas idênticas ao Caso 1).
3. **`HPRouteEntry` (`PivotEntryCore.mqh:49`).** `if(id<1 || id>3)` → `id>4`.
4. **Percentual de risco como input novo.** Ex.: `input double InpRiskPercent=1.0;` em
   `EA.mq5` (validar `0 < InpRiskPercent ≤ 2.0`, teto do `DCRiskLot`). Aplicar
   `dc.riskPercent = InpRiskPercent` **apenas** quando `InpCase==4`, após o `HPSelectProfile`.
5. **Não** tocar em `H1Levels`, no alvo 5R nem nas condições de entrada. O único efeito é o
   `volume` em `OpenCycle` passar pelo ramo `else` (risco, `EA.mq5:413-434`) em vez do
   `if(dc.fixedLot)`.
6. **Preservar os casos 1–3 exatamente** (mesmo `matched_control`, mesmos presets, mesmo
   lucro/trades). O Caso 4 é preset novo: `presets/CASO_04_HERMES_RISCO_1PCT.set`.

### 5.4 Verificações antes de rodar

- Rode `projeto_fonte/tests/test_hermes.cpp` / `test_execution.cpp` etc. — o caminho de risco
  já tem cobertura; confirme que continua verde.
- Confirme que, com `InpCase==1..3`, **nada muda** (mesmo lucro/trades do R200).
- Rode o Caso 4 a 1% e produza a mesma bateria de CSVs (para comparar DD relativo, dispersão
  mensal e fator de lucro contra o Caso 1).

### 5.5 O que reportar do Caso 4

Lado a lado com o Caso 1, na **mesma** janela: DD relativo, DD em dinheiro, fator de lucro,
acerto (deve ser ~igual — entradas iguais), retorno composto, e o **desvio-padrão do retorno
mensal em %**. A decisão sobre o Caso 4 sai do critério de rejeição do Experimento 1, e só é
"confirmada" após a validação OOS da §4.

---

## Resumo de uma linha

Trate o **risco** primeiro (Exp. 1, já no seu código), **desconfie** do lucro até validar fora
da amostra (Exp. 2), e **meça** antes de mexer na saída (Exp. 3). Não persiga "zero mês
negativo" — persiga um drawdown que você escolhe.
