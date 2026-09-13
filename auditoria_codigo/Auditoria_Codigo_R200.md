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

### A01 — O fonte está identificado; o executável efetivamente usado não está vinculado por hash.

**ALTA · LIMITE_DE_PROVENIENCIA**

Os exports identificam nomes/casos e o parameters.txt registra o SHA do controle antigo. Não exportam SHA do fonte atual, SHA do EX5, build do MetaEditor/terminal ou configuração completa do teste. A reprodução agregada do controle é evidência de consistência, não autenticação criptográfica do binário.

**Impacto:** Outra compilação ou histórico/configuração diferente pode conservar o mesmo nome de arquivo; o resultado não fica totalmente reproduzível apenas com os quatro CSV.

**Proposta:** Na próxima release registrar um identificador de build imutável no EA e guardar externamente hashes do MQ5, EX5, preset e relatório nativo junto dos resultados. Não reescrever a proveniência desta rodada como se já existisse.

**Evidência:** `src/EA.mq5` · WriteParameters · linha 547; `src/EA.mq5` · WriteParameters · linha 557; `src/Reports.mqh` · StatNames · linha 5.

### A02 — valid_run não atesta custos, ticks ou qualidade de execução real.

**ALTA · LIMITE_DE_VALIDACAO**

A validade exige reconciliação financeira e ausência de erros internos. Os resultados recebidos indicam comissão/taxas zero, swap negativo e ausência de filtro extra de spread pelo valor padrão 0. Não há nos quatro CSV a configuração nativa de modelagem e latência.

**Impacto:** Reconciliação aritmética correta não demonstra que todos os custos de uma conta futura estejam representados. A contagem de observações de preço não prova modelagem por ticks reais.

**Proposta:** Anexar relatório nativo e especificação do contrato/conta e repetir depois, em amostra não usada no ajuste, com custos e latência explicitamente registrados. Não subtrair spread novamente dos resultados: as ordens já usam ask/bid.

**Evidência:** `src/Reports.mqh` · OnTester · linha 197; `src/EA.mq5` · OpenCycle · linha 449; `src/EA.mq5` · OnTick · linha 534.

### A03 — Lote exato não é limite percentual de risco ou margem.

**MEDIA · DESENHO_FINANCEIRO_CONFIRMADO**

Nos três casos, InpFixedLot é utilizado diretamente. InpMaxMarginPct e InpMaxLot permanecem na interface, mas não limitam estas entradas. Só volume mínimo/máximo/passo e margem livre nativa limitam o lote. O risco nominal é medido pelo stop, sem orçamento percentual prévio.

**Impacto:** O risco por operação varia com ATR e saldo. Os CSV registram máximos de risco de stop sobre saldo de 14,6184%, 16,9772%, 12,2083% nos casos 1/2/3. O campo de margem 20 não significa limite de 20% ativo.

**Proposta:** Documentar claramente os inputs inativos e manter lote 1 nesta comparação. Qualquer versão com orçamento percentual precisa receber novo caso e não ser apresentada como simples correção do mesmo resultado.

**Evidência:** `src/EA.mq5` · inputs · linha 15; `src/EA.mq5` · OpenCycle · linha 408; `src/EA.mq5` · OpenCycle · linha 441; `src/HermesCore.mqh` · HermesExactLot · linha 26.

### A04 — Uma falha ou rejeição pode consumir a oportunidade daquela vela.

**MEDIA · LIMITACAO_OPERACIONAL_OBSERVAVEL**

lastBar é avançado antes de ler indicadores e enviar a entrada. O EA não tenta novamente na mesma vela após G_NO_DATA, spread, stop ou rejeição de ordem. A rodada tem 0 G_NO_DATA e 8/11/13 G_REJECTED; o último retcode de cada caso é 10018, mercado fechado. Não se pode inferir que todas as rejeições tiveram essa causa sem events.csv.

**Impacto:** Parte das oportunidades perdidas pode ser execução/horário, não padrão ruim. Nenhuma tentativa atrasada foi introduzida nesta análise.

