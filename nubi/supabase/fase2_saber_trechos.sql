-- Base de conhecimento, fase 2 (26/09, aprovada pelo Bruno no card #83): pedaços com frase de contexto + vetores
-- (pgvector) + busca híbrida (significado + palavra, fusão RRF). Técnicas da Anthropic (Contextual Retrieval) e da OpenAI.
create extension if not exists vector with schema extensions;

-- sem acento e imutável (a coluna gerada de busca precisa de função imutável)
create or replace function privado.sem_acento(t text) returns text
language sql immutable parallel safe set search_path = ''
as $$ select extensions.unaccent('extensions.unaccent'::regdictionary, coalesce(t, '')) $$;

create table if not exists public.saber_trechos (
  id bigserial primary key,
  saber_id bigint not null references public.saber(id),
  ordem int not null,
  hash text not null,                      -- md5(titulo|texto) do item: mudou o item, refaz os pedaços
  contexto text not null default '',       -- frase de contexto (de onde veio, quando, sobre o quê)
  texto text not null,
  embedding extensions.vector(1536),       -- text-embedding-3-small de "contexto + texto"
  busca tsvector generated always as (to_tsvector('portuguese'::regconfig, privado.sem_acento(contexto || ' ' || texto))) stored,
  modelo text,
  criado_em timestamptz not null default now(),
  unique (saber_id, ordem)
);
create index if not exists saber_trechos_vetor on public.saber_trechos using hnsw (embedding extensions.vector_cosine_ops);
create index if not exists saber_trechos_busca on public.saber_trechos using gin (busca);
create index if not exists saber_trechos_item on public.saber_trechos (saber_id);

alter table public.saber_trechos enable row level security;
drop policy if exists autorizado on public.saber_trechos;
create policy autorizado on public.saber_trechos for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- itens novos ou alterados (sem pedaços com o hash atual), mais novos primeiro
create or replace function public.saber_pendentes(lim int default 50)
returns table (id bigint, tipo text, titulo text, texto text, autor text, conversa text, criado_em timestamptz,
               tags text[], fonte_tabela text, hash text)
language sql stable set search_path = public
as $$
  select s.id, s.tipo, s.titulo, s.texto, s.autor, s.conversa, s.criado_em, s.tags, s.fonte_tabela,
         md5(coalesce(s.titulo, '') || '|' || coalesce(s.texto, ''))
  from saber s
  where coalesce(s.texto, '') <> ''
    and not exists (select 1 from saber_trechos t where t.saber_id = s.id
                    and t.hash = md5(coalesce(s.titulo, '') || '|' || coalesce(s.texto, '')))
  order by s.criado_em desc
  limit greatest(1, least(coalesce(lim, 50), 500));
$$;

-- quanto da base já tem pedaços (para a rotina e para o teste)
create or replace function public.saber_cobertura()
returns table (itens bigint, indexados bigint, trechos bigint)
language sql stable set search_path = public
as $$
  select (select count(*) from saber where coalesce(texto, '') <> ''),
         (select count(distinct saber_id) from saber_trechos),
         (select count(*) from saber_trechos);
$$;

-- busca híbrida: até 60 por significado (vetor) + até 60 por palavra (qualquer palavra, sem acento, português),
-- fusão por posição (RRF, k=60), o melhor pedaço de cada item; decisão substituída vale metade
create or replace function public.buscar_hibrido(q text, qvec text default null, lim int default 20, tipos text[] default null)
returns table (origem text, id bigint, conversa text, autor text, titulo text, texto text, criado_em timestamptz,
               tipo text, fonte_tabela text, fonte_id text, links jsonb, trecho text, contexto text, score float8, saber_id bigint)
language plpgsql stable set search_path = public, extensions
as $$
#variable_conflict use_column
declare
  consulta tsquery;
  palavras text;
begin
  perform set_config('hnsw.ef_search', '100', true);
  palavras := array_to_string(array(
    select distinct w from unnest(regexp_split_to_array(lower(privado.sem_acento(coalesce(q, ''))), '[^a-z0-9]+')) w
    where length(w) >= 3), ' | ');
  consulta := case when palavras <> '' then to_tsquery('portuguese', palavras) end;
  return query
  with sem as (
    select t.id as tid, row_number() over (order by t.embedding <=> qvec::vector) as r
    from saber_trechos t
    where qvec is not null and t.embedding is not null
    order by t.embedding <=> qvec::vector
    limit 60),
  lex as (
    select t.id as tid, row_number() over (order by ts_rank_cd(t.busca, consulta) desc) as r
    from saber_trechos t
    where consulta is not null and t.busca @@ consulta
    order by ts_rank_cd(t.busca, consulta) desc
    limit 60),
  fus as (
    select coalesce(sem.tid, lex.tid) as tid,
           coalesce(1.0 / (60 + sem.r), 0) + coalesce(1.0 / (60 + lex.r), 0) as sc
    from sem full outer join lex on sem.tid = lex.tid),
  por_item as (
    select distinct on (t.saber_id) t.saber_id, t.texto as tr, t.contexto as ctx, f.sc
    from fus f join saber_trechos t on t.id = f.tid
    order by t.saber_id, f.sc desc)
  select case when s.fonte_tabela = 'reuniao_mensagens' then 'mensagem' when s.fonte_tabela = 'conhecimento' then 'conhecimento' else s.tipo end,
         case when s.fonte_tabela in ('reuniao_mensagens', 'conhecimento') then s.fonte_id::bigint else s.id end,
         s.conversa, s.autor, s.titulo, s.texto, s.criado_em, s.tipo, s.fonte_tabela, s.fonte_id, s.links,
         p.tr, p.ctx, (p.sc * case when s.substituido_por is not null then 0.5 else 1 end)::float8, s.id
  from por_item p join saber s on s.id = p.saber_id
  where tipos is null or s.tipo = any(tipos)
  order by 14 desc
  limit greatest(1, least(coalesce(lim, 20), 100));
end;
$$;

grant execute on function public.saber_pendentes(int), public.saber_cobertura(), public.buscar_hibrido(text, text, int, text[]) to authenticated;
