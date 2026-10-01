# -*- coding: utf-8 -*-
"""
🛍️ Bazar (01/10, card #137; pedido do Bruno com a planilha BAZAR_PURE_PERFUMARIA.xlsx e os prints do grupo
"PURE | OFERTAS EXCLUSIVAS").

Duas abas de produto: **caixa avariada** (novo, sem uso, voltou com a caixa danificada ou sem caixa) e **promoção**
(sem venda há 60+ dias, vindo de Análises de Vendas → Para promoção). Cadastro igual à aba "Produtos Bazar" da planilha,
vendas iguais à aba "Vendas" e o texto do grupo igual à aba "WhatsApp".

Regras:
- números SEMPRE calculados aqui (preço promo = original × (1 − desconto), economia, vendidas, estoque, status);
  a IA só escreve a frase do post e faz a arte (sem números; o preço é desenhado por cima pela tela);
- guardado em `ia_resumos`: `bazar|produtos`, `bazar|vendas`, `bazar|textos` (sem tabela nova);
- foto/vídeo/arte no Storage privado (bucket `anexos`, caminho `bazar/…`), aberto por link assinado;
- nada é apagado de verdade: produto sai da lista com `arquivado`, venda é cancelada (status).
"""
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

PRODUTOS = "bazar|produtos"
VENDAS = "bazar|vendas"
TEXTOS = "bazar|textos"
ABAS = {"avariada": "Caixa avariada", "promocao": "Promoção"}
CONDICOES = ["CAIXA COM PEQUENAS AVARIAS", "CAIXA COM AVARIAS", "AVARIA NA CAIXA E PRODUTO ABERTO", "PRODUTO ABERTO",
             "SEM CAIXA", "SEM CAIXA E SEM SPRAY", "LUZ DE LED DA CAIXA NÃO ACENDE", "SEM AVARIA (PROMOÇÃO)"]
PAGAMENTOS = ["Pix", "Dinheiro", "Cartão de crédito", "Cartão de débito", "Link de pagamento", "Outro"]
STATUS_VENDA = ["Pago", "Reservado", "Entregue", "Cancelado"]
CORES = ["❤️", "🩷", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "🤎", "🩵"]
ULTIMAS = 2                          # até 2 un. = "ÚLTIMAS UNIDADES" (como a planilha)
MAX_PRODUTOS = 600
MAX_VENDAS = 3000
BRASILIA = timezone(timedelta(hours=-3))
MENSAGEM_FIXADA = ("🌸 *BEM-VINDOS AO BAZAR PURE PROMOÇÕES!* 🌸\n\nAqui você encontra produtos originais com preços especiais "
                   "porque a caixa ou embalagem externa foi violada durante o transporte.\n\n✅ Consulte a condição informada de "
                   "cada item\n📸 Peça fotos antes de confirmar\n💳 Pagamento e retirada/entrega a combinar\n⏳ Produtos sujeitos à "
                   "disponibilidade\n\nPara comprar, envie o nome ou código do produto no grupo.")
CAMPOS_TEXTO = {"codigo": 20, "produto": 140, "marca": 80, "categoria": 60, "volume": 30, "condicao": 120,
                "localizacao": 80, "observacoes": 500, "descricao": 300, "sku": 60, "foto": 300, "video": 300, "arte": 300}


class ErroBazar(Exception):
    pass


def _ler(repo, chave, padrao):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{chave}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else padrao
    except (TypeError, ValueError):
        return padrao


