"""R210: amalgama o fonte e gera presets/inc de teste. NAO compila MQL5.

Diferencas vs. R200 (projeto_fonte/build.py):
- Novo core QuickHarvestCore.mqh (Caso 5), incluido logo apos XAU_H1_Core.
- 5 casos (1-3 = R200 congelado; 4 = Referencia + risco; 5 = Colheita Rapida).
- Novos inputs de risco/colheita no conjunto base dos presets.
"""
from pathlib import Path
import csv,hashlib,json,re

ROOT=Path(__file__).resolve().parent
source=(ROOT/'src/EA.mq5').read_text()
# QuickHarvestCore vem logo depois de XAU_H1_Core porque usa H1Signal.
names=['XAU_H1_Core.mqh','QuickHarvestCore.mqh','ProtectCore.mqh','EntryCore.mqh',
       'DonchianCore.mqh','HermesCore.mqh','PivotCore.mqh','PivotEntryCore.mqh',
       'PivotRuntime.mqh','Execution.mqh','Reports.mqh']
ea=source
for name in names:
    marker='#include "'+name+'"'
    assert ea.count(marker)==1,name
    ea=ea.replace(marker,(ROOT/'src'/name).read_text())
assert '#include "' not in ea
(ROOT/'Hermes_R210.mq5').write_text(ea)

# Cores portaveis para os testes em C++ (mesmo tratamento do R200).
# Agora sao 8 arquivos ate PivotEntryCore.mqh (7 originais + QuickHarvestCore).
core='\n'.join((ROOT/'src'/n).read_text() for n in names[:8])
core=re.sub(r'const double &(\w+)\[\]',r'const std::vector<double> &\1',core)
(ROOT/'tests/Core_Runtime.inc').write_text(core)
structs='\n'.join(re.findall(r'struct (?:PECycle|PEMonth) \{.*?\};',source,re.S))
(ROOT/'tests/Structures_Runtime.inc').write_text(structs)
(ROOT/'tests/Open_Runtime.inc').write_text(source[source.index('PE_GATE OpenCycle('):source.index('void OnTick(')])
(ROOT/'tests/Execution_Runtime.inc').write_text((ROOT/'src/Execution.mqh').read_text())
(ROOT/'tests/History_Runtime.inc').write_text(source[source.index('bool AggregateCycle('):source.index('void FinishCycle(')])
report=(ROOT/'src/Reports.mqh').read_text();parts=[]
for start,end in [('void MonthValues(', 'string MonthCSV('),('void ShadowValues(', 'string ShadowHeader('),('void BuildPayload(', 'double OnTester(')]:
    parts.append(report[report.index(start):report.index(end)])
runtime='\n'.join(parts).replace('void MonthValues(const int i,double &v[])','template<class V> void MonthValues(const int i,V &v)')
runtime=runtime.replace('void ShadowValues(const int t,double &v[])','template<class V> void ShadowValues(const int t,V &v)')
runtime=re.sub(r'const double &(\w+)\[\]',r'const std::vector<double> &\1',runtime)
runtime=re.sub(r'double &(\w+)\[\]',r'std::vector<double> &\1',runtime)
enums='\n'.join(re.findall(r'enum PE_(?:GATE|STAT) \{.*?\};',source,re.S))
(ROOT/'tests/Reports_Runtime.inc').write_text(enums+'\nconst int MONTH_FIELDS=18,SHADOW_FIELDS=8;\n'+runtime)
adapter=(ROOT/'src/PivotRuntime.mqh').read_text().replace('MqlRates observed[];', 'std::vector<MqlRates> observed;')
(ROOT/'tests/PivotAdapter_Runtime.inc').write_text(adapter)

# Nomes dos casos, agora 5 (DCName no EA).
case_names=re.search(r'string names\[5\]=\{(.*?)\};',source,re.S)[1]
case_names=re.findall(r'"([^"]+)"',case_names)
assert len(case_names)==5,case_names

