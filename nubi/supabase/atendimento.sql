-- Atendimento ao cliente (pedido do Bruno, 26/09): módulo reusável por canal (TikTok Shop primeiro; WhatsApp e Mercado
-- Livre depois). Toda resposta nasce de dado real (pedido ou base de conhecimento da loja), vira rascunho e só sai com
-- aprovação humana. Nada aqui guarda endereço, telefone ou documento do cliente.

create table if not exists public.atendimento_conversas (
  id bigint generated always as identity primary key,
  canal text not null,                       -- tiktok_shop, whatsapp, mercado_livre…
  loja text not null default 'principal',    -- loja/marca (a base de conhecimento é por loja)
  cliente text,                              -- apelido/nome de exibição do cliente no canal (nunca documento/telefone)
  externo_id text,                           -- id da conversa no canal
  pedido_ref text,                           -- pedido ligado à conversa, quando o canal informa
  status text not null default 'nova',       -- nova, rascunho, precisa_info, respondida, encerrada
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  unique (canal, externo_id)
);
create index if not exists atendimento_conversas_fila on public.atendimento_conversas (status, atualizado_em desc);

create table if not exists public.atendimento_mensagens (
  id bigint generated always as identity primary key,
  conversa_id bigint not null references public.atendimento_conversas (id),
  de text not null,                          -- cliente ou loja
  texto text not null,
  externo_id text,
  criado_em timestamptz not null default now()
);
create index if not exists atendimento_mensagens_conversa on public.atendimento_mensagens (conversa_id, id);

-- Base de conhecimento por loja: pergunta-tipo → resposta padrão, com quem confirmou e quando
create table if not exists public.atendimento_kb (
  id bigint generated always as identity primary key,
  loja text not null default 'principal',
  pergunta text not null,
  resposta text not null,
  tags text[],
  status text not null default 'ativa',      -- ativa, proposta (resposta do operador esperando confirmação), inativa
  confirmado_por text,
  confirmado_em timestamptz,
  origem_rascunho bigint,
  substituido_por bigint,
  criado_em timestamptz not null default now()
);
create index if not exists atendimento_kb_loja on public.atendimento_kb (loja, status);

-- Rascunhos = log de aprendizado: pergunta, dado usado, resposta gerada, decisão humana e texto final
create table if not exists public.atendimento_rascunhos (
  id bigint generated always as identity primary key,
  conversa_id bigint not null references public.atendimento_conversas (id),
  mensagem_id bigint references public.atendimento_mensagens (id),
  intencao text,
  fontes jsonb not null default '{}'::jsonb, -- dados usados (pedido já sem dado sensível, itens da base, estoque)
  texto_gerado text,
  texto_final text,
  status text not null default 'pendente',   -- pendente, precisa_info, aprovado, editado, rejeitado, enviado
  pergunta_operador text,                    -- quando falta dado: pergunta objetiva para o lojista
  resposta_operador text,
  motivo text,
  semelhanca numeric,                        -- 0 a 1: quanto o texto final ficou igual ao gerado (mede o acerto)
  modelo text,
  decidido_por text,
  decidido_em timestamptz,
  enviado_em timestamptz,
  criado_em timestamptz not null default now()
);
create index if not exists atendimento_rascunhos_fila on public.atendimento_rascunhos (status, criado_em desc);
create index if not exists atendimento_rascunhos_conversa on public.atendimento_rascunhos (conversa_id, id);

alter table public.atendimento_conversas enable row level security;
alter table public.atendimento_mensagens enable row level security;
alter table public.atendimento_kb enable row level security;
alter table public.atendimento_rascunhos enable row level security;
drop policy if exists autorizado on public.atendimento_conversas;
drop policy if exists autorizado on public.atendimento_mensagens;
drop policy if exists autorizado on public.atendimento_kb;
drop policy if exists autorizado on public.atendimento_rascunhos;
create policy autorizado on public.atendimento_conversas for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy autorizado on public.atendimento_mensagens for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy autorizado on public.atendimento_kb for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));
create policy autorizado on public.atendimento_rascunhos for all to authenticated
  using ((select privado.nubi_autorizado())) with check ((select privado.nubi_autorizado()));

-- 26/09 (pedido do Bruno): o atendente do Mac lê o painel do pedido no chat e envia pelo Chrome o que foi aprovado
alter table public.atendimento_conversas add column if not exists pedido_dados jsonb;
alter table public.atendimento_rascunhos add column if not exists enviar_pelo_mac boolean not null default false;
create index if not exists atendimento_rascunhos_envio on public.atendimento_rascunhos (enviar_pelo_mac, enviado_em);

-- 26/09 (pedido do Bruno): aprender padrões com os chats antigos (fechados) → propostas na base
alter table public.atendimento_conversas add column if not exists aprendido_em timestamptz;
