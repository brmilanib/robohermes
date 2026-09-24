-- Esquema do nubi no Supabase (Explorador de anúncios).
-- Acesso: só os e-mails listados em public.acesso veem e alteram os dados (RLS).

create table if not exists public.acesso (
  email text primary key
);

-- Checagem de acesso num schema privado (fora da API REST).
create schema if not exists privado;
grant usage on schema privado to authenticated;

create or replace function privado.nubi_autorizado() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.acesso
    where lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;
revoke execute on function privado.nubi_autorizado() from public;
grant execute on function privado.nubi_autorizado() to authenticated;

create table if not exists public.snapshots (
  id bigserial primary key,
  marca text not null,
  inicio date not null,
  fim date not null,
  dias int not null,
  arquivo text,
  hash text unique,
  importado_em timestamptz not null default now()
);
create index if not exists snapshots_marca_fim on public.snapshots (marca, fim);

create table if not exists public.anuncios (
  id bigserial primary key,
  snapshot_id bigint not null references public.snapshots (id) on delete cascade,
  titulo text, vendedor text, vendedor_id text, marca_anuncio text, categoria text,
  produto text, linha text, volume text, tipo text, genero text, confianca text,
  gtin text, sku text,
  un int, fat double precision, preco double precision,
  un_hist int, fat_hist double precision, dias_pub int, exposicao text,
  catalogo smallint, "full" smallint, flex smallint, internacional smallint,
  loja_oficial smallint, frete_gratis smallint
);
create index if not exists anuncios_snapshot on public.anuncios (snapshot_id);

create table if not exists public.marcas_config (
  marca text primary key,
  linhas jsonb not null default '[]'::jsonb,
  atualizado_em timestamptz not null default now()
);

create table if not exists public.gtin_info (
  gtin text primary key,
  nome text not null default '',
  marca text not null default '',
  fonte text,
  consultado_em timestamptz
);

alter table public.acesso enable row level security;
alter table public.snapshots enable row level security;
alter table public.anuncios enable row level security;
alter table public.marcas_config enable row level security;
alter table public.gtin_info enable row level security;

create policy "autorizado le acesso" on public.acesso
  for select to authenticated using ((select privado.nubi_autorizado()));
create policy "autorizado" on public.snapshots
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy "autorizado" on public.anuncios
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy "autorizado" on public.marcas_config
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy "autorizado" on public.gtin_info
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Atualiza a consolidação de muitos anúncios numa chamada só (RLS continua valendo).
create or replace function public.atualizar_consolidacao(dados jsonb) returns int
language sql security invoker set search_path = public as $$
  with x as (
    select * from jsonb_to_recordset(dados)
      as t(id bigint, produto text, linha text, volume text, tipo text, genero text, confianca text)
  ), u as (
    update public.anuncios a
       set produto = x.produto, linha = x.linha, volume = x.volume, tipo = x.tipo,
           genero = x.genero, confianca = x.confianca
      from x where a.id = x.id
    returning 1
  )
  select count(*)::int from u;
$$;

-- Unidades por produto em cada período (aba Histórico).
create or replace function public.un_por_produto(ids bigint[])
returns table (snapshot_id bigint, produto text, un bigint)
language sql stable security invoker set search_path = public as $$
  select a.snapshot_id, a.produto, sum(a.un)::bigint
    from public.anuncios a
   where a.snapshot_id = any (ids)
   group by 1, 2;
$$;

revoke execute on function public.atualizar_consolidacao(jsonb) from public, anon;
revoke execute on function public.un_por_produto(bigint[]) from public, anon;
grant execute on function public.atualizar_consolidacao(jsonb) to authenticated;
grant execute on function public.un_por_produto(bigint[]) to authenticated;

-- Painel geral: o período mais recente de cada marca, já somado.
create or replace function public.painel()
returns table (marca text, snapshot_id bigint, inicio date, fim date, dias int, periodos bigint,
               anuncios bigint, vendedores bigint, referencias bigint, un bigint,
               fat double precision, catalogo bigint, duvidas bigint)
