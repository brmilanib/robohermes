bool IsTimeStat(const int i)
 { return i==S_FIRST_EVAL || i==S_LAST_EVAL || i==S_FIRST_ENTRY || i==S_LAST_EXIT || i==S_FIRST_READY || i==S_LAST_ERROR_TIME; }
int StatNames(string &names[])
 {
  return StringSplit("valid_run;profit;deposit;final_balance;mt5_trades;mt5_profit_factor;equity_dd_relative_percent;equity_dd_max_money;equity_percent_at_max_money_dd;cycles_opened;cycles_closed;cycle_wins;cycle_losses;cycle_zero;cycle_win_percent;cycle_profit_factor;cycle_net;average_net_R_initial;max_consecutive_losses;average_hold_hours;max_hold_hours;swap;commission_and_fees;max_open_lots;max_stop_risk_money;max_stop_risk_percent;max_margin;first_evaluation;last_evaluation;first_entry;last_exit;bars_seen;signals_before_filters;first_ready;origin15_cycles;origin14_cycles;origin15_net;origin14_net;BE_armed;BE_confirmed;BE_stop_exits;partial_armed;partial_done;partial_deferrals;BE_deferrals;session_deferrals;stop_freeze_deferrals;BE_requests;partial_requests;ambiguous_partials;error_code;last_retcode;last_error_time;reconcile_difference;monthly_equity_reconcile_difference;monthly_booked_reconcile_difference;unmatched_deals;months_observed;positive_equity_months;negative_equity_months;positive_booked_months;negative_booked_months;mean_MFE_R;mean_winner_MFE_R;mean_loser_MFE_R;mean_MAE_R;path_quote_observations;shadow_original_control;fixed_lot;BE_trigger_R;origin_mode;protect14;BE_unfulfilled;partial_unfulfilled;empty_paths;maximum_monthly_DD_percent;add_fills;cycles_with_add;net_cycles_with_add;add_rejections;risk_blocks;initial_stop_factor;reinvestment_enabled;management_arm;initial_lots_sum;add_lots_sum;pivot_buy_candidates;pivot_sell_candidates;entry_policy;reinvestment_fraction;reinvestment_lot_cap;capital_mode;matched_control190;detail_export_enabled;exported_bar_rows;risk_percent;margin_cap_percent;donchian_mode;source_control180;fixed_lot_mode;target_unit_code;target_value;fixed_target_distance_price;nominal_target_R;target_rejections;target_cap_adjustments;target_cap_failures;fixed_volume_rejections;hp_candidates;hp_extra_eligible;hp_base_selected;hp_pivot_selected;hp_pivot_fills;hp_data_failure_bars;hp_extra_position_blocks;hp_historical_catchup_candidates_discarded",';',names);
 }
string MonthHeader()
 { return "month_server;equity_start;equity_end;equity_change;balance_start;balance_end;booked_net;cycle_net_by_exit;equity_dd_relative_percent;equity_dd_money;evaluated_bars;signals;opened_cycles;closed_cycles;BE_confirmed;partial_exits;first_tick;last_tick"; }
void MonthValues(const int i,double &v[])
 {
  v[0]=months[i].key; v[1]=months[i].path.startEquity; v[2]=months[i].path.endEquity; v[3]=v[2]-v[1];
  v[4]=months[i].path.startBalance; v[5]=months[i].path.endBalance; v[6]=months[i].bookedNet; v[7]=months[i].cycleNet;
  v[8]=months[i].path.maxRelativeDD; v[9]=months[i].path.maxMoneyDD; v[10]=months[i].bars; v[11]=months[i].signals;
  v[12]=months[i].opened; v[13]=months[i].closed; v[14]=months[i].bes; v[15]=months[i].partials;
  v[16]=(double)months[i].firstTick; v[17]=(double)months[i].lastTick;
 }
string MonthCSV(const double &data[],const int start)
 {
  string s=""; for(int j=0;j<MONTH_FIELDS;j++) {
   double v=data[start+j];
   if(j==0) { int k=(int)v; Cell(s,I(k/100)+"-"+((k%100)<10 ? "0" : "")+I(k%100)); }
   else Cell(s,j>=16 ? TS((datetime)v) : N(v));
  } return s;
 }
