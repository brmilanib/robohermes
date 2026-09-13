"""Append three received R200 exports without inventing individual trade details.

Read-only by default. --apply requires frozen audit JSON. --archive-final accepts a
JSON list of final artifact paths after the result import. All writes preserve
old evidence, use a hash-guarded backup and one explicit transaction.
"""
from pathlib import Path
import argparse,csv,json,sqlite3,sys,shutil,zlib
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'XAU_Entries_Lab_170/tools'))
from catalogo_xau import Catalog,js,sha,timestamp
DB=ROOT/'outputs/laboratorio_xau/Laboratorio_XAU.sqlite'
BASE_SHA='ae2e11cb2d08f13367eb38fab3cabbaab2112514d663ed38c689292a4968bea8'
NAMES=['comparacao(7).csv','meses_comparacao(5).csv','arquivos_comparacao(3).csv','breakeven_comparacao(4).csv']
DATE='2026-09-13'
CORE=['runs','monthly_equity','monthly_results','trades','deals','evaluations','events','research_candle_pivots','research_123_structures','research_breakout_candidates']
EXPECTED={'runs':281,'monthly_equity':4392,'monthly_results':4525,'trades':1131,'deals':2262,'evaluations':115678,'events':1168,'research_candle_pivots':14924,'research_123_structures':6552,'research_breakout_candidates':7530}
META_KEYS=['latest_received_batch','active_planned_batch','latest_received_validation','active_research_focus']


def read_csv(p):
 with p.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f,delimiter=';'))
 assert rows and all(None not in r and None not in r.values() for r in rows),p
 return rows


def connection(path):
 db=sqlite3.connect(path,uri=str(path).startswith('file:'));db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
 cat=Catalog.__new__(Catalog);cat.db=db;cat.path=path
 return db,cat


def strict_put(db,cat,t,row):
 pk=[r['name'] for r in sorted(db.execute('PRAGMA table_info("'+t+'")'),key=lambda r:r['pk']) if r['pk']]
 assert pk and all(k in row for k in pk)
 old=db.execute('SELECT * FROM "'+t+'" WHERE '+' AND '.join('"'+k+'"=?' for k in pk),[row[k] for k in pk]).fetchone()
 if old is None:cat.put(t,row)
 else:assert all(old[k]==v for k,v in row.items()),'Conflicting existing row '+t+' '+str([row[k] for k in pk])


def counts(db):return {t:db.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in CORE}


def preserved(db,allow_status=False,allowed_metadata=()):
 tables=[]
 for (t,) in db.execute("SELECT name FROM baseline.sqlite_master WHERE type='table'"):
  cols=[r[1] for r in db.execute('PRAGMA baseline.table_info("'+t+'")')]
  if allow_status and t in ('planned_cases','planned_batches'):cols.remove('status')
  sql=','.join('"'+k+'"' for k in cols);where='';args=[]
  excluded_meta=META_KEYS if allow_status else list(allowed_metadata)
  if excluded_meta and t=='metadata':where=' WHERE key NOT IN ('+','.join('?' for _ in excluded_meta)+')';args=excluded_meta
  assert db.execute('SELECT '+sql+' FROM baseline."'+t+'"'+where+' EXCEPT SELECT '+sql+' FROM main."'+t+'" LIMIT 1',args).fetchone() is None,'Deleted or changed old row in '+t
  tables.append(t)
 if allow_status:
  for t in ('planned_cases','planned_batches'):
   pred="id NOT LIKE 'R200:%'" if t=='planned_cases' else "id<>'R200'"
   assert db.execute('SELECT id,status FROM baseline.'+t+' WHERE '+pred+' EXCEPT SELECT id,status FROM main.'+t+' LIMIT 1').fetchone() is None
 return tables


def verify_new_blobs(db,old):
 n=0
 for r in db.execute('SELECT * FROM blobs'):
  if r['sha256'] in old:continue
  raw=zlib.decompress(r['content']);assert r['codec']=='zlib' and len(raw)==r['bytes_original'] and sha(raw)==r['sha256'];n+=1
 return n


