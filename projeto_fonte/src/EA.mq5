#property strict
#property version "2.00"
#property description "XAU M30: original Hermes control plus two causal 1-2-3 pivot hypotheses. Tester only."
#include <Trade/Trade.mqh>
#include "XAU_H1_Core.mqh"
#include "ProtectCore.mqh"
#include "EntryCore.mqh"
#include "DonchianCore.mqh"
#include "HermesCore.mqh"
#include "PivotCore.mqh"
#include "PivotEntryCore.mqh"

// Three predeclared M30 cases. Exact fixed lot and 5R in every case.
input int InpCase=1;
input double InpMaxMarginPct=20.0;
input double InpMaxLot=1.0;
input double InpFixedLot=1.00;
input double InpMinEntryATR=0.50;
input double InpMaxSpreadPoints=0;
input ulong InpDeviationPoints=20;
input ulong InpMagic=26120200;
input bool InpExportCSV=true;
input bool InpShowIndicators=false;
input bool InpExportOptimizationDetails=true;
input bool InpExportAllBars=true;
input string InpRunTag="R200_01";

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
const int MONTH_FIELDS=18;
const int SHADOW_FIELDS=8;
struct PECycle {
 int number,origin,side,legs,adds;
 int entryPath; HPSignal entryPivot;
 ulong pid,ticket,partialDeal,partialOrder;
 ulong pids[3]; double fills[3],volumes[3],expectedStops[3];
 datetime start,finish,partialTime,beTime;
 double quotedEntry,quotedTarget,targetDistance,targetProfitEstimate; int targetAdjustments;
 double entry,stop,target,volume,initialRisk,balanceBefore,beTrigger,liveStop,peakRisk,desiredStop;
 double gross,swap,costs,net,inVolume,outVolume,finalPrice,partialPrice,partialVolume;
 long finalReason;
 bool closed,partialEnabled,finalObserved,addPending; long addNextMs,addAttempts;
 PERequest be,part;
 EVOFeatures entryFeatures; int entryPolicy;
 PEPath path; double featureADXChange,featureADX,featureATR,featureDistance,featureSlope; datetime signalTime;
};
struct PEMonth {
 int key; long bars,signals,opened,closed,bes,partials;
 double cycleNet,bookedNet;
 datetime firstTick,lastTick;
 PEEquityPath path;
};
PEProfile profile; EVOProfile evo; EVOFeatures features; DCProfile dc;
HPState hpState; HPSignal hpSignal; HPDecision hpRoute;
bool hpDataReady=false; string hpStatus="NOT_STARTED"; int hpProcessedThisBar=0;
long hpCandidates=0,hpExtraEligible=0,hpBaseSelected=0,hpPivotSelected=0,hpPivotFills=0,hpDataFailures=0,hpPositionBlocks=0,hpCatchupIgnored=0;
ENUM_TIMEFRAMES signalTF=PERIOD_M30;
bool channelReady=false; double channelUpper=0,channelLower=0;
datetime channelOldest=0,channelNewest=0,channelClosedAt=0;
int channelBars=0; string channelStatus="NOT_REQUESTED";
double sizedLot=0,sizingRiskBudget=0,sizingMarginBudget=0,sizingMargin=0;
long targetRejects=0,targetAdjustments=0,targetFailures=0,fixedVolumeRejects=0;
double plannedTargetDistance=0,plannedTargetRiskRatio=0,plannedTargetProfit=0;
double minimumLotRiskMoney=0,minimumLotRiskPercent=0,minimumEquityForLot=0,minimumLotMargin=0;
CTrade trade;
PECycle cycles[];
PEMonth months[];
int active=-1;
int hEMA=INVALID_HANDLE,h50=INVALID_HANDLE,h200=INVALID_HANDLE,hADX=INVALID_HANDLE,hATR=INVALID_HANDLE;
int barsFile=INVALID_HANDLE,eventsFile=INVALID_HANDLE,optFile=INVALID_HANDLE,optMonths=INVALID_HANDLE,optShadow=INVALID_HANDLE,optFiles=INVALID_HANDLE;
string folder="",optFolder="",lastReason="";
bool ioFailure=false; long barRows=0;
bool initialized=false,integrity=true,haltEntries=false,closeEmergency=false,finalizing=false;
int errorCode=0,lastRetcode=0;
datetime firstEval=0,lastEval=0,firstReady=0,lastBar=0,lastErrorTime=0,nextMonth=0;
long barsSeen=0,signals=0,counters[G_COUNT],lastEmergencyMs=0;
long partialDefers=0,beDefers=0,sessionDefers=0,stopDefers=0,ambiguousPartials=0,unmatchedDeals=0;
int liveMonth=-1;
double priorEquity=0,priorBalance=0,oldSMA200=0,maxLots=0,maxRisk=0,maxRiskPct=0,maxMargin=0;
double initialDeposit=0,previousClose=0,pivotLevel=0,pivotSwing=0;
int pivotSide=0; datetime pivotTime=0,lastPivotUsed=0;
long addRejects=0,riskBlocks=0,patternBuys=0,patternSells=0;
bool sessionKnown=false; int sessionDay[128],sessionFrom[128],sessionTo[128],sessionCount=0;
ulong receivedPasses[];

string TS(const datetime t) { return t>0 ? TimeToString(t,TIME_DATE|TIME_SECONDS) : ""; }
string N(const double v) { return MathIsValidNumber(v) ? DoubleToString(v,8) : ""; }
string I(const long v) { return (string)v; }
string U(const ulong v) { return (string)v; }
long NowMs() { MqlTick q; if(SymbolInfoTick(_Symbol,q) && q.time_msc>0) return q.time_msc; return (long)TimeCurrent()*1000; }
string EntryName(const int k)
 {
  string names[10]={"BASE","ADX_SUBINDO","ADX25","MOMENTO_3_10","DIST_1ATR","ATR_SEM_CHOQUE",
    "PULLBACK_PROXIMO","RETOMADA_CEDO","PIVO_FILTRADO","ADX_MACD_DIST"};
  return k>=0 && k<10 ? names[k] : "INVALID";
 }
string DCName(const int id)
 {
  string names[3]={"HERMES_REFERENCIA","HERMES_PIVO_CONTINUIDADE","HERMES_PIVO_INICIO"};
  return id>=1 && id<=3 ? names[id-1] : "INVALID";
 }
string ProfileName(const int id) { return DCName(id); }
string TFName(const int id) { return "M30"; }
string TargetUnitName() { return dc.targetMode==1 ? "QUOTE_PRICE" : (dc.targetMode==2 ? "MT5_POINT" : "INITIAL_STOP_R"); }
string TargetLabel() { return dc.targetMode==1 ? "20.00 unidades de preco" : (dc.targetMode==2 ? "20 pontos MT5" : "5R"); }
bool LoadDonchian(const datetime cutoff)
 {
  channelReady=false; channelUpper=0; channelLower=0; channelBars=0;
  channelOldest=0; channelNewest=0; channelClosedAt=0; channelStatus="W1_HISTORY_PENDING";
  // Excludes the W1 candle containing the CLOSED trigger candle, never its own high.
  int containing=iBarShift(_Symbol,PERIOD_W1,cutoff,false);
  if(containing<0) return false;
  int shift=containing+1;
  MqlRates w[]; ArraySetAsSeries(w,true);
  int copied=CopyRates(_Symbol,PERIOD_W1,shift,52,w); channelBars=(int)MathMax(0,copied);
  if(copied!=52) return false;
  channelClosedAt=iTime(_Symbol,PERIOD_W1,shift-1);
  channelNewest=w[0].time; channelOldest=w[51].time;
  if(channelClosedAt<=channelNewest || channelClosedAt>cutoff) { channelStatus="NON_CAUSAL_WINDOW"; return false; }
  double hi[52],lo[52];
  for(int i=0;i<52;i++) {
   hi[i]=w[i].high; lo[i]=w[i].low;
   // A missing full week must be diagnosed; DST offsets remain allowed.
   if(i>0 && (w[i-1].time-w[i].time<5*86400 || w[i-1].time-w[i].time>9*86400)) {
    channelStatus="W1_GAP"; return false;
   }
  }
  channelReady=DCWindow(hi,lo,52,(long)channelClosedAt,(long)cutoff,channelUpper,channelLower);
  channelStatus=channelReady ? "READY" : "INVALID_W1_VALUES"; return channelReady;
 }
