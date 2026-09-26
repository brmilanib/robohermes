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

## Fase 2: dicas de otimização (26/09)

Fontes: guias de boas práticas da [Blip](https://community.blip.ai/studio-219/guia-de-boas-praticas-criando-bases-de-conhecimento-para-agentes-de-ia-5430)
e da [Clint](https://ajuda.clint.digital/pt-BR/articles/12052517-como-construir-uma-base-de-conhecimento-para-o-seu-agente-de-ia).
O artigo da Creativia foi lido pelo Pesquisador nubi em 26/09; as dicas dele estão na seção seguinte.

1. **Um assunto por pedaço.** Pedaço curto, com começo e fim claros (uma decisão, um erro e sua solução, uma regra).
   Pedaço misturado atrapalha a busca.
2. **Pergunta e resposta.** Sempre que der, guardar no formato "pergunta → resposta", que é como os agentes perguntam.
3. **Metadados em todo pedaço:** tipo, data do fato, autor, fonte (link ou tabela) e validade. Filtrar por eles antes
   de buscar (ex.: só `decisao` dos últimos 30 dias).
4. **Frase de contexto** (técnica da Anthropic) no começo de cada pedaço: de onde veio, quando e sobre o quê.
5. **Tamanho e sobreposição.** Pedaços de ~300 a 800 tokens, com uma pequena sobreposição entre pedaços do mesmo texto
   longo, para não cortar uma ideia no meio.
6. **Sem duplicado e sem contradição.** Mesmo assunto repetido vira um só; decisão nova marca a antiga como substituída
   (base da fase 3).
7. **Revisão fixa, pelo menos a cada 15 dias.** Uma rotina lista o que está velho, duplicado ou contraditório e o
   Hermes/Qwen propõe a limpeza (sem apagar: marca `substituido_por`).
8. **Teste com perguntas reais.** Um conjunto de 30 a 50 perguntas que o Bruno e os agentes já fizeram, com a resposta
   certa. A cada mudança, medir quantas a busca acerta (taxa de acerto) e só publicar se não piorar.
9. **"Não sei" é resposta válida.** Se a busca não achar nada relevante, o agente diz que não encontrou na base, em vez
   de inventar.
10. **Citar a fonte.** Toda resposta que usa a base mostra de onde veio (tipo, data e link), para o Bruno conferir.

### Creativia: "Como criar uma base de conhecimento para um agente de IA" (18/08/2026)

Lido por inteiro pelo Pesquisador nubi em 26/09 (relatório completo na base: "Pesquisa profunda"). O artigo trata de
governança e organização, não de técnica: não traz frase de contexto, RRF nem números. O que ele acrescenta à fase 2:

11. **Dono, data, versão e fonte oficial em cada item.** Nada entra no índice sem data e dono. Regra ou taxa de
    marketplace desatualizada vira resposta errada com cara de certa.
12. **Metadados como filtro antes da busca:** plataforma, tema, data da fonte, versão, link e nível de acesso. No pgvector,
    o filtro com índice HNSW roda depois da varredura: usar índice parcial por plataforma ou `hnsw.iterative_scan`.
13. **Testes negativos:** perguntas fora da base, ambíguas, confidenciais, com premissa falsa, sobre versão antiga,
    misturando políticas e fora do escopo. A base precisa passar nelas antes de publicar.
14. **Métricas:** acerto da busca (recall@20), precisão contra a fonte, respostas sem evidência e resolução sem o Bruno.
15. **Duas versões da mesma regra:** mostrar as duas com a data e perguntar, nunca escolher sozinho.
16. **Não jogar tudo na base** e não tentar resolver com prompt o que é problema de dado.

Parâmetros técnicos confirmados nas fontes oficiais (Anthropic, OpenAI e pgvector):
- frase de contexto de 50 a 100 tokens, aplicada no vetor **e** no índice de texto (o maior ganho vem dos dois juntos);
- pedaços de 800 tokens com 400 de sobreposição para começar (testar 400/200 nas tabelas de taxas);
- busca híbrida: `tsvector` em português + `vector`, fundidos por RRF;
- reordenar cerca de 150 candidatos e entregar os 20 melhores;
- glossário de perfumaria (árabes, body splash, decant, GTIN) no pedido que escreve a frase de contexto.

Ponto de atenção: a Anthropic diz que uma base menor que cerca de 200 mil tokens cabe inteira no prompt com cache, sem RAG.
A `saber` tinha cerca de 120 mil tokens em 26/09, mas cresce todo dia. A fase 2 continua valendo, e um teste próprio em
português vem antes de confiar nos números publicados, que são em inglês.
