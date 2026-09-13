from pathlib import Path
import json
out=Path(__file__).resolve().parent
a=json.loads((out/'Auditoria_Codigo_R200.json').read_text())
parts=[(out/'Introducao_Auditoria.md').read_text()]
for f in a['findings']:
    refs='; '.join(f"`{e['file'].split('Hermes_Pivos_Lab_200/')[1]}` · {e['function']} · linha {e['line']}" for e in f['evidence'])
    parts.append(f"### {f['id']} — {f['title']}\n\n**{f['severity']} · {f['classification']}**\n\n{f['observation']}\n\n**Impacto:** {f['impact']}\n\n**Proposta:** {f['proposal']}\n\n**Evidência:** {refs}.\n\n")
parts.append((out/'Encerramento_Auditoria.md').read_text())
(out/'Auditoria_Codigo_R200.md').write_text(''.join(parts),encoding='utf-8')
print('Written',out/'Auditoria_Codigo_R200.md')