// Eight fields per threshold: threshold,closed,reached,returned,loser_returned,
// winner_returned,zero_returned,sum_first_return_quote_R. Observations, NOT BE fills.
void ShadowValues(const int t,double &v[])
 {
  ArrayInitialize(v,0); v[0]=PEThreshold(t);
  if(InpCase!=1) return;
  for(int i=0;i<ArraySize(cycles);i++) if(cycles[i].closed) {
   v[1]++; if(cycles[i].path.reached[t]) v[2]++;
   if(!cycles[i].path.returned[t]) continue;
   v[3]++; if(cycles[i].net<0) v[4]++; else if(cycles[i].net>0) v[5]++; else v[6]++;
   v[7]+=cycles[i].path.returnQuoteR[t];
  }
 }
string ShadowHeader()
 { return "threshold_R;control_cycles;threshold_reached;returned_to_entry;losers_returned;winners_returned;zero_returned;sum_first_return_quote_R"; }
void ExportDeals()
 {
  if(!HistorySelect(0,TimeCurrent()+86400)) { Invalid(401,"Cannot read final deal history."); return; }
  for(int i=0;i<ArraySize(months);i++) months[i].bookedNet=0;
  int f=folder!="" ? OpenText(folder+"\\deals.csv") : INVALID_HANDLE;
  if(folder!="" && f==INVALID_HANDLE) Invalid(402,"Cannot write deals.csv.");
  Row(f,"time_server;cycle;origin_case140;deal;order;position_id;entry_type;side;reason;volume;price;profit;commission;swap;fee;net_deal;magic;comment");
  for(int i=0;i<HistoryDealsTotal();i++) {
   ulong d=HistoryDealGetTicket(i); if(d==0 || HistoryDealGetString(d,DEAL_SYMBOL)!=_Symbol) continue;
   int n=CycleByPid((ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID));
   if(n<0) { if((ulong)HistoryDealGetInteger(d,DEAL_MAGIC)==InpMagic) unmatchedDeals++; continue; }
   double profit=HistoryDealGetDouble(d,DEAL_PROFIT),swap=HistoryDealGetDouble(d,DEAL_SWAP);
   double fee=HistoryDealGetDouble(d,DEAL_FEE),commission=HistoryDealGetDouble(d,DEAL_COMMISSION);
   datetime time=(datetime)HistoryDealGetInteger(d,DEAL_TIME); months[MonthIndex(time)].bookedNet+=profit+swap+fee+commission;
   string s=""; Cell(s,TS(time)); Cell(s,I(cycles[n].number)); Cell(s,I(cycles[n].origin)); Cell(s,U(d));
   Cell(s,I(HistoryDealGetInteger(d,DEAL_ORDER))); Cell(s,I(HistoryDealGetInteger(d,DEAL_POSITION_ID)));
   Cell(s,EnumToString((ENUM_DEAL_ENTRY)HistoryDealGetInteger(d,DEAL_ENTRY)));
   Cell(s,EnumToString((ENUM_DEAL_TYPE)HistoryDealGetInteger(d,DEAL_TYPE)));
   Cell(s,EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(d,DEAL_REASON)));
   Cell(s,N(HistoryDealGetDouble(d,DEAL_VOLUME))); Cell(s,N(HistoryDealGetDouble(d,DEAL_PRICE)));
   Cell(s,N(profit)); Cell(s,N(commission)); Cell(s,N(swap)); Cell(s,N(fee)); Cell(s,N(profit+commission+swap+fee));
   Cell(s,I(HistoryDealGetInteger(d,DEAL_MAGIC))); Cell(s,HistoryDealGetString(d,DEAL_COMMENT)); Row(f,s);
  }
  if(f!=INVALID_HANDLE) FileClose(f);
 }