**Proposta:** Analisar cada ENTRY_REJECTED por horário e retorno usando events.csv. Se houver justificativa, testar uma janela limitada e idempotente de retentativa apenas para rejeições definitivas e snapshot ainda válido, em caso separado.

**Evidência:** `src/EA.mq5` · OnTick · linha 501; `src/EA.mq5` · OnTick · linha 514; `src/EA.mq5` · OpenCycle · linha 451.

### A05 — Os casos com pivô substituem parte das entradas originais.

**MEDIA · EFEITO_DE_CARTEIRA_CONFIRMADO**

O original tem prioridade quando ambos passam na mesma vela, mas uma posição extra aberta antes impede entradas futuras. Pelos agregados, as entradas BASE são 261/241/231 e as PIVOT 0/58/111. Os sinais originais selecionados seguem 1070 em todos. As reduções 20/30 de BASE são diferenças de contagem, não identificação individual dos trades substituídos.

**Impacto:** A diferença de lucro entre casos não é o lucro isolado dos pivôs. Pode incluir pivôs, originais perdidos/recuperados e mudanças na trajetória de saldo.

**Proposta:** Conciliar cycles.csv de cada caso por signal_time e selected_entry_path para separar BASE comum, BASE exclusivo e PIVOT. Medir contribuição e custo de ocupação antes de sugerir filtros.

**Evidência:** `src/PivotEntryCore.mqh` · HPRouteEntry · linha 46; `src/EA.mq5` · OnTick · linha 532; `src/EA.mq5` · SymbolExposure · linha 199.

### A06 — Candidatos elegíveis são medidos antes de stop, posição e envio.

**BAIXA · AMBIGUIDADE_DE_INSTRUMENTACAO**

hp_extra_eligible conta o filtro técnico extra antes de validar o stop. hp_pivot_selected exclui o original vencedor da prioridade; hp_pivot_fills conta fills. Os antigos pivot_buy_candidates/pivot_sell_candidates usam outro detector legado PEPivotSignal e não descrevem o gatilho ativo HPStep.

**Impacto:** 234/320 elegíveis não podem ser comparados diretamente aos 175/242 do estudo anterior, que incluía stop. Tampouco as colunas legadas devem ser somadas aos 761 candidatos ativos.

**Proposta:** No relatório usar funil explícito: geométrico → extra técnico → original não selecionado → disponível → stop/margem/execução → preenchido. Prefixar documentação do detector antigo como diagnóstico legado.

**Evidência:** `src/EA.mq5` · OnTick · linha 522; `src/EA.mq5` · Record · linha 269; `src/Reports.mqh` · StatNames · linha 5.

### A07 — Entrada Início ainda exige tendência local; não busca qualquer reversão.

**MEDIA · LIMITE_DA_HIPOTESE**

Caso 3 retira só preço > SMA200 e SMA200 subindo da entrada extra. Continua exigindo EMA21 > SMA50, SMA50 subindo, ADX ≥ 20, +DI > −DI, candle altista acima da EMA, oscilador crescente e ask ≥ EMA + 0,5 ATR. Usa stop das 3 velas recentes, não o fundo F1 do pivô. Não exige distância máxima da EMA além das restrições indiretas do stop.

**Impacto:** Pivôs precoces contra a tendência local continuarão bloqueados. O rótulo Início pode sugerir abrangência maior que a efetiva. Geometria e stop são hipóteses distintas.

**Proposta:** Pedir ao revisor análise da coerência entre geometria, atraso do gatilho e stop, preservando uma única alteração por futura hipótese. Nenhum relaxamento foi feito nesta rodada.

**Evidência:** `src/PivotEntryCore.mqh` · HPExtraGate · linha 31; `src/ProtectCore.mqh` · PEDistance · linha 39; `src/EA.mq5` · OpenCycle · linha 384.

### A08 — A origem do histórico e a ausência de expiração temporal afetam o catálogo.

