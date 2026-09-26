-- Card #77 (aprovado pelo Bruno em 26/09): provas da conferência de cada par de GTIN suspeito (mesmo nome, GTIN diferente),
-- guardadas à parte para não serem apagadas pelo conferir_gtins, que refaz os pares a cada rodada.
create table if not exists public.produto_conferencias (
  id bigserial primary key,
  par_chave text not null unique,              -- 'par:<gtin_a>|<gtin_b>' (a mesma chave de produto_grupos)
  gtin_a text,
  gtin_b text,
  titulo_a text,
  titulo_b text,
  vendedor_a text,
  vendedor_b text,
  status text not null default 'pendente' check (status in ('pendente', 'conferindo', 'concluida', 'erro')),
  veredito text check (veredito in ('mesmo_produto', 'produtos_diferentes', 'incerto')),
  justificativa text,
  provas jsonb not null default '[]'::jsonb,   -- [{link, anuncio_id, loja, cidade, titulo, gtin, foto, visto_em, fonte}]
  conferido_por text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);
create index if not exists produto_conferencias_status on public.produto_conferencias (status);
alter table public.produto_conferencias enable row level security;
drop policy if exists autorizado on public.produto_conferencias;
create policy autorizado on public.produto_conferencias for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
