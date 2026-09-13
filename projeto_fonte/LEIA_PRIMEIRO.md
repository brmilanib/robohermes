# Hermes Pivôs Lab 2.00 — rodada R200

Esta rodada testa se pivôs confirmados acrescentam entradas úteis ao Hermes M30. A execução continua com **lote fixo de 1,00 e alvo de 5R**, sem parcial, breakeven, médio, pirâmide ou reinvestimento. Os resultados das versões novas ainda precisam do Testador de Estratégias do MT5.

| Caso | Nome | Entrada |
|---|---|---|
| 1 | HERMES_REFERENCIA | Mesma entrada e execução do Hermes caso 2 da versão 1.90. |
| 2 | HERMES_PIVO_CONTINUIDADE | Original ou pivô 1–2–3 de compra, mantendo preço acima da SMA200 e SMA200 subindo. |
| 3 | HERMES_PIVO_INICIO | Original ou o mesmo pivô de compra, sem exigir essas duas condições da SMA200 na entrada extra. |

O caso 1 permite conferir se a atualização preservou a referência. Usando o mesmo histórico, depósito, custos, modelagem e configurações, compare-o com o relatório anterior. As outras duas versões são hipóteses novas; mais candidatos não significam mais lucro.

## O que caracteriza a entrada extra

Um fundo L1, um topo H e um fundo mais alto L2, com L1 < L2 < H. Cada extremo precisa de duas barras à esquerda e duas à direita, com preços estritamente diferentes dos extremos vizinhos. A referência só fica disponível na abertura observada posterior à segunda barra de confirmação. Barras que são simultaneamente topo e fundo reiniciam a sequência.

O candle de rompimento precisa fechar acima de H, tendo o fechamento anterior em H ou abaixo. O pivô deve estar confirmado antes da abertura desse candle. Se o preço tocar ou perder L1 antes do disparo — inclusive dentro do candle do rompimento — a estrutura é invalidada. Cada evento é consumido uma vez, inclusive quando houver posição aberta ou algum bloqueio.

Filtros comuns das entradas extras:

- Candle fechado de alta e fechamento acima da EMA21.
- EMA21 acima da SMA50 e SMA50 acima do valor de cinco barras antes.
- ADX de 14 períodos igual ou superior a 20 e +DI acima de −DI.
- Oscilador SMA3 menos SMA10 válido e acima do valor da barra anterior. Não é exigido cruzamento da linha de sinal.
- Ask da decisão menos EMA21 de pelo menos 0,50 ATR14, conforme `InpMinEntryATR`.
- No caso 2, também fechamento acima da SMA200 e SMA200 subindo. No caso 3, apenas essas duas exigências são removidas da entrada extra.

A entrada original sempre tem prioridade. Só se ela falhar em `EVOEvaluate` o robô pode selecionar o pivô. Uma entrada original aprovada e depois recusada por stop, margem ou spread não aciona uma segunda tentativa alternativa. Continua existindo somente uma posição por vez.

## Stop, alvo e lote

O stop continua no menor fundo do candle de sinal e dos dois anteriores, menos 0,20 ATR14. A distância da entrada cotada até esse stop precisa estar entre 1 e 2,5 ATR; fora disso, o sinal é recusado. O fundo L1 da estrutura **não substitui o stop original**.

O alvo continua em 5 vezes a distância inicial cotada ao stop, com o mesmo arredondamento por tick e a mesma execução da referência. Slippage, gaps, spread, swap e demais custos podem alterar o R realizado.

Todos os presets usam `InpFixedLot=1.00`. Se o contrato não aceitar esse volume ou faltar margem livre, a entrada é recusada, sem reduzir o lote automaticamente. Os parâmetros antigos `InpMaxMarginPct` e `InpMaxLot` foram mantidos por compatibilidade e não limitam o lote fixo desses três casos.

## Instalar e rodar

