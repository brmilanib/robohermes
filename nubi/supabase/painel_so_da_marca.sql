-- 02/10 (Bruno, Al Wataniah set/26: Ranking de marcas R$ 6,4 mi x Painel geral R$ 12,4 mi — "tem algo erradíssimo"):
-- a pesquisa expandida do Explorador traz anúncios de OUTRAS marcas (tipo 'Outra marca'). O Painel geral conta só os
-- anúncios da marca do card. Aplicada em 02/10 (execute_sql).
CREATE OR REPLACE FUNCTION public.painel()
 RETURNS TABLE(marca text, snapshot_id bigint, inicio date, fim date, dias integer, periodos bigint, anuncios bigint, vendedores bigint, referencias bigint, un bigint, fat double precision, catalogo bigint, duvidas bigint)
 LANGUAGE sql STABLE SET search_path TO 'public'
AS $function$
  -- 02/10 (Bruno, Al Wataniah set/26 mostrava R$ 12,4 mi): a pesquisa expandida traz anúncios de OUTRAS marcas
  -- (tipo 'Outra marca'); eles não contam nos números da marca do card
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
    from ultimo u left join public.anuncios a on a.snapshot_id = u.id and coalesce(a.tipo, '') <> 'Outra marca'
   group by u.marca, u.id, u.inicio, u.fim, u.dias
   order by sum(a.un) desc nulls last;
$function$;