def get_inputs(require_audit):
 plan=json.loads((ROOT/'Hermes_Pivos_Lab_200/PLANO_RODADA_200.json').read_text())
 assert plan['batch']=='R200' and len(plan['cases'])==3
 assert sha((ROOT/'Hermes_Pivos_Lab_200/Hermes_Pivos_Lab_200.mq5').read_bytes())==plan['source_sha256']
 raw,months,index,be=[read_csv(ROOT/'upload'/n) for n in NAMES]
 assert [len(x) for x in [raw,months,index,be]]==[3,171,3,5]
 hashes={n:sha((ROOT/'upload'/n).read_bytes()) for n in NAMES}
 bycase={int(r['case']):r for r in raw};pmap={p['case']:p for p in plan['cases']}
 assert set(bycase)==set(pmap)=={1,2,3}
 for case,r in bycase.items():
  p=pmap[case];D=lambda k:Decimal(r[k]);mm=sorted([m for m in months if int(m['case'])==case],key=lambda m:m['month_server'])
  assert r['name']==p['name'] and r['signal_tf']==p['timeframe']=='M30'
  assert len(mm)==len({m['month_server'] for m in mm})==57 and mm[0]['month_server']=='2022-01' and mm[-1]['month_server']=='2026-09'
  assert D('valid_run')==1 and D('deposit')==10000 and D('fixed_lot')==D('max_open_lots')==1
  assert D('target_unit_code')==0 and D('nominal_target_R')==D('target_value')==5 and D('matched_control190')==2
  for field in ['BE_confirmed','partial_done','add_fills','reinvestment_enabled','reconcile_difference','monthly_equity_reconcile_difference','monthly_booked_reconcile_difference','unmatched_deals','hp_data_failure_bars']:
   assert D(field)==0,(case,field)
  assert D('cycles_opened')==D('cycles_closed')==D('initial_lots_sum')==D('mt5_trades')
  assert D('cycle_wins')+D('cycle_losses')+D('cycle_zero')==D('cycles_closed')
  for field in ('equity_change','booked_net','cycle_net_by_exit'):assert sum(Decimal(m[field]) for m in mm)==D('profit')
  assert Decimal(mm[0]['equity_start'])==D('deposit') and Decimal(mm[-1]['equity_end'])==D('final_balance')
  for a,b in zip(mm,mm[1:]):
   for end,start in [('equity_end','equity_start'),('balance_end','balance_start')]:assert Decimal(a[end])==Decimal(b[start])
  assert sum(Decimal(m['opened_cycles']) for m in mm)==D('cycles_opened')
  assert sum(Decimal(m['closed_cycles']) for m in mm)==D('cycles_closed')
  assert sum(Decimal(m['equity_change'])<0 for m in mm)==int(D('negative_equity_months'))
 assert all(r['case']=='1' for r in be)
 assert {int(r['case']) for r in index}=={1,2,3}
 auditfile=HERE.parent/'analise/Analise_R200.json';audit=None
 if auditfile.exists():
  audit=json.loads(auditfile.read_text());assert audit['batch']=='R200'
  assert audit['checks'] and all(x['passed'] is True for x in audit['checks'])
  assert audit['native_backtests_executed_by_assistant'] is False and audit['orders_sent_by_assistant'] is False
  # The independent auditor freezes the same four received files.
  ah=audit['source_sha256']
  apaths={v['path']:v['sha256'] for v in ah.values() if isinstance(v,dict) and 'path' in v and 'sha256' in v}
  for name,digest in hashes.items():assert ah.get(name,ah.get('upload/'+name,apaths.get('upload/'+name)))==digest
 if require_audit:assert audit is not None,'Frozen independent audit required'
 return plan,bycase,pmap,months,index,be,hashes,audit