language sql stable security invoker set search_path = public as $$
  with ultimo as (
    select distinct on (s.marca) s.*
      from public.snapshots s
     order by s.marca, s.fim desc, s.inicio desc, s.id desc
  )
  select u.marca, u.id, u.inicio, u.fim, u.dias,
         (select count(*) from public.snapshots s2 where s2.marca = u.marca),
         count(a.id), count(distinct a.vendedor_id), count(distinct a.produto),
         coalesce(sum(a.un), 0)::bigint, coalesce(sum(a.fat), 0), coalesce(sum(a.catalogo), 0)::bigint,
         count(distinct a.gtin) filter (where a.confianca like 'Dúvida%' and a.gtin <> '')
    from ultimo u join public.anuncios a on a.snapshot_id = u.id
   group by u.marca, u.id, u.inicio, u.fim, u.dias
   order by sum(a.un) desc nulls last;
$$;
revoke execute on function public.painel() from public, anon;
grant execute on function public.painel() to authenticated;

-- Linha original do CSV, coluna por coluna (aba Anúncios mostra igual ao arquivo).
alter table public.anuncios add column if not exists bruto jsonb;

-- Ranking mensal de marcas (relatório "MARCAS" do Nubimetrics, sem produtos).
create table if not exists public.ranking_relatorios (
  id bigserial primary key,
  categoria text not null,
  mes date not null,
  arquivo text,
  hash text unique,
  importado_em timestamptz not null default now(),
  unique (categoria, mes)
);
create table if not exists public.ranking_linhas (
  id bigserial primary key,
  relatorio_id bigint not null references public.ranking_relatorios (id) on delete cascade,
  posicao int, variacao int, marca text, marca_chave text,
  vendas double precision, unidades double precision,
  tendencia text, catalogo double precision, vendedores int, saturacao text, ranking_demanda int,
  bruto jsonb
);
create index if not exists ranking_linhas_rel on public.ranking_linhas (relatorio_id);
create index if not exists ranking_linhas_chave on public.ranking_linhas (marca_chave);
alter table public.ranking_relatorios enable row level security;
alter table public.ranking_linhas enable row level security;
create policy "autorizado" on public.ranking_relatorios
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy "autorizado" on public.ranking_linhas
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Agente de GTIN: registro de cada rodada automática (importação, página aberta, agenda diária).
create table if not exists public.agente_execucoes (
  id bigint generated always as identity primary key,
  origem text not null,
  marca text,
  iniciado_em timestamptz not null default now(),
  terminado_em timestamptz,
  pendentes int, pesquisados int, encontrados int, nao_encontrados int, sem_resposta int, restantes int,
  log text
);
alter table public.agente_execucoes enable row level security;
create policy "autorizado" on public.agente_execucoes
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Vendedores monitorados: export de anúncios de um vendedor seguido, mês fechado.
create table if not exists public.vend_relatorios (
  id bigint generated always as identity primary key,
  vendedor text not null,
  mes date not null,
  arquivo text,
  hash text unique,
  importado_em timestamptz not null default now()
);
create unique index if not exists vend_relatorios_vendedor_mes on public.vend_relatorios (vendedor, mes);
create table if not exists public.vend_anuncios (
  id bigint generated always as identity primary key,
  relatorio_id bigint not null references public.vend_relatorios(id) on delete cascade,
  titulo text, marca text, marca_chave text, gtin text, sku text,
  vendas numeric, unidades int, preco numeric, tipo_pub text,
  fulfillment boolean, catalogo boolean, frete_gratis boolean, desconto boolean, estado text,
  bruto jsonb
);
create index if not exists vend_anuncios_rel on public.vend_anuncios (relatorio_id);
alter table public.vend_relatorios enable row level security;
alter table public.vend_anuncios enable row level security;
create policy "autorizado" on public.vend_relatorios
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy "autorizado" on public.vend_anuncios
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Nomes de marcas: grafias diferentes da mesma marca (YSL -> YVES SAINT LAURENT).
create table if not exists public.marca_apelidos (
  apelido text primary key,
  marca text,
  ignorar boolean not null default false,
  criado_em timestamptz not null default now()
);
alter table public.marca_apelidos enable row level security;
create policy "autorizado" on public.marca_apelidos
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create or replace function public.marcas_vistas() returns table (marca text, fonte text, vendas numeric)
language sql stable security invoker set search_path = public as $$
  select marca, 'ranking', sum(vendas) from public.ranking_linhas where marca is not null group by marca
  union all
  select marca, 'vendedores', sum(vendas) from public.vend_anuncios where marca is not null and marca <> '' group by marca;