1. No MT5, abra **Arquivo → Abrir pasta de dados → MQL5 → Experts**.
2. Copie somente o arquivo principal `Hermes_Pivos_Lab_200.mq5` para essa pasta. Ele já contém os componentes necessários, além da biblioteca padrão `Trade/Trade.mqh` do MT5.
3. Abra-o no MetaEditor e pressione **F7**. O MetaEditor gera o arquivo `.ex5`. Este pacote entrega código-fonte; a compilação nativa ainda precisa ser feita no seu MT5.
4. Abra o Testador com **Ctrl+R**. Selecione `Hermes_Pivos_Lab_200`, XAUUSD e **M30**.
5. Para comparar com a rodada anterior, mantenha o mesmo período **01/01/2022 até 12/09/2026**, depósito **US$ 10.000**, alavancagem, histórico, custos e latência usados no teste do Hermes caso 2. A data final do testador é exclusiva. Esse período não contém 60 meses completos.
6. Em parâmetros de entrada, carregue `presets/00_COMPARAR_3_CASOS.set`. Somente `InpCase` fica marcado para otimização, início 1, passo 1 e fim 3.
7. Use otimização **Algoritmo completo lento**, critério **Critério máximo do usuário**, modelagem **Cada tick é baseado em um tick real**, com agentes **locais** e visualização desativada. A existência e cobertura de ticks reais devem ser conferidas no relatório final.
8. Inicie. Para visualizar depois um caso isolado, desative a otimização, carregue o preset individual correspondente e habilite o modo visual, se desejar.

O robô funciona exclusivamente no Testador de Estratégias. Não envia ordens para uma conta online, nem mesmo DEMO.

## Caminho dos arquivos de comparação

Pressione **Windows + R** e cole:

```text
%APPDATA%\MetaQuotes\Terminal\Common\Files\Hermes_Pivos_Lab_200\R200_01
```

Abra a pasta `OTIMIZACAO_...` criada na rodada mais recente. O caminho completo segue este formato:

```text
%APPDATA%\MetaQuotes\Terminal\Common\Files\Hermes_Pivos_Lab_200\R200_01\OTIMIZACAO_<data_hora>\comparacao.csv
```

Envie `comparacao.csv`, `meses_comparacao.csv`, `arquivos_comparacao.csv` e `breakeven_comparacao.csv`. O Diário do testador também imprime o caminho como `COMPARACAO AUTOMATICA`.

Cada passagem exporta uma pasta `CASO_<n>_M30_...` no mesmo diretório da rodada. O arquivo `arquivos_comparacao.csv` aponta para a pasta exata de cada caso. Envie os detalhes dos dois casos novos para analisar entradas e oportunidades: `bars.csv`, `cycles.csv`, `deals.csv`, `events.csv`, `months.csv`, `parameters.txt`, `summary.csv` e `breakeven_paths.csv`.

Os arquivos de breakeven registram observações do trajeto das operações; não significam que breakeven foi ativado.

## Rastreabilidade e limites desta rodada

`bars.csv` registra o motivo final da decisão, o filtro original, o filtro extra, o caminho selecionado `BASE/PIVOT/NONE`, os três preços de referência, horários de origem, confirmação e disponibilidade. `cycles.csv` e `ENTRY_FILLED` vinculam a entrada executada ao caminho e ao pivô que a originou. As estatísticas adicionais também registram candidatos, bloqueios por posição e falhas de dados.

O detector inicia com 210 candles fechados e depois acompanha todas as barras, inclusive durante operações. Usa apenas a abertura do candle atual como testemunha temporal; não lê seu OHLC para gerar sinal. A origem finita de 210 barras pode produzir diferenças próximas ao início em relação ao catálogo iniciado no primeiro candle de 2022. Se uma cópia de histórico estiver incompleta, o estado não avança; as entradas extras aguardam dados. Sinais históricos recuperados posteriormente não geram entrada atrasada.

Validações locais: núcleo causal, prioridades de entrada, limites dos filtros, adapter de histórico e corpos reais de execução/contabilização com respostas nativas simuladas. O replay dos 761 candidatos geométricos confirmou 1.522 comparações de filtros contra o estudo independente. Ele encontrou 138 candidatos extras no caso 2 e 205 no caso 3; respectivamente 76 e 142 ocorreram quando a referência estava sem posição. Esses números não são operações ou lucros simulados: novas entradas mudam a ocupação futura da carteira.

As bibliotecas e o código original da versão 1.90 foram preservados. Não houve compilação MQL5 nem backtest financeiro desta versão aqui. O histórico de 2022 a 2026 já foi examinado; os resultados deverão ser acompanhados de validação posterior em dados não usados na escolha das regras.

Para reproduzir os testes locais com Python 3 e g++: `python3 verificar.py`. As famílias antigas presentes nas bibliotecas continuam cobertas pelos testes de regressão, mas estão desativadas nos três perfis da rodada. `PLANO_RODADA_200.json`, `CASOS.csv` e `VALIDACAO.json` registram o protocolo, o hash do fonte e o resultado dos testes.
