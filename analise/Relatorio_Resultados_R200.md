# Auditoria dos resultados Hermes Pivôs 2.00 — R200

A Referência continua superior em lucro e consistência mensal. Os dois modelos de pivô aumentaram a atividade, mas reduziram o lucro e aumentaram a contagem de meses completos negativos. A variante Início teve drawdown relativo menor; seu drawdown monetário máximo foi maior. Isso não equivale a uma melhora geral.

## Base examinada

Quatro arquivos recebidos, três casos e 171 registros mensais. Período solicitado: 01/01/2022 até 12/09/2026 exclusivo. Último tick mensal: 11/09/2026 20:57:59, horário do servidor. São 56 meses completos e setembro de 2026 parcial. Os 2199 controles de reconciliação passaram. Não executamos novo backtest.

|Caso|Lucro líquido USD|Trades|Acerto|PF|DD relativo|Meses negativos completos|Setembro parcial USD|
|---|---:|---:|---:|---:|---:|---:|---:|
|1 — HERMES_REFERENCIA|204.912,54|261|26,05%|2.013|42,76%|17|0,00|
|2 — HERMES_PIVO_CONTINUIDADE|191.523,99|299|25,42%|1.799|43,58%|22|0,00|
|3 — HERMES_PIVO_INICIO|169.116,06|342|24,56%|1.586|36,85%|18|-7.502,29|

Nos 56 meses completos, o caso 1 teve 37 positivos, 17 negativos e 2 zerados; o caso 2, 34 positivos e 22 negativos; o caso 3, 38 positivos e 18 negativos. A tela do MT5 mostra 19 negativos no caso 3 porque inclui setembro parcial, com prejuízo de US$ 7.502,29. Os casos 1 e 2 não operaram em setembro e marcaram zero.

## Controle reproduzido e diagnósticos

R200:1 reproduz R190:2: 124 campos comuns iguais, sem divergência econômica ou de execução. As cinco diferenças são passe, número/nome do caso e dois identificadores de controle. Todos os 1026 campos mensais comparáveis também coincidem.

Nos três casos, a soma dos resultados mensais de equity, saldo realizado e ciclos por saída coincide com o lucro total. Equity e balance são contínuos entre meses; ciclos abertos = fechados e fechamentos = vencedores + perdedores. Nenhum saldo final carrega posição aberta. Os gates somam 55.498 avaliações por caso.

Não houve falha de dados do pivô, G_NO_DATA ou interrupção fatal. Houve 8, 11 e 13 requisições rejeitadas nos casos 1, 2 e 3. O último código de retorno é 10018, que significa mercado fechado. Sem os eventos individuais desta rodada, não é possível afirmar que todas as rejeições tiveram esse motivo. Contador de erro fatal zerado não significa ausência de rejeições de ordens. [Documentação MQL5](https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes).

## Pivôs e novas operações

|Caso|Execuções por pivô|Execuções pelo gatilho base|Variação líquida de trades|Variação do lucro USD|Variação do lucro %|
|---|---:|---:|---:|---:|---:|
|2|58|241|+38|-13.388,55|-6,53%|
|3|111|231|+81|-35.796,48|-17,47%|

58 e 111 são execuções identificadas como pivô; os aumentos líquidos foram 38 e 81. As execuções pelo gatilho base caíram de 261 para 241 e 231. Com apenas uma posição por vez, operações extras alteram a disponibilidade para sinais seguintes. Não atribuímos a diferença de lucro apenas aos pivôs, nem sabemos quais operações-base foram substituídas sem os arquivos individuais.

Cada perfil observou 761 candidatos geométricos. Nos casos 2 e 3, hp_extra_eligible = 234/320 e hp_extra_position_blocks = 87/100. Esses contadores têm escopos diferentes: elegibilidade pode coincidir com o gatilho original, seleção precede filtros de execução, e bloqueio por posição não representa uma operação comprovadamente lucrativa perdida.

## Os 17 meses negativos da referência

**Caso 2:** tornou positivos 1 dos 17 meses; melhorou, mas manteve negativos, 2; agravou 5; deixou iguais 9. Em contrapartida, 4 meses antes positivos ficaram negativos e 2 meses antes zerados ficaram negativos. Esta comparação considera somente os mesmos 56 meses completos.

- Negativos que ficaram positivos: 2023-01.
- Positivos que ficaram negativos: 2022-12, 2024-12, 2025-06, 2025-07.
- Zerados que ficaram negativos: 2022-06, 2025-05.

**Caso 3:** tornou positivos 3 dos 17 meses; melhorou, mas manteve negativos, 2; agravou 10; deixou iguais 2. Em contrapartida, 2 meses antes positivos ficaram negativos e 2 meses antes zerados ficaram negativos. Esta comparação considera somente os mesmos 56 meses completos.

- Negativos que ficaram positivos: 2022-01, 2023-01, 2023-04.
- Positivos que ficaram negativos: 2022-08, 2022-10.
- Zerados que ficaram negativos: 2022-06, 2025-05.

