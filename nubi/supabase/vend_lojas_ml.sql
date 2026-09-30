-- Card #126 (autorizado pelo Bruno no card, 30/09), etapa 1: a loja real no Mercado Livre de cada vendedor seguido no
-- Nubimetrics, com a cidade/UF do perfil público (/users/{id}). Alimentada a partir de ia_resumos meli|seguidos por
-- nubi_web.lojas_seguidos (painel #/vendedores-ml e rota meli_seguidos_lojas). O Chefe aplica.
create table if not exists public.vend_lojas_ml (
  vendedor text primary key,                   -- nome do seguido no Nubimetrics (vend_relatorios.vendedor)
  seller_id text not null,
  nickname text,
  nome text,
  cidade text,                                 -- null = o ML não respondeu (nunca inventada)
  uf text,
  link text,
  confianca text,                              -- manual / certa / provável / a conferir
  prova text,
  atualizado_em timestamptz not null default now()
);
create index if not exists vend_lojas_ml_seller on public.vend_lojas_ml (seller_id);
alter table public.vend_lojas_ml enable row level security;
drop policy if exists autorizado on public.vend_lojas_ml;
create policy autorizado on public.vend_lojas_ml for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
