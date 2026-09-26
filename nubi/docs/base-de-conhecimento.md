# Base de conhecimento própria do nubi

Pedido do Bruno (26/09): uma base de conhecimento **nossa**, no nosso banco, organizada com as mesmas técnicas que a
Anthropic e a OpenAI usam para dar memória aos modelos. Serve para os agentes lembrarem do que já foi dito, decidido,
errado e pesquisado. No futuro, vira o material de treino de um agente especialista do nubi.

## Como a Anthropic e a OpenAI fazem (e o que copiamos)

- **Treinamento ≠ memória.** O Claude e o GPT são treinados uma vez e ficam "congelados". A memória dos produtos deles
  vem de **recuperação (RAG)**: buscar o trecho certo e entregar ao modelo na hora da pergunta.
- **OpenAI (File Search / vector stores).** Divide cada documento em pedaços de ~800 tokens, gera um vetor de significado
  (embedding) para cada pedaço e faz busca **híbrida**: por significado e por palavra. Depois reordena os melhores.
- **Anthropic (Contextual Retrieval).** Antes de gerar o vetor, a IA escreve 1 ou 2 frases de **contexto** para cada
  pedaço ("este trecho é da reunião de 25/09 sobre o Início…"). Junta busca por significado com palavra-chave (BM25) e
  reordena. Segundo a Anthropic, isso reduz em 49% a 67% as buscas que falham.

## Fases

| Fase | O quê | Situação |
|---|---|---|
| 1 | **Base única** (`saber`): tudo num lugar, com tipo, data, autor, fonte e links; toda pesquisa na internet guardada | ✅ 26/09 |
| 2 | Pedaços com **frase de contexto** + **vetores** (pgvector) + busca **híbrida** (significado + palavra) + **reordenação** | próxima |
| 3 | Organização viva: Hermes/Qwen marcam duplicado, velho e contraditório; decisão nova substitui a antiga (`substituido_por`) | depois |
| 4 | **Conjunto de treino** (perguntas e respostas revisadas) para um agente próprio do nubi | futuro |

## Fase 1 (no ar)

- **Tabela `saber`**, com uma linha por fato. `tipo` é um de: conversa, decisao, duvida, erro, solucao, card, analise,
  rankeamento, pesquisa_web, conhecimento, regra ou procedimento. Colunas principais: `titulo`, `texto`, `autor`,
  `conversa`, `links`, `tags`, `meta`, `criado_em` (data do fato) e `substituido_por` (fase 3). A origem fica em
  `fonte_tabela` + `fonte_id`, sem duplicar.
- **O que entra.** A função `saber_sincronizar(desde)` no banco é idempotente. A rotina roda de hora em hora (no cron
  das rotinas) e também antes de cada busca, no máximo 1 vez por minuto. Ela junta:
  - `reuniao_mensagens`, com o tipo: decisão do coordenador, dúvida, erro/alerta, análise ou conversa;
  - `conhecimento` (regras, procedimentos, decisões, soluções, aprendizados);
  - `reuniao_tarefas`: card; card 🩺 = erro; 🩺 feito = solução, com o relatório;
  - `coletor_execucoes` que falharam (erros do Mac);
  - `ia_resumos` (resumo do dia, onde focar, plano da semana, notícias);
  - `rank_box` (Laboratório de Rankeamento).
- **Toda pesquisa na internet.** Qualquer `ia.perguntar(..., web=True)` (Claude ou OpenAI) grava na hora um item
  `pesquisa_web` com a pergunta, a resposta, os links e a rotina de origem (gancho `ia.USO["web"]`, ligado em
  `ligar_registro_uso`).
- **Busca.** A função `buscar_arquivo(q, lim, tipos)` ignora acentos e maiúsculas, e todas as palavras precisam aparecer.
  Quem usa:
  - a barra de pesquisa da Sala;
  - a ferramenta `BUSCAR:` dos agentes (reunião, conversas diretas e Laboratório);
  - `agentes.buscar_arquivo`.
- **Nada é apagado.** Decisões antigas continuam lá. Na fase 3 elas ganham `substituido_por`.
