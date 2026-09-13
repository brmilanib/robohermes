"""Produce the R200 review dossier from the received exports, without new trading tests."""
from pathlib import Path
import csv, json, hashlib, math, re, textwrap, shutil
from datetime import datetime
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.ticker import FuncFormatter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, Preformatted, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
CHARTS=OUT/'graficos';CHARTS.mkdir(parents=True,exist_ok=True)
EA=ROOT/'Hermes_Pivos_Lab_200'
SRC=EA/'Hermes_Pivos_Lab_200.mq5'
CODE=SRC.read_text();SOURCE_SHA=hashlib.sha256(SRC.read_bytes()).hexdigest()
EXPECTED_SHA='69a4e02bfaaea2619aad1dea364e8e5c0d03c768ef46f5eeddd2ca7f1235ec9f'
assert SOURCE_SHA==EXPECTED_SHA
INPUTS=['comparacao(7).csv','meses_comparacao(5).csv','arquivos_comparacao(3).csv','breakeven_comparacao(4).csv']
def load(name):
    with (ROOT/'upload'/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f,delimiter=';'))
raw=load(INPUTS[0]);monthly_raw=load(INPUTS[1]);folders=load(INPUTS[2]);shadows=load(INPUTS[3])
def num(v):
    try:return float(v)
    except (TypeError,ValueError):return v
cases={int(r['case']):{k:num(v) for k,v in r.items()} for r in raw}
months={i:sorted([{k:num(v) for k,v in r.items()} for r in monthly_raw if int(r['case'])==i],key=lambda x:x['month_server']) for i in cases}
assert sorted(cases)==[1,2,3] and all(len(v)==57 for v in months.values())
SHORT={1:'Referência',2:'Continuidade',3:'Início'}
COL={1:'#176b85',2:'#d18a22',3:'#8054a3'}
BENCH=json.loads((ROOT/'outputs/rodada190_resultados/Analise_R190.json').read_text())['benchmarks']['2']
byyear={r['year']:r for r in BENCH['years']}
def fmt(n,dec=2):return f'{float(n):,.{dec}f}'.replace(',','X').replace('.',',').replace('X','.')
def pct(n):return fmt(n)+'%'
def negative(i):return sum(r['equity_change']<-.005 for r in months[i] if r['month_server']<'2026-09')
def positive(i):return sum(r['equity_change']>.005 for r in months[i] if r['month_server']<'2026-09')
def zero(i):return 56-positive(i)-negative(i)
for i,c in cases.items():
    assert abs(sum(m['equity_change'] for m in months[i])-c['profit'])<.011
    assert abs(c['deposit']+c['profit']-c['final_balance'])<.011
annual=[]
for year in range(2022,2027):
    b=byyear[year]
    for i in cases:
        rows=[r for r in months[i] if str(r['month_server']).startswith(str(year))]
        start=rows[0]['equity_start'];end=rows[-1]['equity_end'];change=end-start
        annual.append({'year':year,'case':i,'start_equity':start,'end_equity':end,'profit':change,'return_usd':(end/start-1)*100,'return_brl':(end*b['fx_end']/(start*b['fx_start'])-1)*100,'selic':b['selic_return_brl_pct'],'negative_complete':sum(r['equity_change']<-.005 for r in rows if r['month_server']<'2026-09')})
independent=json.loads((ROOT/'outputs/rodada200_resultados/analise/Analise_R200.json').read_text())
assert independent['checks_passed']==len(independent['checks']) or independent['audit_status']=='PASS'
gold={(r['case'],r['year']):r for r in independent['annual_rows']}
for r in annual:
    g=gold[(r['case'],r['year'])]
    for ours,theirs in [('profit','profit_equity_usd'),('return_usd','usd_return_percent'),('return_brl','brl_return_percent'),('selic','selic_return_brl_percent')]:
        assert math.isclose(r[ours],g[theirs],abs_tol=.000001), (r['case'],r['year'],ours)
transitions={}
for i in [2,3]:
    pairs=list(zip(months[1][:-1],months[i][:-1]))
    transitions[i]={
      'negative_to_positive':[a['month_server'] for a,b in pairs if a['equity_change']<-.005 and b['equity_change']>.005],
      'negative_to_zero':[a['month_server'] for a,b in pairs if a['equity_change']<-.005 and abs(b['equity_change'])<=.005],
      'positive_to_negative':[a['month_server'] for a,b in pairs if a['equity_change']>.005 and b['equity_change']<-.005],
      'zero_to_negative':[a['month_server'] for a,b in pairs if abs(a['equity_change'])<=.005 and b['equity_change']<-.005],
    }

