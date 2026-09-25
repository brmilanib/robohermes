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
