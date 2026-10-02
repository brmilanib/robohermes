-- 02/10 (Bruno: "o anúncio é o mesmo, você tem o ID dele, não pode somar — dos seguidos e dos observadores também").
-- Aplicada pelo Chefe em 02/10. O mesmo ID do anúncio em exports de duas marcas (pesquisa expandida) conta UMA vez:
-- fica o do export em que ele não é "Outra marca", depois o mais recente. Antes: 62 anúncios / 4.496 un. em dobro.
CREATE OR REPLACE FUNCTION public.nubi_observados()
 RETURNS TABLE(vendedor_id text, nomes text[], marcas integer, anuncios integer, un bigint, fat double precision, gtins integer, pct_full numeric, pct_catalogo numeric, loja_oficial integer, primeiro date, ultimo date)
 LANGUAGE sql SECURITY DEFINER SET search_path TO 'public', 'pg_catalog'
AS $function$
  with ult as (select max(id) as id from snapshots group by marca),
  todas as (select a.*, s.marca, s.fim as s_fim,
                   row_number() over (partition by coalesce(nullif(a.bruto->>'ID do anúncio',''), a.vendedor_id || '|' || a.titulo)
                                      order by (a.tipo = 'Outra marca'), s.fim desc, s.id desc) as rn
            from anuncios a join snapshots s on s.id = a.snapshot_id where s.id in (select id from ult)),
  base as (select * from todas where rn = 1),
  todos as (select a.vendedor_id, min(s.inicio) as primeiro, max(s.fim) as ultimo from anuncios a join snapshots s on s.id = a.snapshot_id group by 1)
  select b.vendedor_id, (array_agg(distinct b.vendedor))[1:3] as nomes,
         count(distinct b.marca)::int, count(*)::int, sum(b.un)::bigint, sum(b.fat),
         count(distinct nullif(b.gtin,''))::int,
         round(avg(b."full")::numeric, 3), round(avg(b.catalogo)::numeric, 3), max(b.loja_oficial)::int,
         t.primeiro, t.ultimo
  from base b join todos t on t.vendedor_id = b.vendedor_id
  group by b.vendedor_id, t.primeiro, t.ultimo
  order by sum(b.un) desc
$function$;

CREATE OR REPLACE FUNCTION public.nubi_observado_produtos(h text)
 RETURNS TABLE(produto text, marca text, categoria text, gtin text, titulo text, anuncios integer, un bigint, fat double precision, preco double precision, pct_full numeric, catalogo integer, dias_pub integer, un_hist bigint, share numeric)
 LANGUAGE sql SECURITY DEFINER SET search_path TO 'public', 'pg_catalog'
AS $function$
  with ult as (select max(id) as id from snapshots group by marca),
  todas as (select a.*, s.marca,
                   row_number() over (partition by coalesce(nullif(a.bruto->>'ID do anúncio',''), a.vendedor_id || '|' || a.titulo)
                                      order by (a.tipo = 'Outra marca'), s.fim desc, s.id desc) as rn
            from anuncios a join snapshots s on s.id = a.snapshot_id where s.id in (select id from ult)),
  base as (select * from todas where rn = 1),
  tot as (select produto, sum(un) as un_tot from base group by produto),
  meu as (select * from base where vendedor_id = h)
  select m.produto, min(m.marca), min(coalesce(nullif(m.bruto->>'Categoria final',''), m.categoria)) as categoria,
         max(nullif(m.gtin,'')) as gtin, (array_agg(m.titulo order by m.un desc))[1] as titulo,
         count(*)::int, sum(m.un)::bigint, sum(m.fat),
         percentile_cont(0.5) within group (order by m.preco) as preco,
         round(avg(m."full")::numeric, 3), max(m.catalogo)::int, max(m.dias_pub)::int, sum(m.un_hist)::bigint,
         case when t.un_tot > 0 then round((sum(m.un)::numeric / t.un_tot), 4) else 0 end as share
  from meu m join tot t on t.produto = m.produto
  group by m.produto, t.un_tot
  order by sum(m.un) desc, sum(m.fat) desc
$function$;
