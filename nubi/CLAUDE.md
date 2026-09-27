# Regras do nubi (para quem mexe no código)

**Horário: sempre o de Brasília (UTC−3)** ao falar com o Bruno, nos cards, na Sala, nos relatórios e nos horários de
rotina. O banco guarda em UTC: converta antes de mostrar ou escrever (ex.: 00:12 UTC = 21:12 de Brasília).

## Corrigiu, já roda (regra do dono)

Toda correção publicada é aplicada na hora, sem esperar a coleta das 7h:

1. **Coletor (Mac)**: publicar `public/coletor/coletor.py` basta. O vigia do Mac (launchd `com.nubi.coletor.vigia`,
   a cada 15 min) vê a versão nova, atualiza e roda `diario`, que completa só o que falta.
   Para forçar uma coleta sem versão nova: inserir um pedido em `coletor_pedidos` (ou o botão
   "Rodar coleta agora" em Central → 📥 Coletor).
2. **Servidor (resumos, produtos iguais, auditoria, categorias)**: depois do deploy, pôr
   `rotinas.ultima_execucao` de ontem na tarefa afetada (roda no próximo cron da hora) e, se o dado gravado
   estava errado, apagar o registro errado (ex.: `ia_resumos`) para ele ser refeito.
3. **Conferir depois**: ver no Supabase que a coleta/tarefa rodou e que o número bate (auditoria em Ajustes).

## Números

- Zero erro nos números: na dúvida, mostrar "sem dados" em vez de zero; dia sem arquivo de um vendedor = coleta
  pendente (fora dos totais), dia sem venda = linha zerada.
- A tabela do grupo do Nubimetrics (`vend_grupo_dia`) manda nos totais por vendedor quando existe.
- Preço de produto = "Preço Médio" do export do Nubimetrics (não vendas/unidades).

## Segurança e fluxo

- Senhas dos sites (Nubimetrics, UpSeller, Gestor) e a senha de app do Gmail: só no navegador do coletor (preenchimento
  automático do Chrome) ou no Chaveiro do Mac, digitadas pelo Bruno (`coletor guardar-senha <site>`); nunca no nubi, no
  banco, no GitHub, no chat ou no log (autorizado pelo Bruno em 25/09 para o login automático). Nunca copiar tokens,
  cookies ou chaves; nunca renomear os .xlsx.
- Branch de trabalho: `claude/wizardly-ritchie-5fig5i`; sem PR se não pedirem; não mexer no "Branch Tracking" da Vercel.
- Testar no servidor falso (fake_rest + servidor.py) e no mock do Nubimetrics antes de publicar.

## Sala de reunião e Desenvolvimento

- A cada sessão, ler `reuniao_tarefas` com status `aprovada` (fila de desenvolvimento) e as últimas mensagens de
  `reuniao_mensagens`; ao terminar uma tarefa, mudar para `feita` com uma nota e postar na sala como "Claude (código)".
- O Claude (API) coordena a sala e decide; a sessão de código confere cada tarefa aprovada antes de implementar.
- Agentes: `agentes.py` tem o briefing do sistema (`SISTEMA`, vai como system prompt na sala e na auditoria) e a lista
  `AGENTES` (ChatGPT com o Codex mais novo da conta, DeepSeek com o modelo pro para revisão). Agente novo (Hermes):
  acrescentar em `AGENTES` e a chave em `ia.CHAVES`. Ao mudar tabelas, telas ou rotinas, atualizar o `SISTEMA`.

## Roadmap aprovado pelo Bruno (24/09, tarefa #16)

