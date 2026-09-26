"""Fotos e vídeos na conversa direta (26/09): quadros vão como imagens, o áudio vira transcrição, só quem enxerga recebe."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("OPENAI_API_KEY", "x")
import nubi_web as w  # noqa: E402
import agentes  # noqa: E402


def test_preparar_video_e_foto():
    baixados = []
    w._baixar_anexo = lambda repo, c, limite=0: baixados.append(c) or b"\xff\xd8jpeg"
    w.ia.transcrever = lambda audio, nome="a": "Quero os cards maiores e a coluna Em teste mais visível."
    extra, imgs, meta = w.preparar_anexos(None, [
        {"tipo": "video", "nome": "tela.mov", "caminho": "sala/astra/1.mov", "duracao": 90.3,
         "quadros": [f"sala/astra/1-q{i:02d}.jpg" for i in range(15)], "audio": "sala/astra/1-audio.wav"},
        {"tipo": "imagem", "nome": "print.png", "caminho": "sala/astra/2.png", "previa": "sala/astra/2-previa.jpg"}])
    assert len(imgs) == 12 and imgs[0].startswith("data:image/jpeg;base64,")        # teto de 12 imagens no total
    assert "1:30" in extra and "TRANSCRIÇÃO DO ÁUDIO" in extra and "cards maiores" in extra and "print.png" in extra
    assert meta[0]["transcricao"].startswith("Quero") and meta[0]["caminho"] == "sala/astra/1.mov"
    assert "sala/astra/1.mov" not in baixados                                          # o vídeo inteiro não vai para a IA


def test_caminho_de_anexo_validado():
    import importlib
    importlib.reload(w)
    for ruim in ("../segredo", "outro/bucket.png", "sala/../../x"):
        try:
            w._baixar_anexo(type("R", (), {"token": "t"})(), ruim)
            assert False, ruim
        except w.ErroNuvem:
            pass


def test_quem_enxerga_imagens():
    assert agentes.ve_imagens("astra") and agentes.ve_imagens("chatgpt") and agentes.ve_imagens("claude")
    assert not agentes.ve_imagens("deepseek") and not agentes.ve_imagens("gptoss")


def test_imagens_vao_para_a_api():
    enviados = []
    w.ia._post_json = lambda url, corpo, cab, timeout=90: (enviados.append(corpo) or {
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "Vi os cards."}]}]})
    t, _, _ = w.ia.perguntar("olhe", web=False, qual="chatgpt", modelo="gpt-6-astra", imagens=["data:image/jpeg;base64,QUJD"])
    c = enviados[0]["input"][0]["content"]
    assert t == "Vi os cards." and c[0]["type"] == "input_text" and c[1] == {"type": "input_image", "image_url": "data:image/jpeg;base64,QUJD"}
    enviados.clear()
    w.ia._post_json = lambda url, corpo, cab, timeout=90: (enviados.append(corpo) or {
        "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"})
    w.ia.perguntar("olhe", web=False, qual="claude", imagens=["data:image/png;base64,QUJD"])
    b = enviados[0]["messages"][0]["content"]
    assert b[0]["source"] == {"type": "base64", "media_type": "image/png", "data": "QUJD"} and b[1]["type"] == "text"


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
