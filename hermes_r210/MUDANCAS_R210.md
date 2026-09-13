# Hermes R210 — o que mudou e por quê (para o ChatGPT e o proprietário)

Versão nova a partir do R200. **R200 (`../projeto_fonte/`) fica congelado** como
comparador auditado; o R210 acrescenta dois casos novos **isolados**, reaproveitando o
motor de execução já validado. Trabalho a 4 mãos: o Claude escreveu esta versão; o ChatGPT
compila no MetaEditor, roda os backtests no MT5 e devolve os resultados.

> **Filosofia desta rodada (pedido do proprietário):** o robô **não pode ganhar só porque o
> ouro subiu**. Duas frentes: (1) **normalizar o risco** para o resultado deixar de ser uma
> aposta alavancada no preço do ouro; (2) testar uma estratégia de **ganhos menores e mais
> frequentes** — aproveitar a entrada de alto volume, pegar o nosso e sair.

---

## 1. O que é honesto afirmar sobre esta versão

- **Validado aqui (g++):** toda a lógica de decisão portável — roteamento dos casos, o
  `QHGate` do Caso 5 e o corpo de produção do `OpenCycle` — compila e passa em 9/9 testes
  unitários (`python3 verificar.py`). Os **cores auditados do R200 continuam byte-idênticos**
  (a verificação prova isso).
- **NÃO validado aqui:** rentabilidade. Não há MetaTrader neste ambiente — **nenhum backtest
  foi executado**. Os Casos 4 e 5 são **hipóteses a testar**, não melhorias comprovadas.
- **Um passo que depende do ChatGPT:** o EA completo precisa ser **compilado no MetaEditor**.
  A cola de integração no EA (ex.: `ReadQuickHarvest`, o ramo do `OnTick`) segue os padrões do
  próprio projeto, mas não pôde ser compilada aqui. Se aparecer algum erro de compilação,
  me diga o texto do erro que eu corrijo.

**Nunca** apresente Caso 4 ou 5 como "melhoria" antes da validação fora da amostra (§7).

---

## 2. Os cinco casos

| Caso | Nome | Entrada | Sizing | Alvo | Situação |
| --- | --- | --- | --- | --- | --- |
| 1 | HERMES_REFERENCIA | original (pullback+tendência) | **lote fixo 1,00** | 5R | **congelado R200** |
| 2 | HERMES_PIVO_CONTINUIDADE | original + pivô (com SMA200) | lote fixo 1,00 | 5R | congelado R200 |
| 3 | HERMES_PIVO_INICIO | original + pivô (sem SMA200) | lote fixo 1,00 | 5R | congelado R200 |
| 4 | **HERMES_RISCO_REF** | **igual ao Caso 1** | **risco % do patrimônio** | 5R | **novo — a testar** |
| 5 | **HERMES_COLHEITA_RAPIDA** | **surto de volume/range** | risco % do patrimônio | **curto (InpQHTargetR)** | **novo — a testar** |

Selecione o caso pelo input `InpCase` (1..5) ou pelos presets em `presets/`.

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

---

## 6. Como compilar e rodar (MetaEditor + MT5)

1. `cd hermes_r210 && python3 build.py` → gera `Hermes_R210.mq5` (arquivo único) e os presets.
2. Copie `Hermes_R210.mq5` para `MQL5/Experts/` e **compile no MetaEditor** (F7). O EA exige
   Testador (`OnInit` bloqueia uso fora do Strategy Tester).
3. No Testador: XAUUSD, M30, período desejado, **modelagem por ticks reais**, **custos reais**.
4. Carregue um preset de `presets/` (ex.: `CASO_04_...`, `CASO_05_...`) ou ajuste `InpCase`.
5. Exporte os CSVs (bars/events + agregados) como no R200 para comparar.

Checagem local sem MT5: `python3 verificar.py` (compila e roda os 9 testes portáveis em g++ e
prova que os cores do R200 não foram tocados).

---

## 7. Protocolo de validação (obrigatório antes de qualquer conclusão)

1. **Caso 1 no R210 = Caso 1 no R200** (mesmo lucro/trades). Se divergir, pare e me avise.
2. **Caso 4 vs Caso 1** na mesma janela: comparar DD relativo, DD em dinheiro, fator de lucro
   e **desvio-padrão do retorno mensal**.
3. **Caso 5 com custos realistas**: expectância por trade e fator de lucro **após custos**.
4. **Fora da amostra:** walk-forward + uma janela final nunca usada na escolha + teste num
   período do ouro que **não** foi bull market (ex.: 2013–2019).
5. **Forward em DEMO** antes de qualquer real. Depois, micro-real com risco baixo.

Detalhe do raciocínio e das previsões em `../docs/PLANO_EXPERIMENTOS.md` e no parecer
`../docs/PARECER_CLAUDE_R200.md`.

---

## 8. Mapa de mudanças

| Arquivo | Estado | O quê |
| --- | --- | --- |
| `src/XAU_H1_Core.mqh`, `ProtectCore`, `EntryCore`, `DonchianCore`, `HermesCore`, `Execution`, `PivotCore`, `PivotRuntime`, `Reports` | **byte-idêntico ao R200** | motor auditado, intocado |
| `src/PivotEntryCore.mqh` | alterado | roteamento aceita Casos 4/5 (sizing por risco) |
| `src/EA.mq5` | alterado | inputs novos, `ReadQuickHarvest`, ramo do Caso 5, alvo curto, validações |
| `src/QuickHarvestCore.mqh` | **novo** | decisão do Caso 5 (`QHGate`), pura e testada |
| `tests/test_quickharvest.cpp` | novo | testa `QHGate` |
| `tests/test_pivot_entry.cpp` | atualizado | agora valida Casos 4/5 |
| `build.py`, `verificar.py` | adaptados | 5 casos; prova cores congelados |
| `presets/CASO_04_*`, `CASO_05_*`, `00_COMPARAR_5_CASOS` | novos | presets dos casos novos |

**Peço ao ChatGPT:** compilar no MetaEditor; confirmar que os Casos 1–3 reproduzem o R200;
rodar Caso 4 (risco 1%) e Caso 5 (**com custos reais**); devolver os CSVs para eu analisar
regime, custo de ocupação e a fronteira risco×retorno.
