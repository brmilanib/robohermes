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
  const diasDesde = iso => { const t = Date.parse(iso || ""); return isNaN(t) ? null : Math.max(0, Math.floor((Date.now() - t) / 864e5)); };
  const pedir = msg => new Promise(ok => { try { chrome.runtime.sendMessage(msg, r => ok(r || {})); } catch (e) { ok({}); } });
  const TIPO = {gold_special: "Clássico", gold_pro: "Premium", gold_premium: "Premium"};
  let AJ = {busca: true, quadro: true};

  function linhaLoja(a) {
    const l = a.loja || {}, d = diasDesde(a.criado);
    const nome = l.nome || a.apelido || (a.vendedor ? "loja " + a.vendedor : "");
    if (!nome) return `<span class="nubi-ml-fraco">nubi: não achei a loja deste anúncio${a.motivo ? ` — ${esc(a.motivo)}` : ""}</span>`;
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

  const ic = (nome, tam) => (window.nubiIcone ? window.nubiIcone(nome, tam) : "");

  function nota(a, n, contas) {
    // regras fixas e explicadas (sem IA): procura, conversão, reputação da loja e preço contra o catálogo
    const partes = [], peso = [];
    const vc = n.visitas && n.visitas.catalogo != null ? n.visitas.catalogo / 30 : n.visitas && n.visitas.anuncio != null ? n.visitas.anuncio / 30 : null;
    if (vc != null) { partes.push(40 * Math.min(1, vc / 100)); peso.push(40); }
    if (contas.conv != null) { partes.push(25 * Math.min(1, contas.conv / 0.03)); peso.push(25); }
    const nivel = +((n.loja || a.loja || {}).nivel || 0);
    if (nivel) { partes.push(3 * nivel); peso.push(15); }
    if (contas.menor && a.preco) { partes.push(20 * Math.min(1, contas.menor / a.preco)); peso.push(20); }
    if (!peso.length) return null;
    const v = Math.round(100 * partes.reduce((s, x) => s + x, 0) / peso.reduce((s, x) => s + x, 0));
    const txt = vc != null && vc < 20 ? "Demanda fraca: poucas visitas por dia." : contas.conv != null && contas.conv < 0.01 ? "Conversão baixa: muita visita para pouca venda." :
      contas.menor && a.preco > contas.menor * 1.05 ? "Preço acima do menor do catálogo." : vc != null && vc >= 100 ? "Demanda forte." : "Procura e preço dentro da média.";
    return {v, rotulo: v >= 70 ? "Boa" : v >= 45 ? "Média" : "Fraca", txt};
  }

  // um bloco de número no estilo do quadro: ícone colorido, título, valor grande e a linha de baixo
  const linha = (icone, cor, titulo, valor, unid, sub, extra) => `
    <div class="nubi-spy-met"><div class="nubi-spy-l"><span class="nubi-spy-tit"><i class="nubi-spy-bola ${cor}">${ic(icone, 13)}</i>${titulo}</span>
      <b>${valor}${unid ? `<small>${unid}</small>` : ""}</b></div>${extra || ""}${sub ? `<div class="nubi-spy-sub">${sub}</div>` : ""}</div>`;
  const TERMO = ["#ef4444", "#f97316", "#facc15", "#a3e635", "#22c55e"];

  function desenharQuadro(q, a, n) {
    const t = (n && n.tarifas) || {}, tp = a.tipo === "gold_premium" ? "gold_pro" : a.tipo;
    const tf = t[tp] || null;
    const comissao = tf ? (tf.total != null ? tf.total : a.preco * tf.pct / 100 + (tf.fixa || 0)) : null;
    const frete = n && n.frete != null ? n.frete : null;
    const recebido = comissao != null && a.preco ? a.preco - comissao - (frete || 0) : null;
    const h = (n && n.historico) || {}, est = n && n.criado_estimado;
    // data de entrada: a da página; senão o 1º dia com visita (API de visitas); senão o nº do MLB (estimativa)
    const [criado, fonte] = a.criado ? [a.criado, ""] : h.primeira_visita ? [h.primeira_visita, h.precisao && h.precisao !== "dia" ? `1ª visita (pela ${h.precisao === "mês" ? "janela do mês" : "semana"})` : "1ª visita"] :
      est ? [est.data, `estimado pelo nº ${a.item || ""}, pode errar`] : [null, ""];
    const dias = diasDesde(criado);
    const maisDe = !criado && h.mais_velho_que ? diasDesde(h.mais_velho_que) : null;
    const vendasDia = a.vendidos != null && dias ? a.vendidos / Math.max(dias, 1) : null;
    const v = (n && n.visitas) || {};
    const total = h.total != null ? h.total : null;
    const conv = a.vendidos != null && total ? Math.min(1, a.vendidos / total) : null;
    const l = (n && n.loja) || a.loja || {};
    const conc = (n && n.concorrentes) || [];
    const menor = conc.reduce((m, c) => c.preco && (m == null || c.preco < m) ? c.preco : m, null);
    const pos = conc.findIndex(c => c.eu) + 1;
    const proj = v.anuncio != null && conv != null ? v.anuncio * conv : vendasDia != null ? vendasDia * 30 : null;
    const nt = n ? nota(a, n, {conv, menor}) : null;
    const ld = !n ? `<span class="nubi-spy-ld"></span>` : null;
    const catalogo = /\/p\/MLB\d/.test(location.href);
    const nivel = +(l.nivel || 0);
    const cidade = l.cidade ? `${esc(l.cidade)}${l.uf ? " - BR-" + esc(l.uf) : ""}` : "";
    q.innerHTML = `
      <div class="nubi-spy-cab"><span class="nubi-spy-logo">n</span><b>nubi Spy</b>
        <span class="nubi-spy-chips">${a.full ? `<i class="full">${ic("raio", 10)}FULL</i>` : ""}<i>${catalogo ? "CATÁLOGO" : "NORMAL"}</i>${TIPO[a.tipo] ? `<i class="on">${esc(TIPO[a.tipo]).toUpperCase()}</i>` : ""}</span></div>
      ${n && n.erro ? `<div class="nubi-spy-aviso">nubi: ${esc(n.erro)}</div>` : ""}
      <div class="nubi-spy-3">
        <div><small>${ic("frete", 12)} Frete</small><b>${ld || (frete != null ? brl(frete) : a.preco < 79 ? "comprador" : "—")}</b></div>
        <div><small>${ic("pct", 12)} Comissão</small><b>${ld || brl(comissao)}</b>${tf && tf.pct ? `<em>${dec(tf.pct)}%</em>` : ""}</div>
        <div class="verde"><small>${ic("carteira", 12)} Valor recebido</small><b>${ld || brl(recebido)}</b></div>
      </div>
      ${linha("subindo", "laranja", "Conversão", conv != null ? `${(100 * conv).toLocaleString("pt-BR", {maximumFractionDigits: 1})}%` : ld || "—", "",
        conv != null ? `Vende a cada ${nf(Math.round(1 / conv))} visitas` : "precisa das visitas no total",
        `<div class="nubi-spy-barra"><i style="width:${conv != null ? Math.min(100, conv / 0.05 * 100) : 0}%"></i></div>`)}
      ${linha("olho", "azul", "Visitas", ld || dec(v.anuncio != null ? v.anuncio / 30 : null), "/dia",
        [total != null ? `${nf(total)} no total` : "", v.anuncio != null ? `${nf(v.anuncio)} em 30 dias` : ""].filter(Boolean).join(" · ") +
        (v.catalogo != null ? `<br>Catálogo: <b>${dec(v.catalogo / 30)}/dia</b>${v.parte != null ? ` · <b>${v.parte}%</b> deste anúncio` : ""}` : ""))}
      ${linha("carrinho", "verde", `Vendas <small class="nubi-spy-fraco">${a.vendidos != null ? (a.vendidosExato ? "" : "+") + nf(a.vendidos) + " total" : "sem o total"}</small>`,
        dec(vendasDia), "/dia", a.estoque != null ? `Estoque: <b>${nf(a.estoque)} un.</b>${vendasDia ? ` · dura ≈ ${nf(Math.round(a.estoque / vendasDia))} dias` : ""}` : "",
        `<div class="nubi-spy-l nubi-spy-sep"><span class="nubi-spy-tit"><i class="nubi-spy-bola roxo">${ic("cifrao", 13)}</i>Faturamento previsto</span>
          <b>R$ ${a.vendidos != null && a.preco ? mil(a.vendidos * a.preco) : "—"}</b></div>`)}
      ${nt ? `<div class="nubi-spy-nota"><div class="nubi-spy-l"><span class="nubi-spy-tit">${ic("estrela", 13)} Nota nubi</span>
          <span><i class="${nt.rotulo}">${nt.rotulo}</i> <b>${nt.v}</b><small>/100</small></span></div>
        <div class="nubi-spy-barra"><i style="width:${nt.v}%"></i></div><small>${esc(nt.txt)}</small></div>` : ""}
      <div class="nubi-spy-2">
        <div><small>${ic("estrela", 12)} Avaliações</small><b>${a.nota != null ? `${dec(a.nota)} ★` : "—"}</b><small>${a.avaliacoes != null ? `${nf(a.avaliacoes)} no total` : ""}</small></div>
        <div><small>${ic("relogio", 12)} Tempo ativo</small><b class="${dias != null && dias > 180 ? "velho" : ""}">${dias != null ? `${(est && fonte.startsWith("estimado")) || (h.precisao && h.precisao !== "dia" && !a.criado) ? "≈" : ""}${nf(dias)} dias` :
          maisDe != null ? `+${nf(maisDe)} dias` : ld || "—"}</b>
          <small>${criado ? `desde ${esc(dia(criado))}${fonte ? ` · ${esc(fonte)}` : ""}` : maisDe != null ? "mais velho que o histórico de visitas" : a.item ? esc(a.item) : ""}</small></div>
      </div>
      ${conc.length ? `<button class="nubi-spy-conc" data-nubi="conc">${ic("pessoas", 14)} Ver ${nf(n.total_concorrentes || conc.length)} concorrentes${menor ? ` · menor ${brl(menor)}` : ""} ›</button>
        <div class="nubi-spy-lista" hidden>${conc.slice(0, 60).map(c => `<div class="${c.eu ? "eu" : ""}">
          <a href="${esc(c.link)}" target="_blank" rel="noopener">${esc(c.loja || "loja " + c.vendedor_id)}</a>
          <span>${c.full ? `<em class="full">${ic("raio", 11)}FULL</em>` : ""}${c.loja_oficial ? "✔" : ""} ${esc(c.tipo || "")}</span><b>${brl(c.preco)}</b></div>`).join("")}</div>` : ""}
      <div class="nubi-spy-2 bts">
        <button class="nubi-spy-bt escuro" data-nubi="proj" ${proj != null ? "" : "disabled"}>${ic("subindo", 13)} Projeção de vendas</button>
        <button class="nubi-spy-bt" data-nubi="midias" ${a.fotos && a.fotos.length ? "" : "disabled"}>${ic("baixar", 13)} Baixar mídias${a.fotos && a.fotos.length ? ` (${a.fotos.length})` : ""}</button>
      </div>
      ${proj != null ? `<div class="nubi-spy-proj" hidden>${[7, 30, 90].map(d => `<div><small>${d} dias</small><b>≈ ${nf(Math.round(proj / 30 * d))}</b><small>R$ ${mil(proj / 30 * d * (a.preco || 0))}</small></div>`).join("")}
        <p>${conv != null ? "visitas dos últimos 30 dias × conversão" : "ritmo de vendas desde a entrada"}${pos ? ` · você está em ${pos}º de ${conc.length} no preço` : ""}</p></div>` : ""}
      <button class="nubi-spy-bt cheio" data-nubi="calc">${ic("calc", 13)} Abrir na calculadora</button>
      ${a.item ? `<a class="nubi-spy-mais" href="${NUBI}/#/ml/anuncio/${esc(a.item)}" target="_blank" rel="noopener">${ic("abrir", 12)} Ver mais dados no nubi</a>` : ""}
      ${a.itemApi && a.itemApi !== 200 ? `<div class="nubi-spy-diag">ML /items do navegador: ${esc(a.itemApi)}</div>` : ""}`;
    // perfil do vendedor: cartão próprio na coluna da direita, embaixo do "Comprar agora" (como o do Hunter)
    const vend = `<div class="nubi-spy-vcab">${ic("loja", 14)} Perfil do vendedor</div>
        <div class="nubi-spy-vtopo"><span class="nubi-spy-vic">${ic("loja", 18)}</span><div>
          <b>${esc(l.nome || a.apelido || "—")}</b>
          <div class="nubi-spy-fraco">${cidade ? `${ic("local", 11)} ${cidade}` : ""}
            ${l.medalha ? `<em class="medalha">${ic("medalha", 11)} ${esc(l.medalha)}</em>` : ""}${l.loja_oficial ? `<em class="oficial">✔ Loja oficial</em>` : ""}</div></div></div>
        <div class="nubi-spy-l nubi-spy-caixinha"><span>Vendas totais</span><b title="${l.vendas_ok != null ? `${nf(l.vendas)} com as canceladas` : ""}">${nf(l.vendas_ok != null ? l.vendas_ok : l.vendas)}</b></div>
        ${nivel ? `<div class="nubi-spy-termo">${TERMO.map((c, i) => `<i style="background:${c};opacity:${i + 1 === nivel ? 1 : .22}"></i>`).join("")}</div>` : ""}
        <div class="nubi-spy-2 bts">${l.link ? `<a class="nubi-spy-bt" href="${esc(l.link)}" target="_blank" rel="noopener">${ic("abrir", 13)} Ver página</a>` : "<span></span>"}
          ${a.vendedor ? `<a class="nubi-spy-bt" href="${NUBI}/#/ml/loja/${esc(a.vendedor)}" target="_blank" rel="noopener">${ic("grafico", 13)} No nubi</a>` : ""}</div>`;
    let cv = document.getElementById("nubi-ml-vendedor");
    if (!cv) {
      cv = document.createElement("div");
      cv.id = "nubi-ml-vendedor"; cv.className = "nubi-spy nubi-spy-vend";
      const bb = document.querySelector("#buybox-form, form.ui-pdp-buybox, .ui-pdp-buybox");
      const bloco = bb && (bb.closest(".ui-box-component, .ui-pdp-component-list") || bb);
      if (bloco && bloco.parentElement && !q.contains(bloco)) bloco.insertAdjacentElement("afterend", cv); else q.appendChild(cv);
    }
    cv.innerHTML = vend;
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
      if (b.dataset.nubi === "proj") { const pj = q.querySelector(".nubi-spy-proj"); if (pj) pj.hidden = !pj.hidden; }
      if (b.dataset.nubi === "midias") pedir({tipo: "baixar", urls: A.fotos, pasta: A.item || "anuncio"}).then(() => { b.textContent = "✓ baixando"; });
    });
    const A = await pedir({tipo: "pagina", url: location.href, html: document.documentElement.innerHTML});
    const metaPreco = document.querySelector('meta[itemprop="price"]');
    if (metaPreco && +metaPreco.content) A.preco = +metaPreco.content;
    const h1 = document.querySelector("h1.ui-pdp-title, h1");
    if (h1 && h1.textContent.trim()) A.titulo = h1.textContent.trim();
    desenharQuadro(q, A, null);
    const it = await pedir({tipo: "item", mlb: A.item});
    if (it.status) A.itemApi = it.status;
    if (it.status === 200) {
      if (it.criado) A.criado = it.criado;
      if (it.vendidos != null && it.vendidos !== A.vendidos) { A.vendidos = it.vendidos; A.vendidosExato = true; }
      if (it.estoque != null) A.estoque = it.estoque;
      A.vendedor = A.vendedor || it.vendedor; A.tipo = A.tipo || it.tipo; A.categoria = A.categoria || it.categoria;
      A.produto = A.produto || it.catalogo;
    }
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
  const pidDe = url => { const m = String(url).match(/\/p\/(MLB\d{5,})/i); return m ? m[1].toUpperCase() : null; };
  const widDe = url => { const m = String(url).match(/[?&#]wid=(MLB\d{6,})/i); return m ? m[1].toUpperCase() : null; };
  function caixa(c) {
    const box = document.createElement("div");
    box.className = "nubi-ml-linha"; box.innerHTML = `<span class="nubi-ml-fraco">nubi: lendo a loja…</span>`;
    c.appendChild(box);
    return box;
  }
  function andar() {
    while (rodando < 3 && fila.length) {
      const [box, url] = fila.shift();
      rodando++;
      pedir({tipo: "anuncio", url}).then(a => { box.innerHTML = linhaLoja(a); }).finally(() => { rodando--; andar(); });
    }
  }
  // cards de catálogo (/p/MLB…): o nubi diz de quem é o anúncio do card (ou quem ganha o produto), 40 por pedido;
  // os outros (e o que o nubi não achar) leem a página do anúncio
  async function porCatalogo(lote) {
    const chave = ([, url]) => pidDe(url) + (widDe(url) ? ":" + widDe(url) : "");
    for (let i = 0; i < lote.length; i += 40) {
      const parte = lote.slice(i, i + 40);
      const r = await pedir({tipo: "nubi", rota: "ext_vencedores", params: {pids: [...new Set(parte.map(chave))].join(",")}});
      parte.forEach(([box, url]) => {
        const v = (r.produtos || {})[chave([box, url])];
        if (v && v.vendedor) {
          box.innerHTML = linhaLoja({vendedor: v.vendedor, item: v.item, oficial: v.oficial, loja: v.loja}) +
            (v.do_card ? "" : `<span class="nubi-ml-fraco" title="o link do card não diz qual anúncio é">· quem ganha o produto agora</span>`);
        } else fila.push([box, url]);
      });
      andar();
    }
  }
  function varrer() {
    if (!AJ.busca || ehAnuncio()) return;
    const novos = cartoes().slice(0, 60).map(([c, url]) => [caixa(c), url]);
    fila.push(...novos.filter(([, url]) => !pidDe(url)));
    andar();
    const cat = novos.filter(([, url]) => pidDe(url));
    if (cat.length) porCatalogo(cat);
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