$$;
grant execute on function public.marcas_vistas() to authenticated;

-- Coletor do Nubimetrics (Mac mini): mês parcial e registro de cada coleta.
alter table public.vend_relatorios add column if not exists ate date;
create table if not exists public.coletor_execucoes (
  id bigint generated always as identity primary key,
  iniciado_em timestamptz not null default now(),
  terminado_em timestamptz,
  tarefa text, ok boolean, arquivos int, importados int, erros int, mensagem text, log text
);
alter table public.coletor_execucoes enable row level security;
-- andamento ao vivo (o coletor atualiza a mesma linha enquanto roda)
alter table public.coletor_execucoes add column if not exists em_andamento boolean not null default false;
alter table public.coletor_execucoes add column if not exists feito int;
alter table public.coletor_execucoes add column if not exists total int;
alter table public.coletor_execucoes add column if not exists atual text;
alter table public.coletor_execucoes add column if not exists atualizado_em timestamptz;
create policy "autorizado" on public.coletor_execucoes
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Identidade do vendedor (hash do Nubimetrics e impressão digital dos anúncios).
alter table public.vend_relatorios add column if not exists seller_hash text;
alter table public.vend_relatorios add column if not exists nome_exibido text;
alter table public.vend_relatorios add column if not exists impressao jsonb;
create index if not exists vend_relatorios_hash on public.vend_relatorios (seller_hash);
create table if not exists public.vend_decisoes (
  id bigint generated always as identity primary key,
  relatorio_id bigint references public.vend_relatorios(id) on delete cascade,
  vendedor_antes text, vendedor_depois text, tipo text, similaridade numeric, status text, detalhe text,
  criado_em timestamptz not null default now()
);
alter table public.vend_decisoes enable row level security;
create policy "autorizado" on public.vend_decisoes
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- B.I. dos vendedores: foto diária acumulada por produto e resumo por produto/mês.
create table if not exists public.vend_produto_dia (
  vendedor text not null, mes date not null, chave text not null,
  dias jsonb not null default '{}'::jsonb,   -- {"AAAA-MM-DD": {"u": unidades acumuladas, "v": vendas acumuladas, "a": anúncios ativos, "n": anúncios}}
  atualizado_em timestamptz not null default now(),
  primary key (vendedor, mes, chave)
);
alter table public.vend_produto_dia enable row level security;
create policy "autorizado" on public.vend_produto_dia
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create or replace function public.vend_dia_gravar(dados jsonb)
returns void language sql security invoker set search_path = public as $$
  insert into vend_produto_dia (vendedor, mes, chave, dias)
  select d->>'vendedor', (d->>'mes')::date, d->>'chave', d->'dias' from jsonb_array_elements(dados) d
  on conflict (vendedor, mes, chave) do update set dias = vend_produto_dia.dias || excluded.dias, atualizado_em = now();
$$;
create index if not exists vend_anuncios_chave on public.vend_anuncios ((coalesce(nullif(gtin, ''), 'T:' || lower(titulo))));
create or replace function public.vend_prod_mes(ids bigint[], so_chave text default null)
returns table (relatorio_id bigint, chave text, gtin text, marca text, titulo text, unidades bigint, vendas numeric,
               anuncios int, ativos int, fulfillment boolean, catalogo boolean)
language sql stable security invoker set search_path = public as $$
  select a.relatorio_id, k.chave, max(a.gtin), max(a.marca), (array_agg(a.titulo order by a.unidades desc nulls last))[1],
         sum(coalesce(a.unidades, 0))::bigint, sum(coalesce(a.vendas, 0)), count(*)::int,
         (count(*) filter (where lower(coalesce(a.estado, '')) = 'active'))::int, bool_or(a.fulfillment), bool_or(a.catalogo)
  from vend_anuncios a cross join lateral (select coalesce(nullif(a.gtin, ''), 'T:' || lower(a.titulo)) as chave) k
  where a.relatorio_id = any(ids) and (so_chave is null or k.chave = so_chave)
  group by a.relatorio_id, k.chave