def _gravar(repo, chave, valor):
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "ia": "nubi", "criado_em": datetime.now(timezone.utc).isoformat(),
                                            "texto": json.dumps(valor, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")


def _hoje():
    return datetime.now(BRASILIA).date().isoformat()


def _num(v, minimo=0.0):
    if v in (None, ""):
        return None
    try:
        v = float(str(v).replace("R$", "").replace(" ", "").replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        raise ErroBazar(f"número inválido: {v!r}")
    if v < minimo:
        raise ErroBazar(f"número não pode ser menor que {minimo:g}: {v:g}")
    return v


def _desconto(v):
    """Aceita 0,4 ou 40 (%) -> fração 0–0,95."""
    v = _num(v)
    if v is None:
        return None
    if v > 1:
        v = v / 100
    if v > 0.95:
        raise ErroBazar("desconto acima de 95%")
    return round(v, 4)


def _sem_acento(s):
    t = "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn").upper()
    return re.sub(r"\s+", " ", t).strip()


def preco_promo(original, desconto):
    if original is None or desconto is None:
        return None
    return round(original * (1 - desconto), 2)


def brl(v):
    if v is None:
        return "—"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _status(estoque):
    if estoque <= 0:
        return "ESGOTADO"
    return "ÚLTIMAS UNIDADES" if estoque <= ULTIMAS else "DISPONÍVEL"


def produtos(repo):
    xs = _ler(repo, PRODUTOS, [])
    return xs if isinstance(xs, list) else []


def vendas(repo):
    xs = _ler(repo, VENDAS, [])
    return xs if isinstance(xs, list) else []


def calcular(prods, vends):
    """Colunas automáticas da planilha: vendidas (soma das vendas não canceladas), estoque, preço promo, economia, status."""
    vendidas = {}
    for v in vends:
        if v.get("status") != "Cancelado":
            vendidas[v.get("produto_id")] = vendidas.get(v.get("produto_id"), 0) + (v.get("qtd") or 0)
    out = []
    for p in prods:
        q = dict(p)
        q["qtd_vendida"] = vendidas.get(p["id"], 0)
        q["estoque"] = (p.get("qtd_inicial") or 0) - q["qtd_vendida"]
        q["preco_promo"] = preco_promo(p.get("preco_original"), p.get("desconto"))
        q["economia"] = round(p["preco_original"] - q["preco_promo"], 2) if q["preco_promo"] is not None else None
        q["status"] = _status(q["estoque"])
        out.append(q)
    return out


def kpis(itens):
    vivos = [p for p in itens if not p.get("arquivado")]
    return {"produtos": len(vivos), "unidades": sum(max(p["estoque"], 0) for p in vivos),
            "valor_potencial": round(sum(max(p["estoque"], 0) * (p["preco_promo"] or 0) for p in vivos), 2),
            "esgotados": sum(1 for p in vivos if p["status"] == "ESGOTADO")}


def kpis_vendas(vends):
    ok = [v for v in vends if v.get("status") != "Cancelado"]
    return {"total": round(sum(v.get("total") or 0 for v in ok), 2), "vendas": len(ok), "unidades": sum(v.get("qtd") or 0 for v in ok)}


def linha_catalogo(p):
    """Mesma linha da aba WhatsApp da planilha."""
    cab = f"✨ *{p['produto']}*" + (f" | {p['marca']}" if p.get("marca") else "") + (f" | {p['volume']}" if p.get("volume") else "")
    pct = f"{round((p.get('desconto') or 0) * 100):.0f}%"
    return (f"{cab}\nCódigo: {p['codigo']}\nCondição: {p.get('condicao') or '—'}\n"
            f"De: {brl(p.get('preco_original'))} | *Por: {brl(p.get('preco_promo'))}* ({pct} OFF)\n"
            f"Disponível: {max(p['estoque'], 0)} un. | {p['status']}")


def catalogo(itens, aba=None):
    vivos = [p for p in itens if not p.get("arquivado") and p["estoque"] > 0 and (aba is None or p.get("aba") == aba)]
    corpo = "\n\n".join(linha_catalogo(p) for p in vivos)
    return ("🌸 *BAZAR PURE PROMOÇÕES* 🌸\n\nProdutos originais com preço especial por avaria na caixa/embalagem durante o "
            "transporte.\nConsulte condição e fotos de cada item.\n\n" + corpo + "\n\n📲 Para reservar, envie o código ou nome "
            "do produto no grupo.\n⏳ Estoque sujeito à disponibilidade.")


def post(p):
    """Post no MESMO formato do grupo PURE | OFERTAS EXCLUSIVAS (prints do Bruno). Números sempre do sistema."""
    if p.get("preco_original") is None or p.get("preco_promo") is None:
        raise ErroBazar("cadastre o preço original e o desconto antes de compartilhar")
    nome = p["produto"].strip() + (f" – {p['marca'].strip()}" if p.get("marca") else "")
    linhas = ["🔥 OFERTA IMPERDÍVEL NA PURE PERFUMARIA! 🔥", "", f"{p.get('cor') or '❤️'} {nome}"]
    if p.get("descricao"):
        linhas += ["", f"✨ {p['descricao'].strip()}"]
    if p.get("aba") == "avariada" and p.get("condicao"):
        linhas += ["", f"📦 Produto original e novo · {p['condicao'].strip().capitalize()}"]
    linhas += ["", f"De {brl(p['preco_original'])} por apenas {brl(p['preco_promo'])} 😱🔥", "",
               f"💰 Economize {brl(p['economia'])}!", "", "👜 Corre aproveitar essa oferta! ❤️✨"]
    return "\n".join(linhas)


def _proximo_codigo(prods):
    nums = [int(m.group(1)) for p in prods for m in [re.fullmatch(r"BZ(\d+)", str(p.get("codigo") or ""))] if m]
    return f"BZ{(max(nums) + 1 if nums else 1):03d}"


def _limpo(d):
    out = {}
    for k, n in CAMPOS_TEXTO.items():
        if k in d:
            out[k] = re.sub(r"\s+", " ", str(d.get(k) or "")).strip()[:n] if k != "observacoes" else str(d.get(k) or "").strip()[:n]
    if "aba" in d:
        if d["aba"] not in ABAS:
            raise ErroBazar("aba inválida")
        out["aba"] = d["aba"]
    if "qtd_inicial" in d:
        q = _num(d["qtd_inicial"])
        out["qtd_inicial"] = int(q or 0)
    if "preco_original" in d:
        out["preco_original"] = _num(d["preco_original"])
    if "desconto" in d:
        out["desconto"] = _desconto(d["desconto"])
    if "cor" in d:
        out["cor"] = d["cor"] if d["cor"] in CORES else "❤️"
    if "arquivado" in d:
        out["arquivado"] = bool(d["arquivado"])
    for k in ("foto", "video", "arte"):
        if out.get(k) and not re.fullmatch(r"bazar/[A-Za-z0-9_./-]{3,250}", out[k]) or ".." in (out.get(k) or ""):
            raise ErroBazar(f"arquivo inválido em {k}")
    return out


def salvar_produto(repo, d, quem=""):
    prods = produtos(repo)
    reg = _limpo(d)
    if d.get("id"):
        p = next((x for x in prods if x["id"] == int(d["id"])), None)
        if not p:
            raise ErroBazar("produto não encontrado")
        if reg.get("codigo") and any(x["codigo"] == reg["codigo"] and x["id"] != p["id"] for x in prods):
            raise ErroBazar(f"o código {reg['codigo']} já existe")
        p.update(reg)
        p["atualizado_em"] = datetime.now(timezone.utc).isoformat()
        p["atualizado_por"] = quem[:60]
    else:
        if not reg.get("produto"):
            raise ErroBazar("informe o nome do produto")
        if len(prods) >= MAX_PRODUTOS:
            raise ErroBazar(f"limite de {MAX_PRODUTOS} produtos no Bazar")
        if reg.get("codigo") and any(x["codigo"] == reg["codigo"] for x in prods):
            raise ErroBazar(f"o código {reg['codigo']} já existe")
        p = {"aba": "avariada", "marca": "", "categoria": "PERFUME", "volume": "", "condicao": "", "qtd_inicial": 1,
             "preco_original": None, "desconto": 0.4, "localizacao": "", "observacoes": "", "descricao": "", "cor": "❤️",
             "foto": "", "video": "", "arte": "", "sku": "", **reg}
        p["id"] = max([x["id"] for x in prods] + [0]) + 1
        p["codigo"] = p.get("codigo") or _proximo_codigo(prods)
        p["data_cadastro"] = _hoje()
        p["criado_por"] = quem[:60]
        prods.append(p)
    _gravar(repo, PRODUTOS, prods)
    return calcular([p], vendas(repo))[0]


def salvar_venda(repo, d, quem=""):
    prods = {p["id"]: p for p in produtos(repo)}
    vends = vendas(repo)
    if d.get("id"):                                   # só muda status/cliente/pagamento/observações
        v = next((x for x in vends if x["id"] == int(d["id"])), None)
        if not v:
            raise ErroBazar("venda não encontrada")
        for k in ("cliente", "observacoes"):
            if k in d:
                v[k] = str(d[k] or "").strip()[:200]
        if d.get("pagamento") in PAGAMENTOS:
            v["pagamento"] = d["pagamento"]
        if d.get("status") in STATUS_VENDA:
            v["status"] = d["status"]
        _gravar(repo, VENDAS, vends)
        return v
    pid = int(d.get("produto_id") or 0)
    p = prods.get(pid)
    if not p:
        raise ErroBazar("escolha o produto da venda")
    qtd = int(_num(d.get("qtd")) or 0)
    if qtd <= 0:
        raise ErroBazar("quantidade tem que ser 1 ou mais")
    item = calcular([p], vends)[0]
    if qtd > item["estoque"]:
        raise ErroBazar(f"só tem {max(item['estoque'], 0)} un. de {p['produto']} no Bazar")
    unit = item["preco_promo"] if d.get("preco_unit") in (None, "") else _num(d["preco_unit"])
    if unit is None:
        raise ErroBazar("o produto não tem preço promo; cadastre o preço original e o desconto")
    if len(vends) >= MAX_VENDAS:
        raise ErroBazar("limite de vendas guardadas atingido")
    v = {"id": max([x["id"] for x in vends] + [0]) + 1, "data": str(d.get("data") or _hoje())[:10], "produto_id": pid,
         "codigo": p["codigo"], "produto": p["produto"], "qtd": qtd, "preco_unit": round(unit, 2), "total": round(unit * qtd, 2),
         "cliente": str(d.get("cliente") or "").strip()[:120],
         "pagamento": d.get("pagamento") if d.get("pagamento") in PAGAMENTOS else "",
         "status": d.get("status") if d.get("status") in STATUS_VENDA else "Pago",
         "observacoes": str(d.get("observacoes") or "").strip()[:200], "registrado_por": quem[:60],
         "registrado_em": datetime.now(timezone.utc).isoformat()}
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v["data"]):
        raise ErroBazar("data inválida")
    vends.append(v)
    _gravar(repo, VENDAS, vends)
    return v