# Figures show only measurements actually exported. No synthetic intraday equity.
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#243448','text.color':'#243448','axes.edgecolor':'#aab6c2','savefig.facecolor':'white'})
fig,ax=plt.subplots(figsize=(10,4.7))
labels=[r['month_server'] for r in months[1]];x=np.arange(58)
for i in cases:ax.plot(x,[cases[i]['deposit']]+[r['equity_end'] for r in months[i]],color=COL[i],label=f'{i} · {SHORT[i]}',lw=2)
ax.set_xticks([0,12,24,36,48,57],['Início','Dez/22','Dez/23','Dez/24','Dez/25','Set/26*']);ax.set_ylabel('Patrimônio em USD');ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v/1000:.0f} mil'))
ax.grid(axis='y',alpha=.18);ax.legend(frameon=False,loc='upper left');fig.tight_layout();fig.savefig(CHARTS/'patrimonio_mensal.png',dpi=190);plt.close(fig)
fig,axes=plt.subplots(3,1,figsize=(10,7.2),layout='constrained')
for i,ax in zip(cases,axes):
    matrix=np.full((5,12),np.nan)
    for r in months[i]:
        year,mon=map(int,r['month_server'].split('-'));matrix[year-2022,mon-1]=100*r['equity_change']/r['equity_start']
    cmap=plt.colormaps['RdYlGn'].copy();cmap.set_bad('#eeeeee')
    ax.imshow(matrix,cmap=cmap,norm=TwoSlopeNorm(vmin=-35,vcenter=0,vmax=35),aspect='auto')
    for yy in range(5):
        for mm in range(12):
            val=matrix[yy,mm]
            if not np.isnan(val):ax.text(mm,yy,fmt(val,1),ha='center',va='center',fontsize=8,color='#172332')
    ax.set_xticks(range(12),['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set*','Out','Nov','Dez']);ax.set_yticks(range(5),range(2022,2027));ax.set_title(f'{i} · {SHORT[i]} | retorno mensal (%)',loc='left',fontsize=11,fontweight='bold')
fig.savefig(CHARTS/'retornos_mensais.png',dpi=190);plt.close(fig)
fig,axes=plt.subplots(2,1,figsize=(10,5.4),sharex=True,layout='constrained')
for i,ax in zip([2,3],axes):
    deltas=np.array([b['equity_change']-a['equity_change'] for a,b in zip(months[1],months[i])])
    ax.bar(np.arange(57),deltas,color=np.where(deltas>=0,'#2c8c78','#bf585b'),width=.8)
    ax.axhline(0,color='#435669',lw=.7);ax.set_title(f'{i} · {SHORT[i]} menos Referência',loc='left',fontsize=11,fontweight='bold');ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v/1000:.0f} mil'));ax.grid(axis='y',alpha=.15)
axes[-1].set_xticks([0,12,24,36,48,56],['Jan/22','Jan/23','Jan/24','Jan/25','Jan/26','Set/26*']);fig.supylabel('Diferença de resultado mensal (USD)');fig.savefig(CHARTS/'diferenca_mensal.png',dpi=190);plt.close(fig)

fontdir=Path('/usr/share/fonts/truetype/dejavu')
for name,file in [('Body','DejaVuSans.ttf'),('Bold','DejaVuSans-Bold.ttf'),('Mono','DejaVuSansMono.ttf')]:pdfmetrics.registerFont(TTFont(name,str(fontdir/file)))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Body',boldItalic='Bold')
navy=colors.HexColor('#17344c');teal=colors.HexColor('#176b85');gray=colors.HexColor('#536678')
styles={
 'body':ParagraphStyle('body',fontName='Body',fontSize=9.5,leading=14,textColor=navy,spaceAfter=8),
 'small':ParagraphStyle('small',fontName='Body',fontSize=8,leading=11,textColor=gray,spaceAfter=6),
 'audit':ParagraphStyle('audit',fontName='Body',fontSize=9.3,leading=13.2,textColor=navy,spaceAfter=6),
 'h1':ParagraphStyle('h1',fontName='Bold',fontSize=21,leading=25,textColor=navy,spaceAfter=15),
 'h2':ParagraphStyle('h2',fontName='Bold',fontSize=13,leading=17,textColor=teal,spaceBefore=10,spaceAfter=8,keepWithNext=True),
 'h3':ParagraphStyle('h3',fontName='Bold',fontSize=10.5,leading=14,textColor=navy,spaceBefore=8,spaceAfter=6,keepWithNext=True),
 'cell':ParagraphStyle('cell',fontName='Body',fontSize=8,leading=11,textColor=navy),
 'th':ParagraphStyle('th',fontName='Bold',fontSize=8,leading=10,textColor=colors.white),
 'code':ParagraphStyle('code',fontName='Mono',fontSize=7.7,leading=9.5,textColor=navy,spaceAfter=0),
}
story=[];md=[];WIDTH=A4[0]-88
def norm(s):return str(s).replace('—','-').replace('–','-').replace('\u2011','-')
def inline(s):
    s=escape(norm(s));s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s);s=re.sub(r'`([^`]+)`',r'<font name="Mono">\1</font>',s)
    s=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'<link href="\2" color="#176b85">\1</link>',s)
    return s
