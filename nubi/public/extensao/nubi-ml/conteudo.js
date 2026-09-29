// nubi · Mercado Livre — o que aparece na página do ML (29/09, pedido do Bruno: "igual à extensão do Hunter").
// Na busca: embaixo de cada anúncio, a loja real (nome, cidade, reputação, vendas, data do anúncio) e o link para o nubi.
// No anúncio: um quadro com a loja. Só lê a página; nada é clicado nem comprado.
(() => {
  const NUBI = "https://nubi-explorador.vercel.app";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const nf = n => n == null ? "—" : Number(n).toLocaleString("pt-BR");
  const dia = iso => { const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? `${m[3]}/${m[2]}/${m[1]}` : ""; };
  const diasDesde = iso => { const t = Date.parse(iso || ""); return isNaN(t) ? null : Math.max(0, Math.round((Date.now() - t) / 864e5)); };
  const pedir = msg => new Promise(ok => { try { chrome.runtime.sendMessage(msg, r => ok(r || {})); } catch (e) { ok({}); } });

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

  // ---- página do anúncio: um quadro com a loja
  function paginaDoAnuncio() {
    if (!/MLB-?\d{6,}|\/p\/MLB|\/up\/MLBU/.test(location.href) || document.getElementById("nubi-ml-quadro")) return;
    const q = document.createElement("div");
    q.id = "nubi-ml-quadro"; q.className = "nubi-ml-quadro";
    q.innerHTML = `<div class="nubi-ml-cab">nubi · loja deste anúncio</div><div class="nubi-ml-corpo">lendo…</div>`;
    document.body.appendChild(q);
    pedir({tipo: "pagina", url: location.href, html: document.documentElement.innerHTML}).then(a => {
      q.querySelector(".nubi-ml-corpo").innerHTML = linhaLoja(a) +
        (a.item ? `<div style="margin-top:6px"><a class="nubi-ml-bt" href="${NUBI}/#/ml/anuncio/${esc(a.item)}" target="_blank" rel="noopener">🧮 analisar no nubi</a></div>` : "");
    });
  }

  // ---- busca/lista/loja: embaixo de cada anúncio
  const feitos = new WeakSet();
  let fila = [], rodando = 0;
  function cartoes() {
    const out = [];
    document.querySelectorAll("a[href*='mercadolivre.com.br']").forEach(a => {
      const h = a.getAttribute("href") || "";
      if (!/MLB-?\d{6,}|\/p\/MLB\d|\/up\/MLBU\d/.test(h) || /click\d?\.mercadolivre/.test(h)) return;
      const c = a.closest("li.ui-search-layout__item, .poly-card, .ui-search-result, .andes-card") || null;
      if (c && !feitos.has(c)) { feitos.add(c); out.push([c, a.href]); }
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
    fila.push(...cartoes().slice(0, 60));
    andar();
  }

  paginaDoAnuncio();
  varrer();
  new MutationObserver(() => { clearTimeout(varrer.t); varrer.t = setTimeout(varrer, 800); })
    .observe(document.body, {childList: true, subtree: true});
})();