def painel(repo):
    prods, vends = produtos(repo), vendas(repo)
    itens = calcular(prods, vends)
    textos = _ler(repo, TEXTOS, {}) or {}
    por_aba = {a: kpis([p for p in itens if p.get("aba") == a]) for a in ABAS}
    return {"produtos": itens, "vendas": sorted(vends, key=lambda v: (v.get("data") or "", v["id"]), reverse=True),
            "kpis": kpis(itens), "por_aba": por_aba, "kpis_vendas": kpis_vendas(vends),
            "mensagem_fixada": textos.get("mensagem_fixada") or MENSAGEM_FIXADA,
            "catalogo": catalogo(itens), "abas": ABAS, "condicoes": CONDICOES, "pagamentos": PAGAMENTOS,
            "status_venda": STATUS_VENDA, "cores": CORES}


def salvar_mensagem(repo, texto):
    t = str(texto or "").strip()[:3000]
    if not t:
        raise ErroBazar("mensagem vazia")
    textos = _ler(repo, TEXTOS, {}) or {}
    textos["mensagem_fixada"] = t
    _gravar(repo, TEXTOS, textos)
    return t


def levar_ao_bazar(repo, itens, quem=""):
    """Análises de Vendas → Para promoção: cada SKU vira produto da aba Promoção (não duplica o mesmo SKU ainda à venda)."""
    prods = produtos(repo)
    ja = {p.get("sku") for p in calcular(prods, vendas(repo)) if p.get("sku") and not p.get("arquivado") and p["estoque"] > 0}
    criados = []
    for it in itens[:100]:
        sku = str(it.get("sku") or "").strip()
        if not sku or sku in ja:
            continue
        criados.append(salvar_produto(repo, {"aba": "promocao", "sku": sku, "produto": it.get("titulo") or sku,
                                             "marca": it.get("marca") or "", "categoria": it.get("categoria") or "PERFUME",
                                             "condicao": "SEM AVARIA (PROMOÇÃO)", "qtd_inicial": it.get("disponivel") or 1,
                                             "preco_original": it.get("preco"), "desconto": it.get("desconto") or 0.2,
                                             "observacoes": f"sem venda há {it.get('sem_venda_dias')}+ dias"
                                             if it.get("sem_venda_dias") else ""}, quem))
        ja.add(sku)
    return criados


