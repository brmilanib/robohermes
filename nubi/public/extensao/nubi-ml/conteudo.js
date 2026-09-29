// nubi · Mercado Livre — o que aparece na página do ML (29/09, pedido do Bruno: "igual à extensão do Hunter").
// Na busca: embaixo de cada anúncio, a loja real (nome, cidade, reputação, vendas, data do anúncio) e o link para o nubi.
// No anúncio: o quadro "nubi Spy" (frete, comissão, valor recebido, visitas do catálogo, vendas, faturamento, nota, tempo
// ativo, concorrentes, perfil do vendedor) e o painel lateral (Início, Calculadora, Histórico, Tendências, Gerador EAN).
// Só lê a página; nada é clicado nem comprado.
(() => {
  const NUBI = "https://nubi-explorador.vercel.app";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const nf = n => n == null ? "—" : Number(n).toLocaleString("pt-BR");
  const brl = n => n == null || isNaN(n) ? "—" : Number(n).toLocaleString("pt-BR", {style: "currency", currency: "BRL"});
  const mil = n => n == null ? "—" : n >= 1000 ? (n / 1000).toLocaleString("pt-BR", {maximumFractionDigits: 1}) + " mil" : nf(Math.round(n));
  const dec = n => n == null || !isFinite(n) ? "—" : n.toLocaleString("pt-BR", {maximumFractionDigits: n < 10 ? 1 : 0});
  const dia = iso => { const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? `${m[3]}/${m[2]}/${m[1]}` : ""; };
  const diasDesde = iso => { const t = Date.parse(iso || ""); return isNaN(t) ? null : Math.max(0, Math.round((Date.now() - t) / 864e5)); };
  const pedir = msg => new Promise(ok => { try { chrome.runtime.sendMessage(msg, r => ok(r || {})); } catch (e) { ok({}); } });
  const TIPO = {gold_special: "Clássico", gold_pro: "Premium", gold_premium: "Premium"};
  let AJ = {busca: true, quadro: true};

  function linhaLoja(a) {
    const l = a.loja || {}, d = diasDesde(a.criado);
    const nome = l.nome || a.apelido || (a.vendedor ? "loja " + a.vendedor : "");
    if (!nome) return `<span class="nubi-ml-fraco">nubi: não achei a loja deste anúncio</span>`;
    return `<b>🏪 ${l.link ? `<a href="${esc(l.link)}" target="_blank" rel="noopener">${esc(nome)}</a>` : esc(nome)}</b>
      ${l.cidade ? `<span>📍 ${esc(l.cidade)}${l.uf ? "-" + esc(l.uf) : ""}</span>` : ""}
      ${l.nivel ? `<span class="nubi-ml-rep r${esc(l.nivel)}">rep ${esc(l.nivel)}/5</span>` : ""}
      ${l.medalha ? `<span>🎖 ${esc(l.medalha)}</span>` : ""}
      ${l.vendas != null ? `<span>🛒 ${nf(l.vendas)} vendas</span>` : ""}
      ${a.criado ? `<span>📅 criado ${esc(dia(a.criado))}${d != null ? ` (${d} dias)` : ""}</span>` : ""}
      ${a.oficial ? `<span>✔ loja oficial</span>` : ""}
      ${a.vendedor ? `<a class="nubi-ml-bt" href="${NUBI}/#/ml/loja/${esc(a.vendedor)}" target="_blank" rel="noopener">📊 nubi</a>` : ""}
      ${a.item ? `<span class="nubi-ml-fraco">${esc(a.item)}</span>` : ""}`;
  }

  // ---------------- painel lateral (iframe da própria extensão, como o do Hunter)
  let ATUAL = null, PAINEL = null;
  const origemExt = () => { try { const o = new URL(chrome.runtime.getURL("")).origin; return o && o !== "null" ? o : null; } catch (e) { return null; } };
  function mandarPainel(aba) {
    if (PAINEL && PAINEL.contentWindow) PAINEL.contentWindow.postMessage({tipo: "nubi-painel", aba, atual: ATUAL}, origemExt() || "*");
  }
  function abrirPainel(aba) {
    const url = (() => { try { return chrome.runtime.getURL("painel.html"); } catch (e) { return null; } })();
    if (!url) return;
    if (!PAINEL) {
      PAINEL = document.createElement("iframe");
      PAINEL.id = "nubi-ml-painel"; PAINEL.className = "nubi-ml-painel"; PAINEL.src = url;
      PAINEL.dataset.aba = aba || "inicio";
      document.body.appendChild(PAINEL);
    }
    PAINEL.classList.add("aberto");
    document.documentElement.classList.add("nubi-ml-com-painel");
    mandarPainel(aba);
  }
  function fecharPainel() {
    if (PAINEL) PAINEL.classList.remove("aberto");
    document.documentElement.classList.remove("nubi-ml-com-painel");
  }
  window.addEventListener("message", e => {
    if (!PAINEL || e.source !== PAINEL.contentWindow || (origemExt() && e.origin !== origemExt())) return;
    if (e.data && e.data.tipo === "nubi-pronto") mandarPainel(PAINEL.dataset.aba);
    if (e.data && e.data.tipo === "nubi-fechar") fecharPainel();
  });
  function aba() {
    if (document.getElementById("nubi-ml-aba")) return;
    const b = document.createElement("button");
    b.id = "nubi-ml-aba"; b.className = "nubi-ml-aba"; b.title = "nubi"; b.textContent = "n";
    b.addEventListener("click", () => (PAINEL && PAINEL.classList.contains("aberto") ? fecharPainel() : abrirPainel()));
    document.body.appendChild(b);
  }

  // ---------------- página do anúncio: quadro nubi Spy
  const ehAnuncio = () => /\/p\/MLB\d|MLB-?\d{6,}|\/up\/MLBU/.test(location.href);

  function nota(a, n, contas) {
    // regras fixas e explicadas (sem IA): procura, conversão, reputação da loja e preço contra o catálogo
    const partes = [], peso = [];
    const vc = n.visitas && n.visitas.catalogo != null ? n.visitas.catalogo / 30 : n.visitas && n.visitas.anuncio != null ? n.visitas.anuncio / 30 : null;
    if (vc != null) { partes.push(40 * Math.min(1, vc / 100)); peso.push(40); }
    if (contas.vendasDia != null && n.visitas && n.visitas.anuncio) { partes.push(25 * Math.min(1, (contas.vendasDia / (n.visitas.anuncio / 30)) / 0.03)); peso.push(25); }
    const nivel = +((n.loja || a.loja || {}).nivel || 0);
    if (nivel) { partes.push(3 * nivel); peso.push(15); }
    const menor = (n.concorrentes || []).reduce((m, c) => c.preco && (m == null || c.preco < m) ? c.preco : m, null);
    if (menor && a.preco) { partes.push(20 * Math.min(1, menor / a.preco)); peso.push(20); }
    if (!peso.length) return null;
    const v = Math.round(100 * partes.reduce((s, x) => s + x, 0) / peso.reduce((s, x) => s + x, 0));
    const txt = vc != null && vc < 20 ? "Demanda fraca: poucas visitas neste catálogo." : vc != null && vc >= 100 ? "Demanda forte neste catálogo." :
      menor && a.preco > menor * 1.05 ? "Preço acima do menor do catálogo." : "Procura e preço dentro da média.";
    return {v, rotulo: v >= 70 ? "Boa" : v >= 45 ? "Média" : "Fraca", txt};
  }

  function desenharQuadro(q, a, n) {
    const t = (n && n.tarifas) || {}, tp = a.tipo === "gold_premium" ? "gold_pro" : a.tipo;
    const tf = t[tp] || null;
    const comissao = tf ? (tf.total != null ? tf.total : a.preco * tf.pct / 100 + (tf.fixa || 0)) : null;
    const frete = n && n.frete != null ? n.frete : null;
    const recebido = comissao != null && a.preco ? a.preco - comissao - (frete || 0) : null;
    const est = n && n.criado_estimado;
    const criado = a.criado || (est && est.data);
    const dias = diasDesde(criado);
    const vendasDia = a.vendidos != null && dias ? a.vendidos / Math.max(dias, 1) : null;
    const v = (n && n.visitas) || {};
    const nt = n ? nota(a, n, {vendasDia}) : null;
    const l = (n && n.loja) || a.loja || {};
    const conc = (n && n.concorrentes) || [];
    const carregando = !n ? `<span class="nubi-ml-fraco">…</span>` : null;
    q.innerHTML = `
      <div class="nubi-spy-cab"><b>nubi Spy</b><span>${a.produto ? "CATÁLOGO" : "ANÚNCIO"}</span>${TIPO[a.tipo] ? `<span class="on">${esc(TIPO[a.tipo]).toUpperCase()}</span>` : ""}</div>
      ${n && n.erro ? `<div class="nubi-spy-aviso">nubi: ${esc(n.erro)}</div>` : ""}
      <div class="nubi-spy-3">
        <div><small>🚚 Frete</small><b>${carregando || (frete != null ? brl(frete) : a.preco < 79 ? "comprador" : "—")}</b></div>
        <div><small>% Comissão</small><b>${carregando || brl(comissao)}</b></div>
        <div><small>💰 Valor recebido</small><b>${carregando || brl(recebido)}</b></div>
      </div>
      <div class="nubi-spy-caixa">
        <div class="nubi-spy-l"><span>👁 Visitas ${a.produto ? "do catálogo" : "do anúncio"}</span>
          <b>${carregando || dec(((a.produto ? v.catalogo : v.anuncio) ?? null) != null ? (a.produto ? v.catalogo : v.anuncio) / 30 : null)}<small>/dia</small></b></div>
        <div class="nubi-spy-l nubi-ml-fraco"><span>${nf(a.produto ? v.catalogo : v.anuncio)} nos últimos 30 dias${a.produto && v.catalogo_lidos ? ` (${v.catalogo_lidos} anúncios)` : ""}</span>
          <span>${v.parte != null ? `<b>${v.parte}%</b> deste anúncio` : v.anuncio != null && a.produto ? `${nf(v.anuncio)} deste anúncio` : ""}</span></div>
      </div>
      <div class="nubi-spy-caixa">
        <div class="nubi-spy-l"><span>🛒 Vendas <small class="nubi-ml-fraco">· ${a.vendidos != null ? "+" + nf(a.vendidos) + " total" : "sem o total"}</small></span>
          <b>${dec(vendasDia)}<small>/dia</small></b></div>
        <div class="nubi-spy-l"><span>$ Faturamento (vendidos × preço)</span><b>R$ ${a.vendidos != null && a.preco ? mil(a.vendidos * a.preco) : "—"}</b></div>
      </div>
      ${nt ? `<div class="nubi-spy-nota"><div class="nubi-spy-l"><span>⭐ Nota nubi</span><span><i class="${nt.rotulo}">${nt.rotulo}</i> <b>${nt.v}</b><small>/100</small></span></div>
        <div class="nubi-spy-barra"><i style="width:${nt.v}%"></i></div><small>${esc(nt.txt)}</small></div>` : ""}
      <div class="nubi-spy-2">
        <div><small>🏪 Loja desde</small><b>${l.desde ? esc(dia(l.desde)) : "—"}</b><small>${l.vendas != null ? nf(l.vendas) + " vendas" : ""}</small></div>
        <div><small>⏱ Tempo ativo</small><b class="${dias != null && dias > 120 ? "velho" : ""}">${dias != null ? `${est && !a.criado ? "≈" : ""}${dias} dias` : "—"}</b>
          <small>${criado ? `desde ${esc(dia(criado))}${est && !a.criado ? ` (±${est.folga_dias} d, pelo nº)` : ""}` : ""}</small></div>
      </div>
      ${conc.length ? `<button class="nubi-spy-conc" data-nubi="conc">👥 Ver ${nf(n.total_concorrentes || conc.length)} concorrentes ›</button>
        <div class="nubi-spy-lista" hidden>${conc.slice(0, 60).map(c => `<div class="${c.eu ? "eu" : ""}">
          <a href="${esc(c.link)}" target="_blank" rel="noopener">${esc(c.loja || "loja " + c.vendedor_id)}</a>
          <span>${c.full ? "⚡" : ""}${c.loja_oficial ? "✔" : ""} ${esc(c.tipo || "")}</span><b>${brl(c.preco)}</b></div>`).join("")}</div>` : ""}
      <div class="nubi-spy-2">
        ${a.item ? `<a class="nubi-spy-bt" href="${NUBI}/#/ml/anuncio/${esc(a.item)}" target="_blank" rel="noopener">↗ Ver mais dados</a>` : "<span></span>"}
        <button class="nubi-spy-bt" data-nubi="midias" ${a.fotos && a.fotos.length ? "" : "disabled"}>⬇ Baixar mídias${a.fotos && a.fotos.length ? ` (${a.fotos.length})` : ""}</button>
      </div>
      <button class="nubi-spy-bt cheio" data-nubi="calc">🧮 Abrir na calculadora</button>
      <div class="nubi-spy-vend"><div class="nubi-spy-vcab">🏪 Perfil do vendedor</div>
        <b>${esc(l.nome || a.apelido || "—")}</b> ${l.cidade ? `<span class="nubi-ml-fraco">📍 ${esc(l.cidade)}${l.uf ? " - " + esc(l.uf) : ""}</span>` : ""}
        <div class="nubi-spy-l"><span>Vendas totais</span><b>${nf(l.vendas)}</b></div>
        ${l.nivel || l.medalha ? `<div class="nubi-spy-l"><span>Reputação</span><span>${l.nivel ? `<span class="nubi-ml-rep r${esc(l.nivel)}">${esc(l.nivel)}/5</span>` : ""} ${l.medalha ? "🎖 " + esc(l.medalha) : ""}</span></div>` : ""}
        <div class="nubi-spy-2">${l.link ? `<a class="nubi-spy-bt" href="${esc(l.link)}" target="_blank" rel="noopener">Ver página ↗</a>` : "<span></span>"}
          ${a.vendedor ? `<a class="nubi-spy-bt" href="${NUBI}/#/ml/loja/${esc(a.vendedor)}" target="_blank" rel="noopener">📊 no nubi</a>` : ""}</div>
      </div>`;
    ATUAL = {item: a.item, titulo: a.titulo, preco: a.preco, tipo: tp, foto: (a.fotos || [])[0] || "", link: location.href.split("#")[0],
      vendedor: a.vendedor, loja: l.nome || a.apelido || "", tarifas: t, frete};
    if (PAINEL) mandarPainel();
  }

  async function paginaDoAnuncio() {
    if (!ehAnuncio() || document.getElementById("nubi-ml-quadro")) return;
    const q = document.createElement("div");
    q.id = "nubi-ml-quadro"; q.className = "nubi-spy";
    // no lugar do Hunter (embaixo do preço); se a página mudar, fica fixo no canto
    const ancora = document.querySelector(".ui-pdp-container__row--price") || (document.querySelector(".ui-pdp-price") || {}).parentElement ||
      document.querySelector(".ui-pdp-header");
    if (ancora && ancora.parentElement) ancora.insertAdjacentElement("afterend", q); else { q.classList.add("solto"); document.body.appendChild(q); }
    q.innerHTML = `<div class="nubi-spy-cab"><b>nubi Spy</b></div><div class="nubi-ml-fraco" style="padding:10px">lendo o anúncio…</div>`;
    q.addEventListener("click", e => {
      const b = e.target.closest("[data-nubi]"); if (!b) return;
      if (b.dataset.nubi === "conc") { const l = q.querySelector(".nubi-spy-lista"); if (l) l.hidden = !l.hidden; }
      if (b.dataset.nubi === "calc") abrirPainel("calc");
      if (b.dataset.nubi === "midias") pedir({tipo: "baixar", urls: A.fotos, pasta: A.item || "anuncio"}).then(() => { b.textContent = "✓ baixando"; });
    });
    const A = await pedir({tipo: "pagina", url: location.href, html: document.documentElement.innerHTML});
    const metaPreco = document.querySelector('meta[itemprop="price"]');
    if (metaPreco && +metaPreco.content) A.preco = +metaPreco.content;
    const h1 = document.querySelector("h1.ui-pdp-title, h1");
    if (h1 && h1.textContent.trim()) A.titulo = h1.textContent.trim();
    desenharQuadro(q, A, null);
    const n = await pedir({tipo: "nubi", rota: "ext_ml", params: {mlb: A.item, pid: A.produto, vendedor: A.vendedor, categoria: A.categoria,
      tipo: A.tipo, preco: A.preco}});
    desenharQuadro(q, A, n);
  }

  // ---------------- busca/lista/loja: embaixo de cada anúncio
  const feitos = new WeakSet();
  let fila = [], rodando = 0;
  function cartoes() {
    const out = [];
    document.querySelectorAll("a[href*='mercadolivre.com.br']").forEach(a => {
      const h = a.getAttribute("href") || "";
      if (!/MLB-?\d{6,}|\/p\/MLB\d|\/up\/MLBU\d/.test(h) || /click\d?\.mercadolivre/.test(h)) return;
      const c = a.closest("li.ui-search-layout__item, .poly-card, .ui-search-result, .andes-card") || null;
      if (c && !feitos.has(c) && !(document.getElementById("nubi-ml-quadro") || {contains: () => false}).contains(c)) { feitos.add(c); out.push([c, a.href]); }
    });
    return out;
  }
  function andar() {
    while (rodando < 3 && fila.length) {
      const [c, url] = fila.shift();
      rodando++;
      const box = document.createElement("div");
      box.className = "nubi-ml-linha"; box.innerHTML = `<span class="nubi-ml-fraco">nubi: lendo a loja…</span>`;
      c.appendChild(box);
      pedir({tipo: "anuncio", url}).then(a => { box.innerHTML = linhaLoja(a); }).finally(() => { rodando--; andar(); });
    }
  }
  function varrer() {
    if (!AJ.busca || ehAnuncio()) return;
    fila.push(...cartoes().slice(0, 60));
    andar();
  }

  function comecar() {
    aba();
    if (AJ.quadro) paginaDoAnuncio();
    varrer();
    new MutationObserver(() => { clearTimeout(varrer.t); varrer.t = setTimeout(varrer, 800); })
      .observe(document.body, {childList: true, subtree: true});
  }
  try {
    if (chrome.storage && chrome.storage.local) chrome.storage.local.get("ajustes", r => { AJ = {...AJ, ...(r && r.ajustes) || {}}; comecar(); });
    else comecar();
  } catch (e) { comecar(); }
})();
