#!/bin/bash
# Instalador do coletor do Nubimetrics para o nubi (Mac).
# Uso no Terminal do Mac mini:
#   curl -fsSL https://nubi-explorador.vercel.app/coletor/instalar.sh | bash
# Hora da coleta diária (padrão 7h30):
#   curl -fsSL https://nubi-explorador.vercel.app/coletor/instalar.sh | bash -s -- 8 15
set -e
ORIGEM="${NUBI_URL:-https://nubi-explorador.vercel.app}/coletor"
PASTA="$HOME/.nubi-coletor"
HORA="${1:-7}"
MINUTO="${2:-30}"

echo "== Coletor do Nubimetrics para o nubi =="
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import venv" >/dev/null 2>&1; then
  echo "Falta o Python 3. Instale em https://www.python.org/downloads/macos/ e rode este comando de novo."
  exit 1
fi
mkdir -p "$PASTA"
echo "-> baixando o coletor"
curl -fsSL "$ORIGEM/coletor.py" -o "$PASTA/coletor.py"
curl -fsSL "$ORIGEM/com.nubi.coletor.plist" -o "$PASTA/com.nubi.coletor.plist.modelo"
echo "-> preparando o Python (1-2 minutos na primeira vez)"
python3 -m venv "$PASTA/venv"
"$PASTA/venv/bin/pip" install -q --upgrade pip playwright
"$PASTA/venv/bin/python" -m playwright install chromium
cat > "$PASTA/coletor" <<EOS
#!/bin/bash
exec "$PASTA/venv/bin/python" "$PASTA/coletor.py" "\$@"
EOS
chmod +x "$PASTA/coletor"

echo "-> agendando a coleta diária às ${HORA}h$(printf %02d "$MINUTO")"
mkdir -p "$HOME/Library/LaunchAgents"
PLIST="$HOME/Library/LaunchAgents/com.nubi.coletor.plist"
sed -e "s#__PASTA__#$PASTA#g" -e "s#__HORA__#$HORA#g" -e "s#__MINUTO__#$MINUTO#g" \
  "$PASTA/com.nubi.coletor.plist.modelo" > "$PLIST"
launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"

echo
echo "-> 1/2: login do NUBI (o mesmo da página nubi-explorador), para enviar os arquivos"
"$PASTA/coletor" configurar </dev/tty || { echo "Login do nubi não configurado; rode o instalador de novo."; exit 1; }
echo
echo "-> 2/2: login do NUBIMETRICS: vai abrir uma janela do navegador; entre com seu e-mail e senha"
"$PASTA/coletor" entrar </dev/tty
echo
echo "Pronto. A coleta roda todo dia às ${HORA}h$(printf %02d "$MINUTO") (com o Mac ligado e você logado)."
echo "Para rodar agora:        $PASTA/coletor diario"
echo "Para ver a última coleta: $PASTA/coletor status"