$$;
create or replace function public.vend_prod_serie(p_chave text)
returns table (relatorio_id bigint, unidades bigint, vendas numeric, anuncios int, ativos int,
               fulfillment boolean, catalogo boolean, titulo text, marca text)
language sql stable security invoker set search_path = public as $$
  select a.relatorio_id, sum(coalesce(a.unidades, 0))::bigint, sum(coalesce(a.vendas, 0)), count(*)::int,
         (count(*) filter (where lower(coalesce(a.estado, '')) = 'active'))::int, bool_or(a.fulfillment), bool_or(a.catalogo),
         (array_agg(a.titulo order by a.unidades desc nulls last))[1], max(a.marca)
  from vend_anuncios a where coalesce(nullif(a.gtin, ''), 'T:' || lower(a.titulo)) = p_chave
  group by a.relatorio_id
$$;

-- Nomes de marcas: cada grafia, por fonte, no último mês/período em que aparece.
create or replace function public.marcas_resumo()
returns table (marca text, fonte text, mes date, fim date, vendas numeric, vendedores int, posicao int)
language sql stable security invoker set search_path = public as $$
  with rk as (
    select l.marca, r.mes, sum(l.vendas) vendas, min(l.posicao) posicao
    from ranking_linhas l join ranking_relatorios r on r.id = l.relatorio_id
    where l.marca is not null group by l.marca, r.mes),
  vd as (
    select a.marca, r.mes, sum(a.vendas) vendas, count(distinct r.vendedor)::int vendedores
    from vend_anuncios a join vend_relatorios r on r.id = a.relatorio_id
    where a.marca is not null and a.marca <> '' and r.ate is null group by a.marca, r.mes),
  ex as (
    select a.marca_anuncio marca, s.inicio, s.fim, sum(a.fat) vendas, count(distinct a.vendedor_id)::int vendedores
    from anuncios a join snapshots s on s.id = a.snapshot_id
    where a.marca_anuncio is not null and a.marca_anuncio <> '' group by a.marca_anuncio, s.inicio, s.fim)
  select marca, 'ranking', mes, null::date, vendas, null::int, posicao from (select distinct on (marca) * from rk order by marca, mes desc) x
  union all
  select marca, 'vendedores', mes, null::date, vendas, vendedores, null::int from (select distinct on (marca) * from vd order by marca, mes desc) y
  union all
  select marca, 'explorador', inicio, fim, vendas, vendedores, null::int from (select distinct on (marca) * from ex order by marca, fim desc) z;
$$;
grant execute on function public.marcas_resumo() to authenticated;

-- Categoria de cada marca (Alta perfumaria, Designer, Nicho, Árabe, Nacional, Outros) escolhida na tela;
-- sem linha aqui vale a lista automática de categorias.py.
create table if not exists public.marca_categorias (
  marca_chave text primary key, marca text, categoria text not null,
  atualizado_em timestamptz not null default now()
);
alter table public.marca_categorias enable row level security;
create policy "autorizado" on public.marca_categorias
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Resumo do mês escrito pela IA (guardado para não pagar de novo a cada visita).
create table if not exists public.ia_resumos (
  chave text primary key, texto text not null, ia text, criado_em timestamptz not null default now()
);
alter table public.ia_resumos enable row level security;
create policy "autorizado" on public.ia_resumos
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Venda isolada de cada dia por vendedor (export de 1 dia do Nubimetrics), com os itens vendidos
create table if not exists public.vend_vendas_dia (
  vendedor text not null, data date not null,
  v numeric not null default 0, u int not null default 0, anuncios int not null default 0,
  itens jsonb not null default '[]'::jsonb,   -- [{"k": chave, "t": título, "m": marca, "u": unidades, "v": vendas, "a": anúncios ativos, "n": anúncios}]
  atualizado_em timestamptz not null default now(),
  primary key (vendedor, data)
);
alter table public.vend_vendas_dia enable row level security;
create policy "autorizado" on public.vend_vendas_dia
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Tarefas de rotina (editáveis no site: Coletor e agentes > Tarefas de rotina)
create table if not exists public.rotinas (
  id text primary key, ordem int not null default 0, nome text not null, descricao text,
  responsavel text not null, horario text not null default '08:00',
  dias_semana text[] not null default '{seg,ter,qua,qui,sex,sab,dom}', dia_mes int,
  ativo boolean not null default true, observacao text,
  ultima_execucao timestamptz, ultimo_resultado text, atualizado_em timestamptz not null default now()
);
alter table public.rotinas enable row level security;
create policy "autorizado" on public.rotinas
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
-- (as 5 tarefas iniciais: coleta, agente, resumo_dia, resumo_semana, resumo_marcas — ver migration vend_vendas_dia_rotinas)