1. Dados corretos e gates: conferências da auditoria (#5, #6, #7) e gate de publicação com reconciliação (#9).
2. Automações e custo: teto por provedor (#10), terminal remoto só com comandos permitidos (#11), uso/custo por agente (#17, #18).
3. Lojas do dono e marketplaces: StoreConnector, dry-run e retry por conector (#1, #2, #3).
4. Criativo (Gemini para imagem/post, #14), lives, promoções, cotação e compras.
5. Versão para marcas e sellers.
Modelos novos só entram depois do mini-benchmark interno (#15).

## Mini-benchmark de modelos (#15, 27/09) — `nubi_benchmark.py`, migração `supabase/benchmark.sql`

- **Nenhum modelo novo entra em produção sem passar por ele.** Casos fixos e versionados no código (`VERSAO`, `CASOS`:
  resumo do dia, texto de alerta e junção de produtos), rodados com as funções de produção (`_pedido_resumo_dia`,
  `_schema_secoes`, `produtos_iguais.agrupar`) e o modelo fixo (`ia.perguntar_estruturado(qual=, modelo=)`, sem trocar de
  provedor). Rota POST `agentes_benchmark_rodar` {modelo: "claude:claude-sonnet-5" | "embed:text-embedding-3-large"}
  grava 1 linha por caso em `ia_benchmark_execucoes`; GET `agentes_benchmark?modelos=a,b` mostra a comparação lado a
  lado (última rodada de cada modelo). Custo = `nubi_web.custo_usd` (uso × `ia_precos`); sem uso ou sem preço = NULL.
- Acerto: resumo = formato fixo com as 8 seções + termos do gabarito; alerta = cita os produtos do gabarito, não cita o
  que está bem e nenhum número fora da entrada; junção = F1 dos pares ≥ 0,9. Detalhes no topo do módulo.

## Aprovação de tarefas (delegação do Bruno, 24/09)

- O Claude coordenador (Sala) aprova sozinho as tarefas de risco baixo ou médio; risco alto fica como proposta com a
  pergunta em `aguardando`, e o Bruno aprova no card. Travas fixas em `reuniao.RISCO_ALTO` (senhas/chaves, apagar dados,
  estrutura do banco, pagamentos/compras, login do Nubimetrics, publicar para clientes) sempre vão para o Bruno.
- Na execução, a sessão de código decide os detalhes técnicos sozinha; só pergunta ao Bruno (evento `pergunta` +
  `aguardando`) o que for de risco alto.

## Quadro de Desenvolvimento (cards vivos)

- Ao começar uma tarefa: `status='em_desenvolvimento'`, `responsavel` (ex.: `claude_code`, `hermes`), `iniciado_em=now()`.
- A cada passo relevante: inserir em `tarefa_eventos` (`tarefa_id`, `autor`=id do agente, `tipo`='passo', `texto` curto).
  O card mostra o último passo e a animação de "trabalhando".
- Precisa de decisão do Bruno: `tipo`='pergunta' no evento e o texto da pergunta em `reuniao_tarefas.aguardando`.
  A resposta dele chega como evento `autor`='voce', `tipo`='resposta' (e limpa `aguardando`). Ler antes de seguir.
- Terminou: `status='feita'` + nota; aparece em "Novidades no nubi" na tela Início por 48 h.

## Aprovação de tarefas (delegação do Bruno, 24/09)

- O Claude coordenador (Sala) aprova sozinho as tarefas de risco baixo ou médio; risco alto fica como proposta com a
  pergunta em `aguardando`, e o Bruno aprova no card. Travas fixas em `reuniao.RISCO_ALTO` (senhas/chaves, apagar dados,
  estrutura do banco, pagamentos/compras, login do Nubimetrics, publicar para clientes) sempre vão para o Bruno.
- Na execução, a sessão de código decide os detalhes técnicos sozinha; só pergunta ao Bruno (evento `pergunta` +
  `aguardando`) o que for de risco alto.

## Agente do card (25/09)

- Quando o Bruno escreve num card, `responder_card` (nubi_web.py) responde na hora com o Claude (API): lê a tarefa e os
  passos, responde e pode pedir UM comando da lista fechada `COMANDOS_MAC` (grava em `mac_comandos` com `tarefa_id`).
  O despachante do Mac executa e a saída volta ao card como passo do autor `mac`. O agente do card não escreve código.
- "Em execução" só mostra "trabalhando" se houve passo nos últimos 20 min; senão o card aparece como ⏸ parado.
  Tarefa de código parada volta para `aprovada`, não fica fingindo execução.

## Quadro com teste e relatório (25/09)

- Colunas: Propostas → Aprovadas → Em execução → **Em teste** → Feitas. Em teste: `status='em_teste'` + `testador`
  (ex.: `revisor`); reprovou = evento `tipo='erro_teste'` e volta para `em_desenvolvimento`; aprovou = evento `teste_ok`.
- Ao concluir: `reuniao_tarefas.relatorio` (markdown: o que foi feito, arquivos, testes, revisão, publicação, como conferir,
  como reverter) + evento `tipo='relatorio'`. O programador automático segue `PROGRAMADOR.md` (rotina a cada 1 h, aos :40; até 3 cards; card 🩺 urgente primeiro).

## Time trabalhando sozinho (25/09)

- De hora em hora (rotina `design`): Astra/DeepSeek especificam; o coordenador (Claude) **distribui** os cards aprovados
  sem dono (`distribuir_cards`: código → `claude_code`; tela pequena de risco baixo → `copilot`, via issue no GitHub, passo 1b do PROGRAMADOR.md; texto → chatgpt/deepseek/astra/hermes); cada **agente faz** o card
  dele (`trabalhar_agentes`; Hermes pelo Mac com `hermes_card`) e entrega; o coordenador **testa** (`entregar_card`):
  aprovado → `feita` + relatório + aprendizado na caixa; reprovado → `erro_teste` e nova tentativa (máx. 3, depois
  pergunta ao Bruno). Entrega com `PRECISA_CODIGO` passa o card para o programador. Risco alto nunca anda sozinho.

## Ferreiro: Claude Code no Mac mini pela API (25/09)

- `coletor programar <card>` (o Hermes chama na hora em card 🩺 urgente novo; também pela Central): clone em
  `~/.nubi-coletor/projeto`, `claude -p` com a chave da API do Chaveiro (`coletor guardar-senha anthropic`), testes do
  repositório, commit e push SÓ no branch `ferreiro/card-<id>`; card vai para `em_teste` (`responsavel=claude_mac`,
  `testador=claude_code`) e o Chefe revisa, junta e publica (PROGRAMADOR.md passo 1c). Teto US$ 10/dia
  (`NUBI_FERREIRO_TETO`), modelo `NUBI_FERREIRO_MODELO`. Nunca publica nem mexe na branch do nubi. Perfis: `agentes.PERFIS`.

## Hermes vigia de erros (25/09)

- Tarefa do Mac que falha (`_executar` → `anotar_falha`, arquivo `~/.nubi-coletor/falhas.json`) chama o Hermes no próximo
  minuto (`coletor hermes-vigia`, pelo vigia). Ele diagnostica (`RECEITAS`; erro desconhecido: o Hermes no Ollama escolhe da
  lista fechada) e conserta sozinho: rodar de novo, navegador visível, destravar o perfil do Chrome, limpar downloads velhos.
  Login vencido (1 vez por site por dia): primeiro `entrar-auto` (senha do Chrome ou do Chaveiro; UpSeller: código lido no
  Gmail por IMAP, só leitura; máx. 2 tentativas; nunca "esqueci a senha"); não deu, abre a janela e o Bruno clica em
  Entrar; entrou, roda a tarefa de novo. Máx. 2 consertos por tarefa por dia; depois abre card
  `aprovada` (com os 4 itens do #44).
  Tudo que ele faz vai para a Sala como "Hermes".
- Erro que o Hermes não conserta (ou que volta depois de 2 consertos): card 🩺 **urgente** na hora (`responsavel=claude_code`,
  sem duplicar) + alerta 🚨 na Sala; a rotina **Plantão de urgências** (claude.ai, de hora em hora) resolve sem esperar o Bruno.
  Versão nova do coletor → `repetir-falhas` roda de novo o que falhou hoje. Card 🩺 fechado → `memorizar_solucoes` (rotina
  `design`) guarda "Solução: …" fixa na caixa; se o erro voltar, o Hermes mostra a solução na Sala e no card.
- Card aprovado sem os 4 itens do #44 não trava a fila: `completar_modelos` (rotina `design`) e o programador preenchem.

## Base de conhecimento própria (26/09) — ver docs/base-de-conhecimento.md

- Tudo o que o time diz, decide, erra, resolve e pesquisa na internet vai para a tabela `saber` (fase 1).
  A função do banco `saber_sincronizar` roda de hora em hora e antes das buscas; as pesquisas na internet entram na hora,
  pelo gancho `ia.USO["web"]`. Nunca apagar itens dessa tabela.
- Busca: `buscar_arquivo` (barra da Sala e `BUSCAR:` dos agentes).
- Fase 2 (26/09, `saber.py`, migração `supabase/fase2_saber_trechos.sql`): `saber_trechos` com pedaços de ~650 tokens,
  frase de contexto (cabeçalho fixo + frase do gpt-oss grátis nos itens longos) e vetor text-embedding-3-small (pgvector,
  HNSW). `buscar_hibrido` = significado + palavra (português, sem acento) com fusão RRF; os agentes ainda reordenam com o
  gpt-oss. Sem OpenAI ou sem pedaços, volta para `buscar_arquivo` (fase 1). `saber.indexar` roda no cron de hora em hora
  (itens novos/alterados pelo md5); `avaliar_saber` roda 1 vez por dia com 95% indexado (20 perguntas de `saber.AVALIACAO`)
  e posta o placar no card #83.

## Pesquisador nubi (26/09)

- Agente gerenciado da Anthropic (`agent_01NHnnK9D6xL385kM8FVxcxb`, console do Bruno) para pesquisa profunda.
  `pesquisador.py`: o nubi cria o ambiente (rede liberada) na primeira vez, abre a sessão com o contexto em português e
  modelo Sonnet 5 por sessão (`NUBI_PESQUISADOR_MODELO`), no máximo 3 fontes, teto de US$ 0,75 (budget da sessão,
  `NUBI_PESQUISA_TETO_CENTS`) e US$ 3 por dia (`NUBI_PESQUISA_TETO`). Primeiro teste (26/09, Opus 5, 7 fontes): US$ 1,05. Estado em `ia_resumos` `pesquisa|…`.
- Pedido: "/pesquisar pergunta" na Sala ou rota `pesquisa_pedir`. `conferir` roda no cron de hora em hora e quando a
  Sala é aberta: o relatório vai para a Sala, para `saber` (fonte `pesquisa_profunda`) e o custo para `agentes_uso`.
- Internet para todos os agentes (26/09): `agentes.com_arquivo` aceita `PESQUISAR:` (1 por resposta; limites
  `NUBI_WEB_POR_AGENTE`=6 e `NUBI_WEB_POR_DIA`=40, contados no `saber` pela etiqueta `agente:x`; recusa senha/chave/dado
  pessoal) e `PESQUISA_PROFUNDA:` só para o coordenador. Ordem: busca grátis do Ollama (`ia.ollama_web`) resumida pelo
  gpt-oss grátis (DeepSeek de reserva); a busca paga do Claude só se o Ollama falhar. Hermes e Qwen (Mac) usam a rota `agente_pesquisar`.

## Fotos e vídeos na conversa direta (26/09)

- 📎 na conversa direta: o navegador envia o arquivo original para o Storage (bucket privado `anexos`, caminho
  `sala/<agente>/…`), tira até 12 quadros do vídeo (JPEG 1280 px) e separa o áudio (WAV mono 16 kHz, até 12 min).
- O servidor (`preparar_anexos`) baixa só quadros/prévias e áudio, transcreve (`ia.transcrever`, gpt-4o-transcribe →
  whisper-1) e manda as imagens para quem enxerga (`agentes.ve_imagens`: ChatGPT, Astra, Claude). A transcrição fica no
  texto da mensagem (entra na base de conhecimento) e em `meta.anexos`. A tela mostra foto/vídeo com link assinado de 1 h.

## Astra com cards e Ferreiro com fila (26/09, pedido do Bruno)

- O Astra é o responsável por design, usabilidade e organização. Na conversa direta ele grava cards com
  `CRIAR_CARD: {json}` (`criar_cards_do_agente`, até 6 por dia, sem duplicar título; risco alto vira `proposta` com
  `aguardando`). Executor `ferreiro` → `responsavel=claude_mac`; `chefe` → `claude_code`.
- Fila do Ferreiro (`ferreiro_proximo`, em todo tique do Mac, 1 min, logo depois de gravar as saídas): se não há
  `programar_card` pendente/rodando nem card dele em andamento há menos de 90 min, pega o próximo `aprovada` com
  `responsavel=claude_mac` ou `claude_code` (🩺 primeiro, depois os dele, depois prioridade; card do Chefe no máximo
  `FERREIRO_TENTATIVAS`=2 vezes), pulando risco alto e card com `aguardando`. Voltou com ⏸ (sem chave, no teto): espera 1 h.
  O Chefe continua revisando e publicando o branch do Ferreiro.
- Card #89: aprovar ou atribuir um card (`tarefa_responder`, `reuniao_tarefa_salvar`) chama `assumir_aprovados`: distribui,
  roda um card de texto e põe o de código na fila do Mac na hora; quem não pode começar grava o motivo no card
  (`_motivo_card`, sem repetir). Pegar card é sempre com a trava `_pegar` (PATCH condicional em `status=aprovada`).
- **Astra programador** (autorizado pelo Bruno em 26/09): `coletor programar-astra <card>` usa o Codex da OpenAI no Mac
  com o modelo do Astra (`NUBI_ASTRA_MODELO`, chave da OpenAI só no Chaveiro: `coletor guardar-senha openai`), sandbox
  `workspace-write`, branch `astra/card-<id>`, testes do projeto, até 4 cards por dia; nunca publica. Cards com
  `responsavel='astra'` entram na mesma fila (`ferreiro_proximo(quem="astra")`, design primeiro; um de cada vez porque os
  dois usam o mesmo clone). Não pronto ou no limite: o card volta para `aprovada` com `erro_teste` e a fila espera 1 h.

## Agente Navegador (26/09, autorizado pelo Bruno)

- `coletor navegar <card>`: o Claude (API, `NUBI_NAVEGADOR_MODELO`) controla o Chrome do coletor com ferramentas próprias
  (abrir, ler, clicar, digitar, print, pedir_aprovacao, terminar). Regras no código: clique que muda algo só com aprovação
  do Bruno no card, nunca digita senha/cartão/documento/chave, só http(s), 30 passos e ~US$ 5/dia.
- Servidor: fila própria (`ferreiro_proximo(quem="navegador")`), prints em `navegador_print`, pergunta vira `aguardando`.
- Teste: `testes/test_navegador.py` (página local, Claude falso): http(s) só, bloqueios de clique e de senha, aprovação.

## Atendimento ao cliente (26/09, pedido do Bruno) — `atendimento.py`, migração `supabase/atendimento.sql`

- Módulo reusável por canal (`Canal`, `registrar_canal`): TikTok Shop primeiro; WhatsApp e Mercado Livre entram criando
  um Canal com `buscar_pedido` (store_orders por `source`) e `enviar`. Sem integração, `enviar` avisa "copie e cole".
- Fluxo: `receber` → `buscar_dados` (intenção por regras; pedido só com os campos de `pedido_seguro`, nunca endereço,
  telefone, documento ou valores; base `atendimento_kb` da loja e de "todas"; estoque do UpSeller) → sem dado =
  `precisa_info` + pergunta objetiva ao operador (nem chama a IA) → `escrever` (IA grátis `gerar_ia`: gpt-oss, DeepSeek de
  reserva, nunca a paga) → `conferir` (número fora dos dados, promessa fora da base e dado sensível barram; 1 nova
  tentativa) → rascunho `pendente`. Reclamação sem base/pedido sempre vai para o Bruno.
- Nada sai sem aprovação (`decidir`: aprovar/editar/rejeitar, grava `semelhanca`). `responder_operador` guarda a resposta
  do lojista na base (com quem confirmou e quando) e gera o rascunho de novo. Item novo de uma resposta antiga: `substitui`
  (a antiga fica `inativa` com `substituido_por`, nunca apagada). `metricas`: acerto = aprovado sem editar / decididos.
- Tela: Minhas Lojas → 🎵 TikTok Shop (`telaAtendimento`). Testes: `test_atendimento.py`, `test_atendimento_real.py`.
- **Atendente do Mac + resposta sozinha** (pedido do Bruno, 26/09 à tarde): `coletor atender-tiktok` abre o chat do
  Seller Center no Chrome do coletor (mesma trava do Navegador), traz as mensagens sem resposta (`registrar` →
  `atendimento_receber`, com o painel do pedido em `pedido_dados`) e envia as aprovadas (`enviar_aprovada`: o coletor digita
  o texto APROVADO, confere o nome do cliente na tela e o botão Enviar). Sem mudança na caixa de entrada e nada para enviar,
  não chama a IA (a assinatura ignora números e horários). Navegação com o **gpt-oss grátis** pelo servidor
  (`atendimento_navegar_ia` → `ia.ollama_ferramentas`, formato de ferramentas da Anthropic convertido); o Haiku
  (`NUBI_ATENDENTE_MODELO`) só de reserva, com teto `NUBI_ATENDENTE_TETO` US$ 3/dia (no teto, segue só com o grátis). Ligado no botão da tela
  (`ia_resumos` `atendimento|tiktok_atendente`); o tique do Mac chama a cada 5 min ou na hora se há resposta aprovada.
- **No PC do Bruno (Windows)**: `python coletor.py atendente` fica ligado com uma janela do Chrome no chat (a cada 2 min,
  `NUBI_ATENDENTE_SEG`); senhas no Gerenciador de Credenciais (`keyring`, `cofre_ler`/`cofre_gravar`). Enquanto o PC dá
  sinal (`atendimento|computador`, 10 min), o Mac não é chamado. `_processo_vivo` não usa `os.kill(pid, 0)` no Windows (lá
  isso ENCERRA o processo).
- **Shopee (26/09)**: mesmo módulo e mesmo atendente. Canal `shopee` (`CanalNavegador`), liga/desliga por canal
  (`chave_atendente`, `canais_ligados`); o coletor passa por cada plataforma ligada (`PLATAFORMAS`, `DICAS_PLATAFORMA`,
  config por plataforma em `_plat_cfg`). Tela Minhas Lojas → 🛍️ Shopee (`telaAtendimento("shopee")`).
- Responder sozinho (`pode_sozinho`, ligado por padrão, `atendimento|auto`): sai sem aprovação quando a pergunta está coberta
  pela base (`cobre` ≥ 0,75) e não é pedido/troca/reclamação, na saudação, e logo depois que o Bruno responde uma dúvida
  embaixo. O resto espera aprovação. O acerto mede só o que o Bruno decidiu; as automáticas contam à parte.
- **Robô da plataforma não é resposta (27/09)**: `ROBO_PLATAFORMA` tira do histórico o "Assistente AI" da Shopee ("Recebemos
  sua mensagem… aguarde", "não consigo responder, será transferido"); se a última mensagem de verdade é da cliente, a conversa
  ganha rascunho (só a aba Fechados fica como histórico). `retomar_esquecidas` (tique do Mac, a cada 3 min) faz o mesmo com
  as já gravadas como `respondida`. No coletor, `abrir_conversa` abre o chat pelo nome do cliente (a lista da Shopee não
  vira elemento clicável).
- **SAC do UpSeller → base (27/09, pedido do Bruno)**: botão "📥 Trazer o SAC do UpSeller" (aba Base de conhecimento) grava
  `atendimento|importar_sac`=pendente; `sac_proximo` (tique do Mac) põe `importar_sac` na fila a cada 10 min até o importador
  usar `fechados_concluido`. `coletor importar-sac` (Chrome do coletor, logado no UpSeller) lê o SAC com `PAPEL_SAC`: SÓ lê e
  registra (plataforma mercado_livre/shopee/tiktok_shop, sempre respondido+fechado), nunca envia nem digita; `rolar` desce a
  lista. As conversas viram propostas na base pelo `aprender_aos_poucos` (4 a cada 15 min).
- **Menu SAC (27/09, pedido do Bruno)**: o atendimento saiu de Minhas Lojas → menu **💬 SAC** (`#/sac/tiktok`, `#/sac/shopee`,
  `#/sac/ml` só histórico, `#/sac/base` = `telaBaseSac`, uma base para todas as lojas com filtro e ícone de origem;
  `#/estoque/tiktok|shopee` redireciona). Origem do item (`_com_origem`): etiqueta `canal:x` (propostas), conversa do
  rascunho de origem ou "chat de X"; senão manual. O atendente manda o cartão do produto que o cliente está olhando
  (`produto` → `pedido_dados.produto_consultado`): aparece no painel da conversa, na pergunta ao Bruno e nos FATOS (a IA não
  indica o mesmo produto). Conversa aberta ainda sem `pedido_dados.lido_em` sai dos "conhecidos" para ser relida uma vez.
- **Fichas, sugestão da internet e conversa com a IA (27/09, pedido do Bruno)**: `perfume_fichas` (migração em
  `supabase/atendimento.sql`): `fichar_aos_poucos` (tique do Mac, 1 a cada 3 min) pesquisa cada perfume COM estoque
  (`ia.ollama_web` + gpt-oss, `PAPEL_FICHA`) e grava notas/família/"inspirado em"/curiosidades com as fontes; status
  `internet` entra nos FATOS (`ficha_perfume`) mas a resposta passa pelo Bruno (`pode_sozinho`), `confirmada` responde
  sozinha. Tela: SAC → Base → 🧴 Fichas dos perfumes. Em "Precisa de você" a tela pede `atendimento_sugerir` (`sugerir_web`:
  internet + fichas do estoque → sugestão SÓ para o Bruno, guardada em `fontes.sugestao_web`). Dentro da conversa,
  "🤖 Conversar com a IA" (`conversar_ia`, `PAPEL_COPILOTO`, histórico em `ia_resumos` `atendimento|chat|<id>`) com ditado 🎤
  (Web Speech do navegador) e 🔊 leitura; "Usar como resposta" só preenche o campo, quem envia é o Bruno.
- **SAC completo (27/09)**: o importador manda o painel inteiro do UpSeller (nº do pedido e da plataforma, pagamento, loja,
  valor, comprador, logística, rastreio, itens) e `produto`; o coletor pega a foto do produto na página (`JS_FOTOS`, só
  foto de produto) e marca `pedido_dados.fonte=upseller_sac`. `conhecidos_sac` só conta as já importadas assim (as antigas
  são relidas uma vez). O valor e o comprador aparecem só na tela; `pedido_seguro` não passa isso para a IA.
- **Sonnet na escrita e na interpretação (27/09, pedido do Bruno)**: `gerar_qualidade(repo)` usa o Sonnet (`NUBI_ATENDIMENTO_MODELO`,
  API da Anthropic) em `escrever`, `conversar_ia`, `sugerir_web`, `aprender_padroes` e `revisar_propostas`, até
  US$ 10 por dia (`NUBI_ATENDIMENTO_TETO_USD`, soma do `custo_usd` em `agentes_uso` com origem `atendimento_sonnet`, dia de
  Brasília); passou, sem chave ou erro:
  gpt-oss grátis. Navegar no Chrome e fichas seguem no gpt-oss. O aprendiz novo descarta caso particular e resposta vazia e
  marca `produto:<chave>` quando a resposta depende do produto; `buscar_kb(produtos=…)` só usa item de produto quando a
  conversa é desse produto. `revisar_propostas` (tique do Mac, 5 a cada 2 min) revisa as propostas antigas (descartada =
  `inativa` + `descartada_ia`, nunca apagada).
- **Interpretação da conversa inteira (27/09, pedido do Bruno)**: `processar` chama `interpretar` (Sonnet, `PAPEL_INTERPRETE`)
  antes de tudo: lê até 20 mensagens e devolve intenção, se precisa responder e o que o cliente quer de verdade ("disponha"
  depois de resolvido = agradecimento; se a loja já se despediu, `responder=false` → rascunho `sem_resposta` e a conversa
  fica `respondida`). A intenção e a `pergunta_resumida` guiam `buscar_dados`; falhou, segue pelas regras.
  `reinterpretar_pendentes` (tique do Mac, 3 a cada 2 min) refaz as dúvidas e rascunhos antigos sem interpretação.
- **Eco, ✓✓ e Painel do SAC (27/09, pedido do Bruno)**: `_sem_eco` tira mensagem de "cliente" igual a uma resposta da loja
  (a leitura às vezes troca quem falou); `_ja_respondida` + `reinterpretar_pendentes` marcam como respondida a conversa cuja
  última pergunta já tem resposta aprovada/enviada. Na lista, conversa que precisa de resposta pisca e a respondida tem ✓✓
  verde (✓ cinza = aprovada, enviando). SAC → 📊 Painel (`#/sac/painel`, `telaPainelSac`, rota `atendimento_painel` =
  `painel`): precisam de resposta agora, respondidas hoje (e sozinho), mensagens de clientes, tempo mediano, por canal, por
  loja, 7 dias e assuntos; "📺 Modo TV" = tela cheia escura, atualiza a cada 60 s.

