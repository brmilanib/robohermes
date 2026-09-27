-- Card #92 (tabela aprovada pelo Bruno em 27/09): saúde do Mac mini servidor, uma linha a cada 5 min vinda do coletor
-- (mac_tick → servidor_metricas_gravar). Horários em UTC; leitura que falta fica NULL (a tela mostra "sem dados").
create table if not exists public.servidor_metricas (
  id bigserial primary key,
  coletado_em timestamptz not null,
  origem text not null default 'mac_mini',
  cpu_pct numeric(4,1) check (cpu_pct between 0 and 100),
  mem_pct numeric(4,1) check (mem_pct between 0 and 100),
  disco_pct numeric(4,1) check (disco_pct between 0 and 100),
  temp_c numeric(4,1),                          -- NULL sem leitura (macOS não dá temperatura sem sudo)
  agentes jsonb not null default '{}'::jsonb,   -- {nome: ativo}
  faltantes jsonb not null default '[]'::jsonb, -- esperados que não estão ativos
  alertas jsonb not null default '[]'::jsonb,   -- CPU/memória/disco >= 90%, temperatura >= 85 °C, agente ausente
  status text not null default 'ok' check (status in ('ok', 'alerta')),
  recebido_em timestamptz not null default now(),
  unique (coletado_em, origem)
);
create index if not exists servidor_metricas_coletado on public.servidor_metricas (coletado_em desc);
alter table public.servidor_metricas enable row level security;
drop policy if exists autorizado on public.servidor_metricas;
create policy autorizado on public.servidor_metricas for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