def p(s,style='body'):
    story.append(Paragraph(inline(s),styles[style]));md.extend([norm(s),''])
def h(s,level=1):
    story.append(Paragraph(escape(norm(s)),styles['h'+str(level)]));md.extend(['#'*level+' '+norm(s),''])
def page(title):
    if story:story.append(PageBreak())
    h(title)
def table(headers,rows,widths=None,numeric=False):
    data=[[Paragraph(inline(v),styles['th']) for v in headers]]
    data.extend([[Paragraph(inline(v),styles['cell']) for v in row] for row in rows])
    t=Table(data,colWidths=widths or [WIDTH/len(headers)]*len(headers),repeatRows=1,hAlign='LEFT')
    cmds=[('BACKGROUND',(0,0),(-1,0),navy),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,0),.6,teal)]
    for ri in range(1,len(data)):
        if ri%2==0:cmds.append(('BACKGROUND',(0,ri),(-1,ri),colors.HexColor('#f0f4f7')))
    t.setStyle(TableStyle(cmds));story.extend([t,Spacer(1,9)])
    md.append('| '+' | '.join(map(str,headers))+' |');md.append('| '+' | '.join(['---']*len(headers))+' |')
    md.extend('| '+' | '.join(map(str,row))+' |' for row in rows);md.append('')
def pic(name,height,caption):
    story.append(Image(str(CHARTS/name),width=WIDTH,height=height));md.extend([f'![{caption}](graficos/{name})','']);p(caption,'small')
def markdown_fragment(text):
    # Plain audit paragraphs and lists; fenced code stays verbatim in the MD companion.
    buffer=[];fence=False;tab=[]
    def flush():
        if buffer:p(' '.join(buffer),'audit');buffer.clear()
    def flush_table():
        if tab:
            cells=[[v.strip() for v in line.strip().strip('|').split('|')] for line in tab]
            body=[r for r in cells[1:] if not all(re.match(r'^:?-+:?$',v.replace(' ','')) for v in r)]
            table(cells[0],body);tab.clear()
    for line in text.splitlines():
        if not line.startswith('|'):flush_table()
        if line.startswith('```'):flush();fence=not fence;continue
        if fence:
            if line:p(line,'small')
        elif re.match(r'^#{1,6} ',line):flush();h(re.sub(r'^#+ ','',line),2 if line.startswith('## ') or line.startswith('# ') else 3)
        elif not line.strip():flush()
        elif line.startswith('|'):flush();tab.append(line)
        elif line.startswith(('- ','* ')):flush();p('• '+line[2:],'audit')
        elif re.match(r'^\d+\.\s',line):flush();p(line,'audit')
        else:buffer.append(line)
    flush();flush_table()

