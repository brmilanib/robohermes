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
- Conta do Mercado Livre (29/09, autorizado pelo Bruno: "vamos logar uma conta minha que não uso, a mesma que criou a API"):
  o login é na página do ML (OAuth); o refresh_token fica CIFRADO em `ia_resumos` `meli|conta` (chave derivada do
  ML_CLIENT_SECRET, que só existe na Vercel) e o access_token só na memória. Única exceção à regra "nada de token no banco".
- Conta de VENDEDOR do ML (29/09 à tarde, Bruno: "vamos conectar sem problemas uma conta vendedor, a AURASCENT"): a conta
  conectada por OAuth passa a ser a AURASCENT (no lugar da BRUNOMILANI, que é conta sem loja e recebe 403 em /items e na
  busca). Mesmas regras: só LEITURA (o nubi nunca altera anúncio, preço ou pedido), refresh_token cifrado em `meli|conta`.
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

## DeepSeek (28/09, pedido do Bruno)

- **O DeepSeek faz SÓ 2 análises por dia** ("isso não existe essas IAs terem esse tanto de chamada"): `analise_foco` (dados
  coletados: Explorador, Concorrentes e Produtos, 09:15) e `analise_estoque` (estoque × vendas por anúncio). Só dentro de
  `with ia.deepseek_liberado():` o `ia.tem("deepseek")` é True; fora disso ele não existe (Sala, cards, reservas, Estoquista da
  importação pulam). 1 por dia mesmo pedindo de novo. O plano da semana (`analise_semana`) foi desligado. Saiu da distribuição de cards.

- As análises com o DeepSeek usam o **deepseek-v4-pro** (`ia.DEEPSEEK_MODELOS`); os flash (`DEEPSEEK_FLASH`) ficam de
  reserva se o pro recusar. Onde o DeepSeek é só reserva da IA grátis (textos do atendimento `gerar_ia`, resumo de pesquisa
  na internet) vai `modelo="flash"` (barato).
- **Frase de contexto da base (`saber._contextos_ia`) é SÓ gpt-oss grátis**: sem cota (429), o pedaço vai só com o cabeçalho
  e não tenta de novo por 10 min. Em 28/09 o DeepSeek de reserva fazia ~40 chamadas/h das MESMAS frases, comia o tempo dos
  vetores ("tempo esgotado antes de terminar todos os lotes") e nada era salvo (588 itens parados).

## Time enxuto (30/09, pedido do Bruno: "temos agente demais")
- Programam no Mac só o **Astra** (telas, design, estoque) e o **Ferreiro** (coletor, Mac, sites, servidor), um de cada vez no
  mesmo clone (`ferreiro_proximo` só com "astra" e depois o Ferreiro). DeepSeek programador, Navegador e Copilot pausados.
- As análises do dia (`analise_foco`, `analise_estoque`), a lista de compra e o chat de Compras usam o **Astra** (`_astra`, modelo
  do Astra na OpenAI) no lugar do DeepSeek. Leitura rápida do Estoquista pausada (env `NUBI_ESTOQUISTA` religa).
- Rotinas desligadas: `design` (time de hora em hora), `reuniao`, `auditoria` (IA), `rankeamento`, `memoria` (Hermes+Qwen).
  O coordenador só responde quando o Bruno escreve num card. Seguem: Hermes (vigia), Banguela (SAC), rotinas do ChatGPT
  (resumos, produtos iguais, marcas) e o Pesquisador sob pedido. Nada foi apagado: religar = `rotinas.ativo=true`.
- Pesquisador = **Astra** (30/09): `/pesquisar` roda na hora com o modelo do Astra + busca na web da OpenAI
  (`pesquisador._pelo_astra`, até 2 tentativas; relatório na Sala e em `saber`). `NUBI_PESQUISA_ASTRA=0` volta ao agente da Anthropic.
  Junto, o **Hermes** faz a 2ª pesquisa, grátis (`pesquisa_hermes`: busca na web do Ollama, até 8 páginas, + relatório do
  gpt-oss grátis), postada na Sala como Hermes e guardada em `saber`; 1 vez por pedido (`dados.hermes`). `NUBI_PESQUISA_HERMES=0` desliga.

## Compras e vendas do estoque (28/09, pedido do Bruno) — Estoque → 🛒 Compras e vendas (`#/estoque/compras`)

- Relatório do UpSeller **Análises → Vendas por Anúncio, últimos 30 dias** ("Vendas_por_Produtos_AAAAMMDD-AAAAMMDD_….xlsx":
  Produtos, Loja, SKU Principal, ID do Anúncios, Pedidos Válidos, Unidades Vendidas, Valor de Vendas, Preço Médio). O coletor
  baixa junto do estoque da madrugada (`baixar_vendas`, endereço achado guardado em `upseller_vendas_url`; falha nunca derruba o
  estoque) e manda para `estoque_vendas_importar`; também dá para importar à mão na tela. Guardado em `ia_resumos`
  `vendas_anuncio|atual` (linhas) + `vendas_anuncio|AAAA-MM-DD` (totais do dia).
- **Relatório de Vendas do Gestor Seller (card #124, 29/09)**: `baixar_gestor_vendas` (coletor, junto do estoque, Chrome novo,
  falha nunca derruba o estoque) abre Relatório de Vendas (endereço achado em `gestor_vendas_url`), põe os últimos 30 dias,
  marca todas as contas e clica só em "Baixar relatório de vendas" (nunca salvar/importar/excluir). Rota
  `gestor_vendas_importar` (`estoque.ler_gestor_vendas`: colunas casadas por palavra, cabeçalho até a 15ª linha) grava
  `gestor_vendas|atual` (linhas) + `gestor_vendas|AAAA-MM-DD` (totais). `por_anuncio` traz `margem_real_pct`/`lucro_un`
  (lucro do Gestor ÷ faturamento, por SKU) e a aba 📊 Por anúncio mostra "Margem real". Teste: `test_gestor_vendas.py`.
- `estoque.listas` (números em código, SKU casado sem maiúsculas): **zerados** (atual 0, os que venderam primeiro),
  **mais vendidos** (soma dos anúncios/lojas do SKU), **preciso comprar** (venda/dia = unidades ÷ dias; dura = (disponível +
  trânsito) ÷ venda/dia < `ALERTA_DIAS`=15, ou abaixo do mínimo; sugestão = `ALVO_DIAS`=30 dias de venda − disponível −
  trânsito). Rota `estoque_compras`; a análise do dia (`analise_estoque`, DeepSeek v4-pro, `ia_resumos` `analise_estoque|data`)
  aparece no topo da aba.

- **Reposição semanal, lista de compra e chat (29/09, pedido do Bruno)**: `estoque.plano_semanal` (código) = venda/dia ×
  (`REPOR_SEMANA`=7 + `SEGURANCA_DIAS`=7) − disponível − trânsito, só de quem vende; custo = ÚLTIMO preço pago
  (`estoque.ultimo_custo_pago` pelas últimas 12 fotos do estoque: entrada = (custo novo × qtd nova − custo velho × qtd velha)
  ÷ qtd que entrou; vinha zerado = custo novo; conta fora de 0,3–3× não chuta), senão o custo médio. A análise do dia
  (`analise_estoque`, mesma chamada, sem gastar outra) ajusta o plano e devolve `LISTA_JSON`; `estoque.lista_da_resposta` só
  aceita SKUs do plano e só muda quantidade/motivo (nome e custo SEMPRE do sistema). Lista em `ia_resumos` `compras|lista|atual`
  (botão "↺ Voltar ao plano base" = rota `estoque_lista`). A caixa "Análise do Estoquista" do Estoque mostra essa análise
  do dia (`analise_dia` na rota `estoque`); a leitura rápida grátis só aparece sem ela.
- **DeepSeek focado no estoque (29/09 à tarde, pedido do Bruno: "listas, preços, custo, frequência de venda, análise por
  anúncio, reposição")**: `estoque.listas` também devolve `anuncios` (`por_anuncio`: preço médio, custo médio, margem antes
  das taxas, `frequencia`, estoque do SKU), `precos` (`precos_diferentes`: mesmo SKU 15%+ mais caro em outro anúncio/loja)
  e `encalhados` (dura mais de `ENCALHE_DIAS`=90 dias ou sem venda; dinheiro parado = disponível × custo). Vão para a
  análise do dia (seções Anúncios, Preços e margem, Encalhados; `tabelas_extra`) e para o chat; abas novas em Compras.
- **Chat de Compras com o DeepSeek (29/09, EXCEÇÃO pedida pelo Bruno às 2 análises/dia)**: `conversar_compras` (rota
  `estoque_chat`, `PAPEL_CHAT_COMPRAS`, deepseek-v4-pro, dentro de `deepseek_liberado`), no máximo `COMPRAS_CHAT_MAX`=30
  mensagens por dia (env `NUBI_COMPRAS_CHAT_MAX`), conversa do dia em `compras|chat|<data>`. Se ele mandar `LISTA_JSON`, a
  lista é trocada (mesmas travas). Testes: `test_compras_estoque.py`, `test_compras_real.py` (a IA falsa responde o chat).