void ExportDetails()
 {
  if(folder=="") return;
  int f=OpenText(folder+"\\cycles.csv"); if(f==INVALID_HANDLE) { Invalid(403,"Cannot write cycles.csv."); return; }
  Row(f,"cycle;origin_case140;side;entry_time;exit_time;signal_time;closed;initial_entry;initial_stop;target;initial_lot;initial_risk;peak_stop_risk;balance_before;net;gross;swap;commission_fees;net_R_initial;hold_hours;legs;adds;position0;position1;position2;add1_price;add1_lot;add2_price;add2_lot;BE_trigger_R;BE_armed;BE_confirmed_time;partial_armed;partial_time;partial_lot;partial_price;MFE_R;MAE_R;quote_observations;exit_reason;ADX_entry;ATR_entry;entry_distance_ATR;SMA200_slope_ATR;entry_policy;oscillator_valid;fast310_entry;previous_fast310_entry;signal310_entry;ADX_change_entry;TR_ATR_entry;body_ATR_entry;close_location_entry;source_control180;matched_control190;fixed_lot_mode;target_unit;target_value;requested_target_distance_price;quoted_entry;quoted_target;actual_target_distance_price;actual_target_R;estimated_target_gross_profit;target_cap_adjustments;selected_entry_path;hp_signal_time;hp_available_time;hp_p1_price;hp_p2_price;hp_p3_price;hp_p1_time;hp_p2_time;hp_p3_time;hp_pattern_available_time");
  for(int i=0;i<ArraySize(cycles);i++) {
   PECycle c=cycles[i]; string s=""; Cell(s,I(c.number)); Cell(s,I(c.origin)); Cell(s,I(c.side));
   Cell(s,TS(c.start)); Cell(s,TS(c.finish)); Cell(s,TS(c.signalTime)); Cell(s,I(c.closed));
   Cell(s,N(c.entry)); Cell(s,N(c.stop)); Cell(s,N(c.target)); Cell(s,N(c.volume)); Cell(s,N(c.initialRisk)); Cell(s,N(c.peakRisk));
   Cell(s,N(c.balanceBefore)); Cell(s,N(c.net)); Cell(s,N(c.gross)); Cell(s,N(c.swap)); Cell(s,N(c.costs));
   Cell(s,c.initialRisk>0 ? N(c.net/c.initialRisk) : ""); Cell(s,c.finish>0 ? N((c.finish-c.start)/3600.0) : "");
   Cell(s,I(c.legs)); Cell(s,I(c.adds)); for(int j=0;j<3;j++) Cell(s,U(c.pids[j]));
   for(int j=1;j<3;j++) { Cell(s,N(c.fills[j])); Cell(s,N(c.volumes[j])); }
   Cell(s,N(c.beTrigger)); Cell(s,I(c.be.armed)); Cell(s,TS(c.beTime)); Cell(s,I(c.part.armed));
   Cell(s,TS(c.partialTime)); Cell(s,N(c.partialVolume)); Cell(s,N(c.partialPrice));
   Cell(s,N(c.path.maxR)); Cell(s,N(c.path.minR)); Cell(s,I(c.path.observations)); Cell(s,EnumToString((ENUM_DEAL_REASON)c.finalReason));
   Cell(s,N(c.featureADX)); Cell(s,N(c.featureATR)); Cell(s,N(c.featureDistance)); Cell(s,N(c.featureSlope));
   Cell(s,I(c.entryPolicy)); Cell(s,I(c.entryFeatures.oscillatorValid)); Cell(s,N(c.entryFeatures.fast310));
   Cell(s,N(c.entryFeatures.previousFast310)); Cell(s,N(c.entryFeatures.signal310)); Cell(s,N(c.featureADXChange));
   Cell(s,N(c.entryFeatures.trueRangeATR)); Cell(s,N(c.entryFeatures.bodyATR)); Cell(s,N(c.entryFeatures.closeLocation));
   Cell(s,I(dc.sourceControl180)); Cell(s,I(dc.matchedControl)); Cell(s,I(dc.fixedLot)); Cell(s,TargetUnitName());
   Cell(s,N(dc.targetMode==0 ? 5 : 20)); Cell(s,N(c.targetDistance)); Cell(s,N(c.quotedEntry)); Cell(s,N(c.quotedTarget));
   Cell(s,N(c.side*(c.target-c.entry))); Cell(s,MathAbs(c.entry-c.stop)>0 ? N(c.side*(c.target-c.entry)/MathAbs(c.entry-c.stop)) : "");
   Cell(s,N(c.targetProfitEstimate)); Cell(s,I(c.targetAdjustments));
   Cell(s,HPPathName(c.entryPath)); Cell(s,TS((datetime)c.entryPivot.signal_time)); Cell(s,TS((datetime)c.entryPivot.available_time));
   Cell(s,N(c.entryPivot.stop_f1)); Cell(s,N(c.entryPivot.reference_price)); Cell(s,N(c.entryPivot.pullback_f2));
   Cell(s,TS((datetime)c.entryPivot.p1_time)); Cell(s,TS((datetime)c.entryPivot.p2_time)); Cell(s,TS((datetime)c.entryPivot.p3_time));
   Cell(s,TS((datetime)c.entryPivot.pattern_available_time)); Row(f,s);
  }
  FileClose(f);
  f=OpenText(folder+"\\months.csv"); if(f==INVALID_HANDLE) { Invalid(404,"Cannot write months.csv."); return; }
  Row(f,MonthHeader()); for(int i=0;i<ArraySize(months);i++) { double v[18]; MonthValues(i,v); Row(f,MonthCSV(v,0)); } FileClose(f);
  f=OpenText(folder+"\\breakeven_paths.csv"); if(f==INVALID_HANDLE) { Invalid(405,"Cannot write breakeven_paths.csv."); return; }
  Row(f,"cycle;original_control;threshold_R;threshold_reached;returned_after_threshold;first_return_quote_R;net_original;MFE_R;MAE_R");
  for(int i=0;i<ArraySize(cycles);i++) for(int t=0;t<5;t++) {
   string s=""; Cell(s,I(cycles[i].number)); Cell(s,I(InpCase==1)); Cell(s,N(PEThreshold(t)));
   Cell(s,I(cycles[i].path.reached[t])); Cell(s,I(cycles[i].path.returned[t]));
   Cell(s,cycles[i].path.returned[t] ? N(cycles[i].path.returnQuoteR[t]) : "");
   Cell(s,N(cycles[i].net)); Cell(s,N(cycles[i].path.maxR)); Cell(s,N(cycles[i].path.minR)); Row(f,s);
  } FileClose(f);
 }