page('HERMES\nDossiê técnico para revisão')
p('Rodada R200 · versão 2.00 · XAUUSD M30 · 13/09/2026','small')
p('**Conclusão: a Referência permanece como base de pesquisa.** Os dois complementos de pivô aumentaram a atividade, reduziram o lucro líquido e tiveram mais meses completos negativos. O caso Início reduziu o drawdown relativo, mas registrou uma queda máxima em dólares maior. Nenhum dos três atingiu a meta de todos os meses positivos.')
table(['Caso','Lucro líquido USD','Trades','Fator de lucro','DD relativo','Meses negativos¹'],[[f'{i} {SHORT[i]}',fmt(c['profit']),fmt(c['mt5_trades'],0),fmt(c['mt5_profit_factor']),pct(c['equity_dd_relative_percent']),str(negative(i))] for i,c in cases.items()],[95,110,46,65,78,WIDTH-394])
p('¹ Janeiro/2022 a agosto/2026: 56 meses completos. Setembro/2026 é parcial e está incluído nos lucros totais. Contando esse mês parcial, o caso Início tem 19 meses negativos, contra 18 na janela completa.','small')
p('Capital inicial reportado: **US$ 10.000** por caso. Lote fixo **1,00**, alvo nominal **5R**, uma posição por vez. Custos de swap estão incluídos; comissões e taxas foram reportadas como zero. Os testes foram executados pelo usuário e os CSVs foram auditados aqui.')
h('O que este documento entrega',2)
p('Comparativo auditado; tabelas de todos os meses; resultados anuais em dólar e comparação em reais com Selic; gráficos; regras dos três perfis; auditoria técnica do código; limitações dos dados; roteiro de revisão para o Claude. O anexo final reproduz o fonte completo da versão entregue.')
p('O código e os resultados estão associados à mesma rodada, mas os CSVs não incluem o hash do executável EX5. O hash do fonte e a reprodução da referência dão rastreabilidade, sem provar identidade binária. Trata-se de auditoria técnica interna, sem certificação externa.','small')

page('01 · O efeito das entradas novas')
table(['Métrica','1 Referência','2 Continuidade','3 Início'],[
 ['Lucro USD']+[fmt(cases[i]['profit']) for i in cases],
 ['Diferença vs. referência']+['0,00']+[fmt(cases[i]['profit']-cases[1]['profit']) for i in [2,3]],
 ['Variação do lucro']+['0,00%']+[pct(100*(cases[i]['profit']/cases[1]['profit']-1)) for i in [2,3]],
 ['Acerto']+[pct(cases[i]['cycle_win_percent']) for i in cases],
 ['Entradas por PIVOT']+[fmt(cases[i]['hp_pivot_fills'],0) for i in cases],
 ['Entradas por BASE (diferença)']+[fmt(cases[i]['cycles_opened']-cases[i]['hp_pivot_fills'],0) for i in cases],
 ['Swap USD']+[fmt(cases[i]['swap']) for i in cases],
 ['DD máximo em dinheiro USD']+[fmt(cases[i]['equity_dd_max_money']) for i in cases],
 ['Positivos / negativos / zeros¹']+[f'{positive(i)} / {negative(i)} / {zero(i)}' for i in cases],
 ['Setembro/2026 parcial USD']+[fmt(months[i][-1]['equity_change']) for i in cases],
],[176,(WIDTH-176)/3,(WIDTH-176)/3,(WIDTH-176)/3])
p('¹ Meses completos. A classificação usa mudança de patrimônio (equity), incluindo posições abertas na virada. Saldo realizado aparece nos CSVs de origem e é conciliado separadamente.','small')
p('O caso 2 executou 58 entradas por pivô, mas teve apenas 38 operações a mais no total; as entradas BASE passaram de 261 para 241. No caso 3, foram 111 entradas por pivô e 81 operações líquidas a mais; BASE caiu para 231. A nova ocupação altera oportunidades seguintes. Sem os ciclos individuais R200, não é possível atribuir a diferença de lucro exclusivamente aos trades PIVOT nem identificar exatamente quais entradas BASE foram substituídas.')
p('Drawdown relativo e drawdown máximo em dinheiro podem ocorrer em instantes diferentes. O caso 3 teve DD relativo menor, mas DD máximo em dinheiro de US$ '+fmt(cases[3]['equity_dd_max_money'])+'. Isso impede concluir que ele melhorou todos os aspectos de risco.')

page('02 · Evolução do patrimônio')
pic('patrimonio_mensal.png',WIDTH*.47,'Fonte: equity_end dos CSVs mensais, com capital inicial. Linha une observações de fim de mês; não reconstrói o caminho intradiário. * Setembro/2026 parcial.')
h('Leitura do gráfico',2)
p('O gráfico permite comparar a trajetória de capital no mesmo calendário. O valor final menor das versões de pivô é compatível com a conciliação dos resultados mensais. O crescimento percentual depende também do capital acumulado no início de cada período; não significa aumento automático de lote, que permanece fixo.')
p('As curvas de mês fechado não mostram todos os picos e vales do teste. Para risco, usar também o drawdown intrateste reportado pelo MT5. A qualidade e cobertura dos ticks, latência, corretora e especificações completas precisam ser conferidas no relatório nativo de cada caso.')
h('Protocolo de comparação',2)
p('Janela planejada: 01/01/2022 até 12/09/2026 exclusivo. Avaliações reportadas: 02/01/2022 às 23:05 até 11/09/2026 às 20:30, horário do servidor. Cada caso reportou 55.498 barras avaliadas. O período foi usado repetidamente para pesquisa e seleção; não é uma amostra inédita de validação.')