**BAIXA · LIMITACAO_DE_REPRODUCAO**

O detector inicia com 210 velas fechadas e processa continuamente. Não existe expiração fixa de um padrão por número de velas: ele permanece até invalidação, rompimento ou substituição estrutural. Referências na borda de inicialização podem variar em relação a replay iniciado em outra data.

**Impacto:** Replays com origem diferente podem divergir perto do começo. Candidatos antigos não são automaticamente candidatos melhores ou piores; a idade precisa ser medida.

**Proposta:** Registrar origem e idade dos três pivôs em qualquer reprodução; avaliar idade como hipótese prospectiva somente depois de medir distribuição, sem escolher retrospectivamente a idade que elimina perdas.

**Evidência:** `src/PivotRuntime.mqh` · HPSyncClosedBars · linha 13; `src/PivotCore.mqh` · HPExposePivot · linha 155; `src/PivotCore.mqh` · HPStep · linha 195.

### A09 — 5R é alvo nominal sobre a cotação anterior ao fill, não ganho líquido garantido.

**BAIXA · LIMITE_DE_METRICA**

SL/TP são enviados juntos: stop estrutural arredondado e TP arredondado para fora em torno de 5 distâncias do entry cotado. O fill pode diferir. A correção de alvo pós-fill só executa em targetMode > 0; todos R200 usam 0. Custos e gaps também alteram R realizado.

**Impacto:** O lucro líquido de um vencedor não precisa ser exatamente 5 vezes o risco inicial do fill; pequenas diferenças por tick são esperadas. Não chamar isso automaticamente de stop ou alvo adulterado.

**Proposta:** Conservar no dossiê quoted_entry, actual entry, quoted_target e actual_target_R; analisar distribuição quando os cycles nativos dos casos novos forem anexados.

**Evidência:** `src/XAU_H1_Core.mqh` · H1Levels · linha 60; `src/EA.mq5` · OpenCycle · linha 467; `src/Execution.mqh` · EnforceTargetCap · linha 50; `src/Reports.mqh` · ExportDetails · linha 87.

### A10 — O período foi usado repetidamente para escolher hipóteses.

**MEDIA · LIMITACAO_DE_VALIDACAO_TEMPORAL**

A própria declaração da rodada identifica 2022–2026 como janela já examinada. Esta auditoria recebeu comparação agregada, não um novo período intocado. Mais lucro nessa janela, se surgisse, não provaria repetibilidade; nesta rodada as extras pioraram lucro e meses negativos.

**Impacto:** Selecionar somente vencedores históricos e eliminar padrões perdedores aumenta risco de ajustar ruído e regime específico. A auditoria não certifica robô pronto para conta real nem capacidade de zerar meses negativos.

**Proposta:** Manter a versão Referência como controle; pré-declarar poucas hipóteses motivadas por decomposição dos trades e medir em janelas cronológicas separadas e posteriormente forward DEMO.

**Evidência:** `PLANO_RODADA_200.json` · dates_note · linha 15.

### A11 — DD mensal reinicia o pico no mês e não equivale ao DD global.

**BAIXA · LIMITE_DE_METRICA_MENSAL**

Cada mês começa na última equity observada do anterior e reinicia o pico para o DD intramês. O DD global relativo vem de TesterStatistics. equity_change, booked_net e cycle_net_by_exit são conceitos diferentes.

**Impacto:** Somar apenas saídas desloca lucro entre meses de posições carregadas. Máximo de DDs mensais não reproduz necessariamente DD global; percentual no maior DD monetário também é outra estatística.

**Proposta:** Apresentar consistência por equity_change, com saldo realizado como coluna auxiliar. Gráfico de fechamentos mensais deve ser rotulado para não sugerir trajetória intramês ou DD por ticks.

**Evidência:** `src/ProtectCore.mqh` · PEStartEquity · linha 129; `src/EA.mq5` · TrackEquity · linha 211; `src/Reports.mqh` · MonthValues · linha 11; `src/Reports.mqh` · OnTester · linha 151.