bool ValidRunTag()
 {
  int n=StringLen(InpRunTag); if(n<1 || n>32) return false;
  for(int i=0;i<n;i++) { ushort c=StringGetCharacter(InpRunTag,i);
   if(!((c>=48 && c<=57) || (c>=65 && c<=90) || (c>=97 && c<=122) || c==95)) return false;
  }
  return true;
 }
string RunRoot() { return "Hermes_Pivos_Lab_200\\"+InpRunTag; }
string Stamp() { string s=TimeToString(TimeLocal(),TIME_DATE|TIME_SECONDS); StringReplace(s,":","-"); StringReplace(s," ","_"); return s+"_"+U(GetMicrosecondCount()); }
string Q(string s) { StringReplace(s,"\"","\"\""); StringReplace(s,"\r"," "); StringReplace(s,"\n"," "); return "\""+s+"\""; }
void Cell(string &s,const string v) { if(s!="") s+=";"; s+=Q(v); }
void Row(const int f,const string s)
 { if(f!=INVALID_HANDLE && FileWriteString(f,s+"\r\n")==0) { ioFailure=true; Print("HP200 CSV write failed: ",GetLastError()); } }
int OpenText(const string f) { return FileOpen(f,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON,0,CP_UTF8); }
void KV(const int f,const string k,const string v) { string row=""; Cell(row,k); Cell(row,v); Row(f,row); }
int MonthIndex(const datetime t)
 {
  MqlDateTime dt; TimeToStruct(t,dt); int key=dt.year*100+dt.mon;
  for(int i=0;i<ArraySize(months);i++) if(months[i].key==key) return i;
  int n=ArraySize(months); ArrayResize(months,n+1); ZeroMemory(months[n]); months[n].key=key; return n;
 }
void Event(const string kind,const int index,const string detail,const long ret=0)
 {
  int number=index>=0 && index<ArraySize(cycles) ? cycles[index].number : 0;
  int origin=index>=0 && index<ArraySize(cycles) ? cycles[index].origin : 0;
  string s=""; Cell(s,TS(TimeCurrent())); Cell(s,I(InpCase)); Cell(s,I(number)); Cell(s,I(origin));
  Cell(s,kind); Cell(s,I(ret)); Cell(s,detail); Row(eventsFile,s);
  if(kind=="ERROR" || kind=="PARTIAL_DEFERRED" || kind=="BE_DEFERRED" || kind=="AMBIGUOUS_PARTIAL")
    Print("HP200 ",kind," case=",InpCase," cycle=",number," ret=",ret," ",detail);
 }
void Invalid(const int code,const string reason,const bool emergency=false)
 {
  integrity=false; haltEntries=true; closeEmergency=closeEmergency || emergency;
  if(errorCode==0) errorCode=code;
  if(reason!=lastReason) { lastReason=reason; Event("ERROR",active,reason,lastRetcode); }
 }
int CycleByPid(const ulong pid)
 { if(pid==0) return -1; for(int i=ArraySize(cycles)-1;i>=0;i--) for(int j=0;j<cycles[i].legs;j++) if(cycles[i].pids[j]==pid) return i; return -1; }
int LegByPid(const int n,const ulong pid)
 { for(int j=0;j<cycles[n].legs;j++) if(cycles[n].pids[j]==pid) return j; return -1; }
bool OwnSelected()
 {
  return PositionGetString(POSITION_SYMBOL)==_Symbol &&
   (CycleByPid((ulong)PositionGetInteger(POSITION_IDENTIFIER))>=0 || (ulong)PositionGetInteger(POSITION_MAGIC)==InpMagic);
 }
int OwnPositions(double &volume,ulong &ticket)
 {
  int count=0; volume=0; ticket=0;
  for(int i=PositionsTotal()-1;i>=0;i--) {
   ulong t=PositionGetTicket(i); if(t==0 || !OwnSelected()) continue;
   count++; volume+=PositionGetDouble(POSITION_VOLUME); ticket=t;
  }
  return count;
 }
bool SymbolExposure()
 {
  for(int i=PositionsTotal()-1;i>=0;i--) if(PositionGetSymbol(i)==_Symbol) return true;
  for(int i=OrdersTotal()-1;i>=0;i--) if(OrderGetTicket(i)>0 && OrderGetString(ORDER_SYMBOL)==_Symbol) return true;
  return false;
 }
bool OwnPendingOrder()
 {
  for(int i=OrdersTotal()-1;i>=0;i--) if(OrderGetTicket(i)>0 && OrderGetString(ORDER_SYMBOL)==_Symbol &&
   (ulong)OrderGetInteger(ORDER_MAGIC)==InpMagic) return true;
  return false;
 }
void TrackEquity()
 {
  datetime now=TimeCurrent(); if(now<=0) return;
  if(liveMonth<0 || now>=nextMonth) {
   liveMonth=MonthIndex(now);
   if(!months[liveMonth].path.initialized) { PEStartEquity(months[liveMonth].path,priorEquity,priorBalance); months[liveMonth].firstTick=now; }
   MqlDateTime dt; TimeToStruct(now,dt); dt.day=1; dt.hour=0; dt.min=0; dt.sec=0; dt.mon++;
   if(dt.mon>12) { dt.mon=1; dt.year++; } nextMonth=StructToTime(dt);
  }
  double eq=AccountInfoDouble(ACCOUNT_EQUITY),bal=AccountInfoDouble(ACCOUNT_BALANCE);
  if(!PEObserveEquity(months[liveMonth].path,eq,bal)) { Invalid(101,"Invalid monthly equity value."); return; }
  months[liveMonth].lastTick=now; priorEquity=eq; priorBalance=bal;
 }
bool ReadValue(const int h,const int buffer,const int shift,double &v)
 { double a[1]; if(shift<1 || CopyBuffer(h,buffer,shift,1,a)!=1 || a[0]==EMPTY_VALUE || !MathIsValidNumber(a[0])) return false; v=a[0]; return true; }