page('03 · Consistência mês a mês')
pic('retornos_mensais.png',WIDTH*.72,'Retorno = (equity_end / equity_start - 1) × 100. Cinza indica mês não observado. * Somente setembro de 2026 é parcial; meses de setembro dos anos anteriores são completos. Cores saturam em ±35%; os números mostram o retorno efetivo.')
p('A ausência de operação não equivale a lucro. A Referência teve dois meses completos zerados; ambas as versões extras tiveram atividade suficiente para eliminar esses zeros, mas não eliminaram os meses negativos.')

page('04 · Onde houve melhora ou piora')
pic('diferenca_mensal.png',WIDTH*.54,'Diferença de mudança mensal de equity de cada versão menos a Referência. Barras verdes: resultado maior; vermelhas: menor. A diferença não identifica o lucro individual de um tipo de entrada.')
for i in [2,3]:
    t=transitions[i];h(f'{i} · {SHORT[i]}',2)
    p('Meses antes negativos que ficaram positivos: '+(', '.join(t['negative_to_positive']) or 'nenhum')+'.')
    p('Meses antes positivos que ficaram negativos: '+(', '.join(t['positive_to_negative']) or 'nenhum')+'.')
    if t['zero_to_negative']:p('Meses antes zerados que ficaram negativos: '+', '.join(t['zero_to_negative'])+'.')
p('Comparação restrita aos mesmos 56 meses completos. Mudanças de um mês também podem decorrer de posições iniciadas no mês anterior. É necessário analisar ciclos e marcação das posições para explicar cada transição.','small')

page('05 · Resultados anuais e Selic')
table(['Ano','Caso','Lucro USD','Retorno USD','Retorno BRL','Selic BRL'],[[str(r['year'])+('*' if r['year']==2026 else ''),str(r['case']),fmt(r['profit']),pct(r['return_usd']),pct(r['return_brl']),pct(r['selic'])] for r in annual],[48,35,112,103,104,WIDTH-402])
p('Casos: 1 Referência, 2 Continuidade, 3 Início. * 2026 até 11/09/2026, sem anualizar o retorno parcial.','small')
p('Retorno anual USD = patrimônio final / patrimônio inicial do ano − 1. Retorno BRL = (patrimônio final USD × câmbio final) / (patrimônio inicial USD × câmbio inicial) − 1. A Selic foi acumulada no mesmo intervalo. A comparação em BRL evita confrontar diretamente moedas diferentes.')
p('Benchmark reutilizado dos arquivos históricos já arquivados: [SGS do Banco Central](https://www3.bcb.gov.br/sgspub/), série 11 (Selic diária) e série 1 (dólar). A origem, datas e taxas estão em Benchmarks_Anuais.json. Não inclui impostos, spread cambial ou tarifas de remessa; tampouco iguala o risco do robô ao da Selic.','small')

for group,title in [(['2022','2023'],'06 · Todos os meses: 2022 e 2023'),(['2024','2025'],'07 · Todos os meses: 2024 e 2025'),(['2026'],'08 · Todos os meses: 2026 parcial')]:
    page(title);p('Resultado mensal por mudança de patrimônio. USD e percentual sobre o patrimônio no início de cada mês.','small')
    rows=[]
    for ix,r in enumerate(months[1]):
        if r['month_server'][:4] not in group:continue
        row=[r['month_server']+('*' if r['month_server']=='2026-09' else '')]
        for i in cases:
            v=months[i][ix];row += [fmt(v['equity_change']),pct(100*v['equity_change']/v['equity_start'])]
        rows.append(row)
    table(['Mês','Caso 1 USD','Caso 1 %','Caso 2 USD','Caso 2 %','Caso 3 USD','Caso 3 %'],rows,[57,85,65,85,65,85,WIDTH-442])
    if group==['2026']:
        p('* Setembro termina no último tick recebido em 11/09/2026. Não tratá-lo como mês completo. Os resultados anuais de 2026 e o total do teste incluem esse intervalo.','small')
        h('Saldo realizado e patrimônio',2)
        p('O dossiê mede a consistência usando patrimônio: saldo mais resultado aberto. As tabelas de origem também registram booked_net e cycle_net_by_exit, úteis para explicar fechamentos, mas esses conceitos não devem substituir a mudança de equity na avaliação mensal. Uma transferência de lucro aberto para saldo ao fechar uma operação não é uma perda.')