Atividade extra não resolveu a consistência: o total de meses completos negativos passou de 17 para 22 e 18. Escolher retrospectivamente o perfil vencedor de cada mês não cria uma regra que pudesse ser executada antes de conhecer os resultados.

## Resultado anual e Selic

Retorno anual calculado sobre a equity no início de cada ano, sem aportes. 2026 é acumulado até 11/09, sem anualização. O lote continuou fixo em 1,00: calcular retorno sobre capital que variou não significa reinvestimento automático no lote.

|Ano|Caso|Lucro USD|Retorno USD|Retorno convertido BRL|Selic BRL|Excesso BRL p.p.|
|---|---|---:|---:|---:|---:|---:|
|2022|1|14.297,77|142,98%|127,18%|12,39%|114,79|
|2022|2|14.922,19|149,22%|133,02%|12,39%|120,63|
|2022|3|14.614,58|146,15%|130,14%|12,39%|117,75|
|2023|1|7.688,73|31,64%|22,15%|13,04%|9,11|
|2023|2|14.096,05|56,56%|45,27%|13,04%|32,23|
|2023|3|12.040,67|48,92%|38,17%|13,04%|25,13|
|2024|1|21.469,76|67,12%|113,76%|10,88%|102,88|
|2024|2|17.081,81|43,78%|83,90%|10,88%|73,03|
|2024|3|23.825,25|65,00%|111,04%|10,88%|100,17|
|2025|1|94.825,68|177,39%|146,48%|14,32%|132,16|
|2025|2|88.748,82|158,20%|129,43%|14,32%|115,11|
|2025|3|92.445,06|152,85%|124,68%|14,32%|110,36|
|2026*|1|66.630,60|44,94%|34,12%|9,78%|24,34|
|2026*|2|56.675,12|39,13%|28,75%|9,78%|18,97|
|2026*|3|26.190,50|17,13%|8,39%|9,78%|-1,39|

*2026 parcial. Retorno em BRL = (equity final em USD × câmbio final) / (equity inicial em USD × câmbio inicial) − 1. Selic acumulada = produto de (1 + taxa diária SGS 11 / 100) − 1. Foram reutilizados snapshots históricos com hashes verificados das séries SGS 11 (Selic diária) e SGS 1 (câmbio), das mesmas datas dos benchmarks anteriores. Impostos, remessas e spread cambial não estão incluídos; a Selic não tem o mesmo risco do robô. [Banco Central — SGS](https://www3.bcb.gov.br/sgspub/).

## Drawdown e custos

|Caso|DD relativo máximo|DD monetário máximo USD|Percentual no episódio do DD monetário|Swap total USD|
|---|---:|---:|---:|---:|
|1|42,76%|29.778,30|13,19%|-17.865,66|
|2|43,58%|34.410,58|15,89%|-19.737,81|
|3|36,85%|55.534,40|24,69%|-21.182,04|

O maior percentual de queda e a maior queda em dinheiro podem ocorrer em momentos diferentes. O caso 3 reduziu DD relativo de 42,76% para 36,85%, mas aumentou DD monetário de US$ 29.778,30 para US$ 55.534,40. O custo de swap aumentou US$ 1.872,15 e US$ 3.316,38 nos casos 2 e 3. Comissões e taxas foram reportadas como zero; isso não comprova custo futuro igual a zero.

## Equity mensal não é apenas trade fechado

Resultado mensal = realizado + (flutuante final − flutuante inicial). Por exemplo, abril de 2026 da Referência registra +US$ 17.500,19 realizados, mas −US$ 1.378,72 na equity, pois parte do ganho fechado já estava computada em março. São bases contábeis diferentes. A tabela mensal preserva ambas e o resultado flutuante de cada fronteira.

## Alcance da auditoria e material para Claude

A reconciliação valida a coerência interna dos CSVs; não certifica ausência de todos os bugs nem robustez futura. Os quatro arquivos não trazem o hash do EX5 executado, relatório nativo com qualidade/modelagem de ticks, latência e alavancagem, nem cycles/deals/bars/events dos casos 2 e 3. O código do dossiê é a fonte distribuída, não prova criptográfica do binário que rodou.

O arquivo de breakeven tem cinco linhas de observação da Referência apenas. Elas mostram retornos ao ponto de entrada após 1R, 1,5R, 2R, 2,5R e 3R; não demonstram lucros de versões BE executadas, nem resultados BE dos casos 2 e 3. Nenhum perfil desta rodada ativou BE, parcial, médio ou pirâmide.

A amostra já foi reutilizada no desenvolvimento; não é fora da amostra. Antes de novos filtros, é necessário atribuir os resultados dos pivôs, das operações-base substituídas e dos meses afetados. Regras propostas devem usar somente informação disponível antes da entrada e passar por validação temporal separada. Nenhum caso cumpre a meta de 60 meses completos sem prejuízo.

Arquivos derivados: Analise_R200.json reúne dados, critérios e fontes; Meses_R200.csv, Anos_R200.csv, Comparacao_Mensal_R200.csv e Transicoes_Mensais_R200.csv permitem revisão independente. O script não acessa nem altera banco ou robô.
