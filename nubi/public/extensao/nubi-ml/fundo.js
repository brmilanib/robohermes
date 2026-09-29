// nubi · Mercado Livre — parte de fundo da extensão (29/09, pedido do Bruno: "igual à extensão do Hunter").
// Só LÊ: a página do anúncio que o próprio navegador do Bruno abre (com o login dele no ML) e o perfil público da loja.
// Não guarda senha, não manda nada para fora além do ML; nada de token.
const cacheAnuncio = new Map(), cacheLoja = new Map();

function lerAnuncio(html, url) {
  // a página do anúncio já traz o vendedor e as datas no JSON dela; aqui só se procura o texto
  const um = (re) => { const m = html.match(re); return m ? m[1] : null; };
  const vendedor = um(/"seller_id"\s*:\s*"?(\d{4,})/) || um(/"sellerId"\s*:\s*"?(\d{4,})/) ||
    um(/"seller"\s*:\s*\{\s*"id"\s*:\s*"?(\d{4,})/) || um(/_CustId_(\d{4,})/) || um(/[?&]seller_id=(\d{4,})/);
  const item = um(/"item_id"\s*:\s*"(MLB\d{6,})"/) || um(/"id"\s*:\s*"(MLB\d{6,})"/) || (String(url).match(/MLB-?(\d{6,})/) ? "MLB" + String(url).match(/MLB-?(\d{6,})/)[1] : null);
  const criado = um(/"date_created"\s*:\s*"([0-9T:.\-+Z]{10,})"/) || um(/"start_time"\s*:\s*"([0-9T:.\-+Z]{10,})"/);
  const apelido = um(/perfil\.mercadolivre\.com\.br\/([A-Za-z0-9_.\-%]+)/) || um(/"nickname"\s*:\s*"([^"]{2,60})"/);
  const vendidos = um(/"sold_quantity"\s*:\s*(\d+)/);
  const oficial = um(/"official_store_id"\s*:\s*(\d+)/);
  return {vendedor, item, criado, apelido: apelido ? decodeURIComponent(apelido) : null,
    vendidos: vendidos != null ? +vendidos : null, oficial: oficial ? +oficial : null};
}

async function anuncio(url) {
  if (cacheAnuncio.has(url)) return cacheAnuncio.get(url);
  const p = fetch(url, {credentials: "include"}).then(r => r.text()).then(h => lerAnuncio(h, url)).catch(() => ({}));
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
  return false;
});

if (typeof module !== "undefined") module.exports = {lerAnuncio};
