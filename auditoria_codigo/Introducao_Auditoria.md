# Auditoria independente do código — Hermes Pivôs 2.00

**Escopo:** inspeção estática de todos os módulos do fonte e cruzamento com os exports agregados da rodada R200 recebidos em 13/09/2026. É uma revisão técnica do projeto, não certificação externa de rentabilidade. Não houve alteração do EA, compilação nativa, novo backtest ou ajuste de parâmetros nesta auditoria.

Fonte único auditado: `Hermes_Pivos_Lab_200/Hermes_Pivos_Lab_200.mq5`.

SHA-256: `69a4e02bfaaea2619aad1dea364e8e5c0d03c768ef46f5eeddd2ca7f1235ec9f`.

As referências de linhas abaixo usam os módulos de `src`, que compõem o arquivo único. O mapa de hashes acompanha o JSON desta auditoria.

## Parecer

Não identifiquei erro crítico demonstrado de antecipação de preços futuros no detector ativo de pivôs. O encadeamento de confirmação e a separação entre gatilho fechado e entrada na vela seguinte são coerentes com o protocolo. Isso não prova ausência de qualquer bug: a evidência disponível aqui é a leitura do código, os testes portáveis previamente registrados e os exports do usuário. O executável EX5 efetivamente utilizado não foi recebido com hash.

Os três casos declaram `valid_run=1`, reconciliações zeradas e nenhum erro interno de integridade. O controle reproduziu US$ 204.912,54 e 261 operações. As variantes com entradas extras aumentaram operações, mas não melhoraram a consistência mensal: nos 56 meses completos (janeiro/2022 a agosto/2026), foram 17, 22 e 18 meses negativos nos casos 1, 2 e 3. Setembro/2026 é parcial e acrescenta um mês negativo observado ao caso 3; por isso o CSV registra 19 nesse caso. O caso 3 teve menor drawdown relativo, porém menor lucro; nenhum caso venceu todos os critérios.

## Especificação exata das estratégias

**Convenção:** `[1]` é a última vela fechada de M30; `[2]`, a anterior; `[6]`, cinco barras observadas antes de `[1]`. Comparações de média/preço são estritas, salvo o limiar ADX ≥ 20 e a distância mínima com tolerância numérica. Não é necessário SMA50 > SMA200.

| Componente | Implementação real | Utilização |
|---|---|---|
| EMA21 | `iMA`, 21, MODE_EMA, PRICE_CLOSE | Tendência, retomada e distância |
| SMA50 e SMA200 | `iMA`, 50/200, MODE_SMA, PRICE_CLOSE | Tendência e inclinação `[1] > [6]` |
| ADX14 | `iADX`, buffers 0/1/2 | Força ≥ 20 e direção +DI > −DI |
| ATR14 | `iATR`, 14 | Distância, stop e normalização |
| Oscilador 3–10 | SMA3(Close) − SMA10(Close) | Só filtra a entrada extra; valor atual > anterior |
| Linha de sinal | SMA16 do oscilador 3–10 | Calculada e exportada; não exigida na entrada R200 |
| Pivô ativo | Extremo estrito, duas barras de cada lado | Sequência causal F1–T–F2 e rompimento de T |