// Numeric frame carries statistics and ASCII relative-folder index, never raw future prices.
void BuildPayload(const double &stats[],double &payload[])
 {
  int base=S_COUNT+G_COUNT,n=ArraySize(months),len=StringLen(folder);
  int tail=base+1+n*MONTH_FIELDS+5*SHADOW_FIELDS; ArrayResize(payload,tail+1+len);
  for(int i=0;i<base;i++) payload[i]=stats[i]; payload[base]=n;
  for(int m=0;m<n;m++) { double v[18]; MonthValues(m,v); for(int j=0;j<18;j++) payload[base+1+m*18+j]=v[j]; }
  int at=base+1+n*18;
  for(int t=0;t<5;t++) { double v[8]; ShadowValues(t,v); for(int j=0;j<8;j++) payload[at+t*8+j]=v[j]; }
  payload[tail]=len; for(int j=0;j<len;j++) payload[tail+1+j]=StringGetCharacter(folder,j);
 }
bool PayloadValid(const double &p[])
 {
  int base=S_COUNT+G_COUNT; if(ArraySize(p)<base+1 || !MathIsValidNumber(p[base]) || p[base]<0 || p[base]>1200) return false;
  int n=(int)p[base]; if(p[base]!=n) return false;
  int tail=base+1+n*18+40;
  if(ArraySize(p)<tail+1 || !MathIsValidNumber(p[tail]) || p[tail]<0 || p[tail]>512) return false;
  int len=(int)p[tail]; if(p[tail]!=len || ArraySize(p)!=tail+1+len) return false;
  for(int i=0;i<len;i++) if(!MathIsValidNumber(p[tail+1+i]) || p[tail+1+i]<32 || p[tail+1+i]>126 || p[tail+1+i]!=(int)p[tail+1+i]) return false;
  return true;
 }
string PayloadFolder(const double &p[])
 {
  if(!PayloadValid(p)) return "";
  int tail=S_COUNT+G_COUNT+1+(int)p[S_COUNT+G_COUNT]*18+40; string name="";
  for(int i=0;i<(int)p[tail];i++) name+=ShortToString((ushort)p[tail+1+i]); return name;
 }