-- Foto da tela + resumo dos botões quando o coletor erra no Nubimetrics (para ver o erro de fora do Mac)
create table if not exists public.coletor_fotos (
  id bigserial primary key, execucao_id bigint, criado_em timestamptz not null default now(),
  rotulo text, tela text, foto text
);
alter table public.coletor_fotos enable row level security;
create policy "autorizado" on public.coletor_fotos
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Aba Vendas diárias: série por dia/vendedor, média por dia da semana e produtos do período (com a venda de cada dia)
create or replace function public.vend_dia_serie(desde date, ate date)
returns table (data date, vendedor text, v numeric, u int, produtos int)
language sql stable security invoker set search_path = public as $$
  select d.data, d.vendedor, d.v, d.u, jsonb_array_length(d.itens)
  from vend_vendas_dia d where d.data between desde and ate order by d.data, d.vendedor;
$$;
-- vend_dia_produtos(desde, ate, so_vendedor, lim) e vend_dia_semana(desde, ate, so_vendedor): ver migration vend_dia_funcoes

-- Produtos iguais: títulos sem GTIN que são o mesmo perfume (embeddings + regras), juntados nas análises
create table if not exists public.produto_grupos (
  chave text primary key, grupo text not null, titulo text, marca text, grupo_titulo text,
  similaridade real, metodo text not null default 'ia', atualizado_em timestamptz not null default now()
);
alter table public.produto_grupos enable row level security;
create policy "autorizado" on public.produto_grupos
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
-- vend_dia_produtos junta pelo grupo (left join produto_grupos, metodo = 'ia'): ver migration produto_grupos
alter table public.ia_resumos add column if not exists dados jsonb;

-- Classificação de marcas em lote (Batch da OpenAI): lotes enviados e sugestões para aplicar em Ranking > Categorias
create table if not exists public.ia_lotes (
  id text primary key, tipo text not null, status text not null, itens int, detalhe text,
  criado_em timestamptz not null default now(), atualizado_em timestamptz not null default now()
);
alter table public.ia_lotes enable row level security;
create policy "autorizado" on public.ia_lotes
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create table if not exists public.marca_sugestoes (
  marca_chave text primary key, marca text not null, categoria text, confianca text, motivo text,
  fonte text, estado text not null default 'nova', criado_em timestamptz not null default now()
);
alter table public.marca_sugestoes enable row level security;
create policy "autorizado" on public.marca_sugestoes
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Tabela do grupo por dia (Nubimetrics > Comparar concorrentes): vendas, unidades, visitas, conversão e share
create table if not exists public.vend_grupo_dia (
  data date not null, vendedor text not null, nome_exibido text,
  v numeric, u int, visitas int, conversao numeric, share_v numeric, share_u numeric, bruto jsonb,
  atualizado_em timestamptz not null default now(), primary key (data, vendedor)
);
alter table public.vend_grupo_dia enable row level security;
create policy "autorizado" on public.vend_grupo_dia
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Auditoria diária de dados e código (conferências + conversa ChatGPT/Claude)
create table if not exists public.auditorias (
  data date primary key, resumo text, modulo text, conferencias jsonb, conversa jsonb,
  criado_em timestamptz not null default now()
);
alter table public.auditorias enable row level security;
create policy "autorizado" on public.auditorias
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Pedidos de coleta ("Rodar coleta agora"): o vigia do Mac confere a cada 15 min
create table if not exists public.coletor_pedidos (
  id bigserial primary key, pedido_em timestamptz not null default now(), motivo text, tarefa text not null default 'diario',
  atendido_em timestamptz, resultado text
);
alter table public.coletor_pedidos enable row level security;
create policy "autorizado" on public.coletor_pedidos
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Sala de reunião dos agentes e tarefas de desenvolvimento decididas nela
create table if not exists public.reuniao_mensagens (
  id bigserial primary key, criado_em timestamptz not null default now(), autor text not null, texto text not null, meta jsonb
);
alter table public.reuniao_mensagens enable row level security;
create policy "autorizado" on public.reuniao_mensagens
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create table if not exists public.reuniao_tarefas (
  id bigserial primary key, criado_em timestamptz not null default now(), atualizado_em timestamptz not null default now(),
  titulo text not null, descricao text, tipo text not null default 'tarefa', status text not null default 'proposta',
  prioridade text not null default 'media', area text, proposto_por text, decidido_por text, mensagem_id bigint, notas text
);
alter table public.reuniao_tarefas enable row level security;
create policy "autorizado" on public.reuniao_tarefas
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Histórico de cada execução das tarefas de rotina (aba Execuções e Erros da Central)
create table if not exists public.rotinas_execucoes (
  id bigint generated always as identity primary key,
  rotina text not null, origem text, inicio timestamptz not null default now(), fim timestamptz,
  ok boolean, resultado text
);
create index if not exists rotinas_execucoes_inicio on public.rotinas_execucoes (inicio desc);
alter table public.rotinas_execucoes enable row level security;
create policy "autorizado" on public.rotinas_execucoes
  for all to authenticated using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- Agentes de IA (aba Central → Agentes): cadastro, apelido, uso (tokens/custo) e preços por modelo