page('09 · Estratégias efetivamente utilizadas')
p('A estratégia é uma implementação de pesquisa própria com médias, ADX e pivôs. Referências anteriores a Linda Raschke ou Larry Williams não certificam que suas metodologias foram reproduzidas integralmente. O código anexado é a definição operacional.')
table(['Componente','Implementação da rodada'],[
 ['Mercado e direção','XAUUSD M30; somente compras; uma posição por vez.'],
 ['Médias','EMA21; SMA50; SMA200, sobre fechamento.'],
 ['Força/direção','iADX do MT5, período 14; mínimo 20; +DI > −DI. Não é chamada a iADXWilder.'],
 ['Volatilidade','ATR14; distância mínima do ask à EMA21 de 0,50 ATR.'],
 ['Oscilador extra','SMA3 − SMA10; crescente em relação à barra anterior. Sinal SMA16 calculado; não é um cruzamento obrigatório. Nenhuma chamada a iMACD.'],
 ['Stop','Menor mínima do candle fechado de sinal e dos dois anteriores −0,20 ATR. Aceito somente entre 1 e 2,5 ATR da entrada cotada.'],
 ['Alvo e lote','5R sobre risco inicial cotado; lote fixo 1,00. Sem BE, parcial, médio, pirâmide ou reinvestimento.'],
],[122,WIDTH-122])
h('Caso 1 · Referência',2)
p('Mantém as regras originais do Hermes R190:2. O oscilador 3–10 não é um filtro obrigatório desta entrada original. O detalhamento exato das condições de tendência, toque anterior e retomada está na auditoria do código a seguir; as funções executáveis permanecem no anexo.')
h('Casos 2 e 3 · Entrada adicional',2)
p('Fundo F1, topo T, fundo mais alto F2; F1 < F2 < T. Cada extremo exige duas barras à esquerda e duas à direita. O gatilho exige rompimento de T no fechamento, com referência já conhecida antes da abertura do candle de rompimento. Perda de F1 invalida a estrutura, inclusive na vela do rompimento. F1 não substitui o stop estrutural de três candles.')
p('Ambos os extras exigem candle de alta, fechamento acima da EMA21, EMA21 > SMA50, SMA50 subindo, ADX14 ≥20, +DI > −DI, 3–10 crescente e distância mínima de 0,5 ATR. O caso 2 também exige fechamento acima da SMA200 e SMA200 subindo. O caso 3 retira somente essas duas condições da entrada extra.')

page('10 · Auditoria técnica do código')
auditpath=ROOT/'outputs/rodada200_resultados/auditoria_codigo/Auditoria_Codigo_R200.md'
assert auditpath.exists(),'Independent code audit is required before rendering.'
markdown_fragment(auditpath.read_text())

page('11 · Escopo e limites da auditoria de resultados')
p('Recebidos quatro arquivos agregados, com três casos e 171 registros mensais. A conciliação cobre totais, continuidade de patrimônio/saldo, contagem de operações e meses, identificadores, flags de integridade e reprodução da referência. Os registros individuais R200 de barras, ciclos, deals e eventos ainda não foram enviados.')
p('Foram aprovadas '+fmt(independent['checks_passed'],0)+' verificações de conciliação. A Referência reproduziu os 124 campos comuns econômicos e operacionais comparados com R190:2 e os 1.026 campos mensais; as cinco diferenças restantes são identificadores e flags de controle.','small')
p('Os arquivos de detalhes da antiga referência R190:2 existem no banco e apoiam o estudo anterior. Eles não foram copiados para simular recebimento de detalhes da rodada R200. A auditoria agregada não identifica a sequência exata dos trades extras nem verifica individualmente seus preços de execução.')
p('O código foi submetido a oito testes locais de lógica e revisão estática na entrega. Agora existem resultados nativos exportados pelo usuário, mas não recebemos relatório de compilação, executável EX5 ou relatório nativo de qualidade dos ticks. Não foi executado um novo backtest financeiro aqui.')
p('Os cabeçalhos reportam valid_run=1 e ausência de falhas de sincronização de pivôs. Mesmo assim, existem 8/11/13 rejeições de ordens nos casos 1/2/3; o último retcode reportado é 10018. Isso deve ser interpretado com os eventos e horários antes de atribuir oportunidades perdidas a um filtro de estratégia.')
p('Os paths de breakeven desta comparação pertencem somente ao caso 1. Eles observam a trajetória sem ativar breakeven. Não constituem resultados financeiros de cinco variantes de BE.')
h('Estado da meta',2)
p('Nenhum caso atingiu todos os meses positivos. O período exportado contém 56 meses completos, não cinco anos completos. Alterar regras para melhorar meses conhecidos continua sendo pesquisa na amostra; confirmação em dados não usados na escolha segue pendente.')
h('Próximo insumo útil',2)
p('Os três diretórios de detalhes estão identificados em arquivos_comparacao(3).csv. Enviar as pastas completas permite separar PIVOT e BASE, reconhecer substituições de entrada e estudar ganhadores/perdedores com contexto conhecido antes da decisão.')
for f in folders:p(str(f['relative_details_folder']),'small')