double OnTester()
 {
  if(!initialized) return -1e100;
  finalizing=true; SyncCycle(); TrackEquity();
  // Rebuild all P&L from the executed final history, including forced tester exits
  // that may arrive without another OnTick and may carry magic zero.
  for(int i=0;i<ArraySize(cycles);i++) {
   bool ok=AggregateCycle(i); cycles[i].closed=ok && MathAbs(cycles[i].inVolume-cycles[i].outVolume)<1e-8 && cycles[i].finish>0;
   if(!cycles[i].closed) Invalid(406,"Open/unreconciled campaign at tester end.");
   if(cycles[i].closed && !cycles[i].finalObserved) { PEObserve(cycles[i].path,cycles[i].finalPrice); cycles[i].finalObserved=true; }
  }
  for(int m=0;m<ArraySize(months);m++) { months[m].closed=0; months[m].cycleNet=0; }
  for(int i=0;i<ArraySize(cycles);i++) if(cycles[i].closed) { int m=MonthIndex(cycles[i].finish); months[m].closed++; months[m].cycleNet+=cycles[i].net; }
  if(firstReady==0) Invalid(407,"No complete indicator snapshot available.");
  ExportDeals();
  double data[S_COUNT+G_COUNT]; ArrayInitialize(data,0);
  data[S_PROFIT]=TesterStatistics(STAT_PROFIT); data[S_DEPOSIT]=TesterStatistics(STAT_INITIAL_DEPOSIT);
  data[S_FINAL_BALANCE]=data[S_DEPOSIT]+data[S_PROFIT]; data[S_MT5_TRADES]=TesterStatistics(STAT_TRADES);
  data[S_MT5_PF]=TesterStatistics(STAT_PROFIT_FACTOR); data[S_EQUITY_DD_REL]=TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
  data[S_EQUITY_DD_MONEY]=TesterStatistics(STAT_EQUITY_DD); data[S_EQUITY_DD_AT_MONEY]=TesterStatistics(STAT_EQUITYDD_PERCENT);
  data[S_CYCLES_OPENED]=ArraySize(cycles); double winning=0,losing=0; int streak=0;
  for(int i=0;i<ArraySize(cycles);i++) {
   PECycle c=cycles[i]; data[S_BE_ARMED]+=c.be.armed; data[S_BE_CONFIRMED]+=c.beTime>0;
   data[S_PARTIAL_ARMED]+=c.part.armed; data[S_PARTIAL_DONE]+=c.part.done;
   data[S_BE_ATTEMPTS]+=c.be.attempts; data[S_PARTIAL_ATTEMPTS]+=c.part.attempts;
   if(c.be.armed && !c.be.done) data[S_BE_UNFULFILLED]++;
   if(c.part.armed && !c.part.done) data[S_PARTIAL_UNFULFILLED]++;
   data[S_INITIAL_LOTS_SUM]+=c.volume; for(int j=1;j<c.legs;j++) data[S_ADD_LOTS_SUM]+=c.volumes[j];
   data[S_ADD_FILLS]+=c.adds;
   if(c.path.observations==0) data[S_EMPTY_PATHS]++;
   if(!c.closed) continue;
   data[S_CYCLES_CLOSED]++; data[S_CYCLE_NET]+=c.net; data[S_SWAP]+=c.swap; data[S_COSTS]+=c.costs;
   if(c.origin==15) { data[S_ORIGIN15_CYCLES]++; data[S_ORIGIN15_NET]+=c.net; }
   if(c.origin==14) { data[S_ORIGIN14_CYCLES]++; data[S_ORIGIN14_NET]+=c.net; }
   if(c.adds>0) { data[S_ADD_CYCLES]++; data[S_ADD_NET]+=c.net; }
   if(c.net>0) { data[S_WINS]++; winning+=c.net; streak=0; data[S_MFE_WIN_AVG]+=c.path.maxR; }
   else if(c.net<0) { data[S_LOSSES]++; losing-=c.net; streak++; data[S_MFE_LOSS_AVG]+=c.path.maxR; }
   else { data[S_ZERO]++; streak=0; }
   data[S_MAX_LOSS_STREAK]=MathMax(data[S_MAX_LOSS_STREAK],streak);
   if(c.initialRisk>0) data[S_AVG_NET_R]+=c.net/c.initialRisk;
   double hold=(c.finish-c.start)/3600.0; data[S_AVG_HOLD]+=hold; data[S_MAX_HOLD]=MathMax(data[S_MAX_HOLD],hold);
   data[S_MFE_AVG]+=c.path.maxR; data[S_MAE_AVG]+=c.path.minR; data[S_QUOTE_OBSERVATIONS]+=c.path.observations;
   if(c.beTime>0 && c.finalReason==DEAL_REASON_SL) data[S_BE_STOP_EXITS]++;
   if(data[S_FIRST_ENTRY]==0 || c.start<data[S_FIRST_ENTRY]) data[S_FIRST_ENTRY]=(double)c.start;
   data[S_LAST_EXIT]=MathMax(data[S_LAST_EXIT],(double)c.finish);
  }
  double n=data[S_CYCLES_CLOSED];
  if(n>0) { data[S_WIN_PCT]=100*data[S_WINS]/n; data[S_AVG_NET_R]/=n; data[S_AVG_HOLD]/=n; data[S_MFE_AVG]/=n; data[S_MAE_AVG]/=n; }
  if(data[S_WINS]>0) data[S_MFE_WIN_AVG]/=data[S_WINS]; if(data[S_LOSSES]>0) data[S_MFE_LOSS_AVG]/=data[S_LOSSES];
  data[S_CYCLE_PF]=losing>0 ? winning/losing : (winning>0 ? DBL_MAX : 0);
  data[S_MAX_LOTS]=maxLots; data[S_MAX_RISK]=maxRisk; data[S_MAX_RISK_PCT]=maxRiskPct; data[S_MAX_MARGIN]=maxMargin;
  data[S_FIRST_EVAL]=(double)firstEval; data[S_LAST_EVAL]=(double)lastEval; data[S_FIRST_READY]=(double)firstReady;
  data[S_BARS]=barsSeen; data[S_SIGNALS]=signals; data[S_PARTIAL_DEFERRED]=partialDefers; data[S_BE_DEFERRED]=beDefers;
  data[S_SESSION_DEFERS]=sessionDefers; data[S_STOPS_DEFERS]=stopDefers; data[S_AMBIGUOUS_PARTIALS]=ambiguousPartials;
  data[S_UNMATCHED]=unmatchedDeals; data[S_RECONCILE]=data[S_PROFIT]-data[S_CYCLE_NET];
  double eq=0,book=0;
  for(int m=0;m<ArraySize(months);m++) {
   book+=months[m].bookedNet; if(!months[m].path.initialized) continue;
   data[S_MONTHS]++; double delta=months[m].path.endEquity-months[m].path.startEquity; eq+=delta;
   if(delta>.005) data[S_POS_EQ_MONTHS]++; if(delta<-.005) data[S_NEG_EQ_MONTHS]++;
   if(months[m].bookedNet>.005) data[S_POS_BOOK_MONTHS]++; if(months[m].bookedNet<-.005) data[S_NEG_BOOK_MONTHS]++;
   data[S_MONTH_DD_MAX]=MathMax(data[S_MONTH_DD_MAX],months[m].path.maxRelativeDD);
  }
  data[S_MONTH_EQ_RECONCILE]=data[S_PROFIT]-eq; data[S_MONTH_BOOK_RECONCILE]=data[S_PROFIT]-book;
  if(MathAbs(data[S_RECONCILE])>.01 || MathAbs(data[S_MONTH_EQ_RECONCILE])>.01 || MathAbs(data[S_MONTH_BOOK_RECONCILE])>.01 ||
     data[S_UNMATCHED]>0 || data[S_CYCLES_CLOSED]!=data[S_CYCLES_OPENED]) Invalid(408,"Native/cycle/month totals do not reconcile.");
  data[S_SHADOW_CONTROL_ELIGIBLE]=(InpCase==1) ? 1 : 0;
  data[S_FIXED_LOT]=dc.fixedLot ? InpFixedLot : 0; data[S_BE15_R]=profile.be15; data[S_MODE]=profile.mode; data[S_PROTECT14]=profile.protect14;
  data[S_ADD_REJECTS]=addRejects; data[S_RISK_BLOCKS]=riskBlocks; data[S_STOP_FACTOR]=profile.stopFactor;
  data[S_REINVEST]=profile.reinvest; data[S_ARM]=profile.arm; data[S_PATTERN_BUYS]=patternBuys; data[S_PATTERN_SELLS]=patternSells;
  data[S_ENTRY_POLICY]=evo.entryPolicy; data[S_REINVEST_FRACTION]=evo.reinvestFraction;
  data[S_REINVEST_CAP]=dc.fixedLot ? InpFixedLot : InpMaxLot; data[S_CAPITAL_MODE]=evo.capitalMode;
  data[S_RISK_PERCENT]=dc.riskPercent; data[S_MARGIN_CAP_PERCENT]=dc.fixedLot ? 0 : InpMaxMarginPct; data[S_DONCHIAN_MODE]=dc.channelMode;
  data[S_SOURCE_CONTROL180]=dc.sourceControl180; data[S_FIXED_MODE]=dc.fixedLot; data[S_TARGET_MODE]=dc.targetMode;
  data[S_TARGET_VALUE]=dc.targetMode==0 ? 5 : 20; data[S_TARGET_DISTANCE]=HermesTargetDistance(dc.targetMode,_Point);
  data[S_NOMINAL_TARGET_R]=dc.targetMode==0 ? 5 : 0; data[S_TARGET_REJECTS]=targetRejects; data[S_TARGET_ADJUSTMENTS]=targetAdjustments;
  data[S_TARGET_FAILURES]=targetFailures; data[S_FIXED_VOLUME_REJECTS]=fixedVolumeRejects;
  data[S_HP_CANDIDATES]=hpCandidates; data[S_HP_EXTRA_ELIGIBLE]=hpExtraEligible;
  data[S_HP_BASE_SELECTED]=hpBaseSelected; data[S_HP_PIVOT_SELECTED]=hpPivotSelected; data[S_HP_PIVOT_FILLS]=hpPivotFills;
  data[S_HP_DATA_FAILURES]=hpDataFailures; data[S_HP_POSITION_BLOCKS]=hpPositionBlocks; data[S_HP_CATCHUP_IGNORED]=hpCatchupIgnored;
  data[S_MATCHED_CONTROL]=dc.matchedControl; data[S_DETAIL_EXPORT]=folder!=""; data[S_BAR_ROWS]=barRows;
  ExportDetails(); if(ioFailure) Invalid(410,"Detail CSV write failure.");
  data[S_ERROR_CODE]=errorCode; data[S_LAST_RETCODE]=lastRetcode; data[S_LAST_ERROR_TIME]=(double)lastErrorTime;
  data[S_VALID]=integrity ? 1 : 0; for(int i=0;i<G_COUNT;i++) data[S_COUNT+i]=counters[i];
  if(folder!="") {
   int f=OpenText(folder+"\\summary.csv");
   if(f==INVALID_HANDLE) { Invalid(409,"Cannot write summary.csv."); data[S_VALID]=0; }
   else { Row(f,"metric;value"); KV(f,"version","2.00"); KV(f,"case",I(InpCase)); KV(f,"name",ProfileName(InpCase));
    KV(f,"signal_tf",TFName(InpCase)); string names[]; StatNames(names);
    for(int i=0;i<S_COUNT;i++) KV(f,names[i],IsTimeStat(i) ? TS((datetime)data[i]) : N(data[i]));
    for(int i=0;i<G_COUNT;i++) KV(f,EnumToString((PE_GATE)i),N(data[S_COUNT+i])); FileClose(f);
   }
  }
  if(ioFailure) { Invalid(410,"CSV write failure."); data[S_VALID]=0; data[S_ERROR_CODE]=errorCode; }
  if(MQLInfoInteger(MQL_OPTIMIZATION)) { double payload[]; BuildPayload(data,payload); if(!FrameAdd("HP200",InpCase,data[S_PROFIT],payload)) Print("FrameAdd failed: ",GetLastError()); }
  Print("HP200 ",ProfileName(InpCase)," lucro=",data[S_PROFIT]," ciclos=",n," valid_run=",integrity);
  return integrity ? data[S_PROFIT] : -1e100;
 }