bool ReadSignal(H1Signal &s,datetime &signalTime)
 {
  int required=dc.weekly ? 55 : 209;
  if(Bars(_Symbol,signalTF)<required || BarsCalculated(hEMA)<required || BarsCalculated(hADX)<required || BarsCalculated(hATR)<required ||
     (!dc.weekly && BarsCalculated(h200)<209)) return false;
  MqlRates r[]; ArraySetAsSeries(r,true); if(CopyRates(_Symbol,signalTF,1,25,r)!=25) return false;
  signalTime=r[0].time; s.open=r[0].open; s.high=r[0].high; s.low=r[0].low; s.close=r[0].close;
  s.previousHigh=r[1].high; s.previousLow=r[1].low;
  if(!ReadValue(hEMA,0,1,s.ema) || !ReadValue(hATR,0,1,s.atr) ||
     !ReadValue(hADX,0,1,s.adx) || !ReadValue(hADX,1,1,s.plusDI) || !ReadValue(hADX,2,1,s.minusDI)) return false;
  if(!dc.weekly && (!ReadValue(h50,0,1,s.sma50) || !ReadValue(h200,0,1,s.sma200) ||
     !ReadValue(h50,0,6,s.oldSma50) || !ReadValue(h200,0,6,oldSMA200))) return false;
  s.lowest=r[0].low; s.highest=r[0].high; s.touched=false; s.priorTouched=false;
  for(int i=0;i<4;i++) {
   if(i<3) { s.lowest=MathMin(s.lowest,r[i].low); s.highest=MathMax(s.highest,r[i].high); }
   double ema=0; if(!ReadValue(hEMA,0,i+1,ema)) return false;
   if(r[i].low<=ema && r[i].high>=ema) { if(i<3) s.touched=true; if(i>=1) s.priorTouched=true; }
  }
  if(!ReadValue(hADX,0,2,s.oldADX)) return false;
  previousClose=r[1].close; ZeroMemory(features); features.previousClose=previousClose;
  double closes[25]; for(int j=0;j<25;j++) closes[j]=r[j].close;
  features.oscillatorValid=EVOOscillator(closes,25,features.fast310,features.previousFast310,features.signal310);
  if(s.atr>0) {
   features.trueRangeATR=MathMax(s.high-s.low,MathMax(MathAbs(s.high-previousClose),MathAbs(s.low-previousClose)))/s.atr;
   features.bodyATR=(s.close-s.open)/s.atr;
  }
  features.closeLocation=s.high>s.low ? (s.close-s.low)/(s.high-s.low) : .5;
  pivotSide=0; pivotTime=0;
  MqlRates pr[]; ArraySetAsSeries(pr,false);
  if(!dc.weekly && CopyRates(_Symbol,signalTF,1,86,pr)==86) {
   double hi[86],lo[86]; for(int k=0;k<86;k++) { hi[k]=pr[k].high; lo[k]=pr[k].low; }
   int key=-1; pivotSide=PEPivotSignal(hi,lo,86,s.close,previousClose,pivotLevel,pivotSwing,key);
   if(key>=0) pivotTime=pr[key].time;
  }
  channelStatus="NOT_USED_M30_PIVOT_PROTOCOL";
  return s.atr>0;
 }
#include "PivotRuntime.mqh"

void Record(const PE_GATE gate,const int setup,const int origin,const H1Signal &s,const MqlTick &q,const datetime signalTime,
             const double sl=0,const double tp=0,const double risk=0,const string detail="")
 {
  counters[(int)gate]++;
  if(hpSignal.buy) {
   if(gate==G_POSITION && hpRoute.path==HP_PIVOT) hpPositionBlocks++;
   string candidate="signal="+TS((datetime)hpSignal.signal_time)+"; available="+TS((datetime)hpSignal.available_time);
   candidate+="; p1="+TS((datetime)hpSignal.p1_time)+"; p2="+TS((datetime)hpSignal.p2_time)+"; p3="+TS((datetime)hpSignal.p3_time);
   candidate+="; original_gate="+I(hpRoute.original_gate)+"; extra_gate="+I(hpRoute.extra_gate)+"; entry_path="+HPPathName(hpRoute.path)+"; gate="+EnumToString(gate);
   Event("PIVOT_CANDIDATE",active,candidate);
  }
  bool saveBar=InpExportAllBars || setup==0 || gate==G_NO_DATA || gate==G_HALTED ||
    (s.close>s.open && s.ema>s.sma50 && s.close>s.sma200) || gate==G_FILLED;
  string row="";
  if(saveBar && barsFile!=INVALID_HANDLE) {
  Cell(row,TS(TimeCurrent())); Cell(row,TS(signalTime)); Cell(row,I(InpCase)); Cell(row,I(origin)); Cell(row,EnumToString(gate));
  Cell(row,I(setup)); Cell(row,I(active>=0 ? cycles[active].number : 0));
  Cell(row,N(s.open)); Cell(row,N(s.high)); Cell(row,N(s.low)); Cell(row,N(s.close)); Cell(row,N(s.ema));
  Cell(row,N(s.sma50)); Cell(row,N(s.sma200)); Cell(row,N(s.oldSma50)); Cell(row,N(oldSMA200));
  Cell(row,N(s.adx)); Cell(row,N(s.plusDI)); Cell(row,N(s.minusDI)); Cell(row,N(s.atr));
  Cell(row,N(q.bid)); Cell(row,N(q.ask)); Cell(row,N(sl)); Cell(row,N(tp)); Cell(row,N(risk));
  Cell(row,N(AccountInfoDouble(ACCOUNT_BALANCE))); Cell(row,N(AccountInfoDouble(ACCOUNT_EQUITY))); Cell(row,detail);
  Cell(row,I(pivotSide)); Cell(row,N(pivotLevel)); Cell(row,N(pivotSwing)); Cell(row,TS(pivotTime));
  Cell(row,N(s.atr>0 ? (s.close-s.ema)/s.atr : 0)); Cell(row,N(s.atr>0 ? (s.sma200-oldSMA200)/s.atr : 0));
  Cell(row,N(s.oldADX)); Cell(row,N(previousClose));
  bool pc=pivotSide!=0 && s.adx>=20 && s.adx>s.oldADX &&
    (pivotSide==1 ? (s.plusDI>s.minusDI && s.close>s.open && s.close>s.ema) : (s.minusDI>s.plusDI && s.close<s.open && s.close<s.ema));
  int sd=0; bool baseOK=H1EvaluateProfile(s,B_PRIOR_PULLBACK,true,20.0,sd)==0 && sd==1 && PEDistance(q.ask,s.ema,s.atr,InpMinEntryATR);
  Cell(row,I(pc)); Cell(row,I(baseOK && s.sma200>oldSMA200)); Cell(row,I(baseOK));
  Cell(row,N(s.atr>0 ? (q.ask-q.bid)/s.atr : 0)); Cell(row,N(s.atr>0 ? (s.close-s.open)/s.atr : 0));
  Cell(row,I(evo.entryPolicy)); Cell(row,I(features.oscillatorValid)); Cell(row,N(features.fast310));
  Cell(row,N(features.previousFast310)); Cell(row,N(features.signal310)); Cell(row,N(features.trueRangeATR));
  Cell(row,N(features.closeLocation));
  Cell(row,TFName(InpCase)); Cell(row,I(dc.channelMode)); Cell(row,I(channelReady)); Cell(row,I(channelBars));
  Cell(row,N(channelUpper)); Cell(row,N(channelLower)); Cell(row,TS(channelOldest)); Cell(row,TS(channelNewest)); Cell(row,TS(channelClosedAt)); Cell(row,channelStatus);
  Cell(row,N(dc.riskPercent)); Cell(row,N(dc.fixedLot ? 0 : InpMaxMarginPct)); Cell(row,N(sizedLot)); Cell(row,N(sizingRiskBudget));
  Cell(row,N(sizingMarginBudget)); Cell(row,N(sizingMargin)); Cell(row,N(AccountInfoDouble(ACCOUNT_MARGIN_FREE)));
  Cell(row,N(AccountInfoDouble(ACCOUNT_MARGIN))); Cell(row,N(minimumLotRiskMoney)); Cell(row,N(minimumLotRiskPercent));
  Cell(row,N(minimumEquityForLot)); Cell(row,N(minimumLotMargin));
  Cell(row,I(dc.sourceControl180)); Cell(row,I(dc.matchedControl)); Cell(row,I(dc.fixedLot)); Cell(row,TargetUnitName());
  Cell(row,N(dc.targetMode==0 ? 5 : 20)); Cell(row,N(plannedTargetDistance)); Cell(row,N(plannedTargetRiskRatio)); Cell(row,N(plannedTargetProfit));
  Cell(row,I(hpDataReady)); Cell(row,hpStatus); Cell(row,I(hpSignal.buy));
  Cell(row,I(hpRoute.original_gate)); Cell(row,I(hpRoute.extra_gate)); Cell(row,HPPathName(hpRoute.path));
  Cell(row,TS((datetime)hpSignal.signal_time)); Cell(row,TS((datetime)hpSignal.available_time));
  Cell(row,N(hpSignal.stop_f1)); Cell(row,N(hpSignal.reference_price)); Cell(row,N(hpSignal.pullback_f2));
  Cell(row,TS((datetime)hpSignal.p1_time)); Cell(row,TS((datetime)hpSignal.p2_time)); Cell(row,TS((datetime)hpSignal.p3_time));
  Cell(row,TS((datetime)hpSignal.p1_confirmation_time)); Cell(row,TS((datetime)hpSignal.p2_confirmation_time)); Cell(row,TS((datetime)hpSignal.p3_confirmation_time));
  Cell(row,TS((datetime)hpSignal.p1_available_time)); Cell(row,TS((datetime)hpSignal.p2_available_time)); Cell(row,TS((datetime)hpSignal.p3_available_time));
  Cell(row,TS((datetime)hpSignal.pattern_available_time)); Cell(row,I(hpProcessedThisBar));
  Cell(row,I(hpState.bars_processed)); Cell(row,TS((datetime)hpState.last_time)); Cell(row,TS((datetime)hpState.expected_open));
  Row(barsFile,row); barRows++;
  }
  if(barsSeen%24==0 && barsFile!=INVALID_HANDLE) FileFlush(barsFile);
  if(MQLInfoInteger(MQL_VISUAL_MODE)) Comment("HERMES PIVOS 2.00 | TESTADOR | ",ProfileName(InpCase),
   "\n",TFName(InpCase)," | Lote base ",DoubleToString(InpFixedLot,2)," | Alvo ",TargetLabel()," | Gestao por perfil",
   "\nCiclos ",ArraySize(cycles)," | ",EnumToString(gate)," | Origem ",origin,
   "\nIntegridade ",integrity ? "OK" : "ERRO: ver events.csv");
 }