def control_parity(db,bycase,months):
 old=json.loads(db.execute("SELECT raw_metrics_json FROM runs WHERE id='R190:2'").fetchone()[0]);new=bycase[1]
 fields=['profit','deposit','final_balance','mt5_trades','cycles_opened','cycles_closed','cycle_wins','cycle_losses','cycle_profit_factor','equity_dd_relative_percent','equity_dd_max_money','equity_percent_at_max_money_dd','max_stop_risk_money','max_stop_risk_percent','max_open_lots','average_hold_hours','max_hold_hours','first_entry','last_exit','swap','commission_and_fees']
 assert all(old[k]==new[k] for k in fields)
 oldmonths={r['month']:json.loads(r['raw_json']) for r in db.execute("SELECT * FROM monthly_equity WHERE run_id='R190:2'")}
 mfields=[k for k in months[0] if k not in ('pass','case','name')]
 for m in [m for m in months if m['case']=='1']:
  om=oldmonths[m['month_server']]
  for k in mfields:
   if k in ('month_server','first_tick','last_tick'):assert m[k]==om[k],(m['month_server'],k)
   else:assert Decimal(m[k])==Decimal(om[k]),(m['month_server'],k)
 return {'reference':'R190:2','current':'R200:1','equal_aggregate_fields':fields,'equal_monthly_fields':mfields,'months':57,'individual_path_identity_proven':False,'R200_individual_details_received':False,'R190_reference_details_preserved':True}


def preflight():
 inp=get_inputs(False);db,_=connection('file:'+str(DB)+'?mode=ro')
 try:
  assert sha(DB.read_bytes())==BASE_SHA and counts(db)==EXPECTED
  reg=db.execute("SELECT code_sha256,plan_json FROM planned_batches WHERE id='R200'").fetchone()
  assert reg['code_sha256']==inp[0]['source_sha256'] and json.loads(reg['plan_json'])==inp[0]
  assert db.execute("SELECT count(*) FROM runs WHERE batch_id='R200'").fetchone()[0]==0
  return {'dry_run':True,'database_unchanged':True,'counts_before':counts(db),'source_sha256':inp[6],'control_parity':control_parity(db,inp[1],inp[3]),'new_runs':3,'new_monthly_equity_rows':171,'new_individual_trades':0,'new_individual_deals':0,'analysis_present':inp[7] is not None}
 finally:db.close()