int OnTesterInit()
 {
  string names[]; if(StatNames(names)!=S_COUNT) { Print("STAT SCHEMA ERROR"); return INIT_FAILED; }
  if(!ValidRunTag()) return INIT_PARAMETERS_INCORRECT;
  if(!InpExportCSV) return INIT_SUCCEEDED;
  FolderCreate("Hermes_Pivos_Lab_200",FILE_COMMON); FolderCreate(RunRoot(),FILE_COMMON); optFolder=RunRoot()+"\\OTIMIZACAO_"+Stamp();
  if(!FolderCreate(optFolder,FILE_COMMON)) return INIT_FAILED;
  optFile=OpenText(optFolder+"\\comparacao.csv"); optMonths=OpenText(optFolder+"\\meses_comparacao.csv");
  optShadow=OpenText(optFolder+"\\breakeven_comparacao.csv"); optFiles=OpenText(optFolder+"\\arquivos_comparacao.csv");
  if(optFile==INVALID_HANDLE || optMonths==INVALID_HANDLE || optShadow==INVALID_HANDLE || optFiles==INVALID_HANDLE) return INIT_FAILED;
  string header="pass;case;name;signal_tf"; for(int i=0;i<S_COUNT;i++) header+=";"+names[i];
  for(int i=0;i<G_COUNT;i++) header+=";"+EnumToString((PE_GATE)i); Row(optFile,header);
  Row(optMonths,"pass;case;name;"+MonthHeader()); Row(optShadow,"pass;case;name;valid_run;"+ShadowHeader());
  Row(optFiles,"pass;case;name;relative_details_folder;details_exported");
  if(ioFailure) return INIT_FAILED;
  Print("COMPARACAO AUTOMATICA: ",TerminalInfoString(TERMINAL_COMMONDATA_PATH),"\\Files\\",optFolder); return INIT_SUCCEEDED;
 }