void ObserveOpenPath()
 {
  if(active<0) return; double volume=0; ulong ticket=0;
  if(OwnPositions(volume,ticket)<1) return;
  MqlTick q; if(SymbolInfoTick(_Symbol,q) && !PEObserve(cycles[active].path,cycles[active].side==1 ? q.bid : q.ask)) Invalid(102,"Invalid quote for excursion measurement.");
 }
// Closing ownership follows POSITION_IDENTIFIER, including broker/tester exits with magic=0.
// At tester end history contains executed transactions only, not future market bars.
bool AggregateCycle(const int index)
 {
  datetime finish=finalizing ? TimeCurrent()+86400 : TimeCurrent();
  if(!HistorySelect(cycles[index].start,finish)) return false;
  cycles[index].gross=0; cycles[index].swap=0; cycles[index].costs=0;
  cycles[index].inVolume=0; cycles[index].outVolume=0; cycles[index].finish=0;
  for(int i=0;i<HistoryDealsTotal();i++) {
   ulong d=HistoryDealGetTicket(i);
   if(d==0 || HistoryDealGetString(d,DEAL_SYMBOL)!=_Symbol || CycleByPid((ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID))!=index) continue;
   long entry=HistoryDealGetInteger(d,DEAL_ENTRY),side=HistoryDealGetInteger(d,DEAL_TYPE);
   if(side!=DEAL_TYPE_BUY && side!=DEAL_TYPE_SELL) continue;
   cycles[index].gross+=HistoryDealGetDouble(d,DEAL_PROFIT); cycles[index].swap+=HistoryDealGetDouble(d,DEAL_SWAP);
   cycles[index].costs+=HistoryDealGetDouble(d,DEAL_COMMISSION)+HistoryDealGetDouble(d,DEAL_FEE);
   double v=HistoryDealGetDouble(d,DEAL_VOLUME);
   long openingType=cycles[index].side==1 ? DEAL_TYPE_BUY : DEAL_TYPE_SELL;
   if(entry==DEAL_ENTRY_IN && side==openingType) cycles[index].inVolume+=v;
   else if((entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY) && side!=openingType) {
    cycles[index].outVolume+=v; cycles[index].finish=(datetime)HistoryDealGetInteger(d,DEAL_TIME);
    cycles[index].finalPrice=HistoryDealGetDouble(d,DEAL_PRICE); cycles[index].finalReason=HistoryDealGetInteger(d,DEAL_REASON);
   } else return false;
  }
  cycles[index].net=cycles[index].gross+cycles[index].swap+cycles[index].costs;
  return cycles[index].inVolume>0;
 }
void FinishCycle(const int n)
 {
  if(cycles[n].closed) return;
  cycles[n].closed=true;
  // Include the real final fill, never an OHLC high after the position was closed.
  if(!cycles[n].finalObserved && cycles[n].finalPrice>0) {
   if(!PEObserve(cycles[n].path,cycles[n].finalPrice)) Invalid(103,"Invalid final excursion observation.");
   cycles[n].finalObserved=true;
  }
  int mi=MonthIndex(cycles[n].finish); months[mi].closed++; months[mi].cycleNet+=cycles[n].net;
  Event("CYCLE_CLOSED",n,"net="+N(cycles[n].net)+"; MFE_R="+N(cycles[n].path.maxR));
 }
void SyncCycle()
 {
  if(active<0) return; double volume=0; ulong ticket=0; int count=OwnPositions(volume,ticket);
  maxLots=MathMax(maxLots,volume); maxMargin=MathMax(maxMargin,AccountInfoDouble(ACCOUNT_MARGIN));
  if(count>0 || OwnPendingOrder()) return;
  int n=active;
  if(!AggregateCycle(n) || MathAbs(cycles[n].inVolume-cycles[n].outVolume)>1e-8) { Invalid(104,"Closed cycle cannot be reconciled by position identifier."); return; }
  FinishCycle(n); active=-1;
 }

#include "Execution.mqh"

