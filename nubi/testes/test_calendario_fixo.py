"""02/10 (card #143): o calendário do Nubimetrics passou a abrir num painel `position: fixed` (offsetParent nulo): os campos de
data 01/08/2026 → 31/08/2026 existiam, mas o coletor só olhava `offsetParent` e dizia "o calendário não mostrou os campos de data".
Página falsa igual ao print (botão do período, painel fixo com 2 campos e APLICAR); roda `aplicar_periodo` e `resumo_tela`."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PAGINA = """<html><body>
<button id="per">01 AGO - 31 AGO</button><div id="res"></div>
<div id="cal" style="display:none;position:fixed;top:60px;left:20px;background:#fff">
  <input value="01/08/2026" id="a"> <input value="31/08/2026" id="b">
  <button id="ap">APLICAR</button></div>
<script>
 per.onclick = () => cal.style.display = 'block';
 ap.onclick = () => { res.textContent = a.value + '|' + b.value; };
</script></body></html>"""


# variante B: os campos são texto editável (não <input>); variante C: só a grade de dias (clique no início e no fim)
PAGINA_B = """<html><body><button id="per">01 AGO - 31 AGO</button><div id="res"></div>
<div id="cal" style="display:none;position:fixed;top:60px;left:20px;background:#fff">
 <div contenteditable id="a">01/08/2026</div> <div contenteditable id="b">31/08/2026</div><button id="ap">APLICAR</button></div>
<script>per.onclick=()=>cal.style.display='block'; ap.onclick=()=>{res.textContent=a.innerText.trim()+'|'+b.innerText.trim();};
</script></body></html>"""

PAGINA_C = """<html><body><button id="per">01 AGO - 31 AGO</button><div id="res"></div>
<div id="cal" style="display:none;position:fixed;top:60px;left:20px;background:#fff">
 <div style="display:flex;gap:8px"><h3 id="mes">agosto 2026</h3><button id="ant">‹</button><button id="prox">›</button></div><div id="grade"></div>
 <button id="ap">APLICAR</button></div>