void DrainFrames()
 {
  ulong pass=0; long id=0; string name=""; double value=0,data[];
  while(FrameNext(pass,name,id,value,data)) {
   if(name!="HP200" || optFile==INVALID_HANDLE || !PayloadValid(data) || id<1 || id>3) continue;
   bool seen=false; for(int i=0;i<ArraySize(receivedPasses);i++) if(receivedPasses[i]==pass) seen=true; if(seen) continue;
   int n=ArraySize(receivedPasses); ArrayResize(receivedPasses,n+1); receivedPasses[n]=pass;
   string prefix=""; Cell(prefix,U(pass)); Cell(prefix,I(id)); Cell(prefix,ProfileName((int)id));
   string row=prefix; Cell(row,PayloadFolder(data)); Cell(row,N(data[S_DETAIL_EXPORT])); Row(optFiles,row);
   row=prefix; Cell(row,TFName((int)id));
   for(int i=0;i<S_COUNT+G_COUNT;i++) Cell(row,IsTimeStat(i) ? TS((datetime)data[i]) : N(data[i])); Row(optFile,row);
   int base=S_COUNT+G_COUNT,mc=(int)data[base];
   for(int m=0;m<mc;m++) Row(optMonths,prefix+";"+MonthCSV(data,base+1+m*18));
   if(id==1) for(int t=0;t<5;t++) {
    row=prefix; Cell(row,N(data[S_VALID]));
    for(int j=0;j<8;j++) Cell(row,N(data[base+1+mc*18+t*8+j])); Row(optShadow,row);
   }
   FileFlush(optFile); FileFlush(optMonths); FileFlush(optShadow); FileFlush(optFiles);
  }
 }
void OnTesterPass() { DrainFrames(); }
void OnTesterDeinit()
 {
  DrainFrames(); if(optFile!=INVALID_HANDLE) FileClose(optFile); if(optMonths!=INVALID_HANDLE) FileClose(optMonths);
  if(optFiles!=INVALID_HANDLE) FileClose(optFiles); optFiles=INVALID_HANDLE;
  if(optShadow!=INVALID_HANDLE) FileClose(optShadow); optFile=INVALID_HANDLE; optMonths=INVALID_HANDLE; optShadow=INVALID_HANDLE;
  Print("HP200 comparacoes recebidas: ",ArraySize(receivedPasses),". Confira com as passagens concluidas.");
 }