PE_GATE OpenCycle(const int origin,const int side,const H1Signal &s,const MqlTick &q,const datetime signalTime,
                  double &sl,double &tp,double &risk,string &detail)
 {
  double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),entry=side==1 ? q.ask : q.bid;
  H1Signal setup=s; if(evo.entryPolicy==8) { setup.lowest=pivotSwing; setup.highest=pivotSwing; }
  if(!H1Levels(side,entry,setup,.20,1.0,2.5,5.0,tick,sl,tp)) return G_STOP;
  // Original structural stop is retained in every case.
  if(dc.minimumStopATR>1.0 && !DCStructuralStopAccepted(entry,sl,s.atr,dc.minimumStopATR)) {
   detail="Structural stop below required ATR distance; not widened."; return G_STOP;
  }
  if(dc.targetMode>0) {
   double distance=HermesTargetDistance(dc.targetMode,_Point);
   if(!HermesTargetPrice(side,entry,distance,tick,tp)) {
    targetRejects++; detail="Target below one tick, invalid units or non-representable target; no widening."; return G_TARGET;
   }
  }
  plannedTargetDistance=side*(tp-entry); plannedTargetRiskRatio=plannedTargetDistance/MathAbs(entry-sl);
  sl=NormalizeDouble(sl,_Digits); tp=NormalizeDouble(tp,_Digits);
  double minstop=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
  double closePrice=side==1 ? q.bid : q.ask;
  if(side*(closePrice-sl)<minstop || side*(tp-closePrice)<minstop || sl<=0 || tp<=0) {
   detail="Broker stop distance not met; target and structural stop were not enlarged.";
   if(dc.targetMode>0) targetRejects++;
   return G_BROKER_STOPS;
  }
  double mn=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),mx=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX),step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
  if(!MathIsValidNumber(mn) || !MathIsValidNumber(mx) || !MathIsValidNumber(step) || mn<=0 || mx<mn || step<=0) return G_RISK;
  double volume=InpFixedLot,profit=0,margin=0;
  ENUM_ORDER_TYPE type=side==1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
  if(dc.fixedLot) {
   sizingMarginBudget=AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(!HermesExactLot(volume,mn,mx,step)) {
    fixedVolumeRejects++; detail="Exact fixed lot incompatible with symbol min/max/step; NOT reduced."; return G_RISK;
   }
  } else {
   double referenceLoss=0,referenceMargin=0;
   if(!OrderCalcProfit(type,_Symbol,mn,entry,sl,referenceLoss) || referenceLoss>=0) return G_RISK;
   if(!OrderCalcMargin(type,_Symbol,mn,entry,referenceMargin)) return G_MARGIN_ERROR;
   double eq=AccountInfoDouble(ACCOUNT_EQUITY),free=AccountInfoDouble(ACCOUNT_MARGIN_FREE),used=AccountInfoDouble(ACCOUNT_MARGIN);
   minimumLotRiskMoney=-referenceLoss; minimumLotMargin=referenceMargin;
   minimumLotRiskPercent=eq>0 ? 100*(-referenceLoss)/eq : 0;
   minimumEquityForLot=MathMax((-referenceLoss)*100.0/dc.riskPercent,(used+referenceMargin)*100.0/InpMaxMarginPct);
   sizingRiskBudget=eq*dc.riskPercent/100.0;
   sizingMarginBudget=MathMin(free,MathMax(0,eq*InpMaxMarginPct/100.0-used));
   volume=DCRiskLot(eq,free,used,dc.riskPercent,InpMaxMarginPct,-referenceLoss/mn,referenceMargin/mn,mn,mx,step,InpMaxLot);
   if(volume<=0) { detail="Volume below broker minimum within risk/margin budgets; no forced minimum."; riskBlocks++; return G_RISK; }
   // Contract margin may be tiered. Revalue the proposed volume and step down using native values.
   for(int tries=0;tries<8;tries++) {
    if(!OrderCalcProfit(type,_Symbol,volume,entry,sl,profit) || profit>=0) return G_RISK;
    if(!OrderCalcMargin(type,_Symbol,volume,entry,margin)) return G_MARGIN_ERROR;
    if(-profit<=sizingRiskBudget+1e-7 && margin<=sizingMarginBudget+1e-7) break;
    double ratio=MathMin(sizingRiskBudget/(-profit),margin>0 ? sizingMarginBudget/margin : 1.0);
    volume=MathFloor(MathMin(volume-step,volume*ratio)/step+1e-9)*step;
    if(volume<mn-1e-9) { riskBlocks++; return G_RISK; }
   }
  }
  sizedLot=volume;
  if(H1Volume(FIXED_LOT,volume,1,1,mn,mx,step)<=0) return G_RISK;
  if(!OrderCalcProfit(type,_Symbol,volume,entry,sl,profit) || profit>=0) return G_RISK;
  risk=-profit;
  if(!OrderCalcMargin(type,_Symbol,volume,entry,margin)) return G_MARGIN_ERROR;
  sizingMargin=margin;
  if(!dc.fixedLot && risk>sizingRiskBudget+1e-7) { riskBlocks++; return G_RISK; }
  if(!HermesMarginAvailable(margin,AccountInfoDouble(ACCOUNT_MARGIN_FREE)) || (!dc.fixedLot && margin>sizingMarginBudget+1e-7)) {
   detail="Required margin="+N(margin)+"; free="+N(AccountInfoDouble(ACCOUNT_MARGIN_FREE))+"; fixed lot is not reduced.";
   return G_MARGIN_BLOCK;
  }
  if(!OrderCalcProfit(type,_Symbol,volume,entry,tp,plannedTargetProfit)) { detail="Cannot value target profit."; return G_TARGET; }
  double balance=AccountInfoDouble(ACCOUNT_BALANCE); int number=ArraySize(cycles)+1;
  string comment="HP200-O"+I(origin)+"-N"+I(number);
  bool sent=side==1 ? trade.Buy(volume,_Symbol,0,sl,tp,comment) : trade.Sell(volume,_Symbol,0,sl,tp,comment);
  uint ret=trade.ResultRetcode(); detail="ret="+I(ret)+"; deal="+U(trade.ResultDeal())+"; "+trade.ResultRetcodeDescription();
  if(!sent || ret!=TRADE_RETCODE_DONE) {
   lastRetcode=(int)ret; lastErrorTime=TimeCurrent(); Event("ENTRY_REJECTED",-1,detail,ret);
   if(PERetcodeClass(ret)==2 || ret==TRADE_RETCODE_DONE) Invalid(201,"Initial order uncertain; no duplicate entry allowed.",true);
   return G_REJECTED;
  }
  ulong deal=trade.ResultDeal();
  if(deal==0 || !HistoryDealSelect(deal) || HistoryDealGetString(deal,DEAL_SYMBOL)!=_Symbol ||
     (ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=InpMagic || HistoryDealGetInteger(deal,DEAL_ENTRY)!=DEAL_ENTRY_IN ||
     HistoryDealGetInteger(deal,DEAL_TYPE)!=(side==1 ? DEAL_TYPE_BUY : DEAL_TYPE_SELL)) { Invalid(202,"Entry fill identity missing.",true); return G_HALTED; }
  int n=ArraySize(cycles); ArrayResize(cycles,n+1); ZeroMemory(cycles[n]); active=n;
  cycles[n].entryPath=hpRoute.path;
  if(hpRoute.path==HP_PIVOT) cycles[n].entryPivot=hpSignal;
  cycles[n].number=number; cycles[n].origin=origin; cycles[n].side=side; cycles[n].legs=1;
  cycles[n].pid=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID); cycles[n].pids[0]=cycles[n].pid;
  cycles[n].start=(datetime)HistoryDealGetInteger(deal,DEAL_TIME); cycles[n].signalTime=signalTime;
  cycles[n].quotedEntry=entry; cycles[n].quotedTarget=tp; cycles[n].targetDistance=HermesTargetDistance(dc.targetMode,_Point);
  cycles[n].entry=HistoryDealGetDouble(deal,DEAL_PRICE); cycles[n].volume=HistoryDealGetDouble(deal,DEAL_VOLUME);
  cycles[n].fills[0]=cycles[n].entry; cycles[n].volumes[0]=cycles[n].volume; cycles[n].expectedStops[0]=sl;
  cycles[n].stop=sl; cycles[n].liveStop=sl; cycles[n].desiredStop=sl; cycles[n].target=tp; cycles[n].balanceBefore=balance;
  cycles[n].partialEnabled=profile.partial || (origin==14 && profile.protect14);
  cycles[n].beTrigger=cycles[n].partialEnabled ? 1.0 : ((profile.mode==0 && origin!=15) ? 0 : profile.be15);
  cycles[n].path.entry=cycles[n].entry; cycles[n].path.stop=sl; cycles[n].path.side=side;
  cycles[n].entryPolicy=evo.entryPolicy; cycles[n].entryFeatures=features;
  cycles[n].featureADXChange=s.adx-s.oldADX; cycles[n].featureADX=s.adx; cycles[n].featureATR=s.atr;
  cycles[n].featureDistance=(entry-s.ema)/s.atr; cycles[n].featureSlope=(s.sma200-oldSMA200)/s.atr;
  if(cycles[n].pid==0 || side*(cycles[n].entry-sl)<=0 || MathAbs(cycles[n].volume-volume)>1e-8)
    Invalid(203,"Initial fill does not match planned volume/stop.",true);
  if(!OrderCalcProfit(type,_Symbol,volume,cycles[n].entry,sl,profit) || profit>=0) Invalid(204,"Cannot value initial risk.",true);
  else { cycles[n].initialRisk=-profit; cycles[n].peakRisk=-profit; maxRisk=MathMax(maxRisk,-profit); if(balance>0) maxRiskPct=MathMax(maxRiskPct,-profit/balance*100); }
  maxLots=MathMax(maxLots,volume); MonthIndex(cycles[n].start); months[liveMonth].opened++;
  if(evo.entryPolicy==8) lastPivotUsed=pivotTime;
  detail+="; entry_path="; detail+=(hpRoute.path==HP_PIVOT ? "PIVOT" : "BASE");
  detail+="; original_gate="+I(hpRoute.original_gate)+"; extra_gate="+I(hpRoute.extra_gate);
  if(hpRoute.path==HP_PIVOT) {
   hpPivotFills++;
   detail+="; pivot_signal_time="+I(hpSignal.signal_time)+"; p1_time="+I(hpSignal.p1_time)+"; p2_time="+I(hpSignal.p2_time)+"; p3_time="+I(hpSignal.p3_time);
  }
  Event("ENTRY_FILLED",n,detail); ObserveOpenPath(); EnforceTargetCap();
  if(!closeEmergency && PositionForLeg(n,0,deal)) {
   double estimate=0;
   if(OrderCalcProfit(type,_Symbol,cycles[n].volume,cycles[n].entry,cycles[n].target,estimate)) cycles[n].targetProfitEstimate=estimate;
  }
  CheckProtection(); SyncCycle(); return G_FILLED;
 }
