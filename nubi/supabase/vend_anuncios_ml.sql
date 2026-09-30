-- Card #126 (autorizado pelo Bruno no card, 30/09), etapa 2: TODOS os anúncios da vitrine (lista.mercadolivre.com.br/
-- _CustId_<seller_id>) da loja real de cada vendedor seguido, lidos pelo coletor (vitrine-seguidos) com as regras do
-- doCartao da extensão e gravados por nubi_web.gravar_vitrine (rota ml_vitrine_salvar), 1 linha por MLB. As colunas da
-- ligação com o Nubimetrics (vend_anuncio_id, anuncio_explorador_id, gtin, marca_chave, ligacao) ficam para a etapa 3.
-- Só cria (if not exists); nada é apagado. O Chefe aplica.
create table if not exists public.vend_anuncios_ml (
  id bigint generated always as identity,
  vendedor text not null,                      -- nome do seguido no Nubimetrics (vend_lojas_ml.vendedor)
  seller_id text not null,
  mlb text not null unique,                    -- chave lógica (upsert on_conflict=mlb)
  link text,
  titulo text,
  foto text,                                   -- mlstatic, tamanho grande (-O.)
  preco numeric,                               -- null = o card não mostrou
  vendidos integer,                            -- "+5mil vendidos" = 5000 (faixa do ML)
  "full" boolean,                              -- "full" é palavra reservada no Postgres (30/09)
  tipo_pub text,
  produto_catalogo text,                       -- MLB… do /p/ (produto pai) quando o anúncio é de catálogo
  gtin text,
  marca_chave text,
  vend_anuncio_id bigint,                      -- -> vend_anuncios.id quando casou (etapa 3)
  anuncio_explorador_id bigint,                -- -> anuncios.id quando o mesmo produto está no Explorador (etapa 3)
  ligacao text,                                -- gtin / titulo (a conferir) / foto (etapa 3)
  criado_em_ml timestamptz,
  fonte text,                                  -- vitrine / prova (anúncio de prova de meli|seguidos)
  visto_em timestamptz not null default now(),
  primary key (id)
);
create index if not exists vend_anuncios_ml_vendedor on public.vend_anuncios_ml (vendedor);
create index if not exists vend_anuncios_ml_seller on public.vend_anuncios_ml (seller_id);
alter table public.vend_anuncios_ml enable row level security;
drop policy if exists autorizado on public.vend_anuncios_ml;
create policy autorizado on public.vend_anuncios_ml for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
