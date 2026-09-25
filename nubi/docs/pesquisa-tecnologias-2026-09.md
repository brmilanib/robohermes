# Pesquisa: recursos novos da Anthropic (Console) e da OpenAI para o nubi — 25/09/2026

Feita pelo Chefe (Claude Code) a pedido do Bruno. Objetivo: usar melhor o que já pagamos, gastar menos e dar mais
autonomia ao time. Cada item: o que é · como ajuda o nubi · custo · risco · esforço. Os agentes opinam na Sala.

## O que o nubi usa hoje (conferido no código, `nubi/ia.py`)

- Claude: `POST /v1/messages` direto, modelo `claude-opus-5-5`, **sem cache de prompt**, busca na web com a versão
  antiga `web_search_20250305` e JSON extraído do texto (`perguntar_json` + `raw_decode`).
- OpenAI: já usa a **Responses API** (`/v1/responses`) e o **Batch API** (marcas em lote). Embeddings `text-embedding-3-small`.
- Ferreiro: Claude Code no Mac pela API (créditos do Console), ~US$ 0,25 por card pequeno.

## Anthropic — ganhos rápidos (baratos e de risco baixo)

1. **Cache de prompt** (`cache_control`). O coordenador manda o briefing grande (`agentes.SISTEMA` + caixa de conhecimento)
   em TODA chamada. Com cache, a parte repetida custa ~10% (leitura de cache no Opus 5.5: US$ 0,20/milhão, contra
   US$ 4,00 normal). Precisa: prefixo estável (sem data/hora no começo do system). **Maior economia imediata.**
2. **Esforço (`output_config.effort`)**: `low`/`medium`/`high`/`xhigh`/`max`. No Opus 5.5 o padrão é `medium`. Usar `low` no
   que é simples (distribuir cards, preencher os 4 itens, checagens) e `high` na coordenação e na auditoria.
3. **Saída estruturada** (`output_config.format` com JSON Schema, ou ferramentas com `strict: true`): a resposta já vem no
   formato exato. Acaba com os erros de JSON quebrado (cards #19/#20).
4. **Busca/leitura na web nova** (`web_search_20260209`, `web_fetch_20260209`): filtra os resultados antes de ler (menos
   tokens, respostas melhores). Usada no "é a mesma marca?" e na pesquisa de concorrentes.
5. **Lotes (Message Batches)**: **50% mais barato**, resposta em até 24 h. Para as rotinas da madrugada que não têm pressa:
   resumos, análises mensais, auditoria, classificações.
6. **Limites de gasto no Console** (Gerenciar → Limites de gastos) e uma chave por uso (servidor, Ferreiro): se algo sair
   do controle, o Console corta. Sem código.

## Anthropic — recursos maiores (valem um teste antes)

7. **Managed Agents** (beta; no Console: Agentes, Sessões, Implantações, Ambientes, Cofres de credenciais, Repositórios de
   memória). A Anthropic roda o agente **e** o computador dele (container com bash, arquivos, código). Serve para:
   - **Implantações agendadas** (cron): um agente que roda sozinho, p.ex. "todo dia 07:00 conferir os números da coleta",
     sem depender da Vercel nem do Mac;
   - **Cofres de credenciais**: a chave fica guardada na Anthropic e nunca aparece para o agente (troca na saída);
   - **Repositórios de memória**: memória persistente do agente (poderia ser a caixa de conhecimento do Hermes na nuvem);
   - **Outcomes** (resultado com rubrica): um avaliador separado faz o agente refazer até atingir os critérios de pronto;
   - **Multiagente**: um agente delega partes para cópias ou para um modelo mais barato.
   Custo: tokens + tempo de container. Risco: beta, dados na Anthropic. Sugestão: piloto com 1 agente agendado de conferência.
8. **Execução de código** (`code_execution_20260521`): o Claude roda Python num sandbox da Anthropic — analisar a planilha
   do estoque/vendas, fazer gráficos e devolver .xlsx/.pdf. Bom para o Estoquista e os resumos com números.
9. **Files API** (`/v1/files`): sobe a planilha uma vez e reusa em várias perguntas (menos tokens repetidos).
10. **Agent Skills** (Habilidades no Console): pacotes prontos (xlsx, docx, pptx, pdf) ou nossos (ex.: "relatório do nubi").
11. **Citações** nos documentos: a resposta aponta o trecho exato da fonte — bom para auditoria de números.
12. **Contagem de tokens** (`count_tokens`) e **API de Uso e Custo** (Admin API, chave de admin): custo real por dia e por
    modelo direto da Anthropic → aba Agentes e guarda de gasto (#50). Risco: a chave de admin é poderosa (risco alto).
13. **Advisor**: modelo mais barato executa e o Opus aconselha; **Compactação** e **edição de contexto**: conversas longas
   (Sala) sem estourar o contexto.
14. **Contas de serviço + Workload Identity Federation**: acesso sem chave fixa (ex.: GitHub Actions/Vercel).
15. **Fast mode** do Opus 5.5 (2× o preço, até 2,5× mais rápido): não compensa para nós hoje.

## OpenAI — o que vale olhar

1. **Responses API** (já usamos) — ferramentas nativas: busca na web, busca em arquivos (vector stores), Code Interpreter,
   **MCP remoto**; **modo background** para tarefas longas e compactação do histórico no servidor. A Assistants API está
   sendo desligada (meados de 2026) — não usamos, sem impacto.
2. **Batch API** (já usamos nas marcas, 50% mais barato): estender para resumos e classificações da madrugada.
3. **Cache de prompt automático**: já vale nos prompts repetidos; manter o começo das mensagens estável para aproveitar.
4. **Agents SDK**: orquestração de agentes com guardrails — alternativa à nossa Sala, mas o Python do nubi já faz o
   essencial; só se crescer muito.
5. **Geração de imagem** (gpt-image): criativos, posts e banners (roadmap item 4, card #14).
6. **Embeddings + busca em arquivos**: busca semântica na caixa de conhecimento e nos produtos (card #29).
7. **Evals** (e o nosso mini-benchmark #15): comparar modelos com casos do nubi antes de trocar.
8. **Realtime/voz**: futuro (lives, atendimento) — sem prioridade agora.
9. **Codex na nuvem** (já ligado no GitHub como agente parceiro): programar cards por tarefa no GitHub, como o Copilot.

## Proposta do Chefe (ordem sugerida)

1. Cache de prompt + esforço por tarefa + saída estruturada no `ia.py` (1 card, risco baixo; corta boa parte do custo do
   coordenador).
2. Busca na web nova (`_20260209`) no Claude (troca simples).
3. Lotes (50%) nas rotinas da madrugada, Claude e OpenAI.
4. Limite de gasto no Console (o Bruno configura) + chave separada por uso.
5. Piloto de Managed Agents: 1 implantação agendada de conferência de números, com rubrica (outcomes).
6. Execução de código para o Estoquista (análise com gráfico).
7. Geração de imagem da OpenAI para criativos (quando o card #14 andar).

Fontes: documentação da API da Anthropic (Messages, Prompt caching, Batches, Files, Skills, Managed Agents, Admin API);
OpenAI: changelog e "New tools and features in the Responses API" (openai.com), blog "OpenAI for Developers".