void OnTick()
 {
  if(!initialized) return;
  TrackEquity(); ObserveOpenPath(); SyncCycle();
  if(closeEmergency) { EmergencyClose(); TrackEquity(); return; }
  ManageProtection(); TrackEquity(); SyncCycle();
  datetime bar=iTime(_Symbol,signalTF,0); bool newBar=bar>0 && bar!=lastBar;
  if(!newBar) { if(profile.arm==8) ManageAdd(false,false); return; }
  lastBar=bar; lastEval=TimeCurrent(); if(firstEval==0) firstEval=lastEval;
  barsSeen++; int mi=MonthIndex(TimeCurrent()); months[mi].bars++;
  hpRoute.original_gate=-1; hpRoute.extra_gate=HP_DATA_PENDING; hpRoute.setup=-1; hpRoute.side=0; hpRoute.path=HP_NONE;
  hpDataReady=HPSyncClosedBars(bar);
  if(!hpDataReady) hpDataFailures++;
  if(hpSignal.buy) hpCandidates++;
  H1Signal s; ZeroMemory(s); MqlTick q; ZeroMemory(q); datetime signalTime=0;
  sizedLot=0; sizingRiskBudget=0; sizingMarginBudget=0; sizingMargin=0;
  plannedTargetDistance=0; plannedTargetRiskRatio=0; plannedTargetProfit=0;
  minimumLotRiskMoney=0; minimumLotRiskPercent=0; minimumEquityForLot=0; minimumLotMargin=0;
  channelReady=false; channelBars=0; channelUpper=0; channelLower=0; channelOldest=0; channelNewest=0; channelClosedAt=0; channelStatus="SIGNAL_DATA_PENDING";
  if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<q.bid || !ReadSignal(s,signalTime)) { Record(G_NO_DATA,-1,0,s,q,signalTime); return; }
  if(dc.channelMode>0 && !channelReady) { Record(G_NO_DATA,120,evo.family,s,q,signalTime,0,0,0,channelStatus); return; }
  if(firstReady==0 && (dc.channelMode==0 || channelReady)) firstReady=TimeCurrent();
  int side=0;
  double minimumEntryDistance=InpMinEntryATR;
  HPRouteEntry(InpCase,evo,s,features,q.ask,oldSMA200,minimumEntryDistance,
               hpDataReady,hpSignal,hpRoute);
  int setup=hpRoute.setup; side=hpRoute.side;
  if(hpRoute.extra_gate==0) hpExtraEligible++;
  if(hpRoute.path==HP_BASE) hpBaseSelected++;
  if(hpRoute.path==HP_PIVOT) hpPivotSelected++;
  bool pivotOK=pivotSide!=0 && pivotTime!=lastPivotUsed && s.adx>=20 && s.adx>s.oldADX &&
    (pivotSide==1 ? (s.plusDI>s.minusDI && s.close>s.open && s.close>s.ema) : (s.minusDI>s.plusDI && s.close<s.open && s.close<s.ema));
  if(pivotOK) { if(pivotSide==1) patternBuys++; else patternSells++; }
  if(setup==0) { signals++; months[mi].signals++; }
  if(haltEntries) { Record(G_HALTED,setup,0,s,q,signalTime); return; }
  bool recovery=s.close>s.open && s.close>previousClose && s.adx>=20 && s.plusDI>s.minusDI && s.close>s.sma200 &&
    s.ema>s.sma50 && s.sma50>s.oldSma50 && (cyclesSizeOrigin15() ? s.sma200>oldSMA200 : true);
  if(active>=0) { ManageAdd(true,recovery); Record(G_POSITION,setup,active>=0 ? cycles[active].origin : 0,s,q,signalTime); return; }
  if(SymbolExposure()) { Record(G_POSITION,setup,0,s,q,signalTime); return; }
  if(InpMaxSpreadPoints>0 && (q.ask-q.bid)/_Point>InpMaxSpreadPoints) { Record(G_SPREAD,setup,0,s,q,signalTime); return; }
  int origin=evo.family;
  if(setup!=0) {
   PE_GATE gate=setup==120 ? G_NO_DATA : setup==110 ? G_DISTANCE : (setup==111 ? G_REGIME : (setup==109 ? G_DIRECTION : (setup>=100 ? G_ENTRY_FILTER : G_BASE)));
   Record(gate,setup,origin,s,q,signalTime); return;
  }
  double sl=0,tp=0,risk=0; string detail=""; PE_GATE result=OpenCycle(origin,side,s,q,signalTime,sl,tp,risk,detail);
  Record(result,setup,origin,s,q,signalTime,sl,tp,risk,detail); if(closeEmergency) EmergencyClose(); TrackEquity();
 }
