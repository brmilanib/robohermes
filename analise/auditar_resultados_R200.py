#!/usr/bin/env python3
"""Auditoria reprodutível dos CSVs MT5 R200. Não simula nem altera operações.

Moeda: USD para dinheiro do teste, BRL apenas no benchmark convertido.
Valores monetários e identidades de conservação usam Decimal, não float.
O pacote padrão está enraizado no workspace; --root permite reprodução.
"""
from __future__ import annotations
import argparse
import csv
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

D = Decimal
SOURCES = {
    "comparison": "upload/comparacao(7).csv",
    "months": "upload/meses_comparacao(5).csv",
    "folders": "upload/arquivos_comparacao(3).csv",
    "breakeven": "upload/breakeven_comparacao(4).csv",
    "baseline_comparison": "upload/comparacao(6).csv",
    "baseline_months": "upload/meses_comparacao(4).csv",
    "baseline_breakeven": "upload/breakeven_comparacao(3).csv",
    "historical_benchmarks": "outputs/rodada190_resultados/Analise_R190.json",
}
NON_NUMERIC = {"name", "signal_tf", "first_evaluation", "last_evaluation", "first_entry",
               "last_exit", "first_ready", "last_error_time", "month_server", "first_tick",
               "last_tick", "relative_details_folder"}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read_csv(p):
    with p.open(encoding="utf-8-sig", newline="") as f:
        rr = csv.DictReader(f, delimiter=";")
        if len(rr.fieldnames) != len(set(rr.fieldnames)): raise ValueError(f"duplicate columns {p}")
        rows = list(rr)
    if any(None in x or None in x.values() for x in rows): raise ValueError(f"ragged rows {p}")
    return rows
def num(r, k): return D(r[k])
def ints(r, k):
    v = num(r, k)
    assert v == int(v), (k, v)
    return int(v)
def sums(rows, k): return sum((num(x, k) for x in rows), D(0))
def converted(r):
    return {k: v if k in NON_NUMERIC else (int(D(v)) if k in ("case", "pass") else float(D(v))) for k, v in r.items()}
def sign(v): return "positive" if v > 0 else "negative" if v < 0 else "zero"
def seqmax(values, pred):
    current = best = 0
    for v in values:
        current = current + 1 if pred(v) else 0
        best = max(best, current)
    return best
def money(v): return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def pct(v): return f"{float(v):.2f}".replace(".", ",") + "%"
def write_csv(p, rows):
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader(); w.writerows(rows)

