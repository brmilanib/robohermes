// Abre uma tela do nubi no servidor de teste (computador e celular), mostra os erros de JavaScript e salva a foto.
//   PORTA=8765 TELA="#/estoque" node ui_exemplo.mjs
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";
const STUB = `window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) } }; } };`;
const url = `http://127.0.0.1:${process.env.PORTA || 8765}/${process.env.TELA || "#/inicio"}`;
const b = await chromium.launch();
for (const [w, h, suf] of [[1440, 900, "pc"], [390, 844, "celular"]]) {
  const p = await b.newPage({viewport: {width: w, height: h}});
  const erros = []; p.on("pageerror", e => erros.push(e.message));
  await p.route("https://cdn.jsdelivr.net/**", r => r.fulfill({contentType: "application/javascript", body: STUB}));
  await p.route("https://fonts.**", r => r.abort()); await p.route("https://api.open-meteo.com/**", r => r.abort());
  await p.goto(url); await p.waitForTimeout(2500);
  const larg = await p.evaluate(() => document.documentElement.scrollWidth);
  console.log(suf, "erros de JS:", erros.length ? erros : "nenhum", "| rolagem para o lado:", larg > w ? `SIM (${larg}px)` : "não");
  await p.screenshot({path: `${process.env.TMPDIR || "/tmp"}/nubi-${suf}.png`, fullPage: true});
  await p.close();
}
await b.close();
