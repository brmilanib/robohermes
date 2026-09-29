// nubi · Mercado Livre — parte de fundo da extensão (29/09, pedido do Bruno: "igual à extensão do Hunter").
// Só LÊ: a página do anúncio que o próprio navegador do Bruno abre (com o login dele no ML), o perfil público da loja e,
// no nubi, a rota pública ext_* (só dado público do ML: comissão, frete, visitas, concorrentes, tendências).
// Não guarda senha, não manda nada do Bruno para fora; nada de token.
const NUBI = "https://nubi-explorador.vercel.app";
const cacheAnuncio = new Map(), cacheLoja = new Map(), cacheNubi = new Map();

function lerAnuncio(html, url) {
  // a página do anúncio já traz o vendedor, a categoria e as datas no JSON dela; aqui só se procura o texto
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
  const apelido = um(/perfil\.mercadolivre\.com\.br\/([A-Za-z0-9_.\-%]+)/) || um(/"nickname"\s*:\s*"([^"]{2,60})"/);
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
  const up = u.match(/\/up\/(MLBU\d{5,})/i);
  return {vendedor, item, produto, criado, apelido: apelido ? decodeURIComponent(apelido) : null,
    vendidos: vendidos != null ? +vendidos : null, oficial: oficial ? +oficial : null, categoria, tipo,
    preco: preco != null ? +preco : null, titulo: titulo ? titulo.trim() : null, fotos,
    estoque: estoque != null ? +estoque : null, nota: nota != null ? +nota : null, avaliacoes: avaliacoes != null ? +avaliacoes : null,
    full: logistica ? logistica === "fulfillment" : null, nome_loja: nomeLoja, produto_usuario: up ? up[1].toUpperCase() : null};
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

// dado público do ML pelo nubi (rota sem login): comissão, frete, visitas, concorrentes, tendências
async function nubi(rota, params) {
  const qs = new URLSearchParams(Object.entries(params || {}).filter(([, v]) => v != null && v !== ""));
  const url = `${NUBI}/api/app?r=${rota}&${qs}`;
  if (cacheNubi.has(url)) return cacheNubi.get(url);
  const p = fetch(url).then(async r => { const j = await r.json().catch(() => ({})); return r.ok ? j : {erro: j.erro || j.detail || `erro ${r.status}`}; })
    .catch(() => ({erro: "sem resposta do nubi"}));
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
    if (msg && msg.tipo === "pagina") {
      const a = lerAnuncio(msg.html || "", msg.url || "");
      loja(a.vendedor).then(l => responder({...a, loja: l}));
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

if (typeof module !== "undefined") module.exports = {lerAnuncio};