- **Card #122 (29/09)**: painel "📦 Estoque total" no topo do Estoque = `estoque.painel` (rota `estoque`, só de `listas`/
  `encalhados`; None = "sem dados", nunca zero inventado). Compras: ordenar por coluna (`cpTh`/`S.cpOrd`; no celular pelo
  seletor `#cp-ordsel`), filtro loja/canal (`#cp-loja`) em Por anúncio e Preços diferentes, tabelas `.cp-tab` viram cartões
  abaixo de 600 px. O export do UpSeller não tem fornecedor: a lista de compra fica sem agrupar (CSV igual).

- **DeepSeek programador do estoque (29/09, pedido do Bruno: "libera a branch de código pra ele de estoque, mexer no código e
  no layout")**: `coletor programar-deepseek <card>` = o mesmo Codex do Astra com o provedor da API do DeepSeek
  (`DEEPSEEK_PROG_MODELO`=deepseek-v4-pro, `DEEPSEEK_PROG_URL`), chave só no Chaveiro (`coletor guardar-senha deepseek`),
  branch `deepseek/card-N`, até `DEEPSEEK_CARDS_DIA`=6 cards/dia, só a parte do estoque; nunca publica (o Chefe revisa,
  PROGRAMADOR.md 1c). Cards com `responsavel='deepseek_mac'` (o id `deepseek` continua sendo o agente de texto da Sala);
  fila `ferreiro_proximo(quem="deepseek")` depois do Astra; os três dividem o clone (`_CLONE`, `PROGRAMADORES_PID`).

- **Estoque por categoria (30/09, pedido do Bruno: "igual ao ranking de marcas")**: aba 🏷️ Por categoria (`#/estoque/categorias`,
  rota `estoque_categorias`, `categorias.estoque_por_categoria`). O UpSeller não tem marca: `categorias.marca_do_titulo` pega a
  marca conhecida mais longa do título (lista do ranking `SEMENTE`, marcas do Explorador, `marca_categorias` e o último ranking de
  cada categoria); a categoria é a do ranking (`classificar`, a escolha manual vence). Também por tipo de produto
  (`tipo_produto`: Casa, Body splash, Skincare, Perfume) e por marca, com valor pelo custo e vendas de 30 dias do UpSeller
  (cobertura = unidades ÷ venda/dia). Itens com estoque sem marca no título aparecem numa lista. Teste: `test_estoque_categorias.py`.
  Cards e linhas clicáveis (`abrirEcLista`): lista dos produtos com a MARCA editável por SKU (`estoque_marca_salvar`, em
  `ia_resumos` `estoque|marca_sku`; vazia = volta ao título) e a CATEGORIA editável por marca (`ranking_categoria_salvar`,
  vale também no Ranking).
  30/09 (print: 343 SKUs em "Sem categoria"): `classificar` também olha a 1ª palavra ("Lattafa Yara" -> Lattafa = Árabe);
  `marca_do_titulo` ignora o conectivo ("Dolce and Gabbana" = Dolce & Gabbana). Botão "🤖 Pedir ao Astra" (rota
  `estoque_marcas_astra`, modelo do Astra, até `ASTRA_LOTE`=150 títulos): marca em `estoque|marca_sku_ia` (a do Bruno e a do
  título vencem) e categoria em `marca_categorias` só para marca que ainda não tem nenhuma.
- **Explorador: período analisado (30/09, "últimos 30 e 7 dias")**: o export é por período (sem venda por dia); cada período
  importado da marca vira um botão na página da marca (`periodosMarca`, rota `relatorio&periodo=<id>`, `escolher_periodo`:
  padrão = termina por último e mais longo; anterior = termina antes do escolhido começar). 7 e 30 dias aparecem quando o
  export desse período é importado. A Visão geral dos vendedores já tem 7/15/30 dias.
- **Explorador por quinzena (30/09, Bruno: "atualizar todas as marcas dia 02 e 16, ver se o mercado cresce ou cai")**: o
  Nubimetrics atrasa 2 dias, então dia 2 = 16 ao fim do mês anterior e dia **17** = 1 a 15 (`ultima_quinzena`).
  `explorador_quinzena_pendente` (dias 2–6 e 17–21, ou pedido `explorador|quinzena_pedido` pela rota
  `explorador_quinzena_pedir`) devolve até `EXPLORADOR_LOTE`=25 marcas sem o export da quinzena (busca = nome da marca,
  arquivo `MARCA__ini_fim.csv`); o coletor exporta no Explorador e manda para `importar` com `marca`, `inicio`, `fim`.
  Comando da Central `explorador_quinzena`. Comparação = período anterior (`escolher_periodo`). Teste: `test_explorador_quinzena.py`.
- **Scuderia (30/09)**: palavra que a coluna Marca põe ANTES da marca em 2+ anúncios ("SCUDERIA FERRARI") não vira linha
  (`nubi.prefixos_da_marca`, fim da etapa 3); `REGRA_ATUAL` = regra 8.
- **Pesquisa errada do GTIN (30/09, Bruno: "mais de 6 casos na semana", Maktub La Vie da Bidaya = "Outra marca: Jxumsyjn")**:
  a UPCitemdb devolveu para o 634240397363 um espelho de tomada ("Boho Gray Leaves…", marca JXUMSYJN) e a marca pesquisada
  mandava sobre tudo. Agora (`REGRA_ATUAL` = regra 9): (1) `nubi.cita_marca` = o que o PRÓPRIO anúncio diz (coluna Marca
  bate, ou título cita a marca sem citar a marca declarada — contratipo "New Brand (Lattafa Yara)" continua New Brand —,
  ou o SKU traz a marca); em `dono_do_anuncio` qualquer anúncio do GTIN citando a marca vence a pesquisa, e o nome
  pesquisado sai de `pesquisados` (não vota linha/volume). (2) `consultar_gtin` ignora resposta de base pública que não
  parece perfume/cosmético (`parece_perfume`) e deixa a IA pesquisar (`fonte_ia`, web). Teste `test_gtin_pesquisa_errada.py`.
- **Low price (30/09, Bruno: "contratipo tem que entrar na categoria low price, e decant também, tudo que é decant, 10ml,
  poucos ml")**: tipos `TIPO_DECANT` (decant/amostra/miniatura/mini no título, ou volume até `DECANT_MAX_ML`=15 ml; o
  `RE_VOLUME` lê 1 dígito: "5ml") e `TIPO_CONTRATIPO` (contratipo/inspirado/similar/genérico no título, ou anúncio de OUTRA
  marca cujo título cita a marca do export) — `nubi.tipo_low_price`, decidido por anúncio logo depois de `dono_do_anuncio`.
  (Ranking: `ranking_lista` põe primeiro a categoria com mais meses — Perfumes antes de Maquiagem, 30/09, "sumiu os de perfume".)
  Categoria `CAT_LOW`="Low price" (vence a "Categoria final" do arquivo), confiança `CONF_LOW`, produto "Marca Linha Decant
  10 ml"/"Marca Linha Contratipo 100 ml". Não votam no GTIN (entram em `fora`), não entram no `mapa_gtin_global` nem na
  etapa 4; pegam a linha pelo dicionário da etapa 2b. Resumo da marca: `un_low_price`. `REGRA_ATUAL` = regra 10. Teste `test_low_price.py`.

## Perseguir anúncios pelo Apify (28/09, pedido do Bruno) — Estoque → 🎯 Perseguir anúncios (`#/estoque/perseguir`), `perseguir.py`

- O Bruno cadastra anúncio (MLB… ou link) + palavra de busca (+ CEP e apelido opcionais), até `MAX_ANUNCIOS`=40. O robô do
  Apify `maximedupre/mercado-libre-product-rank-checker` (US$ 0,0025 por página; `PAGINAS`=5) confere a posição orgânica toda
  segunda (rotina `perseguir`, 1 disparo por semana) e quando ele pede (🔎). Assíncrono: `iniciar` guarda o run em
  `ia_resumos` `perseguir|execucao`; `conferir` (tela + cron de hora em hora) grava em `perseguir|historico` (60 por anúncio).
  Lista em `perseguir|lista`. Chave `APIFY_TOKEN` só na Vercel (o Bruno coloca). Rotas `estoque_perseguir*`.
- Listas do Estoque (entraram/saíram/zeraram/voltaram) trazem custo médio com a variação em % e, em saíram/zeraram, o que
  está em trânsito e o mínimo (verde se o trânsito cobre o mínimo): `_enriquecer_diff` na rota `estoque`.
- 28/09 (print do Bruno, tudo 0): a importação compara com a última foto de um DIA ANTERIOR (`diff.base`), não com a
  anterior do mesmo dia (várias no dia zeravam as listas). As mudanças são quadros clicáveis (`tileES`) e a lista
  completa (até 400 por tipo) abre no meio, grande, com busca (`abrirMudancasES`).
- Gestor Seller liberado no Mac pausado (28/09, "pode rodar no mac gestor seller"): `fila|mac_libera` = `estoque,gestor`;
  `gestor_pendente` devolve `no_mac` ao servidor; `_vigiar_pausado` faz o gestor por pedido ou horário. Login vencido no
  Gestor: `coletar_gestor` tenta `entrar_sozinho` e importa de novo 1 vez. Avisos de login dizem a máquina certa
  (`_onde_rodar`: Mac ou PC Windows).

## Anúncio sem GTIN no produto certo (29/09, "Xerjoff Outros") — `consolidar`, etapa 2b em `nubi.py`
- As linhas que a marca já tem pelos GTINs viram dicionário para os anúncios SEM GTIN que ficaram em "Outros"
  (confiança "Linha conhecida pelo título"). Mesma linha em outra ordem ("1861 Naxos"/"Naxos 1861") vira uma só,
  a que mais vende; palavras de anúncio (`LINHA_NAO_E`: decant, set, nicho…) não viram linha; se casar com várias,
  ganha a que mais vende. Mudou a regra → suba `REGRA_ATUAL` em `nubi_web.py` (reprocessa tudo uma vez no agente).

## Marca escrita errado, variações da linha e conferência diária (29/09, prints da Lattafa)
- `marca_bate` usa os apelidos da tela Nomes de marcas (`nubi.definir_apelidos`, carregado em `_preparar`) e aceita erro
  de digitação (`grafia_parecida`: mesma 1ª letra e números, 1 letra de diferença, 2 a partir de 7 letras; em nome maior,
  só palavras inteiras). "Lataffa" deixou de ser "Outra marca" na Lattafa; `variantes_da_marca` impede que vire linha.
- Etapa 2c: linha que tem variações conhecidas ("Fakhar" com "Fakhar Black"/"Fakhar Rose") é completada pelo nome
  pesquisado do GTIN ou pelo título que mais vende (`_completar_linha`: "Fakhar Extrait Gold" -> "Fakhar Gold");
  grafia cortada junta ("Platin"/"Platinum"). Produtos trazem `titulo_top` (título do anúncio que mais vende).
- Conferência das marcas (`auditar_explorador`, sem IA) roda 1x/dia no Agente do Explorador: nota por marca, marca
  escrita errado (reprocessa sozinho), outra marca grande (juntar em Nomes de marcas), linhas parecidas e o que mais
  vende em "Outros". Tela: Coletor e agente → 🧹 Conferência; rota `explorador_auditoria` (POST roda agora).
- Regra de agrupamento mudou → `REGRA_ATUAL` sobe (hoje "regra 7") e o agente reprocessa tudo uma vez.
- 30/09 (Ameerati da Al Wataniah preso na LIPX): `mapa_gtin_global` é refeito com os anúncios já gravados; os da marca
  que perdeu o GTIN ("Mesmo GTIN de outra marca") agora contam como presença dela, senão a dona errada nunca saía. Se a
  dona só tem anúncios trocados, o produto ganha o nome dela (linha/tipo/volume dos outros).
- Mesmo GTIN em marcas diferentes = mesmo produto (29/09, LIPX vendendo o Asad Elixir da Lattafa): `construir_gtin_global`
  grava em `ia_resumos` `explorador|gtin_global` o mapa `nubi.mapa_gtin_global` (dona = marca citada nos títulos com 20%+
  das unidades; senão a do GTIN pesquisado; senão a que mais vende; produto = o da dona; título = o que mais aparece, empate
  o mais longo). Etapa 4 do `consolidar`: na marca que não é a dona, o anúncio vira o produto da dona, tipo "Outra marca",
  confiança "Mesmo GTIN de outra marca". No relatório da dona, `_com_marca_trocada` traz esses anúncios (mesmo período)
  para o produto certo (`resumo.un_marca_trocada`, nota nas abas). O mapa é refeito na conferência diária e as marcas cujos
  GTINs mudaram são reagrupadas. "Arabe" não é nome de linha. Produtos: `titulo_top` = título que mais aparece.
- GTIN efetivo (29/09, ICARBONXX com o mesmo SKU, um anúncio sem GTIN): `nubi.gtin_efetivo` — sem GTIN, vale o do outro
  anúncio do MESMO vendedor com o MESMO SKU (se for um só); sem nada, o SKU quando é código de barras válido
  (`_ean_valido`). Só para agrupar (confiança "GTIN pelo SKU do vendedor"); o GTIN gravado continua o do arquivo.

## API oficial do Mercado Livre (29/09, pedido do Bruno) — `meli.py`, rotas `meli_*`, menu Concorrentes → 🛰️ Mercado Livre
- Objetivo: a loja VERDADEIRA (o Nubimetrics embaralha vendedor e anúncio: `ID do anúncio`/`ID do vendedor` são hashes de
  64, com chave secreta, conferido em 14.406 linhas e no botão copiar da tela deles), o link da loja e do anúncio, a foto e o preço de agora.
  Camada só de leitura POR CIMA do Nubimetrics: agrupamento, produtos e números continuam os nossos. Visual do HunterHub.
- Chaves `ML_CLIENT_ID`/`ML_CLIENT_SECRET` na Vercel (o Bruno coloca; nunca no código/banco/log/chat). Token do app
  (client_credentials) só na memória do servidor; erro nunca mostra segredo nem token. Sem as chaves: só um aviso 🔑.
- Hash -> loja (refeito 29/09, depois que o ICARBONXX P3 casou com a LUH20230609125415, loja sem Full e de 230 vendas):
  - o hash do Nubimetrics tem CHAVE SECRETA: 200 MLB da PUREHOME (loja do Bruno, relatório do UpSeller) x os 67 hashes
    dela no Explorador, em sha256/sha512/md5/sha3/blake2 e variações: nada bate. Não tentar desfazer;
  - o Explorador NÃO embaralha a coluna "Loja oficial" (`LOJA.OFICIAL.23829` = official_store_id do ML; 150 dos 1.603
    vendedores têm) e mostra, na coluna Vendedor, o NOME QUE O BRUNO DEU aos vendedores seguidos ("ICARBONXX P3") e o da
    loja dele (PUREHOME). `_linhas_nubi(..., com_bruto=True)` traz `loja_oficial_id` e `exposicao` da linha original;
  - `meli.ofertas_por_gtin` lê TODAS as páginas de `/products/{id}/items` (50 por vez, até 1.000, em paralelo depois do total
    da 1ª página; a 1ª versão lia 50 e a loja certa ficava depois; em produção o Asad Elixir passa de 300); `meli.casar` pontua cada loja: Full e tipo (Clássico/Premium) iguais e o nº da loja oficial
    igual são obrigatórios; preço do dia do export ("Último preço", export de até 5 dias) ±1% = exato; preço médio do mês
    do seguido só "perto"; cada produto conta 1 vez; idade do anúncio só quando o ML dá `/items` (hoje não dá ao app);
  - `meli.decidir`: "certa" = nº da loja oficial só desta loja + (2 produtos ou preço exato), ou preço exato em 3+
    produtos; "provável" = preço do dia + idade num produto, ou mais produtos que qualquer rival (≥ metade dos sondados e
    2) com preço batendo em 2 e 2 pontos de folga. Senão NÃO grava: devolve até 3 candidatas (link + prova) e o Bruno
    escolhe ("✔ É esta" = manual). Trava do Cowork: loja com menos vendas NA VIDA que metade das unidades do mês dele no
    Nubimetrics é descartada. O nome do seguido é rótulo do Bruno: só desempata (+1);
  - `meli.achar_loja` (vendedor inteiro: até 8 GTINs de catálogo, loja oficial e preço do dia primeiro) e
    `meli.casar_vendedores` (quadro do produto, 1 produto: só com loja oficial + preço, ou preço + idade);
  - De-para em `ia_resumos` `meli|hash_lojas` (hash) e `meli|seguidos` (nome do seguido), com `confianca`, `prova`,
    `oficial`, `votos`/`sondados`. Achar o seguido grava também o hash dele no Explorador (e vice-versa). Refazer sem prova
    tira o automático antigo; o "manual" nunca muda (a resposta diz se a busca "confere"). Feito antes da prova nova (sem
    `prova`) aparece "a conferir" (`_a_conferir`); "dúvida" não aparece. O relatório da marca traz `lojas_ml` e o `vid`.
  - Data de criação pelo nº do MLB (29/09): o ML não dá a data do anúncio de outra loja ao app, mas o nº do MLB cresce
    com o tempo em SEQUÊNCIAS separadas (nos anúncios do Bruno: 45xx–50xx de mar a ago/2026 e 61xx–73xx de jan a
    jul/2026). `_calibracao_mlb` junta os MLB do relatório de vendas por anúncio do UpSeller (`vendas_anuncio|atual`) com
    a "Data de criação" das lojas dele no Explorador (vendedores com 5+ SKUs dele: PUREHOME, AURASCENT), 1 vez por dia
    em `meli|calibra_mlb`; `meli.data_pelo_mlb` estima só entre 2 vizinhos da mesma sequência (≤ 90 dias) ou até 60
    dias depois do maior nº, com folga; `casar` compara com a "Data de criação" do Explorador ("criado"). Data batendo
    em 2+ anúncios = "certa"; preço do dia + data num produto = "provável". O botão 🔌 mostra a calibração. O Hunter
    mostra "Anúncio criado": foi assim que o Bruno viu que as datas da KAIDOXSTOREE batem com as do ICARBONXX.
  - O nº da loja oficial é da MARCA (a Mugler "por Auma Perfumaria"): vários vendedores podem estar na mesma (20309 em 5
    vendedores do Explorador). Por isso "certa" pela loja oficial só quando nenhuma outra candidata tem o mesmo nº.
  - ROCHA IMPORTADOS -> OUD_ESSENCE (errado, 29/09): todos os anúncios dele no Explorador são da loja oficial 14017 e a
    OUD_ESSENCE casou só pelo relatório do mês. Vendedor de loja oficial só vira "provável" sem a loja oficial batendo se
    o nome ou a data de criação baterem (`achar_loja`). Nenhum vendedor de loja oficial fechou pela loja oficial em
    produção (AUMA, VANVIC, ROCHA): o botão 🔌 confere, nas lojas que o Bruno confirmou à mão, se o nº do Explorador
    aparece nas ofertas delas no ML (`_conferir_oficiais`) — se não aparecer, o nº do Nubimetrics não é o do ML.
  - CONFERIDO no 🔌 (29/09): o nº "LOJA.OFICIAL" do Nubimetrics NÃO é o official_store_id do ML (WATHIQ 25357 x 361164,
    KLASSEY 25333 x 360842, BAGATELLE 20309/78630 x 220802). `casar` agora exige só "é/não é loja oficial" igual; o nº
    vira prova ("loja oficial nº") só com a tradução aprendida (`meli|oficial_nubi_ml`, `_oficiais`), que o nubi grava
    quando o Bruno confirma uma loja com 1 nº de cada lado (`_aprender_oficial`) e no 🔌.
  - FOTO (29/09, pedido do Bruno: "a foto do anúncio no Nubimetrics é a mesma do ML"): a foto NÃO vem no export; vem na
    resposta interna `analysisitems` que a tela do vendedor carrega. Coletor `fotos-vendedores` (comando da Central
    `vend_fotos`, roda no servidor gamdias onde o Nubimetrics está logado): abre a análise de cada seguido no mês atual,
    passa as páginas da tabela, `fotos_do_json` pega os objetos com link mlstatic (+ campos simples) e manda para
    `ml_vend_fotos` -> ia_resumos `vend_fotos|<vendedor>`; a página do vendedor mostra "📷 Fotos dos anúncios no
    Nubimetrics" (rota `meli_fotos_seguido`, com os nomes dos campos para conferir). Próximo passo: comparar com a foto do
    anúncio no ML. Teste 29/09: o Apify `sourabhbgp/mercadolibre-scraper` (busca, US$ 0,005/resultado) devolveu o
    MLB4350649763 com a foto 951134-MLB91143087125 (a do Cowork) — traz itemId e thumbnail, mas o vendedor só em loja
    oficial; `maximedupre/mercado-libre-search-scraper` NÃO serve (devolve a marca no lugar do vendedor, sem MLB).
  - EXTENSÃO DO CHROME "nubi · Mercado Livre" (29/09, igual à do Hunter): `public/extensao/nubi-ml/` (MV3; zip em
    `public/extensao/nubi-ml.zip`, refeito com `python3 testes/gerar_extensao.py`; teste `test_extensao.py`). Só lê:
    `fundo.js` busca a página do anúncio com o login do próprio navegador e tira do JSON dela vendedor, data de criação,
    vendas e loja oficial (`lerAnuncio`), e o perfil público `/users/{id}`; `conteudo.js` põe a linha da loja embaixo de
    cada anúncio da busca (3 por vez, até 60) e um quadro na página do produto, com "📊 nubi" (#/ml/loja/<id>). Sem login
    do nubi, sem token. Baixar/instalar: card "🧩 Extensão do Chrome" em #/ml.
    Versão 0.2 (29/09, prints do painel do Hunter: "quero essas mesmas funções"): quadro **nubi Spy** embaixo do preço (frete,
    comissão, valor recebido, visitas do catálogo/dia e % deste anúncio, vendas/dia, faturamento = vendidos × preço, nota nubi
    por regra — procura, conversão, reputação, preço x menor do catálogo —, tempo ativo pela data da página ou "≈" pelo nº do
    MLB, concorrentes do catálogo com a loja real, baixar mídias, perfil do vendedor) e o **painel lateral** (aba "n" →
    iframe `painel.html`: Início, Calculadora igual à do Hunter — taxa % da API + custo fixo abaixo de R$ 79, frete do ML ou
    customizado, imposto, lucro/margem/ROI —, Histórico em `chrome.storage.local`, Tendências, Gerador/conferidor EAN-13,
    Ajustes). Dado do ML vem da rota PÚBLICA `ext_ml`/`ext_categorias`/`ext_tendencias` (`rota_extensao`, antes do login em
    `atender`): parâmetros conferidos por regex (`meli.ext_parametros`), só dado público do ML com o token do app, cache
    30 min e até `EXT_POR_MINUTO`=90 pedidos novos por minuto; a data estimada usa a calibração lida com o login do agente
    (só pares nº→data). Nada do Bruno sai por ela. Testes: `test_meli.py` (rota) e `test_extensao.py` (quadro e painel).
    Busca (29/09, print do Bruno: "não achei a loja" em todos os cards): card de catálogo (/p/MLB…) pergunta ao nubi em lote
    (`ext_vencedores`, "pid:wid" = o anúncio do card entre as ofertas; sem wid, o buy box, marcado "quem ganha o produto
    agora"); o resto lê a página e, sem vendedor, a linha mostra o motivo (status, tamanho, título). Data "≈" pelo nº do MLB
    pode errar (print: ≈74 dias x 183 no Hunter): o quadro mostra o nº do anúncio para conferir a calibração.
    Versão 0.3 (29/09, print lado a lado com o Hunter: "deixe mais bonito igual a deles"): ícones de linha (`icones.js`,
    `window.nubiIcone`, carregado antes do conteudo.js e no painel), chips NORMAL/CATÁLOGO + tipo, Conversão (vendidos ÷
    visitas na vida, barra, "vende a cada N visitas"), Visitas (/dia, no total, em 30 dias, catálogo), Vendas/dia,
    Faturamento previsto, Projeção 30 dias (visitas de 30 dias × conversão), Tempo ativo pela 1ª visita, perfil do
    vendedor com termômetro de reputação. Data de entrada SEM /items: `meli.historico_visitas` lê
    `/items/{id}/visits/time_window` (365→180→150→90 dias, o ML limita) e o 1º dia com visita vira a data (se a visita
    começa no 1º dia da janela: "mais velho que"); visitas na vida por `/items/visits` desde essa data. Só estima pelo
    nº do MLB quando não há 1ª visita. Produção 29/09: a janela por dia vai até 150 e por semana/mês o ML recusa; anúncio
    mais velho mostra "+150 dias" (o Hunter tem a data porque usa o login de lojista). Inspeção da página /up/ (Claude no
    Chrome, 29/09): o estado vem em `<script id="__NORDIC_RENDERING_CTX__">` (blocos `melidata_event.event_data`: item_id,
    seller_id, seller_name, listing_type_id, category_id, logistic_type, `"quantity":98,"sold_quantity":500` = estoque
    exato e vendidos em faixa) e `components.header.reviews` {rating, amount}; a DATA DE CRIAÇÃO NÃO está na página. O
    quadro mostra estoque (e quantos dias dura), avaliações, selo FULL e o nome de exibição da loja.
    Versão 0.4 (29/09, print: vendedor "BRUNOMILANI" = o login do Bruno): na página /up/ o JSON vem num texto com aspas
    escapadas (\"seller_id\"); `lerAnuncio` desfaz o escape antes de procurar e o nome vem de `seller_name` (nunca de
    "nickname"/link de perfil, que podem ser de quem está logado). Layout na ordem do Hunter (tiles, conversão, visitas,
    vendas, nota, avaliações + tempo ativo, concorrentes, "Projeção de vendas" escuro + baixar mídias, calculadora) e o
    perfil do vendedor num cartão próprio embaixo do "Comprar agora" (`#nubi-ml-vendedor`, cidade "X - BR-UF", vendas SEM
    as canceladas = `vendas_ok` de `normalizar_loja`, como o Hunter: 25.957 x 26.173). O Hunter mostra a data sem a conta
    do Bruno conectada: a extensão testa o `/items/{id}` público do ML direto do navegador, sem token nem cookie
    (`itemPublico`); se o ML deixar, usa a data de criação, vendidos e estoque de lá; senão o quadro mostra o código.
    0.4.1 (29/09, print: "sem resposta do nubi (Failed to fetch)" e /items do navegador 403): as rotas `ext_*` respondem com
    `Access-Control-Allow-Origin: *` (e `api/app.py` responde OPTIONS) para a extensão não depender da permissão de site do
    Chrome; o servidor já devolvia certo (frete 24,45, comissão 30,84 = Hunter). `/items` público do navegador = 403: a
    data exata e o total de visitas na vida só com token de USUÁRIO do ML (OAuth da conta do Bruno) — decisão dele.
  - BUSCA DA EXTENSÃO PELA PÁGINA REAL (29/09, 0.7.1; print do Bruno com captcha em todos os cards): o coletor salvou a
    busca real (`coletor ml-pagina <url>`, comando `ml_pagina`, rota `ml_pagina_salvar` -> `ia_resumos` `ml|pagina|…`). A
    página NÃO traz o vendedor (0 "seller_id"); traz `printed_result` (item_id, PAD/ORGANIC, sold_quantity,
    first_shipping_logistic_type, price/price_base, product_id e o pid MLBP=catálogo/MLBU=produto do vendedor) -> `lerImpressos`.
    A extensão NÃO abre mais o anúncio por trás (3 em paralelo davam /captcha/wall/logged). `ext_lista` (pública) recebe
    "MLB:pid" e devolve vendedor + loja (MLBP: ofertas do catálogo; MLBU: /user-products, senão /questions/search), visitas
    de 30 dias e data pelo nº do MLB. Produção 29/09 na busca "assad lattafa elixir": 25 de 52 com catálogo (vendedor certo) e
    26 MLBU (vendedor só quando o anúncio tem pergunta). Teste com a página real em `testes/dados/ml_busca_real.html`.
  - 0.7.2 (29/09 à noite, print do Bruno no Chrome dele: "Vendas —" e "a página não trouxe o produto" em TODOS os cards):
    no navegador de verdade o ML tira o script `__NORDIC_RENDERING_CTX__` depois de montar (o coletor salvava antes).
    `cedo.js` (document_start) guarda a cópia do texto com `printed_result` (`globalThis.__nubiScripts`), `pagina.js`
    (world MAIN) manda `window._n.ctx.r`; `doCartao` lê no próprio card "+5mil vendidos", FULL, marca e preço.
  - 0.7.3/0.7.4 (30/09, prints lado a lado com o Hunter: "as lojas novas, anúncios novos não estão puxando"): nome da loja
    que o card mostra (`.poly-component__seller`) quando a API não diz; `ext_lista` dá a data pela 1ª visita dos últimos
    150 dias (`_primeira_visita`, cache 1 dia; `criado_por`), senão pelo nº do MLB; sem vendedor devolve `motivo`.
  - TESTE COM A AURASCENT (29/09, botão 🔌): mesmo com a conta de VENDEDOR, `/items/{id}`, `/items?ids=` e
    `/sites/MLB/search` dão 403; funcionam /users/me, anúncios da própria conta, descrição, catálogo, visitas, tarifa. O
    bloqueio é do APP no ML (DevCenter), não da conta. Vendedor de anúncio fora de catálogo segue sem fonte oficial.
  - PEDIDO AO ML (29/09 à noite): o Bruno abriu o caso **ODDS-22684** no DevCenter (App_id 1895184323212907, assunto
    "Solicitações usuários de teste" / Desbloqueio) pedindo leitura de /items, /items?ids=, /sites/MLB/search e
    /user-products. Resposta vem no e-mail do Bruno. Liberou -> rodar o 🔌 e ligar o multiget /items em `ext_lista`
    (vendedor, estoque, vendidos exatos, date_created, marca em todos os cards).
  - CONTA DO ML CONECTADA (29/09, autorizado): `#/ml` → 🔐 Conectar conta do ML (`meli_conectar` grava o `state` de uso
    único e manda para `auth.mercadolivre.com.br/authorization`); a volta `meli_retorno` é PÚBLICA (antes do login em
    `atender`, confere o state em 15 min, troca o código, `meli.conectar_conta`) e mostra uma página simples. Redirect URI
    cadastrado no DevCenter = `ML_RETORNO` (`https://nubi-explorador.vercel.app/api/app?r=meli_retorno`, ou env
    `NUBI_ML_RETORNO`). `meli._get` usa o token da conta quando há (`_token_usuario`: renova pelo refresh, o ML troca o
    refresh a cada uso e o novo é gravado cifrado; falhou, volta para o token do app e espera 10 min). `meli.cifrar/decifrar`:
    HMAC-SHA256 em contador + etiqueta (só biblioteca padrão). `meli_conta`/`meli_desconectar`; o 🔌 diz qual token vale.
    A extensão (`ext_ml`) passa a trazer `item` (data de criação, vendidos e estoque de /items) quando a conta funciona.
  - COMPARAR Nubimetrics x API do ML (29/09, pedido do Bruno: "tem que bater antes de trocar a fonte"): `#/ml/comparar`
    (`meli_comparar`, `comparar_loja`): uma loja já achada (seguido manual/certa/provável); `meli.foto_da_loja` (busca por
    loja + /items, precisa da conta) tira 1 foto por dia (`meli|foto|<loja>|<data>`, no 1º cron depois da meia-noite de
    Brasília, `fotos_comparar`; lojas em `meli|comparar`); `meli.vendas_entre_fotos` = quanto o "vendidos" de cada anúncio
    subiu entre duas fotos = vendas do dia pelo ML, ao lado de `vend_vendas_dia` (Nubimetrics) nos mesmos dias, e por GTIN.
    Avisa quando o vendido vem em FAIXAS (`vendidos_em_faixa`: números redondos 25/50/100/500…), porque aí a diferença não
    mede venda. Só trocar a fonte depois de dias batendo (✅ até 5%).
  - LOJAS REAIS, FASE 1 (card #121, 30/09): a extensão (0.7.1) manda à rota PÚBLICA `ext_coleta` (limite
    `EXT_COLETA_POR_MINUTO`=30, conta própria) o que a PÁGINA do anúncio aberta pelo Bruno mostrou: MLB, seller_id, nome da
    loja, preço, fotos do mlstatic (até 12), vendidos (`vendidos_faixa` = número redondo de faixa) e Full. `meli.ext_coleta`
    confere tudo; o que não veio fica None (lista `sem_dados`), nunca zero. 1 linha por anúncio em `ia_resumos`
    `ext_coleta|<MLB>` (com `em` UTC e `dia` de Brasília), sem tabela nova e sem senha/token/cookie. Preço de agora pelo
    catálogo: `precos_catalogo` (cron de hora em hora, até 60 s por rodada) lê `/products/{id}/items` (todas as páginas) de
    cada GTIN de `gtin_info` das marcas do Explorador 1 vez por dia -> `meli|preco|<gtin>` (ofertas, menor, total) e
    `meli|preco|dia` (os já lidos hoje). Sob demanda: `meli_preco_catalogo` (GET ?gtin=; POST {gtin}; POST {} as que faltam;
    POST {todos:true} relê todas). A página #/ml/loja/<id> com as fotos e o casamento pela foto ficam para o card seguinte.
    Teste: `test_ext_coleta.py`.
  - De-para do hash do Explorador feito pela regra antiga (sem `prova`) sai da tela (`_hash_ok`): o Bruno conferiu no
    Hunter e GLBRASIL2026/SHOP ELETRONICO estavam errados. Os seguidos antigos (AUMA, BAGATELLE) ficam "a conferir".
  - Caso real (29/09, provado pelo Cowork no navegador: foto do anúncio MLB4350649763, data 07/12/2025, R$ 149,90 e a
    vitrine): ICARBONXX P3 = KAIDOXSTOREE (2540338692), loja oficial nº 23829 (LIPX), gravado como manual.
  - A solução do Cowork (`meli_cruzar.py`: busca por palavra + mesma foto + data) NÃO roda com o token do app:
    `/sites/MLB/search` dá 403 e `/items` não devolve o anúncio. A foto do anúncio não vem no export do Nubimetrics (só
    na tela). Se um dia o ML liberar a busca para o app (DevCenter), a foto vira mais uma prova.
- Onde aparece: quadro do produto → "No Mercado Livre agora" (quem vende pelo catálogo, loja real, link, preço de agora) e
  o nome real embaixo do vendedor; quadro do vendedor → "🔎 Descobrir a loja real" / "Já sei qual é" (`meli_descobrir`,
  `meli_nomear`); `#/ml` (colar link, lojas identificadas, 🔌 testar conexão = `meli_teste`); `#/ml/anuncio/<link|MLB>`
  (cabeçalho, nota 0–100 com os pontos, KPIs, 🧮 calcular margem com tarifa/frete da API e o meu custo do UpSeller);
  `#/ml/loja/<link|id>` (perfil, NOSSOS números do Nubimetrics dos hashes ligados, insights, grade com filtros/exportar;
  cache 6 h em `meli|loja|<id>`). Rota genérica `meli_anuncios` (POST {anuncios, visitas}) para outras telas.
- Vendidos/estoque do ML vêm em faixas (+1.000); nota e insights são regras (sem IA). Testes: `test_meli.py` (dublê da
  API) e `test_ml_real.py` (tela, pc e celular, e sem as chaves).
- Produção (29/09, botão 🔌): o token do app funciona; catálogo pelo GTIN, visitas e /users funcionam; `/items?ids=` não
  devolveu o anúncio (cai para `/items/{id}` um por um; se o ML recusar, título/foto vêm do produto de catálogo) e
  `/sites/MLB/search` (busca por loja) dá 403 para o app — a página da loja usa os anúncios dela no catálogo dos GTINs que
  ela vende no Nubimetrics (`_gtins_da_loja`). Erro de login do app (`ErroLogin`) nunca vira "bloqueado" em silêncio.
- Vendedores SEGUIDOS (Concorrentes → Vendedores): o export não tem ID de anúncio nem loja oficial e o preço é o médio
  do mês; o `seller_hash` (128) não é o hash do Explorador (64). `_descobrir_seguido` junta o Explorador dele (achado pelo
  nome; se não achar, 3+ SKUs iguais, `_explorador_do_seguido`) com o relatório do mês e chama `meli.achar_loja`. Rotas
  `meli_seguido`, `meli_seguido_descobrir` (achou/loja ou candidatas + `explorador` {hashes, como, oficial}),
  `meli_seguido_nomear`; quadro "🏪 Loja no Mercado Livre" na página do vendedor. GTIN colado (13+13) é separado.
- Painel "🔗 Vendedores × ML" (`#/vendedores-ml`, rota `meli_seguidos_lista`, `_painel_seguidos`): todos os seguidos com
  hash, o mesmo vendedor no Explorador (hash + nº da loja oficial), anúncios/ativos/GTIN/catálogo/Full, faturamento,
  unidades, marcas, a loja real com a prova e "🔎 Descobrir"/"↻ Refazer" (e "Descobrir as que faltam"); sem prova mostra
  as candidatas com "✔ É esta". Diagnóstico 🔌 mostra se o ML manda o nº da loja oficial e quantas ofertas leu de quantas o catálogo tem
  (produção 29/09: o nº da loja oficial vem; `/items` e `/items?ids=` dão 403; a paginação funciona).
- `/items` de outras lojas não vem para o token do app: depois de 3 falhas seguidas o nubi para de pedir por 30 min.

## Quadro do produto no Explorador (30/09, pedido do Bruno) — `abrirVendedoresProduto` + rota `estoque_produto`
- Quadro largo (`.modal.larga.pq`): cabeçalho com o mercado (un., faturamento, preço médio e faixa, vendedores, líder) e
  o MEU lado vindo de `produto_meu`: vendo? (vendas por anúncio do UpSeller, 30 dias, por loja), meu preço médio vs.
  mercado, estoque (disponível, trânsito, mínimo, quantos dias dura), custo e margem antes das taxas, minha posição
  (nome das `ml_lojas` na lista de vendedores) e meus anúncios no ML. Casa pelo GTIN (SKU = GTIN), senão pelo nome do
  produto e títulos (`_casar_varios`; produto "Outros" só pelo nome). Número do nome conta: Torino 21 ≠ Torino 25.
  Teste de tela: `test_produto_quadro_real.py`.

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

## Regra do Bruno (30/09): o nubi não depende de concorrente

- **Visão do desafio #126 (palavras do Bruno):** decifrar o Nubimetrics — o vendedor vem com nome fictício e já temos vendas,
  anúncios e histórico dele; achar o vendedor de verdade no ML e LINKAR lojas e anúncios no nubi, para a aba do vendedor
  trazer a loja inteira (vitrine, vendas, o máximo de informação real). Depois, o mesmo nas outras plataformas.
  Duas coisas distintas, um motor só: (A) vendedor seguido → aba do vendedor com a loja inteira; (B) anúncio perseguido
  (Estoque → 🎯 Perseguir anúncios) → todo dia preço, estoque, ativo/inativo e posição, lado a lado com o anúncio do Bruno do
  mesmo produto, com alerta quando mexer. Depois: Amazon e Shopee pela mesma cadeia.

- O nubi é o software de ponta do Bruno: **não usa nem assina** JoomPulse, Real Trends, Hunter Hub, Mercado Radar, SellerRadar
  ou similares (o Hunter só serve de referência visual, no Chrome do Bruno). Fontes: API oficial do ML, a nossa extensão /
  Playwright (páginas públicas) e o **Nubimetrics** (assinado; sócio do ML; números tidos como os mais exatos). Apify e proxy
  só como infraestrutura de coleta bruta, nunca como produto. Pesquisas e cards que sugiram assinar concorrente estão errados.
- A "Pesquisa de mercado" do próprio ML (Seller Center) serve para conferir os números do Nubimetrics.

## Pausar e excluir cards (30/09, pedido do Bruno)

- Status `pausada` (`reuniao.STATUS`): card guardado fora da fila — nenhum agente pega (as filas só leem `aprovada`),
  `_situacao_card` devolve nada, e no quadro aparece dobrado em "⏸ Pausadas". Volta pelo seletor de status do card.
- Botão "🗑 Excluir card" no detalhe (rota `reuniao_tarefa_excluir`, POST `{id}`): apaga `tarefa_eventos` e o card; card em
  execução/teste não sai (mude o status antes). Só pelo login do dono; agente nenhum chama. Teste `test_cards_pausar_excluir.py`.
- 30/09: o Bruno pausou os 21 cards abertos para revisar; ficaram só o #125 e o **#126 (DESAFIO prioritário)**: ligar os 17
  vendedores seguidos à loja real do ML (nome, cidade/UF via `/users/{id}`, link) e trazer TODOS os anúncios deles ligados a
  `vend_anuncios`, com foto, preço, posição, vendidos, estoque e histórico diário (tabelas novas `vend_lojas_ml`,
  `vend_anuncios_ml`, `vend_anuncios_ml_dia`, autorizadas no card). Estratégias no card: API do ML, vitrine
  `lista.mercadolivre.com.br/_CustId_<id>` lida com as regras da extensão (`doCartao`/`cedo.js`), Apify, fotos do Nubimetrics,
  pesquisa do Astra + Hermes (origem "card #126"), Hunter só como conferência no navegador. Ferreiro implementa por etapas.
- Página **🎯 Desafio** (`#/desafio`, rota `desafio` → `painel_desafio`): cards `tipo='desafio'` (#126 Ferreiro, #127 Astra,
  #128 DeepSeek), `ETAPAS_DESAFIO` (situação pelos passos: relatório "etapa N … publicada" = feita), os 17 seguidos com loja
  real/cidade (`_painel_seguidos`), pesquisas cuja origem é "card #N" e a linha do tempo de todos os cards; escrever na página
  = `tarefa_responder` no #126. Teste `test_desafio.py`.
- Pesquisa pedida de dentro de um card (origem "card #N", `pesquisador._passo_card`): os relatórios do Astra e do Hermes (e os
  erros) entram no card como passos. O Astra espera até `TIMEOUT_ASTRA`=200 s (`ia.perguntar(timeout=)`); se demorou mais que
  `HERMES_DEPOIS_S`, o Hermes fica `pendente` e roda na próxima passada do `conferir`.
- DeepSeek (pausado fora das 2 análises) é liberado em `trabalhar_agentes` só para cards `tipo='desafio'` de que é o
  responsável (`ia.deepseek_liberado()`); entrega texto, que o Chefe confere.
  - Etapa 1 (30/09): `nubi_web.lojas_seguidos` pega cada seguido ligado de `meli|seguidos` (sem "dúvida"), lê a cidade/UF
    do perfil público (`meli.lojas` = `/users/{id}`, cache 7 dias) e faz upsert em `vend_lojas_ml` (migração
    `supabase/vend_lojas_ml.sql`, o Chefe aplica; sem a tabela, a tela mostra assim mesmo). Roda ao abrir `#/vendedores-ml`
    (`meli_seguidos_lista`, "📍 cidade - UF" na coluna da loja) e na rota `meli_seguidos_lojas`. Sem resposta do ML: cidade
    None. Teste `test_seguidos_lojas.py`.

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
- Busca local (card #29): o despachante do Mac gera o vetor (nomic-embed-text no Ollama local) de cada item novo de
  `conhecimento` (desde `VETOR_LOCAL_DESDE`, coluna `vetor_local` jsonb) pelo `mac_tick` (`vetorizar` → `vetores`).
  `buscar_conhecimento` (coletor.py) devolve os 5 mais parecidos; sem Ollama/vetores completa por palavras. Usada no `hermes-card`.

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
- **Tom de especialista e pergunta repetida (27/09, pedido do Bruno)**: `SISTEMA` regra 13: dado técnico (família, notas,
  concentração, fixação, lote, validade, conservação) usado e explicado para leigo. Regra 14 + `_resposta_anterior`: cliente
  que pergunta de novo algo já respondido (a mesma pergunta depois da NOSSA última resposta, no chat lido) recebe "Como te
  respondemos logo acima, …" com a resposta de antes; `_sem_eco` só descarta bloco de 2+ mensagens antigas lido de novo.
  Base: item "Qual a validade?" (loja todas, confirmado pelo Bruno): repostos toda semana, lote varia, após aberto ~2 anos.
- **Atendente mais robusto (27/09)**: no PC, `coletor atendente` agora é um vigia (`cmd_atendente_vigia`) que roda o atendente
  como filho (`--filho`) na mesma janela e o abre de novo na versão nova (código 3) ou se cair (o `os.execv` no Windows
  soltava a janela e o processo novo morreu às 11:13). Tela de login (`/login`, `accounts.`) encerra a rodada sem chamar a IA.
  `atendente_proximo` só chama na hora por resposta aprovada DEPOIS da última rodada (antes o Mac sem login na Shopee rodava
  a cada minuto e travava a fila do SAC). SAC: `fechados_concluido` só vale depois de 2 rodadas sem nada novo (`sac_vazias`);
  `JS_FOTOS` também acha fotos em `background-image` e pelo tamanho na tela.
- **SAC rápido e comandos para o PC (27/09, pedido do Bruno)**: importação do SAC com teto próprio `NUBI_SAC_TETO`=US$ 30/dia
  (`sac_gasto` no config do Mac, separado dos US$ 3 do atendente) e rodadas a cada 15 min (`SAC_A_CADA_MIN`; era 2, a CPU do Mac foi a 100%; comando `processos` mostra quem usa a CPU). Comandos do nubi
  para o atendente do PC (lista FECHADA `PC_COMANDOS`: status, limpar_marca, reiniciar, login <canal>): a sessão de código
  grava em `ia_resumos` `atendimento|pc_comando` (ou rota `atendimento_pc_comando`); o PC recebe junto com
  `atendimento_para_enviar` (`pc_comando`), executa (`_pc_comando`) e devolve em `atendimento_pc_resultado` (status feito + saída).
- **Limites do atendente (card #108)**: cada falha de `enviar_aprovada` vai ao nubi (`marcar_enviado` ok=false); a 2ª falha da
  mesma resposta (o `motivo` já começa com `ENVIO_FALHOU`) vira `precisa_info` com o motivo e sai da fila (`enviar_pelo_mac=false`);
  o coletor não tenta a 3ª. Até `ATENDENTE_PAGOS_RODADA`=5 passos com a IA paga por rodada (fora o SAC). Login encerra na hora
  e avisa a Sala uma vez só (`<canal>_login_avisado` no config, limpo quando a página abre sem login).
- **Shopee sem depender da IA (27/09, relatório do PC)**: antes da IA, `_enviar_aprovadas_direto` envia cada resposta aprovada
  da Shopee do jeito fixo (`_enviar_direto`): busca a cliente na caixa de busca, clica na LINHA certa (`JS_LINHA` marca o
  ancestral clicável do menor elemento com o nome; clique de verdade pelo Playwright, em qualquer quadro), confere o nome,
  acha o campo (`JS_CAMPO`: textarea/input/contenteditable mais baixo, sem ser busca) e o ícone de enviar, digita o texto
  APROVADO, envia (Enter; senão o ícone) e confere que a mensagem apareceu fora do campo (`_ja_no_chat`, também evita envio
  em dobro). `abrir_conversa` usa o mesmo clique. IA que pede licença ("posso prosseguir?") recebe "sim" e segue (até 3x).
  Marca não é gravada com "Atrasado/Expira em breve" pendente; a URL da Shopee só é salva se for `webchat`. Teto da IA paga
  conferido antes de cada passo. Vigia com relógio: o filho grava `atendente.vivo` a cada volta e passo; 15 min sem sinal →
  o vigia mata o filho (e o Chrome, `taskkill /T` no Windows) e abre de novo. Comando do PC `diagnostico <canal>` devolve a
  estrutura da página (campos, clicáveis, ícones) para ajustar seletores. No Windows o Python da Store aparece como
  `python3.12.exe` (procurar com `Name like 'python%'`).
- **Sem recarregar o chat (27/09, pedido do Bruno)**: recarregar a Shopee/TikTok a cada rodada fazia pedir captcha, e o
  chat já se atualiza sozinho. No PC cada plataforma tem uma aba fixa (`_aba_do_canal`) e `_no_chat` só abre o endereço
  se a aba ainda não está no chat. Conversa fechada pela Shopee ("fechada automaticamente", sem campo): `_enviar_direto`
  clica em "Recomeçar Conversa" (`_recomecar_conversa`, só esse botão) e digita.


## Servidor Dell do escritório (27/09, pedido do Bruno) — `coletor servidor`

- Windows 11, Xeon 6 núcleos, 64 GB, Quadro P4000 8 GB, 3 internets e nobreak: vira a máquina principal; o Mac mini fica de
  reserva e o gamdias (PC de casa) é a 2ª reserva do atendente. Senhas nunca passam pelo chat: o Bruno roda `configurar` lá.
- Ordem (27/09): gamdias = principal (`servidor`, prioridade 1), Dell = reserva (`servidor --reserva`, prioridade 2). Sinal por máquina em `ia_resumos` `fila|servidor|<nome>` (`atendimento.servidor_ativo`); o de reserva não pega fila nem atende (`computador=servidor:<nome>`) enquanto o principal dá sinal.
- `--so sac` assume só o SAC (gamdias, 27/09, enquanto o Dell não está pronto; Sala e vetores ficam no Mac); `--tudo` volta ao padrão.
- `py -3.12 coletor.py servidor` (`--instalar` põe `nubi-servidor.cmd` na pasta Inicializar do usuário; o Agendador negou acesso sem administrador): a cada
  minuto roda `vigiar` num processo novo (despachante + versão nova a cada ~5 min, `_vigiar_servidor`; sem as coletas com
  horário) e mantém o atendente ligado. `cfg["maquina"]="servidor"`.
- Fila: o servidor manda no `mac_tick` `maquina=servidor` e `pode` (`SERVIDOR_PODE`: importar_sac, hermes, qwen e os
  `servidor_*` de diagnóstico); sinal em `ia_resumos` `fila|servidor` (`servidor_pode`, 3 min). Com sinal, o Mac não pega
  esses comandos nem a Sala nem os vetores (`reserva`) e as filas do atendimento rodam só no tique do Mac (no do servidor só
  se o Mac estiver sem sinal, `_mac_vivo`). `servidor_*` nunca vai para o Mac. Coleta do Nubimetrics, estoque, Gestor,
  logins e Ferreiro/Astra seguem no Mac até estarem prontos no servidor (acrescentar em `SERVIDOR_PODE`).
- Despachante multiplataforma: `_rodar_solto` (Windows: `coletor rodar-logado <log> <argv>` grava saída e `.rc`), `_eu()`
  para chamar o coletor, comandos com PowerShell no Windows. No servidor o SAC usa o 2º perfil do Chrome (`perfil-sac`,
  trava `sac.pid`, cookies do `sessao.json` sem gravar por cima) porque o atendente deixa o perfil principal aberto.
- **Mac pausado (27/09, malware achado no Mac mini: minerador xmrig + porta dos fundos em LaunchAgent)**: `ia_resumos`
  `fila|mac_pausado` com o motivo → `mac_pausado`: o `mac_tick` do Mac só grava estado/saídas e devolve `pausado` (sem comando,
  Sala ou vetor; o vigia do Mac pula as coletas com horário); Ferreiro/Astra/Navegador ficam parados; as filas do atendimento
  rodam no tique do servidor. O servidor (gamdias) assume também `diario`, `estoque`, `gestor`, logins e Mercado Livre
  (`SERVIDOR_PODE`, `COLETAS`; o vigia do servidor roda as coletas com horário). Tirar a pausa = apagar a linha, depois da
  reinstalação do macOS e da troca de chaves. No servidor, coletas e logins usam o perfil `perfil-coleta` do Chrome (o atendente,
  `NUBI_PAPEL=atendente`, fica com o `perfil` principal sempre aberto).
- **Pausa tirada (29/09 à tarde, Bruno: "pode liberar o Mac, está tudo perfeito")**: linha `fila|mac_pausado` apagada
  ANTES da reinstalação do macOS (marcada para 30/09) — risco assumido pelo Bruno. O `seguranca_mac` continua de hora em
  hora. Ferreiro (card #120, extensão na busca) e Astra (card #121, lojas reais com fotos e preço) voltaram à fila.
- **Estoque liberado no Mac pausado + vigia de segurança (28/09, Bruno assumiu o risco)**: `ia_resumos` `fila|mac_libera`
  (texto `estoque`) → o `mac_tick` do Mac pausado devolve `libera`; o vigia do Mac pausado (`_vigiar_pausado`) só atualiza o
  coletor (sem rodar coleta por isso) e faz o estoque do UpSeller (pedido `coletor_pedido?tarefa=estoque` ou horário). Com o
  Mac pausado e com sinal (`_so_no_mac`), o servidor não recebe o pedido de estoque nem `estoque_pendente` (manda `maquina=servidor`).
  `seguranca_mac` (de hora em hora, mesmo pausado): CPU (top), processo xmrig/rigupdater (mata), `/private/tmp/rigupdater`
  (apaga), LaunchAgent `com.vsbgoqkgoyeuwbdw` (bootout + ~/quarentena); arquivo de inicialização NOVO desconhecido só avisa
  (lista conhecida em `seguranca_agentes` no config). Relatório na rota `mac_seguranca` → `ia_resumos` `mac|seguranca`;
  achado vai para a Sala ("Vigia de segurança (Mac)") e notificação no Mac.
- **Teto do Haiku de reserva (27/09, ~US$ 73 num dia)**: `_navegar_reserva` somava só `custo_usd`, que vinha vazio (Haiku
  sem linha em `ia_precos`): 2.440 chamadas sem parar. Agora o gasto é calculado pelos tokens (`_custo_haiku`) e há
  `NAVEGAR_MAX_DIA`=150 chamadas por dia; o Haiku entrou em `ia_precos`. Modelo novo usado em qualquer teto: cadastrar o preço.
- **Navegação só com IA grátis (27/09, pedido do Bruno)**: `_ia_atendente` usa as IAs locais do computador em ordem
  (`ATENDENTE_LOCAIS` = qwen3:8b, hermes3:8b; `NUBI_ATENDENTE_LOCAL`; `_modelos_locais`), depois o gpt-oss grátis do nubi.
  NUNCA IA paga: o servidor não chama mais o Haiku de reserva (`atendimento_navegar_ia` só devolve `erro_ia`). Todas fora =
  a rodada para e tenta na próxima. Interpretar/escrever/aprender continua com o Banguela (Sonnet).
- **Banguela (27/09, nome dado pelo Bruno)**: o agente pago do atendimento = `gerar_qualidade` (Sonnet 5, teto US$ 10/dia,
  cache do briefing). Cartão em `agentes` (id `banguela`), perfil e jeito em `agentes.py`; o custo vai em `agentes_uso` com
  agente `banguela` (`ia.USO["apelido_agente"]`). Buscar/ler chats (Shopee, TikTok, UpSeller) fica com a IA grátis local.
- **Painel do SAC clicável e taxas de resposta (27/09, pedido do Bruno)**: tudo no painel abre a lista certa (`spIr`: canal,
  aba `precisa`/`respondidas`/`sozinho`/`tudo`, conversa, loja do pedido, assunto `S.atAssunto`); a conversa que pisca abre o
  chat. Por canal: "📶 Taxa de resposta (plataforma)" = lida pelo atendente a cada 2 h (`_ler_taxa`, aba própria, só IA
  grátis, `TAXA_FERRAMENTAS`/`PAPEL_TAXA`, só lê) → rota `atendimento_taxa` → `ia_resumos` `atendimento|taxa|<canal>` com
  histórico; "📈 Respondidas pelo nubi (7 dias)" = `taxa_nubi` calculada no `painel`. Shopee: lida SEM IA na aba Data → Chat
  (`TAXA_PAGINA`, `_taxa_do_texto`: respondidos, não respondidos, tempo médio, CSAT e "Perguntas para Respostas"); IA só se a página mudar.
- **Botões do TikTok e Shopee fixa (27/09, prints do Bruno)**: `BOTOES_TIKTOK` (perguntas rápidas "Você tem esse produto em
  estoque?", "Já paguei"… e o nome da loja) entram em `_robo`; `liberar_so_aviso` (no `retomar_esquecidas`) tira de "precisa de
  você" a conversa cuja última mensagem de verdade é da loja (rascunho `sem_resposta`, nunca apagado). Shopee: atendente fica na
  aba "Atendendo Hoje" (`DICAS_PLATAFORMA`), a ferramenta `abrir` é recusada fora do SAC, depois do envio direto limpa a busca
  e volta para "Atendendo Hoje" (`_voltar_atendendo_hoje`); versão nova do atendente só a cada ~1 h (reabrir o Chrome recarrega).
- **Conversa certa, foto certa (28/09, prints do Bruno)**: o atendente só grava `registrar` com o nome do cliente no CABEÇALHO do
  chat aberto (`_conversa_aberta_e_de`/`JS_CABECALHO`: texto igual ao nome, à direita da lista e no topo); senão recusa e manda
  usar `abrir_conversa` (antes gravava foto/produto/pedido de uma cliente na conversa de outra). Foto que aparece em 3+ clientes
  diferentes é imagem fixa da tela, não do produto (`_fotos_genericas`, `_sem_foto_generica` no `receber` e na `fila`). Botões
  da tela ("Recomeçar Conversa", "Enviar pedido", "Nenhum registro"…) entram em `BOTOES_TIKTOK`; resposta nossa longa lida no
  chat de outra cliente é eco (`_enviados` inclui as respostas longas dos últimos 3 dias; a `fila` também).
- **Atendimento só de hoje e sem furos (28/09, prints do Bruno)**: fora do SAC a ferramenta `rolar` é recusada (a IA ia atrás de
  chats de agosto) e o pedido diz "só as conversas de hoje"; a Shopee volta para "Atendendo Hoje" com a busca limpa no começo e
  no fim de toda rodada. Resumo de cada rodada vai para `ia_resumos` `atendimento|rodada|<canal>` (rota `atendimento_rodada`,
  com as gravações recusadas pela trava do cabeçalho). `liberar_so_aviso` também tira o rascunho criado por RELEITURA (mensagem
  igual a uma anterior da cliente com a nossa resposta aprovada ainda esperando envio) e roda na hora no `atendimento_receber`.
  Base: "Tem bastante no estoque?" → "sempre temos bastante em estoque" (confirmado pelo Bruno).
- **Envio seguro (28/09)**: `para_enviar` só pega rascunho `aprovado`/`editado` (antes mandava até substituído/cancelado). Falha
  do envio direto vai ao nubi (`atendimento_enviado` ok=false, conta para as 2 tentativas) e aparece no resumo da rodada.
  `_cancelar_pendentes` (usado pelo `liberar_so_aviso`) NUNCA cancela rascunho que voltou ao Bruno por falha de envio. Envio
  direto: cliente antiga → aba "Todos os Chats" antes da busca (`_aba_todos_os_chats`); "Recomeçar Conversa" achado também pelo texto.
  Resposta que NÃO chegou (sem `enviado_em`, esperando envio ou com `ENVIO_FALHOU`) não conta como "já respondemos"
  (`_nao_entregues` → `_resposta_anterior`: nada de "Como te respondemos logo acima"); na tela ela aparece com
  "⚠️ não chegou à cliente (envio falhou)" (`falhou` nas `respostas` da `fila`).
- **Reenviar pelo nubi (28/09, pedido do Bruno: "tem que funcionar pelo nubi")**: resposta que falhou 2x (`_envio_falhou`) fica
  na tela mesmo com um rascunho novo descartado depois dela (`fila`, `rascunho.envio_falhou`); o campo vem com o texto e
  "🔁 Enviar de novo" chama `atendimento_reenviar` (`reenviar`: volta para a fila do atendente, pode editar, 2 tentativas
  novas). No coletor: "Recomeçar Conversa" confirma a janelinha e espera o campo (`_esperar_campo`, 10 s); a falha leva o
  rodapé da tela (`_rodape`/`JS_RODAPE`); o caminho da IA que não acha "o botão Enviar" (na Shopee é só ícone) usa
  `_enviar_direto`. Comando do PC `testar_envio <canal> <cliente>` abre a conversa e conta o que achou, sem digitar.
  Chat expirado (Shopee: "Não é possível reiniciar a conversa após 7 dias", `CHAT_EXPIRADO` no coletor e no nubi): não é
  falha para repetir nem para o Bruno; `marcar_enviado` põe o rascunho `sem_resposta` e a conversa `fechada` (caso joana, 28/09).
- **Conversas recentes, com data de verdade (28/09, Bruno: "os chats de hoje do TikTok não trouxe")**: proibir `rolar` fazia
  perder conversa nova abaixo do topo e, depois da meia-noite, as da noite ("Ontem"). Agora `rolar` vale até
  `ATENDENTE_ROLAR_MAX`=3 vezes por rodada (a lista volta ao topo no fim, `_rolar_topo`) e o pedido é "hoje e ontem".
  `registrar` recebe `data_ultima` (a data que a tela mostra); `_data_antiga` recusa conversa com mais de `DIAS_RESPONDER`=7
  dias (a joana era de 21/08, relida como nova porque o nubi grava a hora da LEITURA, não a da mensagem).
- **Chegou de verdade, releitura e fotos (28/09, Márcia no TikTok)**: `_atendente_digitar` só dá como enviada quando o texto
  aparece no chat (`_ja_no_chat`, até 6 s; senão erro, que conta nas 2 tentativas); a tela mostra "✓✓ chegou no chat".
  `receber` não grava de novo mensagem cujas linhas já estão nas da cliente (`_ja_recebida`, ≥ 15 letras: releitura com as
  linhas juntas ou separadas). O atendente manda as fotos que a cliente pôs no chat (`JS_FOTOS_CLIENTE`/`_fotos_da_cliente`
  → `pedido_dados.fotos_cliente`, até 6; imagem fixa da tela sai por `_fotos_genericas`); a tela mostra "📷 Fotos que … mandou"
  e os FATOS dizem `cliente_mandou_fotos` (não pedir de novo). `testar_envio <canal> <cliente>|<trecho>` diz se o trecho está no chat.
- **Análise de serviço do TikTok e painel limpo (28/09, prints do Bruno)**: `_taxa_tiktok_do_texto` lê, sem IA, a tela
  TikTok → Análise de serviço → Visão geral (taxa de resposta em 24 h, satisfação, tempo médio e `extras`: chats, só IA, só
  equipe, IA→equipe, conversão, receita/pedidos pós-atendimento, risco, sessões de hoje). Na 1ª vez a IA grátis navega até
  lá e o endereço fica em `tiktok_shop_taxa_url` (config); depois é leitura fixa (`TAXA_LEITOR`). `gravar_taxa` guarda
  `extras`. No Painel do SAC os números da plataforma ficam num bloco "📶 Na plataforma" com quadradinhos (`sp-chip`),
  sem quebrar as linhas do cartão.