def register():
 preflight();plan,bycase,pmap,months,index,be,hashes,audit=get_inputs(True)
 backup=DB.with_name('antes_resultados_R200.sqlite')
 if not backup.exists():shutil.copyfile(DB,backup)
 assert sha(backup.read_bytes())==BASE_SHA
 db,cat=connection(DB);db.execute('ATTACH DATABASE ? AS baseline',(str(backup),));oldblobs={r[0] for r in db.execute('SELECT sha256 FROM blobs')}
 put=lambda t,r:strict_put(db,cat,t,r)
 db.execute('BEGIN IMMEDIATE')
 try:
  sid={n:cat.source(ROOT/'upload'/n,'upload/'+n,'R200_received_MT5_CSV') for n in NAMES}
  ppath=ROOT/'Hermes_Pivos_Lab_200/PLANO_RODADA_200.json';cpath=ROOT/'Hermes_Pivos_Lab_200/Hermes_Pivos_Lab_200.mq5'
  psource=cat.source(ppath,ppath.relative_to(ROOT).as_posix(),'original_plan');csource=cat.source(cpath,cpath.relative_to(ROOT).as_posix(),'R200_planned_source_identity')
  for item in audit.get('benchmark_sources',[]):
   bp=ROOT/item['path'];assert sha(bp.read_bytes())==item['sha256']
   assert db.execute('SELECT 1 FROM blobs WHERE sha256=?',(item['sha256'],)).fetchone() is not None,'Benchmark snapshot must already be archived'
  parity=control_parity(db,bycase,months)
  bm={'received_cases':[1,2,3],'pending_cases':[],'source_sha256':hashes,'source_code_sha256':plan['source_sha256'],'source_code_id':csource,'original_plan_id':psource,'executed_binary_sha256':None,'actual_execution_by':'user_MT5','native_execution_reported_by_user':True,'native_compilation_inspected':False,'source_binary_correspondence_certified':False,'real_tick_percent':None,'modeling_mode_observed':None,'leverage_observed':None,'leverage_requested':100,'native_individual_report_received':False,'individual_execution_paths_received':False,'independent_validation':False,'ranking_scope':'Three same-period M30 cases; control reproduces R190:2 aggregates and 57 monthly rows. Repeated research interval, not untouched validation.','status':'RESULTADOS_RECEBIDOS_3_DE_3_DETALHES_PENDENTES','assistant_orders_sent':False,'assistant_backtests_executed':False,'control_reproduction':parity}
  put('batches',dict(id='R200',ea='Hermes_Pivos_Lab_200',version='2.00',period_start=plan['first_execution_window_start'],period_end=plan['first_execution_window_end_exclusive'],deposit=10000,leverage=None,metadata_json=js(bm)))
  for case,r in sorted(bycase.items()):
   rid='R200:'+str(case);p=pmap[case];f=lambda k:float(r[k]);i=lambda k:int(Decimal(r[k]))
   assert json.loads(db.execute('SELECT parameters_json FROM planned_cases WHERE id=?',(rid,)).fetchone()[0])==p
   params={'planned_parameters':p,'execution_status':'EXECUTADO_USUARIO_CSV_CONCILIADO','source_plan_id':psource,'source_code_sha256':plan['source_sha256'],'executed_binary_sha256':None,'sizing_mode':'EXACT_FIXED_LOT_1.00','target_R':5,'source_control':'R190:2','details_received':False,'observed_exported_parameters':{k:r[k] for k in ['fixed_lot','capital_mode','risk_percent','margin_cap_percent','donchian_mode','matched_control190','fixed_lot_mode','target_unit_code','target_value','fixed_target_distance_price','nominal_target_R','hp_candidates','hp_extra_eligible','hp_base_selected','hp_pivot_selected','hp_pivot_fills']}}
   put('runs',dict(id=rid,batch_id='R200',case_key=str(case),timeframe='M30',model=r['name'],direction='SOMENTE_COMPRAS',target_r=5,target_rule='5R at quoted entry with native tick rounding; original structural stop; no BE, partial, additions or reinvestment',averaging=0,partial_exit=0,fixed_lot=1,profit=f('profit'),trades=i('mt5_trades'),cycles=i('cycles_closed'),wins=i('cycle_wins'),losses=i('cycle_losses'),win_percent=f('cycle_win_percent'),profit_factor=f('cycle_profit_factor'),equity_dd_relative_percent=f('equity_dd_relative_percent'),equity_dd_at_max_money_percent=f('equity_percent_at_max_money_dd'),equity_dd_max_money=f('equity_dd_max_money'),real_tick_percent=None,quality_status='R200_CSV_CONCILIADO_TICKS_BINARIO_DETALHES_PENDENTES',params_json=js(params),raw_metrics_json=js(r)))
   cat.evidence(rid,sid[NAMES[0]],'case='+str(case),'EA_comparison_csv',r)
   put('run_validation',dict(run_id=rid,reported_valid=1,eligible_for_ranking=1,reason='Received user-native export accounting reconciles; eligible for descriptive same-period three-case comparison only. Source/binary correspondence, compiler output, tick quality, modeling mode and individual paths not inspected. No deployment approval or untouched validation.',evaluated_until=timestamp(r['last_evaluation']),source_id=sid[NAMES[0]]))
   put('quality_observations',dict(run_id=rid,source_id=sid[NAMES[0]],real_tick_percent=None,native_label='Tick quality/modeling mode not present in comparison CSV; path quote count is not tick coverage.'))
   put('run_exposure',dict(run_id=rid,sizing_mode='EXACT_FIXED_LOT_1.00',initial_lot=1,maximum_open_lots=f('max_open_lots'),initial_stop_factor=f('initial_stop_factor'),max_stop_risk_money=f('max_stop_risk_money'),max_stop_risk_percent=f('max_stop_risk_percent'),max_margin=f('max_margin'),additions=i('add_fills'),cycles_with_add=i('cycles_with_add'),initial_lots_sum=f('initial_lots_sum'),add_lots_sum=f('add_lots_sum'),source_id=sid[NAMES[0]]))
   put('datasets',dict(id=sha(rid+'|'+sid[NAMES[1]]+'|monthly_equity'),run_id=rid,source_id=sid[NAMES[1]],role='monthly_equity',row_count=57,normalization_note='Server calendar; 56 complete months Jan2022-Aug2026 plus partial Sep2026. Equity mark-to-market is distinct from booked balance and cycle-exit net. Zero inactivity months are not positive months.'))
   if 'benchmarks' in audit:
    put('benchmark_results',dict(id=rid+'|OLIMPO_BENCHMARK_1.0',run_id=rid,method_id='OLIMPO_BENCHMARK_1.0',source_id=sid[NAMES[0]],created=DATE,metrics_json=js(audit['benchmarks'][str(case)])))
   cat.issue('Repeated development window, not untouched validation. Individual R200 cycles/deals/bars/events have not been received; index declares they were exported on the user machine. Existing R190:2 details are preserved without copying them into R200.',rid,sid[NAMES[2]])
  for r in months:
   rid='R200:'+r['case'];row={'run_id':rid,'month':r['month_server'],'source_id':sid[NAMES[1]],'raw_json':js(r)}
   for k in ['equity_start','equity_end','equity_change','balance_start','balance_end','booked_net','cycle_net_by_exit','equity_dd_relative_percent','equity_dd_money']:row[k]=float(r[k])
   for k in ['evaluated_bars','opened_cycles','closed_cycles','partial_exits']:row[k]=int(Decimal(r[k]))
   for k in ['first_tick','last_tick']:row[k]=timestamp(r[k])
   put('monthly_equity',row);put('monthly_results',dict(run_id=rid,month=r['month_server'],closed_trades=row['closed_cycles'],net=row['cycle_net_by_exit'],method='cycle_net_by_exit_server_month_from_MT5_export'))
  for r in index:put('run_detail_exports',dict(run_id='R200:'+r['case'],source_id=sid[NAMES[2]],relative_folder=r['relative_details_folder'],reported_exported=int(Decimal(r['details_exported'])),received=0,raw_json=js(r)))
  for r in be:
   row=dict(run_id='R200:1',threshold_R=float(r['threshold_R']),source_id=sid[NAMES[3]],raw_json=js(r),sum_first_return_quote_R=float(r['sum_first_return_quote_R']))
   for k in ['control_cycles','threshold_reached','returned_to_entry','losers_returned','winners_returned','zero_returned']:row[k]=int(Decimal(r[k]))
   put('breakeven_observations',row)
   cat.evidence('R200:1',sid[NAMES[3]],'threshold_R='+r['threshold_R'],'shadow_observation_not_executed_BE_strategy',r)
  put('equivalent_runs',dict(run_a='R190:2',run_b='R200:1',relationship='Aggregate and all 57 monthly rows reproduce the existing reference. R200 individual exports unreceived; no copied trades/deals and no proven path/binary identity. This repeat is not independent evidence.'))
  comments=[('R200','descriptive_ranking','Reference remains the leader for profit and complete-month consistency. Case 2 adds 38 net trades but loses USD 13,388.55 versus control; case 3 adds 81 net trades but loses USD 35,796.48. These are full-run differences, not standalone profit of pivot trades.'),('R200','monthly_goal','Complete-month negative counts: case 1 = 17, case 2 = 22, case 3 = 18. Case 3 adds a negative partial September 2026, giving 19 observed negative months. None meets the zero-negative-month goal. There are 56 complete months plus partial September, not 60 complete months.'),('R200','entry_attribution','Reported pivot fills: case 2 = 58, case 3 = 111. They exceed net trade increases of 38/81 because changing occupancy can displace original entries. Per-path profit, replacements and rejected opportunities require individual cycles/events/bars.'),('R200','details_scope','Only 4 aggregate/index CSVs were received this round. R190:2 details remain archived; R200:1-3 detail exports all have received = 0, despite index reported_exported = 1.'),('R200','validation_limits','User-reported native CSVs exist; MetaEditor compiler output, EX5 hash, actual source used, modeling mode, tick coverage and brokerage conditions remain unverified. Local planned-source SHA links documented source only.'),('R200:1','BE_scope','Five BE shadow threshold rows exist only for control. No actual BE execution and no BE shadow rows were received for cases 2/3. No new breakeven financial result is inferred.')]
  for subject,category,body in comments:put('research_comments',dict(id=sha(js(['R200_received',subject,category])),created=DATE,author='Codex',subject_type='received_research_result',subject_id=subject,category=category,body=body,source_id=sid[NAMES[0]]))
  put('hypotheses',dict(id='R200_ADDITIONAL_PIVOT_ENTRIES_RECEIVED',status='RESULTADO_DESCRITIVO_SEM_MELHORIA_META_MENSAL',description='Original OR causal LONG 1-2-3 increases frequency but both variations reduce net profit and worsen full-month negative counts versus reference. Case 3 relative DD improves, while absolute maximum DD grows. No new strategy is promoted.',parameters_json=js({'received_cases':[1,2,3],'baseline':'R190:2','goal_passed':False,'independent_validation':False,'negative_complete_months':{'1':17,'2':22,'3':18},'all_observed_negative_months':{'1':17,'2':22,'3':19},'individual_details_pending':[1,2,3]})))
  db.execute("UPDATE planned_batches SET status='RESULTADOS_RECEBIDOS_3_DE_3_DETALHES_PENDENTES' WHERE id='R200'")
  db.execute("UPDATE planned_cases SET status='EXECUTADO_USUARIO_CSV_CONCILIADO' WHERE batch_id='R200'")
  focus=json.loads(db.execute("SELECT value FROM metadata WHERE key='active_research_focus'").fetchone()[0])
  focus.update({'latest_received_batch':'R200','focus_run':'R200:1','current_EA_version':'2.00','EA_version_unchanged':'1.90_REFERENCIA_HISTORICA','descriptive_current_round_profit_winner':'R200:1','preserved_control':'R190:2','ranking_scope':'Three received R200 M30 cases; reference remains the descriptive profit/monthly-consistency leader; W1 is excluded.','individual_details_pending':True,'individual_details_received':False,'R200_details_received':False,'R190_reference_details_received':True,'next_planned_batch':None,'next_planned_version':None,'goal60months_passed':False,'deployment_approved':False,'independent_validation':False,'next_evidence':'Claude independent review and individual R200 cases 2/3 cycles, deals, bars, events, parameters, summary and months for entry-path attribution; do not rerun solely to regenerate existing files.'})
  meta={'latest_received_batch':'R200','active_planned_batch':'R200','latest_received_validation':js({'batch':'R200','received_cases':[1,2,3],'pending_cases':[],'monthly_rows':171,'monthly_equity_reconciled':True,'individual_execution_paths_received':False,'tick_quality_percent':None,'executed_binary_sha256':None,'independent_validation':False,'native_compilation_inspected':False}),'active_research_focus':js(focus)}
  for k,v in meta.items():db.execute('INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v))
  put('release_checks',dict(version='2.00',check_name='received_results_R200_cases1_3',status='CSV_CONCILIADO_DETALHES_PENDENTES',details_json=js({'audit_checks':audit.get('checks'),'source_sha256':hashes,'received_cases':[1,2,3],'individual_details_received':False,'native_compilation_inspected':False,'native_execution_reported_by_user':True,'assistant_native_backtests':False,'source_binary_correspondence_certified':False,'tick_quality_percent':None,'modeling_mode_observed':None,'control_reproduction':parity})))
  put('changes',dict(id='R200_RESULTS_20260913',date=DATE,description='Appended 3 user-reported MT5 runs, 171 monthly equity and cycle-exit rows, 3 detail indexes with unreceived files, and 5 BE control shadows. Preserved 281 earlier runs, 1,131 individual trades, 2,262 deals, all prior research and W1 exclusion. No individual trades copied and no assistant backtest.'))
  artifacts=[Path(__file__)]+[p for p in sorted((HERE.parent/'analise').rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix in ['.py','.json','.csv','.md']]
  source_hashes={}
  for p in artifacts:
   logical=p.relative_to(ROOT).as_posix();source_hashes[logical]=sha(p.read_bytes());s=cat.source(p,logical,'R200_received_result_audit')
   put('research_artifacts',dict(id=sha(logical+'|'+s),release='R200_RESULTS',kind='RECEIVED_RESULT_AUDIT_NOT_NEW_BACKTEST',source_id=s,created=DATE,notes='Audit of received aggregate/monthly results. No new trade records, no new backtest and no automatic promotion.'))
  expected_after=dict(EXPECTED,runs=284,monthly_equity=4563,monthly_results=4696)
  assert counts(db)==expected_after
  assert db.execute("SELECT count(*) FROM trades WHERE run_id LIKE 'R200:%'").fetchone()[0]==0
  assert db.execute("SELECT count(*) FROM deals WHERE run_id LIKE 'R200:%'").fetchone()[0]==0
  assert db.execute("SELECT count(*) FROM run_detail_exports WHERE run_id LIKE 'R200:%' AND received=0").fetchone()[0]==3
  assert db.execute("SELECT received FROM run_detail_exports WHERE run_id='R190:2'").fetchone()[0]==1
  assert db.execute("SELECT count(*) FROM planned_cases WHERE id IN ('R190:5','R190:6') AND status='DESCARTADO_USUARIO_SEM_RELATORIO'").fetchone()[0]==2
  tables=preserved(db,True);blobs=verify_new_blobs(db,oldblobs)
  assert not db.execute('PRAGMA foreign_key_check').fetchall() and db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  db.commit()
 except:db.rollback();db.close();raise
 db.close()
 out={'batch':'R200','status':'RESULTADOS_RECEBIDOS_3_DE_3_DETALHES_PENDENTES','baseline_database_sha256':BASE_SHA,'database_sha256':sha(DB.read_bytes()),'database_bytes':DB.stat().st_size,'counts_before':EXPECTED,'counts_after':expected_after,'old_tables_preserved':tables,'new_blobs_verified':blobs,'source_sha256':hashes,'audit_artifacts_sha256':source_hashes,'registered_cases':[1,2,3],'new_monthly_equity_rows':171,'new_individual_trades':0,'new_individual_deals':0,'individual_details_pending':[1,2,3],'control_reproduction':parity,'source_code_sha256':plan['source_sha256'],'executed_binary_sha256':None,'native_compilation_inspected':False,'native_tick_quality_percent':None,'assistant_backtests_executed':False,'assistant_orders_sent':False,'integrity':'ok','foreign_keys':'ok'}
 (HERE/'Registro_R200_Resultados.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 return out


def archive_final(list_path):
 """Append immutable final documents/code/charts supplied by parent, no run edits."""
 manifest=json.loads((HERE/'Registro_R200_Resultados.json').read_text())
 expected=manifest['database_sha256'];assert sha(DB.read_bytes())==expected
 paths=[Path(p) for p in json.loads(list_path.read_text())]
 paths=[p if p.is_absolute() else ROOT/p for p in paths]
 paths=list(dict.fromkeys(paths+[HERE/'Registro_R200_Resultados.json',HERE/'Indice_Fonte_R200.json',Path(__file__)]))
 assert all(p.is_file() and p.resolve().is_relative_to(ROOT) and p!=DB for p in paths)
 hashes={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in paths}
 backup=DB.with_name('antes_dossie_R200.sqlite')
 if not backup.exists():shutil.copyfile(DB,backup)
 assert sha(backup.read_bytes())==expected
 db,cat=connection(DB);db.execute('ATTACH DATABASE ? AS baseline',(str(backup),));oldcounts=counts(db);oldblobs={r[0] for r in db.execute('SELECT sha256 FROM blobs')}
 db.execute('BEGIN IMMEDIATE')
 try:
  for p in paths:
   logical=p.relative_to(ROOT).as_posix();assert sha(p.read_bytes())==hashes[logical]
   s=cat.source(p,logical,'R200_Claude_review_dossier')
   strict_put(db,cat,'research_artifacts',dict(id=sha('R200_RESULTS_DOSSIER|'+logical+'|'+s),release='R200_RESULTS_DOSSIER',kind='CODE_AUDIT_RESULTS_CHARTS_REVIEW_PACKAGE',source_id=s,created=DATE,notes='User requested a review document for Claude. Source code is unchanged; descriptive result audit, monthly tables and charts are included. No Claude response or new backtest is represented.'))
  strict_put(db,cat,'changes',dict(id='R200_DOSSIER_20260913',date=DATE,description='Archived final R200 code, audit, results, monthly charts and Claude review prompt. Original source and all executed results are unchanged.'))
  oldfocus=json.loads(db.execute("SELECT value FROM metadata WHERE key='active_research_focus'").fetchone()[0])
  focus_comment_id=sha('R200_DOSSIER_METADATA_HISTORY|'+js(oldfocus))
  strict_put(db,cat,'research_comments',dict(id=focus_comment_id,created=DATE,author='Codex',subject_type='metadata_history',subject_id='active_research_focus',category='R200_unambiguous_run_identifiers',body=js({'reason':'Preserve earlier focus verbatim before replacing ambiguous inherited case2 labels by complete run identifiers. Historical case2 fields referred to R190:2, not R200:2. No executed result changes.','previous_metadata':oldfocus}),source_id=None))
  metricmap={}
  for r in db.execute("SELECT id,profit,trades,equity_dd_relative_percent FROM runs WHERE batch_id='R200' ORDER BY id"):
   metricmap[r['id']]={'profit_USD':r['profit'],'cycles':r['trades'],'equity_DD_relative_percent':r['equity_dd_relative_percent'],'negative_complete_months':db.execute("SELECT count(*) FROM monthly_equity WHERE run_id=? AND month<'2026-09' AND equity_change<0",(r['id'],)).fetchone()[0],'negative_observed_months':db.execute("SELECT count(*) FROM monthly_equity WHERE run_id=? AND equity_change<0",(r['id'],)).fetchone()[0]}
  cleanfocus={'metric':'monthly_equity_consistency','latest_received_batch':'R200','current_EA_version':'2.00','focus_run':'R200:1','preserved_control':'R190:2','descriptive_current_round_profit_winner':'R200:1','ranking_scope':'Three received R200 M30 cases on the development interval. Reference remains profit/monthly-consistency leader.','metrics_by_run':metricmap,'complete_months':56,'partial_month':'2026-09','excluded_timeframes':oldfocus.get('excluded_timeframes',['W1']),'weekly_status':oldfocus.get('weekly_status','discarded_by_user'),'details_by_run':{'R190:2':{'received':True,'cycles':261,'deals':522,'bars':55498,'shadow_paths':1305},'R200:1':{'received':False},'R200:2':{'received':False},'R200:3':{'received':False}},'goal60months_passed':False,'deployment_approved':False,'independent_validation':False,'source_binary_correspondence_certified':False,'native_tick_quality_percent':None,'next_planned_batch':None,'next_evidence':oldfocus['next_evidence'],'previous_metadata_comment_id':focus_comment_id}
  db.execute("UPDATE metadata SET value=? WHERE key='active_research_focus'",(js(cleanfocus),))
  assert counts(db)==oldcounts
  tables=preserved(db,False,('active_research_focus',));n=verify_new_blobs(db,oldblobs)
  assert not db.execute('PRAGMA foreign_key_check').fetchall() and db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  db.commit()
 except:db.rollback();db.close();raise
 db.close()
 out={'batch':'R200','stage':'FINAL_DOSSIER_ARCHIVED','baseline_database_sha256':expected,'database_sha256':sha(DB.read_bytes()),'database_bytes':DB.stat().st_size,'counts_unchanged':oldcounts,'files_archived':len(paths),'source_sha256':hashes,'old_tables_preserved':tables,'new_blobs_verified':n,'integrity':'ok','foreign_keys':'ok','no_new_backtest_or_trade_records':True}
 (HERE/'Registro_R200_Final.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 return out

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--archive-final',type=Path)
 args=parser.parse_args();assert not(args.apply and args.archive_final)
 result=archive_final(args.archive_final) if args.archive_final else register() if args.apply else preflight()
 print(json.dumps(result,ensure_ascii=False,indent=2))
