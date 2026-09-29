// nubi · Mercado Livre — roda no mundo da própria página (só lê): manda para a extensão o estado da busca que o ML guarda
// em window._n.ctx.r (a lista "printed_result"), caso o script da página já tenha sido tirado.
(() => {
  const mandar = () => {
    try {
      const r = window._n && window._n.ctx && window._n.ctx.r;
      if (typeof r === "string" && r.length > 200) window.postMessage({nubiEstado: r}, location.origin);
    } catch (e) { /* nada */ }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mandar); else mandar();
})();
