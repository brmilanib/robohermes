"""Amalgamate source and prepare predeclared presets. Does not compile MQL5."""
from pathlib import Path
import csv,hashlib,json,re

ROOT=Path(__file__).resolve().parent
source=(ROOT/'src/EA.mq5').read_text()
names=['XAU_H1_Core.mqh','ProtectCore.mqh','EntryCore.mqh','DonchianCore.mqh','HermesCore.mqh','PivotCore.mqh','PivotEntryCore.mqh','PivotRuntime.mqh','Execution.mqh','Reports.mqh']
ea=source
for name in names:
    marker='#include "'+name+'"'
    assert ea.count(marker)==1,name
    ea=ea.replace(marker,(ROOT/'src'/name).read_text())
assert '#include "' not in ea
(ROOT/'Hermes_Pivos_Lab_200.mq5').write_text(ea)
core='\n'.join((ROOT/'src'/n).read_text() for n in names[:7])
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

case_names=re.search(r'string names\[3\]=\{(.*?)\};',source,re.S)[1]
case_names=re.findall(r'"([^"]+)"',case_names)
REFERENCE_SHA='0ddbee937fc4b5af16510987f84d72e126012e0a080b61ef18530a80275d8e35'
cases=[]
for i,name in enumerate(case_names,1):
    cases.append(dict(case=i,name=name,timeframe='M30',matched_control190=2,matched_control200=1,
        entry='ORIGINAL' if i==1 else 'ORIGINAL_OR_CAUSAL_LONG_123',extra_enabled=i!=1,
        extra_requires_close_above_SMA200=i==2,extra_requires_rising_SMA200=i==2,
        extra_ADX_period=14,extra_min_ADX=20,extra_plus_DI_above_minus_DI=i!=1,
        extra_fast310_above_previous=i!=1,EMA_period=21,SMA_middle=50,SMA_long=200,ATR_period=14,
        minimum_entry_distance_ATR=.5,minimum_structural_stop_ATR=1.0,maximum_structural_stop_ATR=2.5,
        stop_buffer_ATR=.2,stop_lookback_closed_bars=3,target_R=5,requested_fixed_lot=1.0,
        capital_mode='EXACT_FIXED_LOT',partial=False,adds=0,breakeven=False,reinvest=False,
        status='PROGRAMADO_NAO_EXECUTADO'))
base=dict(InpCase=1,InpMaxMarginPct=20.0,InpMaxLot=1.0,InpFixedLot=1.0,InpMinEntryATR=.5,
    InpMaxSpreadPoints=0,InpDeviationPoints=20,InpMagic=26120200,InpExportCSV=True,
    InpShowIndicators=False,InpExportOptimizationDetails=True,InpExportAllBars=True,InpRunTag='R200_01')
assert set(re.findall(r'^input\s+\w+\s+(Inp\w+)',source,re.M))==set(base)
def preset(filename,id,optimization=False):
    lines=['; HERMES PIVOS2.00 | SOMENTE TESTADOR | XAUUSD M30',
           '; Somente InpCase selecionado para otimizacao. Use agentes LOCAIS.',
           '; Datas, deposito, alavancagem, timeframe e modelagem NAO sao definidos por .set.',
           '; Todos os casos: lote fixo1.00, alvo5R, sem parcial/BE/adicoes/reinvestimento.',
           '; InpMaxMarginPct/InpMaxLot mantidos por compatibilidade; nao usados no lote fixo.']
    for key,value in (base|{'InpCase':id}).items():
        if key=='InpCase':lines.append(f'{key}={id}||{1 if optimization else id}||1||{3 if optimization else id}||'+('Y' if optimization else 'N'))
        elif isinstance(value,bool):lines.append(f'{key}={str(value).lower()}||false||0||true||N')
        elif isinstance(value,str):lines.append(f'{key}={value}')
        else:lines.append(f'{key}={value}||{value}||{1 if isinstance(value,int) else .01}||{value}||N')
    (ROOT/'presets'/filename).write_text('\r\n'.join(lines)+'\r\n')
preset('00_COMPARAR_3_CASOS.set',1,True)
for c in cases:preset(f"CASO_{c['case']:02d}_{c['name']}.set",c['case'])
with (ROOT/'CASOS.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,list(cases[0]),delimiter=';');writer.writeheader();writer.writerows(cases)
plan=dict(version='2.00',batch='R200',created='2026-09-13',parent='Olimpo_Consistencia_Lab_190',
    parent_case=2,parent_source_sha256=REFERENCE_SHA,
    source_sha256=hashlib.sha256(ea.encode()).hexdigest(),native_compilation=False,native_backtests=False,
    fixed_lot_default=1.0,initial_capital_for_comparison=10000,
    first_execution_window_start='2022-01-01',first_execution_window_end_exclusive='2026-09-12',
    dates_note='This is the already examined comparison window, not a fresh holdout or 60 complete months.',
    current_source_baseline_control='R190:2',new_control='R200:1',
    priority='Evaluate original first; extra considered only when EVOEvaluate fails. Never fallback after original stop/margin/spread refusal.',
    signal_core='HERMES_PIVOS_2x2_V1',pivot_left_bars=2,pivot_right_bars=2,pivot_seed_closed_bars=210,
    pivot_close_witness='Next observed bar opening; no OHLC of the open bar. References must be known before trigger bar opening.',
    pivot_history_policy='Seed210 plus opening witness, then process every observed closed bar, even while occupied. Invalid/incomplete copy does not advance state. Only latest eligible signal may trade; prior catch-up signals discarded.',
    pivot_seed_limit='A finite210-bar seed can differ near initialization from a catalog begun at the first2022 candle. Exact catalog replication requires identical source origin.',
    extra_common='Confirmed LONG1-2-3 neckline cross AND bullish close>EMA21 AND EMA21>SMA50 AND risingSMA50 AND ADX14>=20 AND +DI>-DI AND valid(SMA3-SMA10)>previous AND ask-EMA21>=InpMinEntryATR.',
    only_extra_variant_difference='Case2 requires close>SMA200 and risingSMA200; case3 omits only these two SMA200 requirements.',
    stop='Original low(signal+2prior)-.2ATR; quoted entry-stop1..2.5ATR or reject. Geometric L1 is not substituted as stop.',
    sizing='All cases exact InpFixedLot(default1.00), native free margin, volume min/max/step; reject rather than downsize.',
    target='Original H1Levels5R at quoted entry with native tick rounding; actual slippage/costs can change realized R.',
    exclusions=['W1','short entries','BE','partial','averaging','pyramiding','reinvestment','same-bar reentry'],
    additional_bar_columns='Pivot availability/origins/confirmation, original gate, extra gate and selected path BASE/PIVOT/NONE.',
    goal='Research monthly consistency and genuine additional entries; new profit and negative-month count unknown until native MT5.',
    validation='Local causal/routing/production-body tests only, followed by native matched-control test and subsequently untouched/forward data.',
    comparison_path=r'%APPDATA%\MetaQuotes\Terminal\Common\Files\Hermes_Pivos_Lab_200\R200_01\OTIMIZACAO_<stamp>\comparacao.csv',
    cases=cases)
(ROOT/'PLANO_RODADA_200.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
print('Generated standalone2.00:3cases,4presets. Native MQL5 compilation/backtest not performed.')