page('12 · Roteiro para revisão pelo Claude')
prompt='''Você é o revisor independente do projeto Hermes. Analise o dossiê, o fonte MQL5 da versão 2.00, a auditoria e os quatro CSVs originais. Não execute ordens nem altere o fonte de referência antes de apresentar seu parecer.

Objetivo do proprietário: aumentar lucro com maior consistência mensal. A meta de nenhum mês negativo é aspiracional e não foi atingida. A amostra foi reutilizada diversas vezes; não a trate como validação inédita.

Confirme primeiro os três casos: Referência, Pivô Continuidade e Pivô Início. Todos são XAUUSD M30, BUY-only, lote fixo 1,00, alvo nominal 5R e stop estrutural. As únicas mudanças planejadas são nas entradas extras. Não substituir iADX por iADXWilder nem SMA3−SMA10 por MACD EMA sem tratar como mudança de estratégia.

1. Recalcule totais e meses completos. Separe setembro/2026 parcial e equity de saldo realizado. Compare retorno anual em moedas iguais com Selic.
2. Audite causalidade: confirmação dos pivôs, disponibilidade temporal, sequência do rompimento, leitura de candles fechados, consumo de sinais, stop e priorização BASE/PIVOT. Cite função e trecho para cada falha concreta.
3. Explique o que podemos concluir com os agregados e o que exige cycles/deals/events/bars individuais. Não atribua a diferença total de lucro aos pivôs isoladamente: a ocupação alterou as entradas BASE.
4. Avalie custos, rejeições, lote, margem e diferenças entre DD relativo e DD máximo em dinheiro. Não interprete redução percentual isolada como redução de todo risco.
5. Proponha no máximo três hipóteses novas e diferentes, com mecanismo, regras exatas, informação disponível no momento da entrada, previsão falsificável e critério de rejeição. Evite grandes grades de otimização e filtros escolhidos só por coincidirem com meses negativos conhecidos.
6. Priorize teste isolado de cada alteração, comparador preservado e validação posterior não usada na escolha. Qualquer análise de padrões deve separar características anteriores à entrada de MFE/MAE e demais resultados conhecidos depois.

Entregue: parecer objetivo; falhas reproduzíveis versus hipóteses; tabela de evidência/impacto; dados faltantes estritamente necessários; três experiências priorizadas. Não invente backtest, execução nativa, lucro, causalidade ou garantia de rentabilidade.'''
(OUT/'Pedido_Revisao_Claude.txt').write_text(prompt)
for para in prompt.split('\n\n'):p(para)

page('13 · Fontes, versões e rastreabilidade')
p('Fonte entregue: Hermes_Pivos_Lab_200.mq5. SHA256:','small');p(SOURCE_SHA,'small')
p('O código abaixo é uma cópia integral desse fonte, com numeração e quebra visual de linhas somente no PDF. Para compilação ou diff, usar o arquivo .mq5 original incluído no pacote. O documento Markdown conserva o código em bloco sem numeração nem quebra inserida.')
for n in INPUTS:
    b=(ROOT/'upload'/n).read_bytes();p(n+' · SHA256 '+hashlib.sha256(b).hexdigest(),'small')
p('Fontes técnicas oficiais: [CopyRates](https://www.mql5.com/en/docs/series/copyrates), [relatório de teste MT5](https://www.metatrader5.com/en/terminal/help/algotrading/testing_report), [otimização e forward](https://www.metatrader5.com/en/terminal/help/algotrading/strategy_optimization). CopyRates define o índice zero como a barra atual; a ordem física retornada precisa ser respeitada. O relatório MT5 é a fonte necessária para conferir modelagem e qualidade de histórico.','small')
p('O banco registra a rodada R200 como executada a partir dos exports recebidos. Hipóteses, código, resultados e documentação ficam separados; resultados anteriores não são apagados. Os CSVs originais são preservados no pacote de revisão.','small')
p('Leitura recomendada para Claude: Dossie_Hermes_R200.md, Pedido_Revisao_Claude.txt, Hermes_Pivos_Lab_200.mq5 e dados originais. As estratégias e limitações devem ser avaliadas antes de sugerir novos parâmetros.')

