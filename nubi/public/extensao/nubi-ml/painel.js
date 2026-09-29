// nubi · painel lateral (29/09, pedido do Bruno: "as mesmas funções das abas do lado do Hunter"): Início, Calculadora,
// Histórico de análises, Tendências de busca, Gerador EAN e Ajustes. Tudo fica NESTE navegador (chrome.storage.local);
// o que vem de fora é só dado público do ML pela rota ext_* do nubi (sem login, sem token).
(() => {
  const NUBI = "https://nubi-explorador.vercel.app";
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const brl = n => n == null || isNaN(n) ? "—" : Number(n).toLocaleString("pt-BR", {style: "currency", currency: "BRL"});
  const pct = n => n == null || !isFinite(n) ? "—" : (100 * n).toFixed(2).replace(".", ",") + "%";
  const num = v => { const x = parseFloat(String(v ?? "").replace(/\./g, "").replace(",", ".")); return isNaN(x) ? 0 : x; };
  const numCampo = v => { const s = String(v ?? "").trim(); return s.includes(",") ? num(s) : (parseFloat(s) || 0); };
  const PADRAO = {nome: "Bruno", imposto: 0, busca: true, quadro: true};

  // guardar neste navegador (sem chrome.storage, nos testes, usa o localStorage)
  const guardado = {
    async ler(k, pad) {
      try { if (chrome?.storage?.local) { const r = await chrome.storage.local.get(k); return r[k] ?? pad; } } catch (e) { /* segue */ }
      try { const v = localStorage.getItem("nubi-" + k); return v ? JSON.parse(v) : pad; } catch (e) { return pad; }
    },
    async gravar(k, v) {
      try { if (chrome?.storage?.local) { await chrome.storage.local.set({[k]: v}); return; } } catch (e) { /* segue */ }
      try { localStorage.setItem("nubi-" + k, JSON.stringify(v)); } catch (e) { /* sem onde guardar */ }
    }
  };
  const pedir = msg => new Promise(ok => { try { chrome.runtime.sendMessage(msg, r => ok(r || {})); } catch (e) { ok({erro: "extensão sem conexão"}); } });

  // tarifa do ML: % do tipo + custo fixo abaixo de R$ 79 (regra de 2025; a API manda a certa quando o anúncio está aberto)
  function taxaFixa(p) { return p <= 0 || p >= 79 ? 0 : p < 12.5 ? p * 0.5 : p < 29 ? 6.25 : p < 50 ? 6.5 : 6.75; }

  let ATUAL = null, ABA = "inicio", CALC = null, AJ = {...PADRAO};

  function novaCalc(a) {
    const t = (a && a.tarifas) || {};
    return {preco: a && a.preco || 0, tipo: a && a.tipo === "gold_special" ? "gold_special" : "gold_pro",
      pct: {gold_special: t.gold_special ? t.gold_special.pct : 12, gold_pro: t.gold_pro ? t.gold_pro.pct : 17},
      fixaApi: {gold_special: t.gold_special ? t.gold_special.fixa : null, gold_pro: t.gold_pro ? t.gold_pro.fixa : null},
      precoApi: a && a.preco || null, custo: 0, imposto: AJ.imposto || 0,
      freteGratis: !!(a && a.preco >= 79) || !!(a && a.frete), frete: a && a.frete || 0, freteCustom: false, freteManual: 0,
      titulo: a && a.titulo || "", foto: a && a.foto || "", link: a && a.link || "", item: a && a.item || ""};
  }

  function contas(c) {
    const p = c.preco || 0;
    const fixa = c.precoApi && Math.abs(p - c.precoApi) < 0.005 && c.fixaApi[c.tipo] != null ? c.fixaApi[c.tipo] : taxaFixa(p);
    const taxa = p * (c.pct[c.tipo] || 0) / 100 + fixa;
    const frete = c.freteCustom ? c.freteManual : c.freteGratis ? c.frete : 0;
    const imposto = p * (c.imposto || 0) / 100;
    const recebido = p - taxa - frete;
    const lucro = recebido - imposto - (c.custo || 0);
    return {taxa, fixa, frete, imposto, recebido, lucro, margem: p ? lucro / p : null, roi: c.custo ? lucro / c.custo : null};
  }

  // ---------------- abas
  const ABAS = {
    inicio() {
      const a = ATUAL;
      return `<p class="sub">Bem-vindo de volta</p><h2>Olá, ${esc(AJ.nome || "Bruno")}</h2>
        ${a && a.item ? `<div class="cartao" style="margin-top:12px"><div class="fraco">Anúncio aberto</div><b>${esc(a.titulo || a.item)}</b>
          <div>${brl(a.preco)} · ${esc(a.loja || "")}</div></div>` : `<p class="fraco" style="margin-top:12px">Abra um anúncio do Mercado Livre para ver os dados dele aqui.</p>`}
        <p class="sub" style="margin-top:14px">ATALHOS</p>
        <div class="grade">
          <button class="atalho" data-ir="calc">🧮<b>Calculadora</b></button><button class="atalho" data-ir="hist">🕘<b>Histórico</b></button>
          <button class="atalho" data-ir="tend">🔥<b>Tendências</b></button><button class="atalho" data-ir="ean">▦<b>Gerador EAN</b></button>
        </div>
        <p class="sub" style="margin-top:14px">NO NUBI</p>
        <div class="grade">
          <a class="atalho" href="${NUBI}/#/ml" target="_blank" rel="noopener">🛰️<b>Mercado Livre</b></a>
          <a class="atalho" href="${NUBI}/#/vendedores-ml" target="_blank" rel="noopener">🔗<b>Vendedores × ML</b></a>
          ${a && a.item ? `<a class="atalho" href="${NUBI}/#/ml/anuncio/${esc(a.item)}" target="_blank" rel="noopener">📊<b>Este anúncio</b></a>` : ""}
          ${a && a.vendedor ? `<a class="atalho" href="${NUBI}/#/ml/loja/${esc(a.vendedor)}" target="_blank" rel="noopener">🏪<b>Esta loja</b></a>` : ""}
        </div>`;
    },
    calc() {
      const c = CALC || (CALC = novaCalc(ATUAL)), r = contas(c);
      const v = x => x ? String(x).replace(".", ",") : "";
      return `<h2>Calculadora</h2><p class="sub">Recalcula na hora conforme você ajusta${c.titulo ? ` · <b>${esc(c.titulo)}</b>` : ""}</p>
        <label>Preço de venda (R$)</label><input id="c-preco" inputmode="decimal" value="${v(c.preco)}">
        <label>Tipo de anúncio · comissão varia por categoria</label>
        <div class="tipos"><button data-tipo="gold_special" class="${c.tipo === "gold_special" ? "on" : ""}">Clássico<small>${v(c.pct.gold_special)}%</small></button>
          <button data-tipo="gold_pro" class="${c.tipo === "gold_pro" ? "on" : ""}">Premium<small>${v(c.pct.gold_pro)}%</small></button></div>
        <div class="grade"><div><label>Custo do produto (R$)</label><input id="c-custo" inputmode="decimal" value="${v(c.custo)}"></div>
          <div><label>Imposto (%)</label><input id="c-imp" inputmode="decimal" value="${v(c.imposto)}"></div></div>
        <div class="chave"><div><b>Frete grátis</b><small>Pago pelo vendedor; obrigatório a partir de R$ 79${c.frete ? ` · ML: ${brl(c.frete)}` : ""}</small></div>
          <input type="checkbox" id="c-fg" style="width:auto" ${c.freteGratis ? "checked" : ""}></div>
        ${c.freteGratis && !c.frete && !c.freteCustom ? `<p class="fraco">O ML não mandou o frete deste anúncio: use o frete customizado.</p>` : ""}
        <div class="chave"><div><b>Frete customizado</b><small>Informar o valor do frete no lugar do estimado</small></div>
          <input type="checkbox" id="c-fc" style="width:auto" ${c.freteCustom ? "checked" : ""}></div>
        ${c.freteCustom ? `<label>Frete (R$)</label><input id="c-fm" inputmode="decimal" value="${v(c.freteManual)}">` : ""}
        <div class="lucro ${r.lucro < 0 ? "neg" : ""}"><div class="fraco">Lucro líquido</div><div class="v">${brl(r.lucro)}</div>
          <div class="duas"><div><small>MARGEM</small><b>${pct(r.margem)}</b></div><div><small>ROI</small><b>${c.custo ? pct(r.roi) : "—"}</b></div></div></div>
        <div class="linha"><span>Frete</span><b>${brl(r.frete)}</b></div>
        <div class="linha"><span>Taxa ML</span><b>${brl(r.taxa)} <span class="fraco">${v(c.pct[c.tipo])}%${r.fixa ? ` + ${brl(r.fixa)}` : ""}</span></b></div>
        <div class="linha"><span>Imposto</span><b>${brl(r.imposto)}</b></div>
        <div class="linha"><span>Valor recebido</span><b>${brl(r.recebido)}</b></div>
        <div class="linha"><span>Valor líquido</span><b>${brl(r.lucro)}</b></div>
        <button class="bt cheio" id="c-salvar" ${c.custo ? "" : "disabled"}>💾 Salvar análise</button>
        ${c.custo ? "" : `<p class="fraco" style="text-align:center">Informe o custo do produto para salvar no histórico</p>`}
        <button class="bt leve cheio" id="c-limpar">Limpar</button>`;
    },
    async hist() {
      const h = await guardado.ler("historico", []);
      if (!h.length) return `<h2>Histórico de análises</h2><p class="sub">Seus cálculos salvos</p><p class="fraco">Nada salvo ainda. Use a calculadora e "Salvar análise".</p>`;
      const quando = t => { const d = (Date.now() - t) / 864e5; return d < 1 ? "hoje" : d < 30 ? `há ${Math.round(d)} dia(s)` : `há ${Math.round(d / 30)} mês(es)`; };
      return `<h2>Histórico de análises</h2><p class="sub">Seus cálculos salvos (${h.length})</p>` + h.map((x, i) => `
        <div class="item">${x.foto ? `<img src="${esc(x.foto)}" alt="">` : `<div class="sem"></div>`}
          <div class="meio"><b title="${esc(x.titulo)}">${esc(x.titulo || x.item || "Análise")}</b>
            <span class="fraco">${quando(x.quando)} · ${brl(x.preco)} · custo ${brl(x.custo)}</span></div>
          <div class="dir"><b class="${x.lucro < 0 ? "neg" : ""}">${brl(x.lucro)}</b><div class="fraco">${pct(x.margem)}</div></div>
          <div><button class="mini" data-reabrir="${i}" title="Abrir na calculadora">🧮</button>
            ${x.link ? `<a class="mini" href="${esc(x.link)}" target="_blank" rel="noopener" title="Abrir o anúncio">↗</a>` : ""}
            <button class="mini" data-apagar="${i}" title="Apagar">🗑</button></div></div>`).join("");
    },
    async tend() {
      const cats = await pedir({tipo: "nubi", rota: "ext_categorias"});
      const sel = await guardado.ler("tend_cat", "");
      const t = await pedir({tipo: "nubi", rota: "ext_tendencias", params: {categoria: sel}});
      return `<h2>🔥 Tendências de busca</h2><p class="sub">Termos mais buscados no Mercado Livre hoje</p>
        <label>Categoria</label><select id="t-cat"><option value="">Geral</option>${(cats.categorias || []).map(c =>
          `<option value="${esc(c.id)}" ${c.id === sel ? "selected" : ""}>${esc(c.nome)}</option>`).join("")}</select>
        <div style="margin-top:10px">${t.erro ? `<p class="erro">${esc(t.erro)}</p>` : (t.termos || []).map((x, i) => `
          <div class="termo"><span class="n">${i + 1}</span><a href="https://lista.mercadolivre.com.br/${encodeURIComponent(x.termo)}" target="_blank" rel="noopener">${esc(x.termo)}</a>
            <button class="mini" data-copiar="${esc(x.termo)}" title="Copiar">⧉</button></div>`).join("") || `<p class="fraco">Sem termos agora.</p>`}</div>`;
    },
    ean() {
      return `<h2>▦ Gerador EAN</h2><p class="sub">EAN-13 com o dígito verificador certo (para kits e produtos sem código)</p>
        <div class="grade"><div><label>Começo (prefixo)</label><input id="e-pre" inputmode="numeric" value="789"></div>
          <div><label>Quantos</label><input id="e-qtd" inputmode="numeric" value="5"></div></div>
        <button class="bt cheio" id="e-gerar">Gerar</button><div id="e-lista" style="margin-top:10px"></div>
        <label style="margin-top:16px">Conferir um código</label><input id="e-conf" inputmode="numeric" placeholder="cole o EAN/GTIN"><div id="e-res" class="fraco"></div>
        <p class="fraco" style="margin-top:12px">Código gerado aqui não é registrado na GS1: serve para uso interno. Para vender como marca própria, use o seu prefixo GS1.</p>`;
    },
    ajustes() {
      return `<h2>⚙ Ajustes</h2><p class="sub">Ficam só neste navegador</p>
        <label>Seu nome</label><input id="a-nome" value="${esc(AJ.nome)}">
        <label>Imposto padrão na calculadora (%)</label><input id="a-imp" inputmode="decimal" value="${String(AJ.imposto || 0).replace(".", ",")}">
        <div class="chave"><div><b>Loja embaixo de cada anúncio da busca</b></div><input type="checkbox" id="a-busca" style="width:auto" ${AJ.busca ? "checked" : ""}></div>
        <div class="chave"><div><b>Quadro nubi Spy na página do produto</b></div><input type="checkbox" id="a-quadro" style="width:auto" ${AJ.quadro ? "checked" : ""}></div>
        <button class="bt cheio" id="a-salvar">Salvar</button><p class="fraco" id="a-ok"></p>`;
    }
  };

  function eanDigito(d12) { let s = 0; for (let i = 0; i < 12; i++) s += +d12[i] * (i % 2 ? 3 : 1); return (10 - s % 10) % 10; }
  function eanValido(c) { c = String(c).replace(/\D/g, ""); if (![8, 12, 13, 14].includes(c.length)) return false;
    const d = c.padStart(14, "0"); let s = 0; for (let i = 0; i < 13; i++) s += +d[i] * (i % 2 ? 1 : 3); return (10 - s % 10) % 10 === +d[13]; }

  async function desenhar(aba) {
    ABA = aba || ABA;
    document.querySelectorAll("#pn-trilho button").forEach(b => b.classList.toggle("on", b.dataset.aba === ABA));
    const corpo = $("#pn-corpo");
    if (ABA === "tend") corpo.innerHTML = `<p class="fraco">Buscando as tendências…</p>`;
    corpo.innerHTML = await ABAS[ABA]();
  }

  // ---------------- eventos
  document.addEventListener("click", async e => {
    const t = e.target.closest("button, a"); if (!t) return;
    if (t.dataset.aba || t.dataset.ir) return desenhar(t.dataset.aba || t.dataset.ir);
    if (t.id === "pn-fechar") return parent.postMessage({tipo: "nubi-fechar"}, "*");
    if (t.dataset.tipo) { CALC.tipo = t.dataset.tipo; return desenhar("calc"); }
    if (t.id === "c-limpar") { CALC = novaCalc(null); return desenhar("calc"); }
    if (t.id === "c-salvar") {
      const r = contas(CALC), h = await guardado.ler("historico", []);
      h.unshift({titulo: CALC.titulo, foto: CALC.foto, link: CALC.link, item: CALC.item, preco: CALC.preco, custo: CALC.custo, tipo: CALC.tipo,
        imposto: CALC.imposto, frete: r.frete, lucro: r.lucro, margem: r.margem, quando: Date.now()});
      await guardado.gravar("historico", h.slice(0, 300));
      return desenhar("hist");
    }
    if (t.dataset.apagar != null) { const h = await guardado.ler("historico", []); h.splice(+t.dataset.apagar, 1); await guardado.gravar("historico", h); return desenhar("hist"); }
    if (t.dataset.reabrir != null) {
      const x = (await guardado.ler("historico", []))[+t.dataset.reabrir];
      CALC = Object.assign(novaCalc(null), {preco: x.preco, custo: x.custo, tipo: x.tipo || "gold_pro", imposto: x.imposto || 0, titulo: x.titulo,
        foto: x.foto, link: x.link, item: x.item, freteCustom: !!x.frete, freteManual: x.frete || 0, freteGratis: !!x.frete});
      return desenhar("calc");
    }
    if (t.dataset.copiar) { try { await navigator.clipboard.writeText(t.dataset.copiar); t.textContent = "✓"; } catch (er) { /* sem área de transferência */ } return; }
    if (t.id === "e-gerar") {
      const pre = String($("#e-pre").value).replace(/\D/g, "").slice(0, 11), qtd = Math.min(50, Math.max(1, +$("#e-qtd").value || 1));
      const cods = Array.from({length: qtd}, () => { let d = pre; while (d.length < 12) d += Math.floor(Math.random() * 10); return d + eanDigito(d); });
      $("#e-lista").innerHTML = cods.map(c => `<div class="termo"><span class="ean" style="flex:1">${c}</span><button class="mini" data-copiar="${c}">⧉</button></div>`).join("") +
        `<button class="bt leve" data-copiar="${cods.join("\n")}">Copiar todos</button>`;
      return;
    }
    if (t.id === "a-salvar") {
      AJ = {nome: $("#a-nome").value.trim() || "Bruno", imposto: numCampo($("#a-imp").value), busca: $("#a-busca").checked, quadro: $("#a-quadro").checked};
      await guardado.gravar("ajustes", AJ);
      $("#a-ok").textContent = "Salvo. Recarregue a página do ML para valer na busca e no quadro.";
    }
  });
  document.addEventListener("input", e => {
    const id = e.target.id;
    if (id === "e-conf") { const c = e.target.value.replace(/\D/g, ""); $("#e-res").innerHTML = !c ? "" : eanValido(c) ? `<span class="ok">✔ código válido</span>` : `<span class="erro">✘ dígito verificador não bate</span>`; return; }
    if (!CALC || !/^c-/.test(id)) return;
    if (id === "c-preco") CALC.preco = numCampo(e.target.value);
    if (id === "c-custo") CALC.custo = numCampo(e.target.value);
    if (id === "c-imp") CALC.imposto = numCampo(e.target.value);
    if (id === "c-fm") CALC.freteManual = numCampo(e.target.value);
    if (id === "c-fg") CALC.freteGratis = e.target.checked;
    if (id === "c-fc") CALC.freteCustom = e.target.checked;
    // redesenha sem perder o campo em que o Bruno está digitando
    const pos = e.target.selectionStart;
    desenhar("calc").then(() => { const n = document.getElementById(id); if (n && n.type !== "checkbox") { n.focus(); try { n.setSelectionRange(pos, pos); } catch (er) { /* número */ } } });
  });
  document.addEventListener("change", async e => {
    if (e.target.id === "t-cat") { await guardado.gravar("tend_cat", e.target.value); desenhar("tend"); }
  });

  // a página do ML manda o anúncio aberto e qual aba abrir
  window.addEventListener("message", e => {
    if (e.source !== parent || !e.data || e.data.tipo !== "nubi-painel") return;
    const chave = a => a ? JSON.stringify([a.item, a.preco, a.tarifas, a.frete]) : "";
    const mudou = e.data.atual && chave(ATUAL) !== chave(e.data.atual);
    ATUAL = e.data.atual || ATUAL;
    if (e.data.aba === "calc" || mudou) {      // o anúncio novo (ou a comissão que chegou) entra; o custo digitado fica
      const velho = CALC;
      CALC = novaCalc(ATUAL);
      if (velho && velho.item === CALC.item) Object.assign(CALC, {custo: velho.custo, imposto: velho.imposto});
    }
    desenhar(e.data.aba || ABA);
  });

  guardado.ler("ajustes", PADRAO).then(a => { AJ = {...PADRAO, ...a}; desenhar("inicio"); parent.postMessage({tipo: "nubi-pronto"}, "*"); });
})();