O código usa `iADX`, não `iADXWilder`; a MetaQuotes documenta essas funções separadamente. Uma reprodução deve respeitar a implementação escolhida, sem trocar automaticamente o suavizador. [Documentação iADX](https://www.mql5.com/en/docs/indicators/iadx), [documentação iADXWilder](https://www.mql5.com/en/docs/indicators/iadxwilder).

A associação histórica do projeto com Linda Raschke não autentica este robô como reprodução de uma estratégia original dela. O fonte comprova a fórmula SMA3 − SMA10, sinal SMA16 e a regra de crescimento. Não há chamada a `iMACD`, requisito de cruzar zero, requisito de cruzar o sinal ou inferência de IA durante a execução. São regras determinísticas.

### Caso 1 — HERMES_REFERENCIA

Compra quando todas as condições forem verdadeiras:

1. EMA21[1] > SMA50[1] e SMA50[1] > SMA50[6].
2. Close[1] > SMA200[1] e SMA200[1] > SMA200[6].
3. ADX14[1] ≥ 20 e +DI[1] > −DI[1]. Não exige ADX subindo.
4. Pelo menos uma das velas `[2]`, `[3]` ou `[4]` toca sua própria EMA21: Low ≤ EMA ≤ High. A vela gatilho `[1]` não satisfaz sozinha esse toque anterior.
5. Close[1] > Open[1], Close[1] > EMA21[1] e Close[1] > High[2].
6. Ask no instante da decisão − EMA21[1] ≥ 0,5 ATR14[1], no preset atual.

Em seguida, passam os filtros de posição, spread se habilitado, stop, volume e margem. O oscilador não limita este caso. Evidências: `XAU_H1_Core.mqh:H1Evaluate/H1EvaluateProfile`, `EntryCore.mqh:EVOEvaluate` e `EA.mq5:ReadSignal`.

### Caso 2 — HERMES_PIVO_CONTINUIDADE

Mantém o caso 1 e acrescenta outra rota de compra, considerada somente quando o filtro original `EVOEvaluate` falha. A nova rota exige:

- Sequência confirmada F1–T–F2 com F1 < F2 < T; fechamento anterior ≤ T e fechamento do gatilho > T.
- EMA21[1] > SMA50[1], SMA50[1] > SMA50[6], Close[1] > SMA200[1] e SMA200[1] > SMA200[6].
- ADX14[1] ≥ 20 e +DI[1] > −DI[1].
- Candle altista fechado acima da EMA21; SMA3 − SMA10 maior que no candle anterior.
- Ask − EMA21[1] ≥ 0,5 ATR14[1].

A rota extra não exige o toque anterior na EMA nem o rompimento específico de High[2]; exige o rompimento do topo T do pivô.

### Caso 3 — HERMES_PIVO_INICIO

É idêntico ao caso 2, retirando **somente da rota extra** as duas condições de SMA200: preço acima dela e inclinação ascendente. Todas as regras da rota original permanecem. A tendência local EMA21/SMA50 continua obrigatória; não é um detector irrestrito de início de qualquer tendência.

### Causalidade e estado do pivô

O extremo de uma vela só fica disponível na abertura observada posterior ao fechamento da segunda vela à direita. O rompimento usa referências disponíveis antes da abertura da vela gatilho. O detector avalia o sinal antes de incorporar o novo pivô confirmado naquela iteração. Empates são excluídos; uma vela que simultaneamente é topo e fundo estritos reinicia a sequência. Pivôs consecutivos do mesmo tipo só substituem o anterior se forem mais extremos.

O padrão comprador é invalidado se uma vela posterior atingir Low ≤ F1, inclusive a própria vela de rompimento. Cada snapshot de padrão produz no máximo um evento. O núcleo também conta estruturas vendedoras para referência, mas só emite `signal.buy` para operar. O estado é atualizado mesmo com posição aberta; evento bloqueado não fica na fila para entrada posterior.

O adaptador inicia com 210 velas fechadas em ordem cronológica. Em falha de cópia, não grava estado parcial. Em recuperação, processa o histórico observado e descarta gatilhos antigos; só o mais recente pode operar. A hora de abertura seguinte é testemunho do fechamento; o detector não usa OHLC da vela aberta. A mesma origem histórica é necessária para comparação exata perto da inicialização.

### Execução e saídas comuns

Há uma decisão por nova vela M30 e no máximo uma posição/campanha do símbolo. A compra a mercado usa o ask; a trajetória é marcada pelo bid. A prioridade da rota original é resolvida antes da execução: se ela passar no setup e depois falhar no stop, margem ou spread, não há fallback para o pivô.

SL comprador = min(Low[1], Low[2], Low[3]) − 0,20 ATR, arredondado para o tick para fora. A distância do ask cotado ao SL precisa ficar entre 1 e 2,5 ATR; caso contrário a entrada é recusada. O fundo geométrico F1 invalida o padrão, mas não é o stop executado. TP nominal = ask cotado + 5 × (ask cotado − SL), com arredondamento de tick. O volume é exatamente 1,00 lote no preset, ou a operação é recusada se volume/margem nativa não permitirem; não há redução automática.

SL/TP acompanham a ordem. O fill é conferido por identificador da posição, deal, volume, símbolo, magic e direção. Uma resposta ambígua bloqueia novas entradas em vez de reenviá-las cegamente. A proteção existente é monitorada, com parada ou fechamento de emergência em inconsistências. O PnL líquido reconstrói DEAL_PROFIT + DEAL_SWAP + DEAL_COMMISSION + DEAL_FEE dos ciclos próprios.

Não há BE, parcial, médio, piramidagem, reinvestimento, saída por inversão de indicador ou tempo máximo nesta rodada. Normalmente a saída é SL, TP ou encerramento do testador; inconsistências técnicas podem acionar emergência. Não há API, chave de IA, banco online ou aprendizagem automática dentro deste EA.

### Código legado presente, porém sem ativação nos três perfis

`HPSelectProfile` herda DC caso 2 → EVO caso 28 → família 15 e verifica: capital fixo, alvo 5R, channelMode 0, entryPolicy 0, sem parcial/BE/adições/reinvestimento. Nomes como Donchian, W1, 20 pontos, 20 unidades de preço, médios e outras famílias aparecem nos módulos/testes porque o motor é compartilhado com releases anteriores. Sua presença textual não significa uso no R200.

`PEPivotSignal` continua gerando métricas legadas. A decisão extra R200 usa `HPStep/HPExtraGate`. `pivot_buy_candidates` e `hp_candidates` não são aliases. O robô bloqueia uso fora do Testador, inclusive em conta DEMO online: `OnInit` exige `MQL_TESTER`.

## Achados e recomendações específicas

Os itens distinguem comportamento intencional, limitação de evidência e melhoria possível; não são 12 bugs comprovados. A severidade expressa impacto para interpretação ou reprodução do projeto.