<script>
 const N=['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
 let m=7, y=2026, sel=[];
 function des(){ mes.textContent=N[m]+' '+y; grade.innerHTML=''; const n=new Date(y,m+1,0).getDate();
   for(let d=1;d<=n;d++){const b=document.createElement('button'); b.textContent=d; b.onclick=()=>{sel.push([y,m+1,d]); if(sel.length>2)sel=[[y,m+1,d]];}; grade.appendChild(b);} }
 ant.onclick=()=>{m--; if(m<0){m=11;y--;} des();}; prox.onclick=()=>{m++; if(m>11){m=0;y++;} des();};
 per.onclick=()=>{cal.style.display='block'; des();};
 ap.onclick=()=>{res.textContent=sel.map(x=>x.join('-')).join('|');};
</script></body></html>"""


# D: campos dentro de wrapper; E: campos não editáveis (B2 não pode dar sucesso falso); F: botão "1" de paginação fora do calendário
PAGINA_D = PAGINA_B.replace('<div contenteditable id="a">01/08/2026</div>', '<div><span contenteditable id="a">01/08/2026</span></div>') \
    .replace('<div contenteditable id="b">31/08/2026</div>', '<div><span contenteditable id="b">31/08/2026</span></div>') \
    .replace("a.innerText.trim()+'|'+b.innerText.trim()", "a.innerText.trim()+'|'+b.innerText.trim()")
PAGINA_E = PAGINA_B.replace(" contenteditable", "")
PAGINA_F = PAGINA_C.replace('<div id="res"></div>', '<div id="res"></div><button id="pag">1</button>') \
    .replace("per.onclick=", "pag.onclick=()=>{res.dataset.errado='pag'}; per.onclick=")


# G: datas soltas fora do calendário não podem ser clicadas; H: botão extra (×) na linha do mês → não adivinha a seta
PAGINA_G = PAGINA_B.replace('<button id="per">', '<span id="solta" onclick="res.dataset.errado=1">05/08/2026</span><span>10/08/2026</span><button id="per">')
PAGINA_H = PAGINA_C.replace('<button id="prox">›</button>', '<button id="prox">›</button><button id="x" onclick="res.dataset.errado=1">×</button>')


# I (card #144): react-day-picker v9 em modo intervalo (rótulo em inglês, data-day, setas sem texto), cabeçalho com o período e
# intervalo antigo já escolhido (01/08 → 31/08): o 1º clique não basta, tem de limpar e refazer
PAGINA_I = """<html><body><button id="per">01 AGO - 31 AGO</button><div id="res"></div>
<div id="cal" style="display:none;position:fixed;top:60px;left:20px;background:#fff">
 <div><span id="h1">01/08/2026</span><svg></svg><span id="h2">31/08/2026</span></div>
 <div class="rdp-root" data-mode="range"><nav><button class="rdp-button_previous" aria-label="Go to the Previous Month" id="ant"></button>
 <button class="rdp-button_next" aria-label="Go to the Next Month" id="prox"></button></nav><span id="mes"></span><div id="g" style="display:flex;flex-wrap:wrap;width:280px"></div></div>
 <button id="ap">APLICAR</button></div><button id="pag">1</button>
<script>
 const iso=(y,m,d)=>y+'-'+String(m+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');
 const br=s=>s.slice(8)+'/'+s.slice(5,7)+'/'+s.slice(0,4);
 let m=7,y=2026,from='2026-08-01',to='2026-08-31';
 function cab(){h1.textContent=from?br(from):'';h2.textContent=to?br(to):'';}
 function clique(d){ // regra do react-day-picker (addToRange)
   if(!from){from=d;to=null;} else if(from&&!to){ if(d<from){to=from;from=d;} else to=d; }
   else { if(d===to&&d===from){from=null;to=null;} else if(d===to){from=d;to=null;} else if(d===from){from=null;to=null;}
          else if(d<from)from=d; else to=d; } cab(); }
 function des(){ mes.textContent='August 2026'; g.innerHTML=''; const n=new Date(y,m+1,0).getDate();
   // dia de fora (mês anterior) com o mesmo número 1: não pode ser clicado
   g.innerHTML='<div class="rdp-outside" data-day="'+iso(y,m-1,1)+'" data-outside="true"><button>1</button></div>';
   for(let d=1;d<=n;d++){const td=document.createElement('div'); td.dataset.day=iso(y,m,d); const b=document.createElement('button'); b.textContent=d;
     b.onclick=()=>clique(td.dataset.day); td.appendChild(b); g.appendChild(td);} }
 ant.onclick=()=>{m--; if(m<0){m=11;y--;} des();}; prox.onclick=()=>{m++; if(m>11){m=0;y++;} des();};
 pag.onclick=()=>{res.dataset.errado='pag'};
 per.onclick=()=>{cal.style.display='block'; des();};
 ap.onclick=()=>{res.textContent=h1.textContent+'|'+h2.textContent;};
</script></body></html>"""


def main():
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        pg = nav.new_page()
        pg = nav.new_page(); pg.set_content(PAGINA)
        c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
        got = pg.inner_text("#res")
        assert got == "01/09/2026|30/09/2026", got
        assert 'v="01/09/2026"' in c.resumo_tela(pg), c.resumo_tela(pg)   # o resumo também enxerga os campos do painel fixo
        pg = nav.new_page(); pg.set_content(PAGINA_B)
        c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
        got = pg.inner_text("#res")
        assert got == "01/09/2026|30/09/2026", got
        pg = nav.new_page(); pg.set_content(PAGINA_C)
        c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
        got = pg.inner_text("#res")
        assert got == "2026-9-1|2026-9-30", got
        pg = nav.new_page(); pg.set_content(PAGINA_D)
        c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
        got = pg.inner_text("#res")
        assert got == "01/09/2026|30/09/2026", got
        pg = nav.new_page(); pg.set_content(PAGINA_E)
        try:
            c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
            assert False, "campo não editável não pode dar sucesso"
        except c.Falha:
            pass
        pg = nav.new_page(); pg.set_content(PAGINA_F)
        c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
        assert pg.inner_text("#res") == "2026-9-1|2026-9-30" and not pg.evaluate("res.dataset.errado"), "clicou fora do calendário"
        pg = nav.new_page(); pg.set_content(PAGINA_G)
        c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
        assert pg.inner_text("#res") == "01/09/2026|30/09/2026" and not pg.evaluate("res.dataset.errado"), "clicou data solta"
        pg = nav.new_page(); pg.set_content(PAGINA_H)
        try:
            c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
            assert False, "não devia adivinhar a seta"
        except c.Falha:
            pass
        assert not pg.evaluate("res.dataset.errado"), "clicou o botão extra"
        pg = nav.new_page(); pg.set_content(PAGINA_I)
        c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
        assert pg.inner_text("#res") == "01/09/2026|30/09/2026" and not pg.evaluate("res.dataset.errado"), pg.inner_text("#res")
        pg = nav.new_page()                       # J: rótulo do mês em inglês ("August 2026"), como o react-day-picker
        pg.set_content(PAGINA_C.replace("agosto 2026", "August 2026").replace(
            "const N=['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];",
            "const N=['January','February','March','April','May','June','July','August','September','October','November','December'];"))
        c.aplicar_periodo(pg, "2026-09-01", "2026-09-30")
        assert pg.inner_text("#res") == "2026-9-1|2026-9-30", pg.inner_text("#res")
        pg = nav.new_page(); pg.set_content(PAGINA_C)   # o diagnóstico traz o HTML do calendário (dias + APLICAR)
        pg.click("#per")
        html = c._html_do_calendario(pg)
        assert "APLICAR" in html and 'id="grade"' in html, html[:200]
        nav.close()
    print("ok: calendário em painel fixo")


if __name__ == "__main__":
    main()
