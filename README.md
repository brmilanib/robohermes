# Robo Hermes — XAUUSD M30 (projeto R200)

Repositório de trabalho do robô **Hermes** (Expert Advisor MQL5 para MetaTrader 5),
negociando **XAUUSD (ouro) em M30, apenas compras**, lote fixo 1,00, alvo nominal 5R,
uma posição por vez.

Este repositório reúne (a) o **pacote R200** entregue pelo proprietário e construído com o
ChatGPT, e (b) o **parecer independente do Claude** solicitado no dossiê. A divisão de
trabalho é a que o próprio dossiê propôs: o ChatGPT constrói e executa; o Claude revisa,
audita a causalidade e propõe experimentos falsificáveis. Nada aqui altera o fonte de
referência.

## Leia primeiro — o essencial, sem rodeios

- O backtest de 5 anos (US$ 10 mil → US$ 214 mil, caso Referência) é **impressionante, mas
  é resultado _in-sample_**: a mesma janela 2022–2026 foi usada repetidamente para pesquisar
  e escolher hipóteses. O próprio dossiê alerta para isto. **Não é previsão de futuro.**
- **~79% de todo o lucro veio de 2025 + 2026** — exatamente a alta histórica do ouro e a
  expansão de volatilidade. Com **lote fixo**, o robô é uma aposta altamente alavancada num
  regime específico do ouro. Isso pode não se repetir.
- O problema real a resolver **não é "meses negativos"** — é **risco/drawdown e dependência
  de regime**. Drawdown relativo de **42,76%**, risco de até **14,6% da conta num único
  trade**, até **13 perdas seguidas**.
- **Nenhuma estratégia garante "sem meses negativos" nem "renda alta garantida".** Perseguir
  isso adicionando filtros na mesma amostra histórica é _overfitting_ — e a rodada R200
  **provou** isso: as duas entradas de pivô pioraram lucro e consistência.
- O caminho honesto para renda durável em dólar: **normalizar o risco → validar fora da
  amostra → começar pequeno (DEMO, depois micro-real) → aceitar drawdowns**. Menos
  empolgante, mas real.

## O que está aqui

| Caminho | Conteúdo |
| --- | --- |
| `docs/PARECER_CLAUDE_R200.md` | **Parecer independente** — reprodução dos números, auditoria de causalidade (com função/linha), análise de risco/regime, resposta às 8 perguntas prioritárias, tabela evidência×impacto, dados faltantes. |
| `docs/PLANO_EXPERIMENTOS.md` | **Três experimentos priorizados** (falsificáveis, isolados) + protocolo de validação + **especificação de implementação do Caso 4** (sizing por risco) para o ChatGPT. |
| `projeto_fonte/` | Fonte completo do EA (módulos `src/`, presets, testes), como entregue. |
| `analise/`, `auditoria_codigo/`, `dados_originais/` | Tabelas derivadas, auditoria de código e os CSVs originais da rodada. |
| `Dossie_Hermes_R200.md` / `.pdf` | Dossiê original do proprietário/ChatGPT. |

## Achado central de engenharia

O **motor de dimensionamento por risco já existe e já foi testado** no EA
(`OpenCycle` em `projeto_fonte/src/EA.mq5:413-434`, `DCRiskLot` em
`projeto_fonte/src/DonchianCore.mqh:62`, e o modo `PERCENT_RISK` em
`projeto_fonte/src/XAU_H1_Core.mqh:70`). Os três casos R200 apenas rodam com ele
**desligado** (`dc.fixedLot=true`). Ativá-lo, como um **Caso 4 isolado** com as mesmas
entradas da Referência, é a mudança de maior alavancagem sobre o problema real — e é
pequena. Ver `docs/PLANO_EXPERIMENTOS.md`.