def importar_planilha(repo, conteudo, quem=""):
    """Traz os produtos da planilha BAZAR_PURE_PERFUMARIA.xlsx (aba "Produtos Bazar") para o sistema, 1 vez. Não duplica
    produto com o mesmo nome e marca. As vendas da planilha (aba "Vendas") entram também, se houver."""
    import io
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=False)
    if "Produtos Bazar" not in wb.sheetnames:
        raise ErroBazar('a planilha não tem a aba "Produtos Bazar"')
    ws = wb["Produtos Bazar"]
    cab_linha, cols = None, {}
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), 1):
        nomes = [_sem_acento(c).strip() if isinstance(c, str) else "" for c in row]
        if "PRODUTO" in nomes and any(n.startswith("PRECO ORIGINAL") for n in nomes):
            cab_linha, cols = i, {n: j for j, n in enumerate(nomes) if n}
            break
    if not cab_linha:
        raise ErroBazar("não achei o cabeçalho (Produto, Preço Original…) na aba Produtos Bazar")

    def col(nome, row):
        j = next((j for n, j in cols.items() if n.startswith(nome)), None)
        v = row[j] if j is not None and j < len(row) else None
        return None if v is None or (isinstance(v, str) and v.startswith("=")) or not isinstance(v, (str, int, float, datetime)) else v

    existentes = {(_sem_acento(p["produto"]).strip(), _sem_acento(p.get("marca")).strip()) for p in produtos(repo)}
    novos = 0
    for row in ws.iter_rows(min_row=cab_linha + 1, values_only=True):
        nome = col("PRODUTO", row)
        if not nome or not str(nome).strip():
            continue
        marca = str(col("MARCA", row) or "").strip()
        chave = (_sem_acento(nome).strip(), _sem_acento(marca).strip())
        if chave in existentes:
            continue
        dc = col("DATA CADASTRO", row)
        salvar_produto(repo, {"aba": "avariada", "codigo": str(col("CODIGO", row) or "").strip(), "produto": str(nome).strip(),
                              "marca": marca, "categoria": str(col("CATEGORIA", row) or "").strip(),
                              "volume": str(col("VOLUME", row) or "").strip(),
                              "condicao": str(col("CONDICAO", row) or "").strip(), "qtd_inicial": col("QTD. INICIAL", row) or 0,
                              "preco_original": col("PRECO ORIGINAL", row), "desconto": col("DESCONTO", row),
                              "localizacao": str(col("LOCALIZACAO", row) or "").strip(),
                              "observacoes": str(col("OBSERVACOES", row) or "").strip()}, quem)
        if isinstance(dc, datetime):                  # data de cadastro da planilha vale
            prods = produtos(repo)
            prods[-1]["data_cadastro"] = dc.date().isoformat()
            _gravar(repo, PRODUTOS, prods)
        existentes.add(chave)
        novos += 1
    return novos