page('Anexo · Código-fonte completo')
p('Hermes_Pivos_Lab_200.mq5 · versão 2.00 · '+str(len(CODE.splitlines()))+' linhas originais.','small')
p('Linhas longas são quebradas visualmente. O prefixo numérico identifica a linha original; trechos de continuação têm prefixo vazio. Esta formatação não modifica o arquivo .mq5 fornecido.','small')
md.extend(['```cpp',CODE.rstrip('\n'),'```',''])
wrapped=[]
max_chars=int(WIDTH/pdfmetrics.stringWidth('0','Mono',styles['code'].fontSize))
for lineno,line in enumerate(CODE.splitlines(),1):
    expanded=line.expandtabs(4)
    segments=textwrap.wrap(expanded,width=max_chars-7,replace_whitespace=False,drop_whitespace=False,break_long_words=True,break_on_hyphens=False) or ['']
    for j,segment in enumerate(segments):wrapped.append((f'{lineno:04d} | ' if j==0 else '     | ')+segment)
story.append(Preformatted('\n'.join(wrapped[:58]),styles['code']))
for k in range(58,len(wrapped),69):
    story.append(PageBreak())
    story.append(Preformatted('\n'.join(wrapped[k:k+69]),styles['code']))

def footer(c,doc):
    c.saveState();w,hh=A4
    c.setStrokeColor(colors.HexColor('#dbe3e9'));c.line(44,hh-34,w-44,hh-34)
    c.setFont('Bold',8);c.setFillColor(teal);c.drawString(44,hh-25,'HERMES · PESQUISA E AUDITORIA')
    c.setFont('Body',7.5);c.setFillColor(gray);c.drawRightString(w-44,hh-25,'R200 / 2.00 · 13.09.2026')
    c.drawString(44,24,'Backtests recebidos do usuário · revisão técnica interna');c.drawRightString(w-44,24,str(doc.page));c.restoreState()
pdf=OUT/'Dossie_Hermes_R200.pdf'
doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=49,bottomMargin=42,title='Hermes R200 - Dossiê técnico e código-fonte',author='Projeto Hermes / Bruno Milani')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
(OUT/'Dossie_Hermes_R200.md').write_text('\n'.join(md),encoding='utf-8')
(OUT/'Benchmarks_Anuais.json').write_text(json.dumps({'source':'outputs/rodada190_resultados/Analise_R190.json benchmarks.2','historical_reference':BENCH,'calculated_annual':annual,'formulas':{'USD':'equity_end/equity_start-1','BRL':'(equity_end*FX_end)/(equity_start*FX_start)-1'}},ensure_ascii=False,indent=2))
shutil.copyfile(SRC,OUT/SRC.name)
for name,rows in [('Resultados_Mensais_R200.csv',[{'case':i,**r,'return_percent':100*r['equity_change']/r['equity_start'],'complete_month':r['month_server']<'2026-09'} for i in cases for r in months[i]]),('Resultados_Anuais_R200.csv',annual)]:
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter=';');writer.writeheader();writer.writerows(rows)
reader=PdfReader(pdf);texts=[p.extract_text() or '' for p in reader.pages]
assert all(t.strip() for t in texts)
assert all('Hermes_Pivos_Lab_200' in '\n'.join(texts) for _ in [0])
assert CODE.rstrip('\n') in (OUT/'Dossie_Hermes_R200.md').read_text()
assert hashlib.sha256((OUT/SRC.name).read_bytes()).hexdigest()==SOURCE_SHA
validation={'pages':len(reader.pages),'source_lines':len(CODE.splitlines()),'source_sha256':SOURCE_SHA,'all_pages_have_text':True,'full_code_in_markdown':True,'native_results_source':'user CSV exports','monthly_rows':len(monthly_raw),'negative_complete':{str(i):negative(i) for i in cases},'annual_rows':len(annual),'visual_QA':'PENDING','PDF_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}
(OUT/'Validacao_Dossie.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2));print(json.dumps(validation,ensure_ascii=False))