create table if not exists public.agentes (
  id text primary key, nome text not null, apelido text, icone text, cor text, papel text, onde text,
  ordem int default 100, ultimo_teste jsonb, atualizado_em timestamptz default now()
);
create table if not exists public.agentes_uso (
  id bigint generated always as identity primary key,
  agente text not null, modelo text, origem text, inicio timestamptz not null default now(), fim timestamptz,
  ok boolean, tokens_in int, tokens_out int, custo_usd numeric, erro text
);
create index if not exists agentes_uso_inicio on public.agentes_uso (inicio desc);
create table if not exists public.ia_precos (modelo text primary key, entrada numeric, saida numeric, obs text);
alter table public.agentes enable row level security;
alter table public.agentes_uso enable row level security;
alter table public.ia_precos enable row level security;
create policy "autorizado" on public.agentes for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy "autorizado" on public.agentes_uso for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy "autorizado" on public.ia_precos for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
insert into public.agentes (id, nome, icone, cor, papel, onde, ordem) values
  ('claude', 'Claude', '✴️', '#d97757', 'Coordena a Sala e decide; revisa a auditoria', 'API Anthropic', 1),
  ('chatgpt', 'ChatGPT', '🧠', '#10a37f', 'Código (Codex), resumos, auditoria de código, marcas em lote e produtos iguais', 'API OpenAI', 2),
  ('deepseek', 'DeepSeek', '🐋', '#4d6bfe', 'Matemática e revisão: contas, totais, casos de borda e custo', 'API DeepSeek', 3),
  ('gptoss', 'gpt-oss', '🦙', '#6b4fb3', 'Segunda opinião barata: caminhos simples, escala, planos passo a passo', 'Ollama Cloud (cota grátis)', 4),
  ('hermes', 'Hermes', '🪽', '#a2741a', 'Vigia 24h, logs, testes, documentação e memória', 'Mac mini (Ollama local, grátis)', 5),
  ('claude_code', 'Claude (código)', '💻', '#b3541e', 'Programa, testa e publica o nubi (tarefas aprovadas)', 'Sessão Claude Code (plano)', 6)
on conflict (id) do nothing;
insert into public.ia_precos (modelo, entrada, saida, obs) values
  ('claude-opus-5-5', 4, 20, 'US$ por 1M tokens (tabela da Anthropic)'),
  ('claude-sonnet-5', 2, 10, 'US$ por 1M tokens (tabela da Anthropic)'),
  ('gpt-oss', 0, 0, 'cota grátis do Ollama Cloud'),
  ('hermes3', 0, 0, 'roda no Mac mini'),
  ('gpt-5.3-codex', null, null, 'preencher com o preço da OpenAI'),
  ('gpt-4.1', null, null, 'preencher com o preço da OpenAI'),
  ('text-embedding-3-small', null, null, 'preencher com o preço da OpenAI'),
  ('deepseek', null, null, 'preencher com o preço do DeepSeek')
on conflict (modelo) do nothing;
