# Registro para os cards #126 e #127 — 30/09/2026

Não enviado ao banco: restrição explícita desta execução. O coletor/Chefe deve anexar estes passos aos dois cards.
Sem commit, push, publicação ou mudança de branch. Entrega separável em (a) backend e (b) tela.

## Etapa (a) — casamento
Implementadas regras do #128 já presentes no clone, foto exata, ligação ao Explorador do mesmo seller,
leitura das provas e ofertas por GTIN, persistência e conferência manual. Títulos e empates ficam a conferir.
Confirmação e recusa não são sobrescritas por nova rodada, nem pelo PATCH automático concorrente.
Rotas testadas com repositório falso. SQL apenas como contrato de integração, não aplicado.

## Etapa (b) — página
Página de vendedor seguido com anúncios reais, foto, preço/datagem, variação, Full/tipo, vendidos, posição,
estoque, link do ML e linha Nubimetrics. Busca, filtros, cobertura e conferência manual no celular e no computador.

## Pendências de aceite
- Texto integral do #126 e documento remoto do #128 não disponíveis no clone; usados o escopo do pedido,
  o resumo de CLAUDE.md e as regras/testes do #128 versionados. Solicitados ao Bruno para conferência complementar.
- Chefe deve conciliar/aplicar o contrato da tabela com a etapa 2 do Ferreiro e revisar/publicar.
- Não consultado nem alterado o banco real. Cobertura de 80% em SIENO./KLASSEYLOJA não foi medida;
  Bruno confirma com um vendedor após a coleta. Não confundir cobertura dos anúncios encontrados com vitrine completa.
- Testes visuais e fumaça dependem de executar fora do sandbox que bloqueia Chromium e servidor local.

## Resultado dos testes nesta execução
Python 3.12 do ambiente `venv-projeto` (o python3 padrão não possui Playwright).
Rodados todos os 85 `test_*.py`: 60 passaram, 25 falharam. `fumaca.py` também foi executado e falhou.
Os 16 casos de `test_seguidos_casamento.py` passaram, assim como `test_meli.py` e `test_seguidos_lojas.py`,
reexecutados após o ajuste final. Sintaxe de todo o JavaScript validada por `node --check`; `git diff --check` limpo.

24 falhas ocorreram ao iniciar servidor/navegador: sandbox nega bind/acesso ao localhost ou inicialização do
Chromium (MachPortRendezvous Permission denied); nos dois testes com Google Chrome o processo aborta na partida.
`fumaca.py`: Operation not permitted ao acessar o servidor local, antes de validar as rotas.
`test_ferreiro.py`: mesma asserção do histórico, no ambiente herdado do Aider. A hipótese inicial de busca textual
foi descartada, pois a conferência por nome exato também falhou. Coletor e teste original preservados.
Não há aprovação visual nem suíte totalmente verde. Não foram usados sites reais para validar a funcionalidade.

Resultado por arquivo (falha não foi ignorada nem convertida em skip):
```text
PASS test_agentes_uso.py 1.1s
PASS test_anexos.py 1.5s
PASS test_arquivo.py 0.5s
PASS test_assumir_aprovados.py 0.4s
PASS test_astra_cards.py 0.3s
PASS test_atendente_resumo_hora.py 0.5s
FAIL test_atendente_tiktok.py 0.1s
PASS test_atendimento.py 0.1s
FAIL test_atendimento_real.py 23.1s
PASS test_auditoria_produtos_iguais.py 0.6s
PASS test_benchmark.py 0.3s
PASS test_br.py 0.1s
FAIL test_busca_local.py 0.3s
PASS test_cache_claude.py 0.1s
PASS test_cache_embeddings.py 0.3s
FAIL test_caixa_pacotes.py 2.0s
FAIL test_card_detalhe_janela_central.py 22.4s
FAIL test_card_rolagem.py 0.3s
FAIL test_card_rolagem_real.py 22.5s
PASS test_cards_pausar_excluir.py 0.3s
PASS test_categorias.py 0.3s
PASS test_compras_estoque.py 0.4s
FAIL test_compras_real.py 22.7s
FAIL test_conversar.py 0.1s
PASS test_criativo.py 0.3s
PASS test_desafio.py 0.3s
PASS test_estoque.py 0.2s
FAIL test_estoque_categorias.py 22.9s
PASS test_explorador_quinzena.py 0.3s
PASS test_ext_coleta.py 0.3s
FAIL test_extensao.py 0.4s
FAIL test_ferreiro.py 4.3s
PASS test_foco.py 0.3s
PASS test_gate9_auma_2509.py 0.3s
PASS test_gate9_dia_sem_arquivo.py 0.2s
PASS test_gate9_unidades_faixa.py 0.2s
FAIL test_gestor_conferencia.py 0.0s
PASS test_gestor_sku.py 0.3s
FAIL test_gestor_vendas.py 0.2s
FAIL test_grupo_exportar.py 0.3s
FAIL test_grupo_exportar_coberto.py 0.3s
FAIL test_grupo_exportar_escondido.py 0.3s
PASS test_grupo_navegador_fechou.py 0.1s
FAIL test_grupo_vazio.py 0.5s
PASS test_gtins_iguais.py 0.3s
PASS test_hermes_memoria.py 0.2s
PASS test_hermes_vigia.py 0.3s
PASS test_ia_primeiro_json.py 0.0s
PASS test_ia_retry_429.py 0.0s
PASS test_ia_schema.py 0.0s
PASS test_inicio_decisoes.py 0.3s
PASS test_inicio_extras.py 0.3s
PASS test_internet_agentes.py 0.1s
PASS test_linha_conhecida.py 0.3s
FAIL test_lista_vendedores_recarrega.py 0.3s
FAIL test_login_auto.py 0.1s
PASS test_marca_prefixo.py 0.3s
PASS test_marcas.py 0.3s
PASS test_meli.py 0.4s
PASS test_memoria.py 0.4s
FAIL test_ml_real.py 22.7s
FAIL test_navegador.py 0.2s
PASS test_navegador_fechou.py 0.1s
PASS test_nomes_locais.py 0.2s
PASS test_painel_dia_dias_produto.py 0.8s
PASS test_periodos_explorador.py 0.3s
PASS test_perseguir.py 0.0s
PASS test_personalidade.py 0.1s
PASS test_pesquisador.py 0.1s
FAIL test_posicao_anuncio.py 0.6s
FAIL test_produto_quadro_real.py 22.2s
PASS test_produtos_iguais_conferencia.py 2.3s
PASS test_rankeamento.py 0.3s
PASS test_ranking_valor_abreviado_p75.py 0.3s
PASS test_retry_conector.py 0.3s
PASS test_reuniao_direta.py 0.4s
PASS test_saber_fase2.py 0.1s
PASS test_seguidos_casamento.py 0.3s
PASS test_seguidos_lojas.py 0.2s
FAIL test_servidor_fila.py 0.4s
PASS test_servidor_metricas.py 0.3s
PASS test_store_connector.py 0.0s
PASS test_tarefas.py 0.3s
PASS test_teto_custo.py 0.3s
PASS test_zeladores.py 0.1s
FAIL fumaca.py 21.9s
```