bool cyclesSizeOrigin15() { return active>=0 && cycles[active].origin==15; }
bool WriteParameters()
 {
  int f=OpenText(folder+"\\parameters.txt"); if(f==INVALID_HANDLE) return false;
  KV(f,"EA","Hermes_Pivos_Lab_200"); KV(f,"version","2.00"); KV(f,"case",I(InpCase)); KV(f,"profile",ProfileName(InpCase));
  KV(f,"run_tag",InpRunTag); KV(f,"symbol",_Symbol); KV(f,"currency",AccountInfoString(ACCOUNT_CURRENCY));
  KV(f,"signal_tf",TFName(InpCase)); KV(f,"source_control170","28"); KV(f,"source_control180",I(dc.sourceControl180)); KV(f,"matched_control190",I(dc.matchedControl));
  KV(f,"risk_percent",N(dc.riskPercent)); KV(f,"margin_cap_percent",dc.fixedLot ? "no_extra_percent_cap_free_margin_only" : N(InpMaxMarginPct));
  KV(f,"max_lot",dc.fixedLot ? N(InpFixedLot) : N(InpMaxLot)); KV(f,"initial_lot_reference",N(InpFixedLot));
  KV(f,"fixed_lot_mode",I(dc.fixedLot)); KV(f,"capital_mode",dc.fixedLot ? "EXACT_FIXED_LOT" : "EQUITY_RISK_2PCT");
  KV(f,"target_unit",TargetUnitName()); KV(f,"target_unit_code",I(dc.targetMode)); KV(f,"target_value",dc.targetMode==0 ? "5" : "20");
  KV(f,"resolved_target_distance_price",N(HermesTargetDistance(dc.targetMode,_Point)));
  KV(f,"target_R",dc.targetMode==0 ? "5" : "variable_target_divided_by_original_stop"); KV(f,"partial_enabled","0"); KV(f,"BE_trigger_R","0"); KV(f,"max_adds","0");
  KV(f,"case_protocol","1 HERMES_REFERENCIA;2 HERMES_PIVO_CONTINUIDADE;3 HERMES_PIVO_INICIO. All M30, exact fixed lot, target5R, no partial/BE/add/reinvestment.");
  KV(f,"reference_source_sha256","0ddbee937fc4b5af16510987f84d72e126012e0a080b61ef18530a80275d8e35");
  KV(f,"reference_EA","Olimpo_Consistencia_Lab_190 case2");
  KV(f,"native_compilation_or_backtest_by_assistant","false; native user validation pending");
  KV(f,"M30_entry","Original Hermes rules: EMA21>SMA50; rising SMA50/SMA200; close>SMA200; ADX14>=20; +DI>-DI; prior EMA touch; bullish close above EMA21 and prior high; ask-EMA>=minimum_distance_ATR. Always original first.");
  KV(f,"extra_entry_common","Fresh causal confirmed LONG 1-2-3 neckline cross; bullish closed candle above EMA21; EMA21>SMA50 and SMA50>SMA50[6]; ADX14>=20; +DI>-DI; valid SMA3-SMA10 oscillator greater than its previous value; ask-EMA>=minimum_distance_ATR.");
  KV(f,"extra_entry_case2","Also close>SMA200 and SMA200>SMA200[6].");
  KV(f,"extra_entry_case3","Only the two SMA200 conditions are omitted for the extra entry; original entry rules unchanged.");
  KV(f,"entry_priority","Extra only when original EVOEvaluate fails. An original signal later rejected by stop/margin/spread does not fall back to another entry. One position; pivot event consumed even while blocked.");
  KV(f,"pivot_algorithm","HERMES_PIVOS_2x2_V1; strict 2-left/2-right extrema; tied extrema excluded; double-extreme candle resets alternating sequence; L1-H-L2 with L1<L2<H; closed crossing of H; known before trigger open; invalidated by low<=L1. Geometric L1 is NOT execution stop.");
  KV(f,"pivot_time_rule","Pivots available at next observed opening after second right candle; breakout evaluated only using references known at breakout-bar open; no open-candle OHLC used.");
  KV(f,"pivot_seed","210 closed bars seeded chronologically once; only latest signal may be traded; subsequent closed bars caught up continuously, including occupied periods; historical catch-up signals discarded. Seed boundary may differ from a catalog started in 2022.");
  KV(f,"pivot_data_failure","Extra entries blocked only; original reference remains eligible. State not advanced on incomplete/invalid copy; next bar retries chronological catch-up. No synthetic history.");
  KV(f,"minimum_structural_stop_ATR",N(dc.minimumStopATR));
  KV(f,"stop","Original: minimum low of closed signal plus 2 prior bars minus .20ATR14; entry-stop must be1..2.5ATR or reject. No widening and no replacing stop with geometric L1.");
  KV(f,"sizing","Every case exact InpFixedLot=1.00 default; native free-margin and volume constraints; unavailable lot rejected, never silently reduced. InpMaxMarginPct/InpMaxLot are retained compatibility inputs and unused in these fixed-lot cases.");
  KV(f,"target_execution","Original H1Levels5R quoted-entry target with attached server SL/TP. Tick rounding and actual slippage retained from reference; fills/costs can change realized R. No partial, no BE, no averaging or pyramiding.");
  KV(f,"minimum_distance_ATR",N(InpMinEntryATR)); KV(f,"all_bars",I(InpExportAllBars));
  KV(f,"channel_mode","0_not_used");
  KV(f,"warmup","Original minimum209 bars unchanged; extra pivot seed needs210 closed bars plus current opening witness. Signal indicator failure remains G_NO_DATA.");
  KV(f,"entry_frequency","One decision per new M30 bar, only closed inputs. Extra candidates are hypotheses, not guaranteed fills or profits.");
  KV(f,"account_margin_mode",I(AccountInfoInteger(ACCOUNT_MARGIN_MODE))); KV(f,"leverage",I(AccountInfoInteger(ACCOUNT_LEVERAGE)));
  KV(f,"account_stopout_mode",I(AccountInfoInteger(ACCOUNT_MARGIN_SO_MODE)));
  KV(f,"account_margin_call_level",N(AccountInfoDouble(ACCOUNT_MARGIN_SO_CALL)));
  KV(f,"account_stopout_level",N(AccountInfoDouble(ACCOUNT_MARGIN_SO_SO)));
  KV(f,"initial_deposit",N(initialDeposit)); KV(f,"point",N(_Point)); KV(f,"tick_size",N(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE)));
  KV(f,"contract_size",N(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE)));
  KV(f,"tick_value_profit",N(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE_PROFIT))); KV(f,"tick_value_loss",N(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE_LOSS)));
  KV(f,"volume_min",N(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN))); KV(f,"volume_max",N(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX))); KV(f,"volume_step",N(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP)));
  KV(f,"margin_initial",N(SymbolInfoDouble(_Symbol,SYMBOL_MARGIN_INITIAL))); KV(f,"margin_maintenance",N(SymbolInfoDouble(_Symbol,SYMBOL_MARGIN_MAINTENANCE))); KV(f,"trade_calc_mode",I(SymbolInfoInteger(_Symbol,SYMBOL_TRADE_CALC_MODE)));
  KV(f,"magic",U(InpMagic)); KV(f,"deviation_points",U(InpDeviationPoints)); KV(f,"max_spread_points",N(InpMaxSpreadPoints));
  KV(f,"scope","Strategy Tester only; predeclared hypotheses, no fitted future outcomes. Profit unknown; native report needed for dates/tick quality/model/latency.");
  FileClose(f); return !ioFailure;
 }
