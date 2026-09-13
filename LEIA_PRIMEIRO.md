# Hermes R200 - pacote para revisão no Claude

1. Leia Dossie_Hermes_R200.pdf: auditoria, gráficos, 57 meses de cada caso (56 completos), resultado anual e código completo no anexo.
2. Para facilitar análise de texto/código, use Dossie_Hermes_R200.md. O bloco do código mantém as linhas originais sem a numeração visual do PDF.
3. No Claude, anexe o PDF e os quatro CSVs da pasta dados_originais. Se necessário, anexe também Hermes_Pivos_Lab_200.mq5 ou o Markdown.
4. Cole o conteúdo de Pedido_Revisao_Claude.txt como solicitação de análise.
5. As pastas analise e auditoria_codigo contêm tabelas derivadas, verificações, evidências e scripts. O projeto completo do EA está em projeto_fonte, com módulos, presets e testes.

O caso 1 é a referência. Casos 2 e 3 são hipóteses executadas, ainda sem aprovação como melhorias. Lucros: USD 204.912,54 / 191.523,99 / 169.116,06. Meses completos negativos: 17 / 22 / 18. Setembro de 2026 é parcial e leva o caso 3 a 19 negativos quando incluído.

A execução nativa ocorreu no MT5 do usuário. A análise local concilia os exports; não substitui o relatório nativo de modelagem/ticks nem certifica o executável utilizado. Os quatro arquivos não contêm detalhes de todos os trades R200. O índice arquivos_comparacao aponta para as pastas individuais exportadas no computador do usuário; elas ainda não foram anexadas aqui.

Não confundir os 58/111 fills por PIVOT com 58/111 trades líquidos adicionais. A ocupação alterou também as entradas BASE. Nenhuma regra ou resultado novo foi criado para este dossiê.

Os scripts de pesquisa preservam referências aos caminhos do laboratório e às versões anteriores para rastreabilidade. Reexecutar todos os scripts pode exigir os arquivos históricos e o banco; o .mq5 único pode ser compilado com a biblioteca padrão do MT5. O banco completo atualizado é entregue separadamente, sem inflar este pacote.