def pedido_frase(p):
    return (f"Escreva UMA frase curta (até 90 caracteres) para um post de oferta no WhatsApp de uma perfumaria, sobre o "
            f"produto \"{p['produto']}\" da marca \"{p.get('marca') or ''}\" ({p.get('categoria') or 'perfume'}). Tom: elegante e "
            "animado, como \"Uma fragrância feminina marcante, elegante e sofisticada!\". Não cite preço, desconto, números nem "
            "estoque. Escolha também 1 emoji de coração na cor que combina com o frasco/perfume, um destes: "
            + " ".join(CORES) + ". Responda só neste formato, numa linha: EMOJI | frase")


def ler_frase(texto):
    """'💜 | Uma fragrância…' -> (cor, frase). Cor fora da lista vira ❤️; frase sem números."""
    t = str(texto or "").strip().splitlines()[0] if str(texto or "").strip() else ""
    cor, _, frase = t.partition("|") if "|" in t else ("", "", t)
    cor = cor.strip() if cor.strip() in CORES else "❤️"
    frase = re.sub(r"\s+", " ", frase.strip().strip('"').strip())
    if re.search(r"\d", frase):                      # número na frase da IA não entra (preço é do sistema)
        frase = re.sub(r"\s*\S*\d\S*", "", frase).strip()
    return cor, frase[:160]


def pedido_arte(p):
    return ("Edite esta foto de produto para virar a arte de um post de oferta da PURE PERFUMARIA (WhatsApp/Instagram), formato "
            "quadrado. Mantenha o frasco, a caixa e o rótulo EXATAMENTE como estão (mesmas letras, cores e formato; não invente "
            "nem troque nada escrito no produto). Melhore a luz, deixe o fundo elegante e limpo (tons suaves que combinem com o "
            f"perfume \"{p['produto']}\" de \"{p.get('marca') or ''}\"), com um leve brilho de luxo. NÃO escreva nenhum texto, "
            "preço, número ou logo na imagem: o preço é colocado depois. Deixe espaço livre na parte de baixo da imagem.")