def case_row(i,name):
    extra=i in (2,3)
    return dict(case=i,name=name,timeframe='M30',
        entry='ORIGINAL' if i in (1,4) else ('ORIGINAL_OR_CAUSAL_LONG_123' if extra else 'QUICK_HARVEST_VOLUME_BURST'),
        extra_enabled=extra,
        extra_requires_close_above_SMA200=i==2,extra_requires_rising_SMA200=i==2,
        EMA_period=21,SMA_middle=50,SMA_long=200,ATR_period=14,ADX_period=14,min_ADX=20,
        minimum_entry_distance_ATR=.5,minimum_structural_stop_ATR=1.0,maximum_structural_stop_ATR=2.5,
        stop_buffer_ATR=.2,stop_lookback_closed_bars=3,
        target_R=5 if i!=5 else 'InpQHTargetR',
        sizing='EXACT_FIXED_LOT' if i in (1,2,3) else 'RISK_PERCENT',
        partial=False,adds=0,breakeven=False,reinvest=False,
        status='CONGELADO_R200' if i in (1,2,3) else 'NOVO_R210_NAO_VALIDADO')
cases=[case_row(i,name) for i,name in enumerate(case_names,1)]

base=dict(InpCase=1,InpMaxMarginPct=20.0,InpMaxLot=1.0,InpFixedLot=1.0,InpMinEntryATR=.5,
    InpMaxSpreadPoints=0,InpDeviationPoints=20,InpMagic=26120200,InpExportCSV=True,
    InpShowIndicators=False,InpExportOptimizationDetails=True,InpExportAllBars=True,InpRunTag='R210_01',
    InpRiskPercent=1.0,InpQHTargetR=1.0,InpQHVolFactor=1.5,InpQHRangeFactor=1.0,
    InpQHMinCloseLoc=0.6,InpQHMinADX=20.0,InpQHMaxSpreadATR=0.10)
assert set(re.findall(r'^input\s+\w+\s+(Inp\w+)',source,re.M))==set(base)

def preset(filename,id,sweep=None):
    # sweep: {input: (start, step, end)} marca esses inputs para otimizacao (||Y).
    sweep=sweep or {}
    lines=['; HERMES R210 | SOMENTE TESTADOR | XAUUSD M30',
           '; Casos 1-3: congelados do R200 (lote fixo 1.00, alvo 5R).',
           '; Caso 4: Referencia + sizing por risco (InpRiskPercent, ate 5%).',
           '; Caso 5: Colheita Rapida (surto de volume, alvo curto InpQHTargetR, risco).',
           '; Datas, deposito, alavancagem, modelagem e CUSTOS nao sao definidos por .set.']
    for key,value in (base|{'InpCase':id}).items():
        if key in sweep:
            s,st,e=sweep[key]
            lines.append(f'{key}={s}||{s}||{st}||{e}||Y')
        elif isinstance(value,bool):
            lines.append(f'{key}={str(value).lower()}||false||0||true||N')
        elif isinstance(value,str):
            lines.append(f'{key}={value}')
        else:
            lines.append(f'{key}={value}||{value}||{1 if isinstance(value,int) else .01}||{value}||N')
    (ROOT/'presets'/filename).write_text('\r\n'.join(lines)+'\r\n')

for old in (ROOT/'presets').glob('*.set'): old.unlink()   # limpa presets herdados do R200
preset('00_COMPARAR_5_CASOS.set',1,sweep={'InpCase':(1,1,5)})
for c in cases:
    preset(f"CASO_{c['case']:02d}_{c['name']}.set",c['case'])
# Varredura de risco pedida: Caso 4 (Referencia) a 2%, 3%, 4% e 5% num unico teste.
preset('CASO_04_RISCO_2a5pct.set',4,sweep={'InpRiskPercent':(2.0,1.0,5.0)})
with (ROOT/'CASOS.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,list(cases[0]),delimiter=';');writer.writeheader();writer.writerows(cases)

manifest=dict(version='2.10',batch='R210',parent='R200:1(projeto_fonte)',
    source_sha256=hashlib.sha256(ea.encode()).hexdigest(),native_compilation=False,native_backtests=False,
    frozen_from_r200=['XAU_H1_Core.mqh','ProtectCore.mqh','EntryCore.mqh','DonchianCore.mqh','HermesCore.mqh','Execution.mqh','PivotCore.mqh','PivotRuntime.mqh','Reports.mqh'],
    changed=['EA.mq5','PivotEntryCore.mqh'],added=['QuickHarvestCore.mqh'],
    cases=cases,
    note='Casos 4 e 5 sao hipoteses NAO validadas: exigem backtest MT5 com custos realistas e validacao fora da amostra. Ver MUDANCAS_R210.md.')
(ROOT/'MANIFESTO_R210.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('R210: 5 casos, 6 presets, single-file Hermes_R210.mq5 gerado. Sem compilacao/backtest MQL5.')
