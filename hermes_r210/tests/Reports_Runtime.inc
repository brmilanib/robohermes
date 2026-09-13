enum PE_GATE { G_NO_DATA=0,G_BASE,G_DIRECTION,G_DISTANCE,G_REGIME,G_POSITION,
 G_SPREAD,G_STOP,G_BROKER_STOPS,G_RISK,G_MARGIN_ERROR,G_MARGIN_BLOCK,G_REJECTED,G_FILLED,G_HALTED,G_ENTRY_FILTER,G_TARGET,G_COUNT };
enum PE_STAT {
 S_VALID=0,S_PROFIT,S_DEPOSIT,S_FINAL_BALANCE,S_MT5_TRADES,S_MT5_PF,S_EQUITY_DD_REL,S_EQUITY_DD_MONEY,S_EQUITY_DD_AT_MONEY,
 S_CYCLES_OPENED,S_CYCLES_CLOSED,S_WINS,S_LOSSES,S_ZERO,S_WIN_PCT,S_CYCLE_PF,S_CYCLE_NET,S_AVG_NET_R,
 S_MAX_LOSS_STREAK,S_AVG_HOLD,S_MAX_HOLD,S_SWAP,S_COSTS,S_MAX_LOTS,S_MAX_RISK,S_MAX_RISK_PCT,S_MAX_MARGIN,
 S_FIRST_EVAL,S_LAST_EVAL,S_FIRST_ENTRY,S_LAST_EXIT,S_BARS,S_SIGNALS,S_FIRST_READY,
 S_ORIGIN15_CYCLES,S_ORIGIN14_CYCLES,S_ORIGIN15_NET,S_ORIGIN14_NET,
 S_BE_ARMED,S_BE_CONFIRMED,S_BE_STOP_EXITS,S_PARTIAL_ARMED,S_PARTIAL_DONE,S_PARTIAL_DEFERRED,S_BE_DEFERRED,
 S_SESSION_DEFERS,S_STOPS_DEFERS,S_BE_ATTEMPTS,S_PARTIAL_ATTEMPTS,S_AMBIGUOUS_PARTIALS,S_ERROR_CODE,S_LAST_RETCODE,S_LAST_ERROR_TIME,
 S_RECONCILE,S_MONTH_EQ_RECONCILE,S_MONTH_BOOK_RECONCILE,S_UNMATCHED,S_MONTHS,S_POS_EQ_MONTHS,S_NEG_EQ_MONTHS,S_POS_BOOK_MONTHS,S_NEG_BOOK_MONTHS,
 S_MFE_AVG,S_MFE_WIN_AVG,S_MFE_LOSS_AVG,S_MAE_AVG,S_QUOTE_OBSERVATIONS,S_SHADOW_CONTROL_ELIGIBLE,
 S_FIXED_LOT,S_BE15_R,S_MODE,S_PROTECT14,S_BE_UNFULFILLED,S_PARTIAL_UNFULFILLED,S_EMPTY_PATHS,
 S_MONTH_DD_MAX,S_ADD_FILLS,S_ADD_CYCLES,S_ADD_NET,S_ADD_REJECTS,S_RISK_BLOCKS,S_STOP_FACTOR,
 S_REINVEST,S_ARM,S_INITIAL_LOTS_SUM,S_ADD_LOTS_SUM,S_PATTERN_BUYS,S_PATTERN_SELLS,S_ENTRY_POLICY,S_REINVEST_FRACTION,S_REINVEST_CAP,S_CAPITAL_MODE,S_MATCHED_CONTROL,S_DETAIL_EXPORT,S_BAR_ROWS,S_RISK_PERCENT,S_MARGIN_CAP_PERCENT,S_DONCHIAN_MODE,S_SOURCE_CONTROL180,S_FIXED_MODE,S_TARGET_MODE,S_TARGET_VALUE,S_TARGET_DISTANCE,S_NOMINAL_TARGET_R,S_TARGET_REJECTS,S_TARGET_ADJUSTMENTS,S_TARGET_FAILURES,S_FIXED_VOLUME_REJECTS,S_HP_CANDIDATES,S_HP_EXTRA_ELIGIBLE,S_HP_BASE_SELECTED,S_HP_PIVOT_SELECTED,S_HP_PIVOT_FILLS,S_HP_DATA_FAILURES,S_HP_POSITION_BLOCKS,S_HP_CATCHUP_IGNORED,S_COUNT };
const int MONTH_FIELDS=18,SHADOW_FIELDS=8;
template<class V> void MonthValues(const int i,V &v)
 {
  v[0]=months[i].key; v[1]=months[i].path.startEquity; v[2]=months[i].path.endEquity; v[3]=v[2]-v[1];
  v[4]=months[i].path.startBalance; v[5]=months[i].path.endBalance; v[6]=months[i].bookedNet; v[7]=months[i].cycleNet;
  v[8]=months[i].path.maxRelativeDD; v[9]=months[i].path.maxMoneyDD; v[10]=months[i].bars; v[11]=months[i].signals;
  v[12]=months[i].opened; v[13]=months[i].closed; v[14]=months[i].bes; v[15]=months[i].partials;
  v[16]=(double)months[i].firstTick; v[17]=(double)months[i].lastTick;
 }

template<class V> void ShadowValues(const int t,V &v)
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

void BuildPayload(const std::vector<double> &stats,std::vector<double> &payload)
 {
  int base=S_COUNT+G_COUNT,n=ArraySize(months),len=StringLen(folder);
  int tail=base+1+n*MONTH_FIELDS+5*SHADOW_FIELDS; ArrayResize(payload,tail+1+len);
  for(int i=0;i<base;i++) payload[i]=stats[i]; payload[base]=n;
  for(int m=0;m<n;m++) { double v[18]; MonthValues(m,v); for(int j=0;j<18;j++) payload[base+1+m*18+j]=v[j]; }
  int at=base+1+n*18;
  for(int t=0;t<5;t++) { double v[8]; ShadowValues(t,v); for(int j=0;j<8;j++) payload[at+t*8+j]=v[j]; }
  payload[tail]=len; for(int j=0;j<len;j++) payload[tail+1+j]=StringGetCharacter(folder,j);
 }
bool PayloadValid(const std::vector<double> &p)
 {
  int base=S_COUNT+G_COUNT; if(ArraySize(p)<base+1 || !MathIsValidNumber(p[base]) || p[base]<0 || p[base]>1200) return false;
  int n=(int)p[base]; if(p[base]!=n) return false;
  int tail=base+1+n*18+40;
  if(ArraySize(p)<tail+1 || !MathIsValidNumber(p[tail]) || p[tail]<0 || p[tail]>512) return false;
  int len=(int)p[tail]; if(p[tail]!=len || ArraySize(p)!=tail+1+len) return false;
  for(int i=0;i<len;i++) if(!MathIsValidNumber(p[tail+1+i]) || p[tail+1+i]<32 || p[tail+1+i]>126 || p[tail+1+i]!=(int)p[tail+1+i]) return false;
  return true;
 }
string PayloadFolder(const std::vector<double> &p)
 {
  if(!PayloadValid(p)) return "";
  int tail=S_COUNT+G_COUNT+1+(int)p[S_COUNT+G_COUNT]*18+40; string name="";
  for(int i=0;i<(int)p[tail];i++) name+=ShortToString((ushort)p[tail+1+i]); return name;
 }
