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
