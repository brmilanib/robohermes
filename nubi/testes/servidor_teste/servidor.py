"""
Servidor de TESTE do nubi (sem Supabase e sem IA de verdade): http://127.0.0.1:8765 (PORTA=...)
  IA_FALSA=1 OLLAMA_API_KEY=x ANTHROPIC_API_KEY=x PORTA=8765 python3 servidor.py
Login falso: o Playwright troca o supabase-js por um stub (ver LEIA-ME.md desta pasta).
"""
import sys, os, json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.dirname(__file__))
import fake_rest, nubi, nubi_web
def fake(url, cab=None):
    if "openbeautyfacts" in url and "3386460028462" in url:
        return {"status": 1, "product": {"brands": "Montblanc", "product_name": "Starwalker", "generic_name": "Eau de Toilette", "quantity": "75 ml"}}
    if "openbeautyfacts" in url and "3386460101035" in url:
        return {"status": 1, "product": {"brands": "Montblanc", "product_name": "Explorer", "generic_name": "Eau de Parfum", "quantity": "100 ml"}}
    if "openbeautyfacts" in url: return {"status": 0}
    return {"items": []}
nubi._get_json = fake; nubi.time.sleep = lambda s: None
PUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "public")
if os.environ.get("IA_FALSA"):
    import ia
    def _ia(url, corpo, cab, timeout=90):
        if "embeddings" in url:
            import hashlib, re as _re, unicodedata as _u
            def vec(t):
                t = "".join(c for c in _u.normalize("NFKD", t.lower()) if not _u.combining(c))
                v = [0.0] * 64
                for w in _re.findall(r"[a-z0-9]{3,}", t):
                    v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
                return v
            return {"data": [{"index": i, "embedding": vec(t)} for i, t in enumerate(corpo["input"])]}
        txt = json.dumps(corpo, ensure_ascii=False)
        open(os.path.join(os.environ.get("TMPDIR", "/tmp"), "nubi_ultimo_prompt.txt"), "w").write(corpo.get("input", ""))
        if "ollama.com" in url:
            return {"model": corpo["model"], "message": {"content": "gpt-oss: OK, modelo " + corpo["model"]}, "prompt_eval_count": 50, "eval_count": 12}
        if "deepseek.com" in url:
            return {"model": corpo["model"], "usage": {"prompt_tokens": 1200, "completion_tokens": 300},
                    "choices": [{"message": {"content": "DeepSeek aqui: sugiro cache nas consultas do dia e índice em vend_vendas_dia(data)."}}]}
        if "anthropic" in url:
            if "agente responsável por esta tarefa" in txt:
                return {"model": corpo["model"], "usage": {"input_tokens": 900, "output_tokens": 80}, "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": json.dumps({"resposta": "Não precisa rodar nada: o despachante já está ativo. Vou conferir o status das coletas no Mac.", "comando": "status"}, ensure_ascii=False)}]}
            if "coordenador dos agentes" in txt:
                return {"content": [{"type": "text", "text": json.dumps({"resposta": "Decidido: vamos priorizar a correção da SIENO e o índice sugerido pelo DeepSeek.", "tarefas": [{"titulo": "Índice em vend_vendas_dia(data)", "descricao": "Criar índice e medir a tela Vendas diárias.", "tipo": "tarefa", "status": "aprovada", "prioridade": "media", "area": "dados", "proposto_por": "DeepSeek"}], "atualizar": []}, ensure_ascii=False)}]}
            return {"model": corpo["model"], "usage": {"input_tokens": 2000, "output_tokens": 400}, "stop_reason": "end_turn", "content": [{"type": "text", "text": "## Revisão do Claude\n- Concordo com o item 1.\n```python\nx = 1\n```"}]}
        if "engenheiro de dados" in txt:
            r = "ChatGPT: a SIENO está sem 4 dias; primeiro garantir a coleta dela antes de qualquer análise."
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": r, "annotations": []}]}]}
        if "auditor de dados" in txt:
            r = "## Achados\n- SIENO: dia faltando = falha de coleta.\n```python\ndef f():\n    return 1\n```\n## Ações\n1. Reenviar."
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": r, "annotations": []}]}]}
        if corpo.get("text", {}).get("format", {}).get("type") == "json_schema":
            tipos = corpo["text"]["format"]["schema"]["properties"]["secoes"]["items"]["properties"]["tipo"]["enum"]
            j = {"secoes": [{"tipo": t, "itens": [
                {"texto": f"Item de {t}: SIENO P13 vendeu **R$ 2,3 mi** (+55%).", "vendedor": "SIENO P13", "produto": "", "marca": ""},
                {"texto": "Good Girl puxou as vendas com R$ 190 mil.", "vendedor": "", "produto": "Perfume Carolina Herrera Good Girl Eau D", "marca": "CAROLINA HERRERA"},
                {"texto": "Lattafa subindo 20% no mês.", "vendedor": "", "produto": "", "marca": "LATTAFA"}]} for t in tipos]}
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(j, ensure_ascii=False), "annotations": []}]}]}
        if "ANÁLISE DA SEMANA" in txt:
            r = "## 🗓️ A semana em números\n- Os vendedores venderam **R$ 2,1 mi** na semana, +8%.\n## 🏆 Vendedores que cresceram\n- SIENO P13: +20%.\n## 📉 Vendedores que caíram\n- AUMA: -5%.\n## 💡 Oportunidades para esta semana\n- Good Girl sem estoque.\n## ✅ Plano da semana\n- Repor Lattafa."
        elif "RESUMO DO DIA" in txt:
            r = "## 📊 O dia em resumo\n- Os vendedores venderam **R$ 320 mil** no dia, *SIENO P13:* acelerou.\n## 🔥 Produtos que puxaram o dia\n- Yara Lattafa: 40 un.\n## 📉 Quedas e sinais de atenção\n- AUMA caiu 30%.\n## 📦 Estoque dos concorrentes\n- Good Girl pausado na AUMA.\n## 💡 Oportunidades\n- Anunciar Good Girl.\n## ⚠️ Alertas\n- Queda forte na AUMA.\n## ✅ O que fazer hoje\n- Confira estoque de Good Girl."
        elif "análise MENSAL" in txt or "escreva o resumo" in txt:
            r = "## Mercado\n- Vendas de **R$ 193,6 mi** em agosto, +8% no mês.\n## Categorias\n- Nacional lidera com 29,1%.\n## O que fazer agora\n- Reforçar estoque de Lattafa."
        elif "MESMA marca" in txt:
            r = '{"mesma": true, "confianca": "alta", "motivo": "JPG é a sigla de Jean Paul Gaultier."}'
        else:
            r = '{"encontrado": false}'
        return {"output": [{"type": "message", "content": [{"type": "output_text", "text": r, "annotations": []}]}]}
    ia._http_json = _ia
    LOTE = {}
    def _openai(metodo, caminho, corpo=None, cab=None, timeout=120, bruto=False):
        if caminho == "files" and metodo == "POST":
            LOTE["jsonl"] = corpo.split(b"application/jsonl\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0].decode(); return {"id": "file1"}
        if caminho == "batches": return {"id": "batch1"}
        if caminho.startswith("batches/"): return {"status": "completed", "output_file_id": "out1", "request_counts": {"completed": 3}}
        linhas = []
        for l in LOTE["jsonl"].splitlines():
            j = json.loads(l); m = j["body"]["input"]
            cat = "Árabe" if "LATTAFA" in m.upper() or "ARMAF" in m.upper() else "Designer"
            txt = json.dumps({"categoria": cat, "confianca": "alta", "motivo": "teste"}, ensure_ascii=False)
            linhas.append(json.dumps({"custom_id": j["custom_id"], "response": {"body": {"output": [{"type": "message", "content": [{"type": "output_text", "text": txt}]}]}}}, ensure_ascii=False))
        return "\n".join(linhas).encode()
    ia._openai = _openai
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def go(self, m):
        u = urlparse(self.path)
        if u.path == "/api/app":
            q = {k: v[0] for k, v in parse_qs(u.query).items()}; rota = q.pop("r", "")
            n = int(self.headers.get("Content-Length") or 0); corpo = self.rfile.read(n) if n else b""
            tok = self.headers.get("Authorization", "")[7:]
            st, tipo, dados, extra = nubi_web.atender(m, rota, q, corpo, tok)
        else:
            st, tipo, extra = 200, "text/html; charset=utf-8", {}
            dados = open(PUB + "/index.html", "rb").read()
        self.send_response(st); self.send_header("Content-Type", tipo)
        for k, v in extra.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(dados)
    def do_GET(self): self.go("GET")
    def do_POST(self): self.go("POST")
ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORTA", "8765"))), H).serve_forever()
