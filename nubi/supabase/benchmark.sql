-- Card #15 (tabelas aprovadas pelo Bruno em 27/09): mini-benchmark interno de modelos (nubi_benchmark.py).
-- Casos fixos e versionados (a versão e o gabarito ficam no código; aqui a cópia de cada versão rodada) e
-- 1 linha por caso e modelo em cada rodada. custo_usd NULL = sem uso relatado ou sem preço em ia_precos (nunca estimado).
create table if not exists public.ia_benchmark_casos (
  id text primary key,                          -- '<versao>|<caso>'
  versao_casos text not null,
  caso text not null,
  tipo text not null check (tipo in ('resumo_dia', 'alerta', 'juncao')),
  entrada jsonb not null,
  gabarito jsonb not null,
  criado_em timestamptz not null default now()
);
create table if not exists public.ia_benchmark_execucoes (
  id bigserial primary key,
  rodada text not null,                         -- '<início em UTC>|<provedor:modelo>': uma tentativa, nunca misturada
  versao_casos text not null,
  caso_id text not null references public.ia_benchmark_casos (id),
  tipo text not null,
  modelo text not null,                         -- candidato como foi pedido (provedor:modelo)
  modelo_api text,                              -- nome que a API devolveu
  latencia_ms int not null,
  tokens_in int,
  tokens_out int,
  custo_usd numeric,
  acerto boolean not null,
  nota numeric,
  erro text,
  saida jsonb,
  criado_em timestamptz not null default now()
);
create index if not exists ia_benchmark_execucoes_versao on public.ia_benchmark_execucoes (versao_casos, rodada desc);
alter table public.ia_benchmark_casos enable row level security;
alter table public.ia_benchmark_execucoes enable row level security;
drop policy if exists autorizado on public.ia_benchmark_casos;
create policy autorizado on public.ia_benchmark_casos for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
drop policy if exists autorizado on public.ia_benchmark_execucoes;
create policy autorizado on public.ia_benchmark_execucoes for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