def main(root, out):
    out.mkdir(parents=True, exist_ok=True)
    raw = {k: read_csv(root / p) for k, p in SOURCES.items() if p.endswith(".csv")}
    benchmark = json.loads((root / SOURCES["historical_benchmarks"]).read_text())
    bench = benchmark["benchmarks"]["2"]
    bench_y = {x["year"]: x for x in bench["years"]}
    checks = []
    def check(label, condition, details=None):
        checks.append({"check": label, "passed": bool(condition), "details": details})
        if not condition: raise AssertionError((label, details))

    rr = {x["case"]: x for x in raw["comparison"]}
    folders = {x["case"]: x for x in raw["folders"]}
    check("three_unique_cases", len(rr) == len(raw["comparison"]) == 3 and set(rr) == {"1", "2", "3"})
    check("three_folder_records", len(folders) == len(raw["folders"]) == 3 and set(folders) == set(rr))
    expected = [f"{y}-{m:02}" for y in range(2022, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]
    months = {c: sorted([x for x in raw["months"] if x["case"] == c], key=lambda x: x["month_server"]) for c in rr}
    check("171_month_rows", len(raw["months"]) == 171)
    monthly_rows, annual_rows, cases = [], [], {}
    benchmark_sources = []
    for s in benchmark["benchmark_sources"]:
        p = root / s["path"]
        check("benchmark_source_sha256:" + s["path"], p.exists() and sha(p) == s["sha256"])
        benchmark_sources.append(s)

    def bench_calc(initial, final, b):
        ret = final / initial - 1
        brl = final * D(str(b["fx_end"])) / (initial * D(str(b["fx_start"]))) - 1
        return {"usd_return_percent": float(ret * 100), "brl_return_percent": float(brl * 100),
                "selic_return_brl_percent": b["selic_return_brl_pct"],
                "excess_vs_selic_brl_pp": float(brl * 100) - b["selic_return_brl_pct"],
                "fx_start": b["fx_start"], "fx_end": b["fx_end"],
                "fx_start_date": b["fx_start_date"], "fx_end_date": b["fx_end_date"],
                "start": b["start"], "end_exclusive": b["end_exclusive"],
                "selic_observations": b["selic_observations"]}

    for c, r in rr.items():
        mm = months[c]; full = mm[:-1]
        check(f"case{c}:months_sequence", [x["month_server"] for x in mm] == expected)
        for x in mm:
            label = f"case{c}:{x['month_server']}"
            check(label + ":identity", x["name"] == r["name"] and x["pass"] == r["pass"])
            check(label + ":equity_delta", num(x,"equity_end") - num(x,"equity_start") == num(x,"equity_change"))
            check(label + ":balance_delta", num(x,"balance_end") - num(x,"balance_start") == num(x,"booked_net"))
            check(label + ":float_reconcile", num(x,"equity_change") - num(x,"booked_net") ==
                  (num(x,"equity_end") - num(x,"balance_end")) - (num(x,"equity_start") - num(x,"balance_start")))
            check(label + ":month_time", x["first_tick"][:7].replace(".","-") == x["month_server"] and
                  x["last_tick"][:7].replace(".","-") == x["month_server"])
        for a, b in zip(mm, mm[1:]):
            check(f"case{c}:continuity:{b['month_server']}", num(a,"equity_end") == num(b,"equity_start") and
                  num(a,"balance_end") == num(b,"balance_start"))
        for k in ("equity_change", "booked_net", "cycle_net_by_exit"):
            check(f"case{c}:total:{k}", sums(mm,k) == num(r,"profit"), str(sums(mm,k)))
        for mk, rk in [("evaluated_bars","bars_seen"),("signals","signals_before_filters"),
                       ("opened_cycles","cycles_opened"),("closed_cycles","cycles_closed"),
                       ("BE_confirmed","BE_confirmed"),("partial_exits","partial_done")]:
            check(f"case{c}:sum:{mk}", sums(mm,mk) == num(r,rk), str(sums(mm,mk)))
        check(f"case{c}:initial_final", num(mm[0],"equity_start") == num(r,"deposit") == D(10000) and
              num(mm[-1],"equity_end") == num(r,"final_balance") == num(r,"deposit") + num(r,"profit"))
        check(f"case{c}:closed_cycles_and_outcomes", num(r,"cycles_opened") == num(r,"cycles_closed") == num(r,"mt5_trades") ==
              num(r,"cycle_wins") + num(r,"cycle_losses") + num(r,"cycle_zero"))
        check(f"case{c}:win_rate", abs(num(r,"cycle_win_percent") - num(r,"cycle_wins") / num(r,"cycles_closed") * 100) <= D("0.00000001"))
        check(f"case{c}:reported_MT5_cycle_factor", num(r,"mt5_profit_factor") == num(r,"cycle_profit_factor"))
        check(f"case{c}:gates_sum", sum((D(v) for k,v in r.items() if k.startswith("G_")),D(0)) == num(r,"bars_seen"))
        check(f"case{c}:execution_counts", num(r,"G_FILLED") == num(r,"cycles_opened") and
              num(r,"hp_base_selected") + num(r,"hp_pivot_selected") == num(r,"signals_before_filters"))
        for k in ("valid_run", "fixed_lot", "max_open_lots", "fixed_lot_mode", "detail_export_enabled"):
            check(f"case{c}:{k}", num(r,k) == 1)
        for k in ("reconcile_difference","monthly_equity_reconcile_difference","monthly_booked_reconcile_difference",
                  "unmatched_deals","error_code","G_NO_DATA","hp_data_failure_bars","hp_historical_catchup_candidates_discarded",
                  "add_fills","BE_confirmed","partial_done","reinvestment_enabled","G_HALTED"):
            check(f"case{c}:zero:{k}", num(r,k) == 0)
        check(f"case{c}:monthly_max_DD", abs(max(num(x,"equity_dd_relative_percent") for x in mm) - num(r,"maximum_monthly_DD_percent")) <= D("0.00000001"))
        check(f"case{c}:folder", folders[c]["name"] == r["name"] and folders[c]["pass"] == r["pass"] and D(folders[c]["details_exported"]) == 1)
        check(f"case{c}:M30_5R", r["signal_tf"] == "M30" and num(r,"nominal_target_R") == 5)
        case = converted(r)
        for label, subset in [("observed", mm), ("complete",full)]:
            for metric in ("equity_change", "booked_net"):
                counts = {s: sum(sign(num(x,metric)) == s for x in subset) for s in ("positive","negative","zero")}
                case[f"{label}_{metric}_months"] = counts
                if label == "observed":
                    kind = "equity" if metric == "equity_change" else "booked"
                    for s in ("positive", "negative"):
                        check(f"case{c}:reported_{s}_{kind}", counts[s] == ints(r,f"{s}_{kind}_months"))
        case["complete_months"] = len(full)
        case["partial_month"] = converted(mm[-1])
        case["negative_complete_months"] = [x["month_server"] for x in full if num(x,"equity_change") < 0]
        case["negative_observed_months"] = [x["month_server"] for x in mm if num(x,"equity_change") < 0]
        case["max_consecutive_negative_complete_months"] = seqmax(full,lambda x: num(x,"equity_change") < 0)
        case["no_entry_observed_months"] = [x["month_server"] for x in mm if num(x,"opened_cycles") == 0]
        case["average_net_per_cycle"] = float(num(r,"profit") / num(r,"cycles_closed"))
        case["gross_before_swap_fees"] = float(num(r,"profit") - num(r,"swap") - num(r,"commission_and_fees"))
        case["profit_delta_vs_reference"] = float(num(r,"profit") - num(rr["1"],"profit"))
        case["profit_change_vs_reference_percent"] = float((num(r,"profit") / num(rr["1"],"profit")-1)*100)
        case["net_trade_increase_vs_reference"] = ints(r,"cycles_closed") - ints(rr["1"],"cycles_closed")
        case["non_pivot_fills"] = ints(r,"cycles_closed") - ints(r,"hp_pivot_fills")
        case["non_pivot_fill_change_vs_reference"] = case["non_pivot_fills"] - ints(rr["1"],"cycles_closed")
        case["detail_folder"] = folders[c]["relative_details_folder"]
        case["trade_details_received_for_this_run"] = False
        case["benchmark_total"] = bench_calc(num(r,"deposit"),num(r,"final_balance"),bench["total"])
        cases[c] = case
        for x in mm:
            y = converted(x)
            y["partial_month"] = x["month_server"] == "2026-09"
            y["return_equity_percent"] = float(num(x,"equity_change") / num(x,"equity_start") * 100)
            y["floating_start"] = float(num(x,"equity_start") - num(x,"balance_start"))
            y["floating_end"] = float(num(x,"equity_end") - num(x,"balance_end"))
            y["sign_equity"] = sign(num(x,"equity_change"))
            y["sign_booked"] = sign(num(x,"booked_net"))
            monthly_rows.append(y)
        for year in range(2022,2027):
            ym = [x for x in mm if x["month_server"].startswith(str(year))]
            annual = {"case":int(c),"name":r["name"],"year":year,"partial_year":year==2026,
                "months_observed":len(ym), "equity_start":float(num(ym[0],"equity_start")),
                "equity_end":float(num(ym[-1],"equity_end")),"profit_equity_usd":float(sums(ym,"equity_change")),
                "profit_booked_usd":float(sums(ym,"booked_net")),"opened_cycles":int(sums(ym,"opened_cycles")),
                "closed_cycles":int(sums(ym,"closed_cycles")),
                "positive_complete_months":sum(num(x,"equity_change")>0 for x in ym if x["month_server"]!="2026-09"),
                "negative_complete_months":sum(num(x,"equity_change")<0 for x in ym if x["month_server"]!="2026-09"),
                "zero_complete_months":sum(num(x,"equity_change")==0 for x in ym if x["month_server"]!="2026-09"),
                "negative_observed_months":sum(num(x,"equity_change")<0 for x in ym)}
            annual.update(bench_calc(num(ym[0],"equity_start"),num(ym[-1],"equity_end"),bench_y[year]))
            annual_rows.append(annual)

    old = next(x for x in raw["baseline_comparison"] if x["case"] == "2")
    allowed = {"pass","case","name","shadow_original_control","matched_control190"}
    common = set(old) & set(rr["1"])
    differences = [{"field":k,"R190_2":old[k],"R200_1":rr["1"][k]} for k in sorted(common) if old[k] != rr["1"][k]]
    check("baseline_aggregate_parity", all(x["field"] in allowed for x in differences))
    oldmonths = sorted([x for x in raw["baseline_months"] if x["case"] == "2"],key=lambda x:x["month_server"])
    check("baseline_57_months",len(oldmonths)==57)
    monthcompared = 0
    for a,b in zip(oldmonths,months["1"]):
        for k in set(a)&set(b)-{"pass","case","name"}:
            check(f"baseline_month:{a['month_server']}:{k}",a[k]==b[k]); monthcompared+=1
    bb = raw["breakeven"]
    check("BE_shadow_reference_only",len(bb)==5 and {x["case"] for x in bb}=={"1"})
    for b in bb:
        check("BE_partition:"+b["threshold_R"],num(b,"returned_to_entry")==num(b,"losers_returned")+num(b,"winners_returned")+num(b,"zero_returned"))
        check("BE_monotonic_bounds:"+b["threshold_R"],num(b,"returned_to_entry")<=num(b,"threshold_reached")<=num(b,"control_cycles")==261)

    comparison = []
    for i, month in enumerate(expected):
        rec = {"month":month,"partial_month":month=="2026-09"}
        base = num(months["1"][i],"equity_change")
        for c in rr:
            x=months[c][i]
            rec[f"case{c}_equity_usd"]=float(num(x,"equity_change"))
            rec[f"case{c}_booked_usd"]=float(num(x,"booked_net"))
            rec[f"case{c}_return_percent"]=float(num(x,"equity_change")/num(x,"equity_start")*100)
            rec[f"case{c}_equity_end"]=float(num(x,"equity_end"))
            rec[f"case{c}_opened_cycles"]=ints(x,"opened_cycles")
            rec[f"case{c}_delta_vs_reference_usd"]=float(num(x,"equity_change")-base)
        comparison.append(rec)
    transitions={}
    transition_rows=[]
    for c in ("2","3"):
        types={"negative_to_positive":[],"negative_to_zero":[],"negative_still_negative_improved":[],
            "negative_still_negative_unchanged":[],"negative_still_negative_worsened":[],
            "positive_to_negative":[],"zero_to_negative":[],"zero_to_positive":[]}
        for i,m in enumerate(expected[:-1]):
            a=num(months["1"][i],"equity_change");b=num(months[c][i],"equity_change")
            key=None
            if a<0:
                key="negative_to_positive" if b>0 else "negative_to_zero" if b==0 else "negative_still_negative_"+("improved" if b>a else "worsened" if b<a else "unchanged")
            elif b<0: key="positive_to_negative" if a>0 else "zero_to_negative"
            elif a==0 and b>0:key="zero_to_positive"
            if key:
                rec={"case":int(c),"month":m,"transition":key,"baseline_equity_usd":float(a),"variant_equity_usd":float(b),"delta_usd":float(b-a)}
                types[key].append(rec);transition_rows.append(rec)
        transitions[c]={"counts":{k:len(v) for k,v in types.items()},"rows":types,
            "baseline_negative_profit_sum":float(sum((num(months["1"][i],"equity_change") for i in range(56) if num(months["1"][i],"equity_change")<0),D(0))),
            "variant_same_17_month_profit_sum":float(sum((num(months[c][i],"equity_change") for i in range(56) if num(months["1"][i],"equity_change")<0),D(0)))}

    # Compatibility view for the existing OLIMPO_BENCHMARK_1.0 registry.
    benchmark_cases={}
    for c in rr:
        def legacy_benchmark(b, initial, final):
            copied={k:b[k] for k in ("start","end_exclusive","fx_start","fx_end","fx_start_date","fx_end_date","selic_observations")}
            days=(date.fromisoformat(b["end_exclusive"])-date.fromisoformat(b["start"])).days
            usd_factor=final/initial
            brl_factor=usd_factor*b["fx_end"]/b["fx_start"]
            copied.update({"calendar_days":days,"initial_usd":initial,"final_usd":final,"profit_usd":round(final-initial,2),
                "usd_return_pct":(usd_factor-1)*100,"brl_return_pct":(brl_factor-1)*100,
                "selic_return_brl_pct":b["selic_return_brl_percent"],
                "excess_brl_pp":(brl_factor-1)*100-b["selic_return_brl_percent"],
                "fx_change_pct":(b["fx_end"]/b["fx_start"]-1)*100,"benchmark_status":"CALCULATED_SAME_CURRENCY",
                "usd_CAGR_pct":(usd_factor**(365.25/days)-1)*100,
                "brl_CAGR_pct":(brl_factor**(365.25/days)-1)*100,
                "selic_CAGR_brl_pct":((1+b["selic_return_brl_percent"]/100)**(365.25/days)-1)*100,
                "notes":["CAGR calculado para compatibilidade; relatórios anuais mostram retorno realizado sem anualizar 2026."]})
            copied["excess_CAGR_brl_pp"]=copied["brl_CAGR_pct"]-copied["selic_CAGR_brl_pct"]
            return copied
        total=legacy_benchmark(cases[c]["benchmark_total"],cases[c]["deposit"],cases[c]["final_balance"])
        years=[]
        for a in annual_rows:
            if a["case"] != int(c):continue
            y=legacy_benchmark(a,a["equity_start"],a["equity_end"])
            y.update({"year":a["year"],"partial_year":a["partial_year"],"negative_months":a["negative_observed_months"],
                      "negative_complete_months":a["negative_complete_months"],"opened_cycles":a["opened_cycles"]})
            years.append(y)
        benchmark_cases[c]={"total":total,"years":years}

    result={"schema_version":"1.0","batch":"R200","version":"2.00","audit_status":"PASS_RECONCILIATION_NOT_PROFIT_CERTIFICATION",
        "requested_start":"2022-01-01","requested_end_exclusive":"2026-09-12","observed_last_tick":"2026-09-11 20:57:59",
        "complete_calendar_months":56,"partial_month":"2026-09","cases":cases,"monthly_rows":monthly_rows,
        "annual_rows":annual_rows,"monthly_comparison":comparison,"transitions":transitions,
        "baseline_parity":{"baseline":"R190:2","current":"R200:1","common_fields":len(common),
            "matching_fields":len(common)-len(differences),"permitted_identity_differences":differences,
            "monthly_fields_compared":monthcompared,"all_economic_and_execution_fields_match":True},
        "breakeven_shadow":[converted(x) for x in bb],"detail_folders":raw["folders"],
        "checks":checks,"checks_passed":len(checks),
        "source_sha256":{k:{"path":p,"sha256":sha(root/p)} for k,p in SOURCES.items()},
        "benchmark_sources":benchmark_sources,"benchmarks":benchmark_cases,
        "formulas":{"month_equity":"equity_end-equity_start = booked_net+(floating_end-floating_start)",
            "year_return_usd":"(equity_end/equity_start-1)*100; Jan1 opening equity each year; 2026 partial unannualized",
            "brl_return":"((equity_end_usd*FX_end)/(equity_start_usd*FX_start)-1)*100",
            "selic_return":"100*(product(1+daily_SGS11_percent/100)-1), using archived annual inputs",
            "excess_brl_pp":"brl_return_percent-selic_return_brl_percent"},
        "limits":["Não houve execução de backtest nem envio de ordens pelo assistente.",
            "Agregados não provam quais trades de BASE foram substituídos nem o lucro isolado dos pivôs; faltam cycles/deals/events/bars dos casos 2 e 3 desta rodada.",
            "Pasta declarada como exportada no CSV não prova que seus arquivos individuais foram recebidos.",
            "Qualidade de ticks reais, relatório nativo completo, versão do binário EX5, alavancagem e latência não são comprovados por estes quatro CSVs.",
            "DD relativo máximo e DD monetário máximo podem ocorrer em episódios diferentes; não usar a percentagem do maior DD monetário como DD relativo máximo.",
            "Retornos em BRL são comparação hipotética por FX SGS1 nas datas, antes de impostos, remessas e spread cambial. Selic não tem a mesma exposição/risco do robô.",
            "Toda a amostra 2022-2026 já foi usada no desenvolvimento; não é um teste fora da amostra.",
            "Há 56 meses completos e setembro parcial, não 60 meses completos. Nenhum caso cumpre zero meses negativos."],
        "native_backtests_executed_by_assistant":False,"orders_sent_by_assistant":False,
        "goal_zero_negative_months_passed":False,"new_strategy_rules_tested_by_assistant":False}
    (out/"Analise_R200.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    write_csv(out/"Meses_R200.csv",monthly_rows)
    write_csv(out/"Anos_R200.csv",annual_rows)
    write_csv(out/"Comparacao_Mensal_R200.csv",comparison)
    write_csv(out/"Transicoes_Mensais_R200.csv",transition_rows)
    summary=[{k:cases[c][k] for k in ("case","name","profit","final_balance","cycles_closed","cycle_win_percent","cycle_profit_factor",
        "equity_dd_relative_percent","equity_dd_max_money","equity_percent_at_max_money_dd","swap","hp_pivot_fills","net_trade_increase_vs_reference","profit_delta_vs_reference")}
        | {"negative_complete_months":cases[c]["complete_equity_change_months"]["negative"],
           "negative_observed_months":cases[c]["observed_equity_change_months"]["negative"]} for c in rr]
    write_csv(out/"Resumo_Casos_R200.csv",summary)

    report = [
        "# Auditoria dos resultados Hermes Pivôs 2.00 — R200", "",
        "A Referência continua superior em lucro e consistência mensal. Os dois modelos de pivô aumentaram a atividade, mas reduziram o lucro e aumentaram a contagem de meses completos negativos. A variante Início teve drawdown relativo menor; seu drawdown monetário máximo foi maior. Isso não equivale a uma melhora geral.", "",
        "## Base examinada", "",
        f"Quatro arquivos recebidos, três casos e 171 registros mensais. Período solicitado: 01/01/2022 até 12/09/2026 exclusivo. Último tick mensal: 11/09/2026 20:57:59, horário do servidor. São 56 meses completos e setembro de 2026 parcial. Os {len(checks)} controles de reconciliação passaram. Não executamos novo backtest.", "",
        "|Caso|Lucro líquido USD|Trades|Acerto|PF|DD relativo|Meses negativos completos|Setembro parcial USD|",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for c, r in cases.items():
        report.append(f"|{c} — {r['name']}|{money(r['profit'])}|{int(r['cycles_closed'])}|{pct(r['cycle_win_percent'])}|{r['cycle_profit_factor']:.3f}|{pct(r['equity_dd_relative_percent'])}|{r['complete_equity_change_months']['negative']}|{money(r['partial_month']['equity_change'])}|")
    report += ["",
        "Nos 56 meses completos, o caso 1 teve 37 positivos, 17 negativos e 2 zerados; o caso 2, 34 positivos e 22 negativos; o caso 3, 38 positivos e 18 negativos. A tela do MT5 mostra 19 negativos no caso 3 porque inclui setembro parcial, com prejuízo de US$ 7.502,29. Os casos 1 e 2 não operaram em setembro e marcaram zero.", "",
        "## Controle reproduzido e diagnósticos", "",
        f"R200:1 reproduz R190:2: {len(common)-len(differences)} campos comuns iguais, sem divergência econômica ou de execução. As cinco diferenças são passe, número/nome do caso e dois identificadores de controle. Todos os {monthcompared} campos mensais comparáveis também coincidem.", "",
        "Nos três casos, a soma dos resultados mensais de equity, saldo realizado e ciclos por saída coincide com o lucro total. Equity e balance são contínuos entre meses; ciclos abertos = fechados e fechamentos = vencedores + perdedores. Nenhum saldo final carrega posição aberta. Os gates somam 55.498 avaliações por caso.", "",
        "Não houve falha de dados do pivô, G_NO_DATA ou interrupção fatal. Houve 8, 11 e 13 requisições rejeitadas nos casos 1, 2 e 3. O último código de retorno é 10018, que significa mercado fechado. Sem os eventos individuais desta rodada, não é possível afirmar que todas as rejeições tiveram esse motivo. Contador de erro fatal zerado não significa ausência de rejeições de ordens. [Documentação MQL5](https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes).", "",
        "## Pivôs e novas operações", "",
        "|Caso|Execuções por pivô|Execuções pelo gatilho base|Variação líquida de trades|Variação do lucro USD|Variação do lucro %|",
        "|---|---:|---:|---:|---:|---:|"]
    for c in ("2", "3"):
        r=cases[c]
        report.append(f"|{c}|{int(r['hp_pivot_fills'])}|{r['non_pivot_fills']}|+{r['net_trade_increase_vs_reference']}|{money(r['profit_delta_vs_reference'])}|{pct(r['profit_change_vs_reference_percent'])}|")
    report += ["",
        "58 e 111 são execuções identificadas como pivô; os aumentos líquidos foram 38 e 81. As execuções pelo gatilho base caíram de 261 para 241 e 231. Com apenas uma posição por vez, operações extras alteram a disponibilidade para sinais seguintes. Não atribuímos a diferença de lucro apenas aos pivôs, nem sabemos quais operações-base foram substituídas sem os arquivos individuais.", "",
        "Cada perfil observou 761 candidatos geométricos. Nos casos 2 e 3, hp_extra_eligible = 234/320 e hp_extra_position_blocks = 87/100. Esses contadores têm escopos diferentes: elegibilidade pode coincidir com o gatilho original, seleção precede filtros de execução, e bloqueio por posição não representa uma operação comprovadamente lucrativa perdida.", "",
        "## Os 17 meses negativos da referência", ""]
    translated = {"negative_to_positive":"Negativos que ficaram positivos", "positive_to_negative":"Positivos que ficaram negativos", "zero_to_negative":"Zerados que ficaram negativos"}
    for c in ("2", "3"):
        t=transitions[c]; q=t["counts"]
        report += [f"**Caso {c}:** tornou positivos {q['negative_to_positive']} dos 17 meses; melhorou, mas manteve negativos, {q['negative_still_negative_improved']}; agravou {q['negative_still_negative_worsened']}; deixou iguais {q['negative_still_negative_unchanged']}. Em contrapartida, {q['positive_to_negative']} meses antes positivos ficaram negativos e {q['zero_to_negative']} meses antes zerados ficaram negativos. Esta comparação considera somente os mesmos 56 meses completos.", ""]
        for key in translated:
            if t["rows"][key]:
                report.append("- " + translated[key] + ": " + ", ".join(x["month"] for x in t["rows"][key]) + ".")
        report.append("")
    report += [
        "Atividade extra não resolveu a consistência: o total de meses completos negativos passou de 17 para 22 e 18. Escolher retrospectivamente o perfil vencedor de cada mês não cria uma regra que pudesse ser executada antes de conhecer os resultados.", "",
        "## Resultado anual e Selic", "",
        "Retorno anual calculado sobre a equity no início de cada ano, sem aportes. 2026 é acumulado até 11/09, sem anualização. O lote continuou fixo em 1,00: calcular retorno sobre capital que variou não significa reinvestimento automático no lote.", "",
        "|Ano|Caso|Lucro USD|Retorno USD|Retorno convertido BRL|Selic BRL|Excesso BRL p.p.|",
        "|---|---|---:|---:|---:|---:|---:|"]
    for a in sorted(annual_rows,key=lambda a:(a['year'],a['case'])):
        report.append(f"|{a['year']}{'*' if a['partial_year'] else ''}|{a['case']}|{money(a['profit_equity_usd'])}|{pct(a['usd_return_percent'])}|{pct(a['brl_return_percent'])}|{pct(a['selic_return_brl_percent'])}|{money(a['excess_vs_selic_brl_pp'])}|")
    report += ["",
        "*2026 parcial. Retorno em BRL = (equity final em USD × câmbio final) / (equity inicial em USD × câmbio inicial) − 1. Selic acumulada = produto de (1 + taxa diária SGS 11 / 100) − 1. Foram reutilizados snapshots históricos com hashes verificados das séries SGS 11 (Selic diária) e SGS 1 (câmbio), das mesmas datas dos benchmarks anteriores. Impostos, remessas e spread cambial não estão incluídos; a Selic não tem o mesmo risco do robô. [Banco Central — SGS](https://www3.bcb.gov.br/sgspub/).", "",
        "## Drawdown e custos", "",
        "|Caso|DD relativo máximo|DD monetário máximo USD|Percentual no episódio do DD monetário|Swap total USD|",
        "|---|---:|---:|---:|---:|"]
    for c,r in cases.items():
        report.append(f"|{c}|{pct(r['equity_dd_relative_percent'])}|{money(r['equity_dd_max_money'])}|{pct(r['equity_percent_at_max_money_dd'])}|{money(r['swap'])}|")
    report += ["",
        "O maior percentual de queda e a maior queda em dinheiro podem ocorrer em momentos diferentes. O caso 3 reduziu DD relativo de 42,76% para 36,85%, mas aumentou DD monetário de US$ 29.778,30 para US$ 55.534,40. O custo de swap aumentou US$ 1.872,15 e US$ 3.316,38 nos casos 2 e 3. Comissões e taxas foram reportadas como zero; isso não comprova custo futuro igual a zero.", "",
        "## Equity mensal não é apenas trade fechado", "",
        "Resultado mensal = realizado + (flutuante final − flutuante inicial). Por exemplo, abril de 2026 da Referência registra +US$ 17.500,19 realizados, mas −US$ 1.378,72 na equity, pois parte do ganho fechado já estava computada em março. São bases contábeis diferentes. A tabela mensal preserva ambas e o resultado flutuante de cada fronteira.", "",
        "## Alcance da auditoria e material para Claude", "",
        "A reconciliação valida a coerência interna dos CSVs; não certifica ausência de todos os bugs nem robustez futura. Os quatro arquivos não trazem o hash do EX5 executado, relatório nativo com qualidade/modelagem de ticks, latência e alavancagem, nem cycles/deals/bars/events dos casos 2 e 3. O código do dossiê é a fonte distribuída, não prova criptográfica do binário que rodou.", "",
        "O arquivo de breakeven tem cinco linhas de observação da Referência apenas. Elas mostram retornos ao ponto de entrada após 1R, 1,5R, 2R, 2,5R e 3R; não demonstram lucros de versões BE executadas, nem resultados BE dos casos 2 e 3. Nenhum perfil desta rodada ativou BE, parcial, médio ou pirâmide.", "",
        "A amostra já foi reutilizada no desenvolvimento; não é fora da amostra. Antes de novos filtros, é necessário atribuir os resultados dos pivôs, das operações-base substituídas e dos meses afetados. Regras propostas devem usar somente informação disponível antes da entrada e passar por validação temporal separada. Nenhum caso cumpre a meta de 60 meses completos sem prejuízo.", "",
        "Arquivos derivados: Analise_R200.json reúne dados, critérios e fontes; Meses_R200.csv, Anos_R200.csv, Comparacao_Mensal_R200.csv e Transicoes_Mensais_R200.csv permitem revisão independente. O script não acessa nem altera banco ou robô."]
    (out/"Relatorio_Resultados_R200.md").write_text("\n".join(report)+"\n")
    print(json.dumps({"checks_passed":len(checks),"cases":summary,"output":str(out)},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[3]);p.add_argument("--out",type=Path)
    args=p.parse_args();main(args.root,args.out or args.root/"outputs/rodada200_resultados/analise")
