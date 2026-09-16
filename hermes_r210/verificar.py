"""R210: checagens causais/decisao/corpo de producao. NAO compila MQL5 nem roda backtest.

Prova o que da para provar AQUI (sem MetaTrader):
- os cores auditados do R200 continuam byte-identicos (nao mexi neles);
- a amalgama gera um unico .mq5 sem includes pendentes e so-testador;
- toda a bateria de testes portaveis em C++ compila e passa (inclui os novos
  test_caso4/test_quickharvest e o test_pivot_entry atualizado);
- os presets batem com o conjunto de inputs e InpCase varia 1..5.
A rentabilidade dos Casos 4/5 continua DESCONHECIDA ate o backtest nativo.
"""
from pathlib import Path
import subprocess,tempfile,json,hashlib,re
ROOT=Path(__file__).resolve().parent
R200=ROOT.parent/'projeto_fonte'
subprocess.run(['python3',str(ROOT/'build.py')],check=True)

results=[]
tests=['test_core','test_execution','test_donchian','test_hermes','test_entry',
       'test_pivot','test_pivot_entry','test_pivot_adapter','test_quickharvest','test_dd_throttle',
       'test_withdrawal','test_ema_cross','test_double_swing']
with tempfile.TemporaryDirectory() as directory:
    for name in tests:
        binary=str(Path(directory)/name)
        subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Wno-misleading-indentation',
                        str(ROOT/'tests'/f'{name}.cpp'),'-o',binary],check=True)
        output=subprocess.run([binary],check=True,capture_output=True,text=True).stdout.strip()
        results.append(dict(test=name,passed=True,output=output))

source=(ROOT/'src/EA.mq5').read_text();ea=(ROOT/'Hermes_R210.mq5').read_text()
manifest=json.loads((ROOT/'MANIFESTO_R210.json').read_text())
assert len(manifest['cases'])==10 and len({c['name'] for c in manifest['cases']})==10
assert '#include "' not in ea and 'if(!MQLInfoInteger(MQL_TESTER))' in ea
assert 'if(_Period!=signalTF)' in ea and 'signalTF=(InpCase==10) ? PERIOD_M2 : PERIOD_M30;' in ea
assert 'HPSelectProfile(InpCase,dc,evo,profile)' in ea
assert 'if(InpCase==5)' in ea and 'QHGate(' in ea and 'ReadQuickHarvest(' in ea
assert 'InpCase==10' in ea and 'DSGate(' in ea and 'ReadDoubleSwing(' in ea
assert all(x not in ea for x in ['WebRequest(','ShellExecute','OnTimer('])
assert manifest['source_sha256']==hashlib.sha256(ea.encode()).hexdigest()

# Presets: mesmo conjunto de inputs; InpCase varia dentro de 1..10.
assert len(list((ROOT/'presets').glob('*.set')))==13
inputs=set(re.findall(r'^input\s+\w+\s+(Inp\w+)',source,re.M))
for path in (ROOT/'presets').glob('*.set'):
    params=dict(line.split('=',1) for line in path.read_text().splitlines() if line and not line.startswith(';'))
    assert set(params)==inputs,path.name
    value,start,step,end,opt=params['InpCase'].split('||')
    assert 1<=int(start)<=int(end)<=10 and int(step)==1,path.name
    assert params['InpRunTag']=='R210_01'

# Contagem de estatisticas inalterada (nao adicionei campos ao PE_STAT).
stat_names=re.search(r'return StringSplit\("([^"]+)',(ROOT/'src/Reports.mqh').read_text())[1].split(';')
stat_enum=[x.strip() for x in re.search(r'enum PE_STAT\s*\{(.*?)\};',source,re.S)[1].split(',')]
assert len(stat_names)==len(stat_enum)-1==116

# Cores auditados do R200 permanecem byte-identicos (prova de nao-alteracao).
frozen=['XAU_H1_Core.mqh','ProtectCore.mqh','EntryCore.mqh','DonchianCore.mqh','HermesCore.mqh',
        'Execution.mqh','PivotCore.mqh','PivotRuntime.mqh','Reports.mqh']
for name in frozen:
    assert (ROOT/'src'/name).read_bytes()==(R200/'src'/name).read_bytes(),f'core alterado: {name}'
changed=[n for n in ['EA.mq5','PivotEntryCore.mqh'] if (ROOT/'src'/n).read_bytes()!=(R200/'src'/n).read_bytes()]

validation=dict(version='2.10',source_sha256=manifest['source_sha256'],cases=10,presets=13,statistics_fields=116,
    frozen_cores_identical_to_r200=True,changed_files=changed,
    added_files=['QuickHarvestCore.mqh','DDThrottleCore.mqh','WithdrawalCore.mqh','EMACrossCore.mqh','DoubleSwingCore.mqh'],
    local_tests=results,native_MQL5_compilation=False,native_MT5_backtests=False,
    note='Casos 4-10 sao hipoteses NAO validadas. Caso 10 roda em M2 (nunca testado neste projeto). '
         'Exigem backtest MT5 com custos realistas e validacao fora da amostra antes de qualquer '
         'conclusao de lucro. Sem simulacao de PnL aqui.')
(ROOT/'VALIDACAO.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(validation,ensure_ascii=False,indent=2))