### A12 — Flags de breakeven não constituem simulação contrafactual completa.

**BAIXA · LIMITACAO_DE_METRICA_BE**

Os thresholds 1/1,5/2/2,5/3R guardam atingiu/retornou e primeira cotação de retorno; não guardam o instante do retorno. O agregado de otimização publica esses flags somente para o caso 1. Nenhum BE está ativado.

**Impacto:** Não é possível deduzir PnL mensal, swap recalculado ou novas entradas liberadas por um BE apenas desse CSV. MFE após entrada não pode ser filtro disponível antes de entrar.

**Proposta:** Solicitar ao Claude distinguir flags observados, proxies e backtests de gestão reais. Qualquer BE proposto requer execução temporal completa em caso próprio.

**Evidência:** `src/ProtectCore.mqh` · PEObserve · linha 110; `src/Reports.mqh` · ExportDetails · linha 97; `src/Reports.mqh` · DrainFrames · linha 261.

O retorno 10018 significa mercado fechado segundo a [tabela oficial da MetaQuotes](https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes). Modo, dados e condições selecionados são parte do experimento, conforme a [documentação de testes](https://www.metatrader5.com/en/terminal/help/algotrading/testing).

## Leitura correta dos relatórios

- `profit` é a estatística financeira do testador; `cycle_net` reconstrói negócios; `equity_change` mede a variação patrimonial entre fechamentos de mês. A soma mensal é confrontada com o lucro total, com tolerância de US$ 0,01.
- `booked_net` registra realizado no mês de cada deal. `cycle_net_by_exit` atribui todo o resultado do ciclo ao mês da saída. Podem divergir da equity mensal quando a posição atravessa meses.
- O DD relativo global vem do MT5. O percentual no ponto do maior DD monetário é outra estatística; o DD mensal reinicia o pico a cada mês.
- O código não cria meses sem nenhum tick observado. A cobertura do calendário precisa ser verificada separadamente; período parcial não deve ser apresentado como ano/mês completo.
- Taxas iguais a zero refletem o teste fornecido. O spread já está nas cotações de entrada/saída; acrescentá-lo integralmente outra vez duplicaria esse custo.
- O BE shadow é observacional. O arquivo agregado publica thresholds somente para o caso 1; não são resultados financeiros de uma nova gestão com BE.

## Perguntas prioritárias para o Claude

1. A inspeção confirma os filtros ativos descritos? Identifique divergências com função/linha e um contraexemplo reproduzível, se existirem.
2. Como separar o efeito das 58/111 entradas de pivô do efeito das 20/30 entradas BASE a menos? Exigir decomposição por timestamp e rota antes de culpar o padrão.
3. O stop das três velas recentes é consistente com a geometria F1–T–F2? Qual hipótese única e pré-declarada investigaria isso, sem afastar stops retrospectivamente para salvar perdas conhecidas?
4. Ask ≥ EMA + 0,5 ATR ajuda a confirmação ou atrasa o gatilho? Propor comparação causal com validação cronológica; não usar MFE ou resultado futuro como entrada.
5. Há custo de ocupação excessivo de posições com 5R? Quais dados faltam para testar isso, respeitando a preferência por evitar parciais em alvos curtos?
6. Existem regimes identificáveis antes da entrada e estáveis em subperíodos, ou o padrão foi selecionado apenas porque ganhou neste histórico já visto?
7. A melhora de DD do caso 3 justifica menor lucro e mais meses negativos segundo um objetivo definido antes de olhar os resultados?
8. Quais testes mínimos distinguem correção do código, reprodução do backtest e vantagem da estratégia em dados novos e DEMO?

Solicitar hipóteses falsificáveis, evidência contrária e uma ordem curta de testes. Não pedir promessa de eliminar todo mês negativo. Não ativar novos casos, alterar a versão atual nem contar uma proposta como melhoria confirmada.
