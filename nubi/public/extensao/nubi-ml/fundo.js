// nubi · Mercado Livre — parte de fundo da extensão (29/09, pedido do Bruno: "igual à extensão do Hunter").
// Só LÊ: a página do anúncio que o próprio navegador do Bruno abre (com o login dele no ML), o perfil público da loja e,
// no nubi, a rota pública ext_* (só dado público do ML: comissão, frete, visitas, concorrentes, tendências).
// Não guarda senha, não manda nada do Bruno para fora; nada de token.
const NUBI = "https://nubi-explorador.vercel.app";
const cacheAnuncio = new Map(), cacheLoja = new Map(), cacheNubi = new Map();

function lerAnuncio(html, url) {
  // a página do anúncio já traz o vendedor, a categoria e as datas no JSON dela; aqui só se procura o texto.
  // 29/09 (print do Bruno: vendedor "BRUNOMILANI" na página /up/): lá o JSON vem dentro de um texto, com as aspas
  // escapadas (\"seller_id\"); sem desfazer isso o leitor não achava o vendedor e pegava o apelido de quem está logado
  html = String(html || "").replace(/\\+"/g, '"').replace(/\\u002[fF]/g, "/");
  const um = (re) => { const m = html.match(re); return m ? m[1] : null; };
  const u = String(url || "");
  const vendedor = um(/"seller_id"\s*:\s*"?(\d{4,})/) || um(/"sellerId"\s*:\s*"?(\d{4,})/) ||
    um(/"seller"\s*:\s*\{\s*"id"\s*:\s*"?(\d{4,})/) || um(/_CustId_(\d{4,})/) || um(/[?&]seller_id=(\d{4,})/);
  const doLink = u.match(/[?&#]wid=(MLB\d{6,})/i) || u.match(/\/MLB-?(\d{6,})/i);
  const item = um(/"item_id"\s*:\s*"(MLB\d{6,})"/) || (doLink ? (doLink[1].startsWith("MLB") ? doLink[1] : "MLB" + doLink[1]) : null) ||
    um(/"id"\s*:\s*"(MLB\d{6,})"/);
  const pl = u.match(/\/p\/(MLB\d{5,})/i);
  const produto = pl ? pl[1].toUpperCase() : um(/"catalog_product_id"\s*:\s*"(MLB\d{5,})"/) || um(/"product_id"\s*:\s*"(MLB\d{5,})"/);
  const criado = um(/"date_created"\s*:\s*"([0-9T:.\-+Z]{10,})"/) || um(/"start_time"\s*:\s*"([0-9T:.\-+Z]{10,})"/);
  // o nome vem do vendedor do anúncio (seller_name); "nickname" e o link de perfil da página podem ser de QUEM ESTÁ LOGADO
  const apelido = um(/"seller_name"\s*:\s*"([^"]{2,80})"/) || um(/"seller"\s*:\s*\{[^{}]*?"nickname"\s*:\s*"([^"]{2,60})"/);
  const vendidos = um(/"sold_quantity"\s*:\s*(\d+)/);
  const oficial = um(/"official_store_id"\s*:\s*(\d+)/);
  const categoria = um(/"category_id"\s*:\s*"(MLB\d{1,9})"/) || um(/"categoryId"\s*:\s*"(MLB\d{1,9})"/);
  const tipo = um(/"listing_type_id"\s*:\s*"(gold_special|gold_pro|gold_premium|free)"/) || um(/"listingTypeId"\s*:\s*"(gold_special|gold_pro)"/);
  const preco = um(/<meta[^>]+itemprop="price"[^>]+content="([\d.]+)"/) || um(/"price"\s*:\s*([\d]+(?:\.\d+)?)\s*[,}]/);
  const titulo = um(/<h1[^>]*class="[^"]*ui-pdp-title[^"]*"[^>]*>([^<]{3,200})</) || um(/<meta[^>]+property="og:title"[^>]+content="([^"]{3,200})"/);
  const fotos = [...new Set((html.match(/https:\/\/http2\.mlstatic\.com\/D_NQ_NP_(?:2X_)?[0-9A-Za-z_\-]+-(?:O|F)\.(?:webp|jpg|jpeg|png)/g) || [])
    .map(f => f.replace("D_NQ_NP_", "D_NQ_NP_2X_").replace("D_NQ_NP_2X_2X_", "D_NQ_NP_2X_")))].slice(0, 30);
  // 29/09 (inspeção da página /up/ pelo Claude no Chrome): o estado vem no script __NORDIC_RENDERING_CTX__, nos blocos
  // melidata_event.event_data — busca pela chave, não pela posição. A data de criação NÃO está na página.
  const estoque = um(/"quantity"\s*:\s*(\d+)\s*,\s*"sold_quantity"/) || um(/"available_quantity"\s*:\s*(\d+)/);
  const nota = um(/"reviews"\s*:\s*\{\s*"rating"\s*:\s*([\d.]+)/);
  const avaliacoes = um(/"reviews"\s*:\s*\{[^{}]*?"amount"\s*:\s*(\d+)/) || um(/"reviews"\s*:\s*\{\s*"count"\s*:\s*(\d+)/);
  const logistica = um(/"logistic_type"\s*:\s*"([a-z_]+)"/);
  const nomeLoja = um(/"seller_name"\s*:\s*"([^"]{2,80})"/);
  // 29/09 (busca igual ao Hunter): marca do anúncio (atributo BRAND/Marca) e o tipo de envio (Full, Flex, Agência)
  const marca = um(/"(?:id|attribute_id)"\s*:\s*"BRAND"[^{}]*?"value_name"\s*:\s*"([^"]{1,60})"/) || um(/"Marca"\s*,\s*"value"\s*:\s*"([^"]{1,60})"/);
  const up = u.match(/\/up\/(MLBU\d{5,})/i);
  return {vendedor, item, produto, criado, apelido: apelido ? decodeURIComponent(apelido) : null,
    vendidos: vendidos != null ? +vendidos : null, oficial: oficial ? +oficial : null, categoria, tipo,
    preco: preco != null ? +preco : null, titulo: titulo ? titulo.trim() : null, fotos,
    estoque: estoque != null ? +estoque : null, nota: nota != null ? +nota : null, avaliacoes: avaliacoes != null ? +avaliacoes : null,
    full: logistica ? logistica === "fulfillment" : null, logistica, marca, nome_loja: nomeLoja, produto_usuario: up ? up[1].toUpperCase() : null};
}

// 30/09 (card #120, "igual ao Hunter em todos os cards"): a página de BUSCA já traz os resultados no estado dela
// (__PRELOADED_STATE__ ou __NORDIC_RENDERING_CTX__, às vezes num texto com as aspas escapadas). Cada resultado é lido
// pelo lerAnuncio só no pedaço dele; o link vai junto para casar o card patrocinado (click1), que não tem o MLB no link.
function estadoJson(s) {
  let t = String(s || "").trim().replace(/^[^{"]*?=\s*/, "").replace(/;\s*$/, "").replace(/^JSON\.parse\(([\s\S]*)\)$/, "$1");
  for (let i = 0; i < 3 && typeof t === "string"; i++) { try { t = JSON.parse(t); } catch (e) { return null; } }
  return t && typeof t === "object" ? t : null;
}

function lerBusca(html) {
  const ID = /^MLB\d{6,}$/, achados = [];
  const andar = (o, n) => {
    if (typeof o === "string" && /^\s*[{[]/.test(o)) o = estadoJson(o);
    if (!o || typeof o !== "object" || n > 40) return;
    if (Array.isArray(o)) return o.forEach(x => andar(x, n + 1));
    const c = o.polycard || (ID.test(o.id || o.item_id || "") && (o.permalink || o.url || o.seller || o.price != null) ? o : null);
    if (c) return achados.push(c);
    Object.values(o).forEach(x => andar(x, n + 1));
  };
  const scripts = [...String(html || "").matchAll(/<script[^>]*id="(?:__PRELOADED_STATE__|__NORDIC_RENDERING_CTX__)"[^>]*>([\s\S]*?)<\/script>/g)];
  scripts.forEach(m => {
    const o = estadoJson(m[1]);
    if (o) andar(o, 0);
    // não deu para ler como JSON: um pedaço por "polycard", com as aspas desfeitas como no lerAnuncio
    else m[1].replace(/\\+"/g, '"').split(/(?="polycard"\s*:)/).slice(1).forEach(p => achados.push({texto: p}));
  });
  const vistos = new Set(), out = [];
  achados.forEach(c => {
    const t = c.texto || JSON.stringify(c), md = c.metadata || {};
    const um = re => (t.match(re) || [])[1] || null;
    const mu = md.url || um(/"url"\s*:\s*"([^"]+)"/) || "";
    const link = c.permalink || c.url || (mu ? (/^https?:/.test(mu) ? mu : "https://" + mu) + (md.url_params || "") : "");
    const a = lerAnuncio(t, link);
    a.item = c.id || c.item_id || md.id || um(/"id"\s*:\s*"(MLB\d{6,})"/);
    if (!a.item || vistos.has(a.item)) return;
    vistos.add(a.item);
    if (a.preco == null) { const p = um(/"(?:current_price|price)"\s*:\s*\{[^{}]*?"(?:value|amount)"\s*:\s*([\d.]+)/); a.preco = p != null ? +p : null; }
    const v = t.match(/(\+?)\s*(\d+(?:\.\d{3})*)\s*(mil)?\s*vendidos?/i);
    if (a.vendidos == null && v) { a.vendidos = +v[2].replace(/\./g, "") * (v[3] ? 1000 : 1); a.vendidosMais = !!v[1]; }
    if (a.full == null && /:\s*"(?:[a-z_]+_)?(?:full|fulfillment)(?:_[a-z_]+)?"/i.test(t)) a.full = true;
    a.apelido = a.apelido || um(/"seller"\s*:\s*\{[^{}]*?"text"\s*:\s*"(?:Vendido )?[Pp]or\s*(?:\{[^}"]*\}\s*)?([^"{}]{2,80}?)\s*(?:\{[^}"]*\})?"/);
    delete a.fotos;
    out.push({...a, link});
  });
  return out;
}

async function anuncio(url) {
  if (cacheAnuncio.has(url)) return cacheAnuncio.get(url);
  // o motivo vai junto quando não acha a loja (29/09: "não achei a loja" em todos os cards da busca)
  const p = fetch(url, {credentials: "include"}).then(async r => {
    const h = await r.text();
    const a = lerAnuncio(h, url);
    if (!a.vendedor) a.motivo = `página ${r.status}, ${Math.round(h.length / 1024)} KB` + (r.redirected ? `, foi para ${new URL(r.url).pathname.slice(0, 40)}` : "") +
      ((h.match(/<title>([^<]{0,60})/) || [])[1] ? ` ("${h.match(/<title>([^<]{0,60})/)[1].trim()}")` : "");
    return a;
  }).catch(e => ({motivo: "a página não abriu (" + String(e && e.message || e).slice(0, 60) + ")"}));
  cacheAnuncio.set(url, p);
  return p;
}

async function loja(id) {
  if (!id) return null;
  if (cacheLoja.has(id)) return cacheLoja.get(id);
  const p = fetch(`https://api.mercadolibre.com/users/${id}`).then(r => r.ok ? r.json() : null).then(u => u && {
    id: u.id, nome: u.nickname, link: (u.permalink || "").replace(/^http:/, "https:"),
    cidade: (u.address || {}).city || "", uf: String((u.address || {}).state || "").replace(/^BR-/, ""),
    nivel: ((u.seller_reputation || {}).level_id || "").slice(0, 1), medalha: (u.seller_reputation || {}).power_seller_status || "",
    vendas: ((u.seller_reputation || {}).transactions || {}).total ?? null, desde: u.registration_date || ""
  }).catch(() => null);
  cacheLoja.set(id, p);
  return p;
}

// 29/09 (Bruno: "minha conta não está conectada ao Hunter e ele mostra a data"): tenta o /items público do ML direto do
// navegador, sem token e sem cookie. Se o ML deixar: data de criação, vendidos e estoque de verdade. Se não: diz o código.
async function itemPublico(mlb) {
  if (!/^MLB\d{6,}$/.test(mlb || "")) return {};
  try {
    const r = await fetch(`https://api.mercadolibre.com/items/${mlb}`, {credentials: "omit"});
    if (!r.ok) return {status: r.status};
    const x = await r.json();
    return {status: 200, criado: x.date_created || x.start_time || null, vendidos: x.sold_quantity ?? null,
      estoque: x.available_quantity ?? null, vendedor: x.seller_id ? String(x.seller_id) : null, tipo: x.listing_type_id || null,
      categoria: x.category_id || null, catalogo: x.catalog_product_id || null};
  } catch (e) { return {status: 0}; }
}

// dado público do ML pelo nubi (rota sem login): comissão, frete, visitas, concorrentes, tendências
async function nubi(rota, params) {
  const qs = new URLSearchParams(Object.entries(params || {}).filter(([, v]) => v != null && v !== ""));
  const url = `${NUBI}/api/app?r=${rota}&${qs}`;
  if (cacheNubi.has(url)) return cacheNubi.get(url);
  const uma = () => fetch(url, {mode: "cors", credentials: "omit", cache: "no-store"}).then(async r => { const j = await r.json().catch(() => ({})); return r.ok ? j : {erro: j.erro || j.detail || `erro ${r.status}`}; });
  // 1 nova tentativa (o nubi pode estar trocando de versão); o erro diz o motivo
  const p = uma().catch(() => new Promise(ok => setTimeout(ok, 1500)).then(uma))
    .catch(e => ({erro: `sem resposta do nubi (${String(e && e.message || e).slice(0, 60)})`}));
  cacheNubi.set(url, p);
  setTimeout(() => cacheNubi.delete(url), 20 * 60 * 1000);
  return p;
}

if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
  chrome.runtime.onMessage.addListener((msg, _de, responder) => {
    if (msg && msg.tipo === "anuncio" && /^https:\/\/[a-z.]*mercadolivre\.com\.br\//.test(msg.url || "")) {
      anuncio(msg.url).then(async a => responder({...a, loja: await loja(a.vendedor)}));
      return true;
    }
    if (msg && msg.tipo === "busca") {
      Promise.all(lerBusca(msg.html || "").map(async a => ({...a, loja: await loja(a.vendedor)}))).then(r => responder({resultados: r}));
      return true;
    }
    if (msg && msg.tipo === "pagina") {
      const a = lerAnuncio(msg.html || "", msg.url || "");
      loja(a.vendedor).then(l => responder({...a, loja: l}));
      return true;
    }
    if (msg && msg.tipo === "item") {
      itemPublico(String(msg.mlb || "")).then(responder);
      return true;
    }
    if (msg && msg.tipo === "nubi" && /^ext_[a-z]+$/.test(msg.rota || "")) {
      nubi(msg.rota, msg.params).then(responder);
      return true;
    }
    if (msg && msg.tipo === "baixar" && Array.isArray(msg.urls) && chrome.downloads) {
      const pasta = String(msg.pasta || "ml").replace(/[^A-Za-z0-9_\-]/g, "").slice(0, 40) || "ml";
      msg.urls.filter(u => /^https:\/\/http2\.mlstatic\.com\//.test(u)).slice(0, 30).forEach((u, i) =>
        chrome.downloads.download({url: u, filename: `nubi-ml/${pasta}/${String(i + 1).padStart(2, "0")}.${(u.match(/\.(webp|jpe?g|png)$/) || [0, "jpg"])[1]}`}));
      responder({ok: true});
      return false;
    }
    return false;
  });
}

if (typeof module !== "undefined") module.exports = {lerAnuncio, lerBusca, itemPublico};
