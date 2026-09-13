"""Compare the production extra gate against independently catalogued snapshots.

Run: python3 tests/replay_extra_entry.py <bars.csv> <comparacao_OR123_candidatos.csv>
The independently computed structural stop is supplied as a frozen reference.
This checks gates and the 1..2.5ATR refusal only; it does not simulate a portfolio.
"""
from pathlib import Path
import csv, hashlib, json, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parents[1]
def rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream,delimiter=';'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main(bars_path,candidates_path):
    bars={r['signal_time'].replace('.','-'):r for r in rows(bars_path)}
    candidates=rows(candidates_path)
    inputs=[];expected=[]
    for row in candidates:
        bar=bars[row['signal_bar_open']]
        for case in [2,3]:
            values=[case,bar['open'],bar['close'],bar['ema21'],bar['sma50'],bar['old_sma50'],
                    bar['sma200'],bar['adx'],bar['plus_di'],bar['minus_di'],bar['atr'],bar['old_sma200'],
                    bar['ask'],bar['oscillator_valid'],bar['fast310'],bar['previous_fast310'],row['original_structural_stop']]
            inputs.append(' '.join(map(str,values)))
            expected.append((case,row, row['OR123_CONTINUIDADE_pass' if case==2 else 'OR123_INICIO_pass']=='True'))
    with tempfile.TemporaryDirectory() as directory:
        binary=str(Path(directory)/'replay_extra')
        subprocess.run(['g++','-std=c++17',str(ROOT/'tests/replay_extra_entry.cpp'),'-o',binary],check=True)
        output=subprocess.run([binary],input='\n'.join(inputs)+'\n',text=True,capture_output=True,check=True).stdout.splitlines()
    assert len(output)==len(expected)
    counts={str(case):{'combined_extra_gate_and_structural_stop':0,'extra_not_original':0,'baseline_flat':0,'baseline_occupied':0} for case in [2,3]}
    for line,(case,row,want) in zip(output,expected):
        gate,structural=map(int,line.split());actual=gate==0 and structural==1
        assert actual==want,(case,row['event_id'],gate,structural,want)
        if actual:
            counts[str(case)]['combined_extra_gate_and_structural_stop']+=1
            if row['not_current_setup']=='True':
                counts[str(case)]['extra_not_original']+=1
                counts[str(case)]['baseline_flat' if row['baseline_flat']=='True' else 'baseline_occupied']+=1
    result=dict(kind='PRODUCTION_GATE_REPLAY_NOT_MARKET_BACKTEST',source_bars_sha256=digest(bars_path),
                source_candidates_sha256=digest(candidates_path),production_gate_sha256=digest(ROOT/'src/PivotEntryCore.mqh'),
                production_stop_core_sha256=digest(ROOT/'src/XAU_H1_Core.mqh'),candidates=len(candidates),
                comparisons=len(expected),all_match=True,counts=counts,
                limits='Reference stop supplied from independent study; broker constraints, changed position occupancy, fills and PnL are not simulated. Native MT5 pending.')
    (ROOT/'VALIDACAO_REPLAY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main(*sys.argv[1:])
