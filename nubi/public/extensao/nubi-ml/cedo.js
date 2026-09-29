// nubi · Mercado Livre — roda no começo da página (29/09, print do Bruno: "Vendas —" e "a página não trouxe o produto" em
// todos os cards). O estado da busca (script __NORDIC_RENDERING_CTX__ com a lista "printed_result") é tirado da página
// depois que ela monta; guardamos uma cópia do texto assim que o script aparece, para o conteudo.js ler depois. Só lê.
(() => {
  const porScript = new Map(), extras = new Set();
  const util = t => t && t.length > 200 && /printed_result|polycard/.test(t);
  // cópia viva: sempre o texto mais longo de cada script (o parser pode entregar o texto em pedaços)
  globalThis.__nubiScripts = {[Symbol.iterator]: function* () { yield* porScript.values(); yield* extras; }};
  const pegar = s => {
    if (!s || s.tagName !== "SCRIPT") return;
    const t = s.textContent || "";
    if (util(t) && t.length > (porScript.get(s) || "").length) porScript.set(s, t);
  };
  const varrer = () => document.querySelectorAll("script").forEach(pegar);
  try {
    new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => {
      if (n.tagName === "SCRIPT") { pegar(n); setTimeout(() => pegar(n), 0); }
      else if (n.parentNode && n.parentNode.tagName === "SCRIPT") pegar(n.parentNode);
    }))).observe(document.documentElement || document, {childList: true, subtree: true});
  } catch (e) { /* sem observador: fica só a varredura abaixo */ }
  document.addEventListener("DOMContentLoaded", varrer);
  // a página também guarda o estado em window._n.ctx.r (mundo da página): pagina.js manda para cá
  window.addEventListener("message", e => {
    if (e.source === window && e.data && typeof e.data.nubiEstado === "string" && util(e.data.nubiEstado)) extras.add(e.data.nubiEstado);
  });
})();
