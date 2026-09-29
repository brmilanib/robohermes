// 29/09 (Bruno: "quando dou um clique na extensão quero esse menu igual [ao do Hunter]"). Só abre o painel na aba do ML e links do nubi;
// nada de login nem token aqui.
const $ = s => document.querySelector(s);
const ML = /^https:\/\/[a-z.]*mercadolivre\.com\.br\//;
let ABA = null;
document.querySelectorAll("[data-ic]").forEach(i => { if (window.nubiIcone) i.innerHTML = window.nubiIcone(i.dataset.ic, 20); });
try { if (localStorage.getItem("nubi-tema") === "escuro") document.body.classList.add("escuro"); } catch (e) { /* sem storage */ }
$("#tema").onclick = () => { const e = document.body.classList.toggle("escuro"); try { localStorage.setItem("nubi-tema", e ? "escuro" : "claro"); } catch (er) { /* sem storage */ } };
chrome.storage && chrome.storage.local.get("ajustes", r => { const n = ((r || {}).ajustes || {}).nome; if (n) { $("#nome").textContent = n; $(".avatar").textContent = n.split(/\s+/).map(x => x[0]).join("").slice(0, 2).toUpperCase(); } });
function estado(txt, ok) { $("#estado").textContent = txt; $("#abrir").disabled = !ok; document.querySelectorAll("[data-aba]").forEach(b => b.disabled = !ok); }
chrome.tabs.query({active: true, currentWindow: true}, abas => {
  ABA = abas && abas[0];
  if (!ABA || !ML.test(ABA.url || "")) return estado("Abra uma página do Mercado Livre", false);
  chrome.tabs.sendMessage(ABA.id, {tipo: "oi"}, r => {
    if (chrome.runtime.lastError || !r) return estado("Recarregue a página do ML para ligar o nubi", false);
    estado(r.anuncio ? "Painel disponível · anúncio aberto" : "Painel disponível nesta aba", true);
  });
});
function abrir(aba) { if (!ABA) return; chrome.tabs.sendMessage(ABA.id, {tipo: "abrir_painel", aba}, () => window.close()); }
$("#abrir").onclick = () => abrir("inicio");
document.querySelectorAll("[data-aba]").forEach(b => b.onclick = () => abrir(b.dataset.aba));