int OnInit()
 {
  if(!MQLInfoInteger(MQL_TESTER)) { Print("Use Ctrl+R. EA de pesquisa, exclusivo do Testador de Estrategias."); return INIT_FAILED; }
  if(!HPSelectProfile(InpCase,dc,evo,profile) || !ValidRunTag()) return INIT_PARAMETERS_INCORRECT;
  signalTF=PERIOD_M30; HPCoreReset(hpState); HPClearSignal(hpSignal);
  if(_Period!=signalTF) { Print("Caso ",InpCase," exige ",TFName(InpCase)," no testador."); return INIT_PARAMETERS_INCORRECT; }
  if(!MathIsValidNumber(InpMaxMarginPct) || InpMaxMarginPct<=0 || InpMaxMarginPct>50 ||
     !MathIsValidNumber(InpMaxLot) || InpMaxLot<=0) return INIT_PARAMETERS_INCORRECT;
  string symbol=_Symbol; StringToUpper(symbol); if(StringFind(symbol,"XAU")<0 && StringFind(symbol,"GOLD")<0) return INIT_PARAMETERS_INCORRECT;
  if((profile.reinvest && evo.lotCap<InpFixedLot) || !MathIsValidNumber(InpFixedLot) || InpFixedLot<=0 || !MathIsValidNumber(InpMinEntryATR) || InpMinEntryATR<0 || InpMinEntryATR>3 ||
    !MathIsValidNumber(InpMaxSpreadPoints) || InpMaxSpreadPoints<0) return INIT_PARAMETERS_INCORRECT;
  double mn=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),mx=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX),step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
  if(!MathIsValidNumber(mn) || !MathIsValidNumber(mx) || !MathIsValidNumber(step) || mn<=0 || mx<mn || step<=0) return INIT_PARAMETERS_INCORRECT;
  if(dc.fixedLot && !HermesExactLot(InpFixedLot,mn,mx,step))
   Print("Lote fixo incompativel; sinais serao registrados como recusados, sem reduzir volume.");
  if(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE)<=0) return INIT_PARAMETERS_INCORRECT;
  if(profile.addFraction>0 && AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING) {
   Print("Perfis com adicoes exigem conta HEDGE no testador; nao executados em NETTING."); return INIT_PARAMETERS_INCORRECT;
  }
  initialDeposit=AccountInfoDouble(ACCOUNT_BALANCE); LoadSessions();
  TesterHideIndicators(true); hEMA=iMA(_Symbol,signalTF,21,0,MODE_EMA,PRICE_CLOSE);
  if(!dc.weekly) { h50=iMA(_Symbol,signalTF,50,0,MODE_SMA,PRICE_CLOSE); h200=iMA(_Symbol,signalTF,200,0,MODE_SMA,PRICE_CLOSE); }
  hADX=iADX(_Symbol,signalTF,14); hATR=iATR(_Symbol,signalTF,14);
  if(hEMA==INVALID_HANDLE || (!dc.weekly && (h50==INVALID_HANDLE || h200==INVALID_HANDLE)) || hADX==INVALID_HANDLE || hATR==INVALID_HANDLE) return INIT_FAILED;
  trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpDeviationPoints); trade.SetAsyncMode(false); trade.SetTypeFillingBySymbol(_Symbol);
  ArrayInitialize(counters,0); priorEquity=AccountInfoDouble(ACCOUNT_EQUITY); priorBalance=AccountInfoDouble(ACCOUNT_BALANCE);
  MqlRates warmup[]; int required=dc.weekly ? 55 : 209;
  int count=CopyRates(_Symbol,signalTF,0,required,warmup);
  if(count<required) Print("Aquecimento incompleto ",count,"/",required,". Verifique G_NO_DATA.");

  if(InpExportCSV && (!MQLInfoInteger(MQL_OPTIMIZATION) || InpExportOptimizationDetails)) {
   FolderCreate("Hermes_Pivos_Lab_200",FILE_COMMON); FolderCreate(RunRoot(),FILE_COMMON);
   folder=RunRoot()+"\\CASO_"+I(InpCase)+"_"+TFName(InpCase)+"_"+Stamp();
   if(!FolderCreate(folder,FILE_COMMON)) return INIT_FAILED;
   barsFile=OpenText(folder+"\\bars.csv"); eventsFile=OpenText(folder+"\\events.csv");
   if(barsFile==INVALID_HANDLE || eventsFile==INVALID_HANDLE || !WriteParameters()) return INIT_FAILED;
   Row(eventsFile,"time_server;case;cycle;origin_case140;event;retcode;detail");
   Row(barsFile,"event_time;signal_time;case;origin_case140;gate;setup_gate;cycle;open;high;low;close;ema21;sma50;sma200;old_sma50;old_sma200;adx;plus_di;minus_di;atr;bid;ask;sl;tp;risk_money;balance;equity;detail;pivot_side;pivot_break_level;pivot_stop_swing;pivot_time;distance_atr;sma200_slope_atr;previous_adx;previous_close;pivot_pattern_eligible;original15_candidate;original14_candidate;spread_atr;body_atr;entry_policy;oscillator_valid;fast310;previous_fast310;signal310;true_range_atr;close_location;signal_tf;donchian_mode;donchian_ready;donchian_bars;donchian_upper;donchian_lower;donchian_oldest_open;donchian_newest_open;donchian_latest_close;donchian_status;risk_percent;margin_cap_percent;planned_lot;risk_budget;margin_budget;planned_margin;free_margin;used_margin;minimum_lot_risk_money;minimum_lot_risk_percent;minimum_equity_for_minimum_lot;minimum_lot_margin;source_control180;matched_control190;fixed_lot_mode;target_unit;target_value;planned_target_distance_price;planned_target_R;planned_target_gross_profit;hp_data_ready;hp_status;hp_candidate;hp_original_gate;hp_extra_gate;selected_entry_path;hp_signal_time;hp_available_time;hp_p1_price;hp_p2_price;hp_p3_price;hp_p1_time;hp_p2_time;hp_p3_time;hp_p1_confirmation_time;hp_p2_confirmation_time;hp_p3_confirmation_time;hp_p1_available_time;hp_p2_available_time;hp_p3_available_time;hp_pattern_available_time;hp_processed_this_bar;hp_total_processed;hp_last_processed_open;hp_expected_next_open");
   Print("RELATORIOS: ",TerminalInfoString(TERMINAL_COMMONDATA_PATH),"\\Files\\",folder);
  }
  if(InpShowIndicators && MQLInfoInteger(MQL_VISUAL_MODE)) {
   ChartIndicatorAdd(0,0,hEMA); if(!dc.weekly) { ChartIndicatorAdd(0,0,h50); ChartIndicatorAdd(0,0,h200); }
   ChartIndicatorAdd(0,(int)ChartGetInteger(0,CHART_WINDOWS_TOTAL),hADX); ChartIndicatorAdd(0,(int)ChartGetInteger(0,CHART_WINDOWS_TOTAL),hATR);
  }
  if(ioFailure) return INIT_FAILED;
  initialized=true; Print("Hermes Pivos 2.00: ",ProfileName(InpCase),". Hipotese fixa; detalhes por caso."); return INIT_SUCCEEDED;
 }

#include "Reports.mqh"

void OnDeinit(const int reason)
 {
  if(barsFile!=INVALID_HANDLE) FileClose(barsFile); if(eventsFile!=INVALID_HANDLE) FileClose(eventsFile);
  if(hEMA!=INVALID_HANDLE) IndicatorRelease(hEMA); if(h50!=INVALID_HANDLE) IndicatorRelease(h50); if(h200!=INVALID_HANDLE) IndicatorRelease(h200);
  if(hADX!=INVALID_HANDLE) IndicatorRelease(hADX); if(hATR!=INVALID_HANDLE) IndicatorRelease(hATR); Comment("");
 }
