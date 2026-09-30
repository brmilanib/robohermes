-- Cards #126/#127, etapa 3. CONTRATO para revisão do Chefe com a etapa 2 do Ferreiro.
-- Não aplicado pelo Astra. A coleta escreve dados; só estas rotas escrevem as ligações.
create table if not exists public.vend_anuncios_ml (
  vendedor text not null,
  mlb text not null,
  seller_id text not null,
  dados jsonb not null default '{}',
  primary key (vendedor, mlb)
);
alter table public.vend_anuncios_ml add column if not exists vend_anuncio_id bigint;
alter table public.vend_anuncios_ml add column if not exists anuncio_explorador_id bigint;
alter table public.vend_anuncios_ml add column if not exists confianca_ligacao text;
-- Sem cascade: reimportar o relatório não pode apagar uma decisão manual.
alter table public.vend_anuncios_ml enable row level security;
drop policy if exists autorizado on public.vend_anuncios_ml;
create policy autorizado on public.vend_anuncios_ml for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
