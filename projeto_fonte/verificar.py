"""Causal/decision/production-body checks. Not a native MQL5 compiler or backtest."""
from pathlib import Path
import subprocess,tempfile,json,hashlib,re
ROOT=Path(__file__).resolve().parent
subprocess.run(['python3',str(ROOT/'build.py')],check=True)
results=[]
with tempfile.TemporaryDirectory() as directory:
    for name in ['test_core','test_execution','test_donchian','test_hermes','test_entry','test_pivot','test_pivot_entry','test_pivot_adapter']:
        binary=str(Path(directory)/name)
        subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Wno-misleading-indentation',str(ROOT/'tests'/f'{name}.cpp'),'-o',binary],check=True)
        output=subprocess.run([binary],check=True,capture_output=True,text=True).stdout.strip()
        results.append(dict(test=name,passed=True,output=output))
source=(ROOT/'src/EA.mq5').read_text();ea=(ROOT/'Hermes_Pivos_Lab_200.mq5').read_text()
plan=json.loads((ROOT/'PLANO_RODADA_200.json').read_text())
assert len(plan['cases'])==3 and len({c['name'] for c in plan['cases']})==3
assert '#include "' not in ea and 'if(!MQLInfoInteger(MQL_TESTER))' in ea
assert 'if(_Period!=signalTF)' in ea and 'signalTF=PERIOD_M30;' in ea
assert 'HPSelectProfile(InpCase,dc,evo,profile)' in ea
assert 'HPRouteEntry(InpCase,evo,s,features,q.ask,oldSMA200' in ea
assert all(x not in ea for x in ['WebRequest(','ShellExecute','OnTimer('])
assert plan['source_sha256']==hashlib.sha256(ea.encode()).hexdigest()
assert len(list((ROOT/'presets').glob('*.set')))==4
for path in (ROOT/'presets').glob('*.set'):
    params=dict(line.split('=',1) for line in path.read_text().splitlines() if line and not line.startswith(';'))
    assert set(params)==set(re.findall(r'^input\s+\w+\s+(Inp\w+)',source,re.M))
    value,start,step,end,opt=params['InpCase'].split('||')
    assert 1<=int(start)<=int(end)<=3 and int(step)==1
    assert params['InpFixedLot'].split('||')[0]=='1.0'
    assert params['InpMinEntryATR'].split('||')[0]=='0.5'
    assert params['InpRunTag']=='R200_01'
    assert [key for key,value in params.items() if value.endswith('||Y')] in ([],['InpCase'])
stat_names=re.search(r'return StringSplit\("([^"]+)',(ROOT/'src/Reports.mqh').read_text())[1].split(';')
stat_enum=[x.strip() for x in re.search(r'enum PE_STAT\s*\{(.*?)\};',source,re.S)[1].split(',')]
assert len(stat_names)==len(stat_enum)-1==116
for name in ['XAU_H1_Core.mqh','ProtectCore.mqh','EntryCore.mqh','DonchianCore.mqh','HermesCore.mqh','Execution.mqh']:
    assert (ROOT/'src'/name).read_bytes()==(ROOT.parent/'Olimpo_Consistencia_Lab_190/src'/name).read_bytes()
assert hashlib.sha256((ROOT.parent/'Olimpo_Consistencia_Lab_190/Olimpo_Consistencia_Lab_190.mq5').read_bytes()).hexdigest()==plan['parent_source_sha256']
assert hashlib.sha256((ROOT/'src/PivotCore.mqh').read_bytes()).hexdigest()=='b44977e36b54319eeabf1144fdd82619dc74ad1868192187544098e408506986'
validation=dict(version='2.00',source_sha256=plan['source_sha256'],profiles=3,presets=4,statistics_fields=116,
    local_tests=results,original_core_libraries_unchanged=True,original_execution_library_unchanged=True,
    baseline190_source_unchanged=True,pivot_core_sha256=hashlib.sha256((ROOT/'src/PivotCore.mqh').read_bytes()).hexdigest(),
    native_MQL5_compilation=False,native_MT5_backtests=False,
    note='Tests exercise causal pivot core, production entry routing, exact MT5 adapter body and inherited execution/accounting with deterministic API mocks. No MQL5 compilation or market/PnL simulation. New profit and monthly outcomes unknown until native MT5.')
replay=ROOT/'VALIDACAO_REPLAY.json'
if replay.exists():
    data=json.loads(replay.read_text())
    assert data['production_gate_sha256']==hashlib.sha256((ROOT/'src/PivotEntryCore.mqh').read_bytes()).hexdigest()
    assert data['production_stop_core_sha256']==hashlib.sha256((ROOT/'src/XAU_H1_Core.mqh').read_bytes()).hexdigest()
    validation['closed_snapshot_gate_replay']=data
(ROOT/'VALIDACAO.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(validation,ensure_ascii=False,indent=2))
