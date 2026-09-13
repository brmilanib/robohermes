// Execution is ticket-based. Volume changes are never blindly retried after
// an ambiguous reply. Baseline broker SL/TP remain while an amendment is deferred.
void LoadSessions()
 {
  sessionCount=0; sessionKnown=false;
  for(int d=0;d<7;d++) for(uint i=0;i<18;i++) {
   datetime from=0,to=0; if(!SymbolInfoSessionTrade(_Symbol,(ENUM_DAY_OF_WEEK)d,i,from,to)) break;
   if(sessionCount>=128) break;
   sessionKnown=true; sessionDay[sessionCount]=d; sessionFrom[sessionCount]=(int)((long)from%86400);
   sessionTo[sessionCount]=(int)((long)to%86400); sessionCount++;
  }
 }
bool SessionOpen()
 {
  if(!sessionKnown) return true; // server remains authoritative when schedule is unavailable
  MqlDateTime dt; TimeToStruct(TimeCurrent(),dt); int sec=dt.hour*3600+dt.min*60+dt.sec;
  for(int i=0;i<sessionCount;i++) {
   int a=sessionFrom[i],b=sessionTo[i],day=sessionDay[i];
   if(a==b && day==dt.day_of_week) return true;
   if(b>a && day==dt.day_of_week && sec>=a && sec<b) return true;
   if(b<a && ((day==dt.day_of_week && sec>=a) || ((day+1)%7==dt.day_of_week && sec<b))) return true;
  }
  return false;
 }
bool CanRequest()
 { return SessionOpen() && MQLInfoInteger(MQL_TRADE_ALLOWED) && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) &&
    AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) && AccountInfoInteger(ACCOUNT_TRADE_EXPERT); }
ENUM_ORDER_TYPE_FILLING Filling()
 {
  long flags=SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE);
  if((flags&SYMBOL_FILLING_FOK)!=0) return ORDER_FILLING_FOK;
  if((flags&SYMBOL_FILLING_IOC)!=0) return ORDER_FILLING_IOC;
  return ORDER_FILLING_RETURN;
 }
bool PositionForLeg(const int n,const int leg,ulong &ticket)
 {
  ticket=0;
  for(int i=PositionsTotal()-1;i>=0;i--) {
   ulong t=PositionGetTicket(i);
   if(t>0 && PositionGetString(POSITION_SYMBOL)==_Symbol &&
      (ulong)PositionGetInteger(POSITION_IDENTIFIER)==cycles[n].pids[leg]) { ticket=t; return true; }
  }
  return false;
 }
// Only narrows a configured fixed-distance TP. Never widens target or SL.
// The broker SL/TP stays attached during a rejected amendment. Failures halt
// entries and request a ticket-based protected close, recorded as invalid run.
void EnforceTargetCap()
 {
  if(active<0 || dc.targetMode==0 || closeEmergency) return;
  int n=active; ulong ticket=0; if(!PositionForLeg(n,0,ticket)) return;
  double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  double liveTarget=PositionGetDouble(POSITION_TP),sl=PositionGetDouble(POSITION_SL);
  double distance=cycles[n].side*(liveTarget-cycles[n].entry);
  double tolerance=MathMax(1e-10,tick*1e-7);
  if(liveTarget<=0 || distance<=0 || sl<=0) {
   targetFailures++; Invalid(330,"Invalid fixed-target protection after fill.",true); return;
  }
  if(distance<=cycles[n].targetDistance+tolerance) return;
  double allowed=0;
  if(!HermesTargetPrice(cycles[n].side,cycles[n].entry,cycles[n].targetDistance,tick,allowed)) {
   targetFailures++; Invalid(331,"Actual fill cannot represent requested target cap.",true); return;
  }
  MqlTick q;
  if(!CanRequest() || !SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<q.bid) {
   targetFailures++; Invalid(332,"Target cap cannot be confirmed; protected close requested.",true); return;
  }
  double cp=cycles[n].side==1 ? q.bid : q.ask;
  double minDistance=MathMax(SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL),SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL))*_Point;
  if(cycles[n].side*(allowed-cp)<minDistance || cycles[n].side*(cp-sl)<minDistance) {
   targetFailures++; Invalid(333,"Target cap amendment blocked by stops/freeze; protected close requested.",true); return;
  }
  MqlTradeRequest req={}; MqlTradeResult res={}; req.action=TRADE_ACTION_SLTP; req.position=ticket;
  req.symbol=_Symbol; req.magic=InpMagic; req.sl=sl; req.tp=NormalizeDouble(allowed,_Digits);
  bool sent=OrderSend(req,res);
  if(!PositionSelectByTicket(ticket)) { SyncCycle(); return; }
  double confirmed=PositionGetDouble(POSITION_TP);
  double confirmedDistance=cycles[n].side*(confirmed-cycles[n].entry);
  if(confirmed>0 && confirmedDistance>0 && confirmedDistance<=cycles[n].targetDistance+tolerance &&
     MathAbs(confirmed-req.tp)<=tolerance && MathAbs(PositionGetDouble(POSITION_SL)-sl)<=tolerance) {
   cycles[n].target=confirmed; cycles[n].targetAdjustments++; targetAdjustments++;
   Event("TARGET_CAP_CONFIRMED",n,"quoted_entry="+N(cycles[n].quotedEntry)+"; fill="+N(cycles[n].entry)+"; TP="+N(confirmed),res.retcode);
   return;
  }
  lastRetcode=(int)res.retcode; lastErrorTime=TimeCurrent(); targetFailures++;
  Event("TARGET_CAP_FAILED",n,"No second volume entry; SL remains; sent="+I(sent),res.retcode);
  Invalid(334,"TP amendment unconfirmed after fill; protected close requested.",true);
 }
double ActiveRisk()
 {
  if(active<0) return 0;
  double risk=0;
  for(int i=0;i<cycles[active].legs;i++) {
   ulong t=0; if(!PositionForLeg(active,i,t)) continue;
   double p=0,sl=PositionGetDouble(POSITION_SL);
   ENUM_ORDER_TYPE type=cycles[active].side==1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(sl<=0 || !OrderCalcProfit(type,_Symbol,PositionGetDouble(POSITION_VOLUME),cycles[active].fills[i],sl,p)) return -1;
   risk+=MathMax(0,-p); // BE is valid zero risk; locked gains do not finance extra risk here.
  }
  return risk;
 }
void CheckProtection()
 {
  if(active<0) return; int n=active; double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  EnforceTargetCap(); if(closeEmergency || active<0) return;
  for(int i=PositionsTotal()-1;i>=0;i--) {
   ulong ticket=PositionGetTicket(i); if(ticket==0 || !OwnSelected()) continue;
   int leg=LegByPid(n,(ulong)PositionGetInteger(POSITION_IDENTIFIER));
   if(leg<0) { Invalid(301,"Untracked position in active campaign.",true); return; }
   double sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP),v=PositionGetDouble(POSITION_VOLUME);
   if(PositionGetInteger(POSITION_TYPE)!=(cycles[n].side==1 ? POSITION_TYPE_BUY : POSITION_TYPE_SELL) || sl<=0 ||
      !PENear(tp,cycles[n].target,tick) || cycles[n].side*(sl-cycles[n].expectedStops[leg])<-tick*.51) {
    Invalid(302,"Missing, widened or unexpected SL/TP.",true); return;
   }
   if(cycles[n].side*(sl-cycles[n].desiredStop)>tick*.51) { Invalid(303,"SL exceeds the requested protection level."); return; }
   cycles[n].expectedStops[leg]=sl;
   double wanted=cycles[n].volumes[leg];
   bool halfAllowed=leg==0 && cycles[n].partialEnabled && cycles[n].part.attempts>0;
   if(MathAbs(v-wanted)>1e-8 && !(halfAllowed && MathAbs(v-wanted*.5)<1e-8)) {
    Invalid(304,"Unexpected remaining volume; no further volume request allowed."); return;
   }
  }
  double risk=ActiveRisk();
  if(risk<0) { Invalid(305,"Cannot value remaining stop risk.",true); return; }
  cycles[n].peakRisk=MathMax(cycles[n].peakRisk,risk); maxRisk=MathMax(maxRisk,risk);
  double balance=AccountInfoDouble(ACCOUNT_BALANCE); if(balance>0) maxRiskPct=MathMax(maxRiskPct,100*risk/balance);
  if(risk>cycles[n].initialRisk*profile.capRisk+.05) Invalid(306,"Stop-risk budget exceeded after fill.",true);
 }
void Defer(PERequest &r,const string kind,const long ret,const string detail)
 {
  PERejected(r,NowMs(),ret); lastRetcode=(int)ret; lastErrorTime=TimeCurrent();
  if(kind=="PARTIAL_DEFERRED") partialDefers++; else beDefers++;
  if(ret==10018) sessionDefers++; if(ret==10016 || ret==10029) stopDefers++;
  Event(kind,active,detail,ret);
 }
bool MoveStops(const double desired)
 {
  if(active<0) return false; int n=active; long now=NowMs();
  if(cycles[n].side*(desired-cycles[n].desiredStop)>1e-8) {
   cycles[n].desiredStop=desired; cycles[n].be.done=false; cycles[n].be.uncertain=false; PEArm(cycles[n].be,now);
  }
  bool all=true; double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  for(int leg=0;leg<cycles[n].legs;leg++) {
   ulong ticket=0; if(!PositionForLeg(n,leg,ticket)) continue;
   double sl=PositionGetDouble(POSITION_SL);
   if(cycles[n].side*(sl-desired)>=-tick*.5) { cycles[n].expectedStops[leg]=sl; continue; }
   all=false;
   if(!PERequestDue(cycles[n].be,now)) continue;
   if(cycles[n].be.attempts>=24) { cycles[n].be.uncertain=true; Invalid(310,"SL amendment retry budget exhausted."); return false; }
   if(!CanRequest()) { Defer(cycles[n].be,"BE_DEFERRED",10018,"Session or trading permission unavailable."); continue; }
   MqlTick q; if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<q.bid) continue;
   double cp=cycles[n].side==1 ? q.bid : q.ask;
   double distance=MathMax(SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL),SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL))*_Point+tick;
   if(cycles[n].side*(cp-desired)<distance || cycles[n].side*(cycles[n].target-cp)<distance ||
      (SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL)>0 && cycles[n].side*(cp-sl)<distance)) {
    Defer(cycles[n].be,"BE_DEFERRED",10029,"Stop/target freeze distance; original SL remains."); continue;
   }
   MqlTradeRequest req={}; MqlTradeResult res={}; req.action=TRADE_ACTION_SLTP; req.position=ticket;
   req.symbol=_Symbol; req.magic=InpMagic; req.sl=NormalizeDouble(desired,_Digits); req.tp=cycles[n].target;
   PEAttempt(cycles[n].be,now); bool sent=OrderSend(req,res); cycles[n].be.lastRet=res.retcode;
   bool exists=PositionSelectByTicket(ticket);
   if(exists && cycles[n].side*(PositionGetDouble(POSITION_SL)-desired)>=-tick*.5) {
    cycles[n].expectedStops[leg]=PositionGetDouble(POSITION_SL); cycles[n].be.nextTryMs=now;
    Event("SL_CONFIRMED",n,"ticket="+U(ticket)+"; sl="+N(desired),res.retcode);
   } else if(!exists) continue;
   else {
    int cls=PERetcodeClass(res.retcode);
    // An SLTP retry is idempotent and changes no volume; re-read before every retry.
    if(cls==3) { cycles[n].be.uncertain=true; Invalid(311,"Permanent/unknown SL amendment rejection."); }
    Defer(cycles[n].be,"BE_DEFERRED",res.retcode,"SL not yet confirmed; sent="+I(sent));
   }
  }
  all=true; int stillOpen=0;
  for(int leg=0;leg<cycles[n].legs;leg++) { ulong t=0; if(PositionForLeg(n,leg,t)) {
   stillOpen++; if(cycles[n].side*(PositionGetDouble(POSITION_SL)-desired)<-tick*.5) all=false;
  } }
  if(stillOpen==0) return false;
  if(all) {
   cycles[n].be.done=true;
   if(cycles[n].beTime==0 && cycles[n].side*(desired-cycles[n].entry)>=-tick*.5) {
    cycles[n].beTime=TimeCurrent(); months[MonthIndex(TimeCurrent())].bes++; Event("BE_CONFIRMED",n,"SL anchored to actual primary entry or better.");
   }
  }
  return all;
 }
bool ReconcilePartial()
 {
  if(active<0) return false; int n=active; if(cycles[n].part.done) return true;
  ulong ticket=0; if(!PositionForLeg(n,0,ticket)) return false;
  double live=PositionGetDouble(POSITION_VOLUME);
  if(PEVolumeState(cycles[n].volume,live)!=1 || cycles[n].part.attempts==0) return false;
  if(!HistorySelect(cycles[n].start,TimeCurrent())) return false;
  double volume=0,value=0; datetime when=0;
  for(int i=0;i<HistoryDealsTotal();i++) {
   ulong d=HistoryDealGetTicket(i);
   if((ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID)!=cycles[n].pid || HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_OUT ||
      HistoryDealGetInteger(d,DEAL_REASON)!=DEAL_REASON_EXPERT || (ulong)HistoryDealGetInteger(d,DEAL_MAGIC)!=InpMagic) continue;
   double v=HistoryDealGetDouble(d,DEAL_VOLUME); volume+=v; value+=v*HistoryDealGetDouble(d,DEAL_PRICE);
   when=(datetime)HistoryDealGetInteger(d,DEAL_TIME);
  }
  if(MathAbs(volume-cycles[n].volume*.5)>1e-8) { Invalid(312,"Partial remainder has no matching executed history."); return false; }
  cycles[n].part.done=true; cycles[n].part.uncertain=false; cycles[n].partialTime=when;
  cycles[n].partialVolume=volume; cycles[n].partialPrice=value/volume; months[MonthIndex(when)].partials++;
  PEArm(cycles[n].be,NowMs()); Event("PARTIAL_CONFIRMED",n,"volume="+N(volume)+"; price="+N(value/volume));
  return true;
 }
void TryPartial()
 {
  if(active<0) return; int n=active; long now=NowMs();
  if(ReconcilePartial()) { MoveStops(cycles[n].entry); return; }
  if(cycles[n].part.uncertain) {
   if(now-cycles[n].part.lastTryMs>60000) Invalid(313,"Unresolved partial reply; no duplicate reduction. Broker SL remains.");
   return;
  }
  if(!PERequestDue(cycles[n].part,now)) return;
  if(cycles[n].part.attempts>=24) { cycles[n].part.uncertain=true; Invalid(314,"Partial retry budget exhausted."); return; }
  MqlTick q; if(!SymbolInfoTick(_Symbol,q)) return;
  if(!PEPartialPriceReady(q.bid,cycles[n].entry,cycles[n].stop,cycles[n].target)) return;
  if(!CanRequest()) { Defer(cycles[n].part,"PARTIAL_DEFERRED",10018,"Session/permission unavailable."); return; }
  ulong ticket=0; if(!PositionForLeg(n,0,ticket) || PEVolumeState(cycles[n].volume,PositionGetDouble(POSITION_VOLUME))!=0) return;
  MqlTradeRequest req={}; MqlTradeResult res={}; req.action=TRADE_ACTION_DEAL; req.position=ticket;
  req.symbol=_Symbol; req.magic=InpMagic; req.type=ORDER_TYPE_SELL; req.price=q.bid;
  req.volume=cycles[n].volume*.5; req.type_filling=Filling(); req.deviation=InpDeviationPoints; req.comment="EV160-PARTIAL";
  PEAttempt(cycles[n].part,now); bool sent=OrderSend(req,res); cycles[n].partialDeal=res.deal; cycles[n].partialOrder=res.order;
  cycles[n].part.lastRet=res.retcode;
  if(ReconcilePartial()) { MoveStops(cycles[n].entry); return; }
  if(!PositionSelectByTicket(ticket)) return; // SL/TP may have closed the entire position meanwhile
  int cls=PERetcodeClass(res.retcode);
  if(cls==1 && res.deal==0) { Defer(cycles[n].part,"PARTIAL_DEFERRED",res.retcode,"Definitive rejection; sent="+I(sent)); return; }
  cycles[n].part.uncertain=true; ambiguousPartials++; lastRetcode=(int)res.retcode; lastErrorTime=TimeCurrent();
  Event("AMBIGUOUS_PARTIAL",n,"Await history/remaining-volume confirmation; never resend blindly.",res.retcode);
  if(cls==3) Invalid(315,"Permanent/unknown partial response.");
 }
void ManageProtection()
 {
  if(active<0) return; CheckProtection(); if(closeEmergency || active<0) return;
  int n=active; MqlTick q; if(!SymbolInfoTick(_Symbol,q)) return;
  if(cycles[n].partialEnabled) {
   if(PEPartialPriceReady(q.bid,cycles[n].entry,cycles[n].stop,cycles[n].target)) PEArm(cycles[n].part,NowMs());
   TryPartial();
  } else if(cycles[n].beTrigger>0) {
   double r=(q.bid-cycles[n].entry)/(cycles[n].entry-cycles[n].stop);
   if(r>=cycles[n].beTrigger) PEArm(cycles[n].be,NowMs());
   if(cycles[n].be.armed && !cycles[n].be.done) MoveStops(cycles[n].entry);
  }
  if(profile.arm==8 && cycles[n].be.armed && !cycles[n].be.done) MoveStops(cycles[n].desiredStop);
 }
void ManageAdd(const bool newBar,const bool recovery)
 {
  if(active<0 || haltEntries || closeEmergency || profile.addFraction<=0) return;
  int n=active; if(cycles[n].addPending || NowMs()<cycles[n].addNextMs) return;
  if(profile.arm!=8 && !newBar) return;
  MqlTick q; if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<q.bid) return;
  double distance=cycles[n].entry-cycles[n].stop,r=(q.bid-cycles[n].entry)/distance;
  if(!PEAddWindow(profile.arm,cycles[n].adds,r,recovery)) return;
  cycles[n].addNextMs=NowMs()+5000;
  if(!CanRequest() || OwnPendingOrder()) return;
  if(cycles[n].addAttempts>=24) { cycles[n].addPending=true; Event("ADD_CANCELLED",n,"24 rejected/submitted attempts reached."); return; }
  double v=0; ulong t=0; if(OwnPositions(v,t)!=cycles[n].legs) return;
  if(InpMaxSpreadPoints>0 && (q.ask-q.bid)/_Point>InpMaxSpreadPoints) return;
  double sl=cycles[n].stop;
  if(profile.arm==8) {
   sl=cycles[n].entry+cycles[n].adds*distance;
   sl=MathFloor(sl/SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE)+1e-9)*SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(!MoveStops(sl)) return; // lock primary/all existing legs before adding
  }
  double volume=cycles[n].volume*profile.addFraction;
  double stops=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
  if(q.bid-sl<stops || cycles[n].target-q.bid<stops) return;
  double loss=0,margin=0,existing=ActiveRisk();
  if(!OrderCalcProfit(ORDER_TYPE_BUY,_Symbol,volume,q.ask,sl,loss) || existing<0) { Invalid(320,"Cannot value proposed addition."); return; }
  if(!PERiskWithin(existing,MathMax(0,-loss),cycles[n].initialRisk,profile.capRisk)) { riskBlocks++; Event("ADD_RISK_BLOCK",n,"Nominal stop budget."); return; }
  if(!OrderCalcMargin(ORDER_TYPE_BUY,_Symbol,volume,q.ask,margin) || margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)) { Event("ADD_MARGIN_BLOCK",n,"Insufficient free margin."); return; }
  cycles[n].addAttempts++;
  bool sent=trade.Buy(volume,_Symbol,0,NormalizeDouble(sl,_Digits),cycles[n].target,"EV160-ADD-N"+I(cycles[n].number));
  uint ret=trade.ResultRetcode();
  if(!sent || ret!=TRADE_RETCODE_DONE) {
   addRejects++; lastRetcode=(int)ret; lastErrorTime=TimeCurrent(); Event("ADD_REJECTED",n,trade.ResultRetcodeDescription(),ret);
   cycles[n].addNextMs=NowMs()+PERetryDelayMs(ret);
   if(PERetcodeClass(ret)==2 || ret==TRADE_RETCODE_DONE) { cycles[n].addPending=true; Invalid(321,"Uncertain addition; no duplicate request.",true); }
   else if(PERetcodeClass(ret)==3) { cycles[n].addPending=true; Invalid(322,"Permanent addition rejection."); }
   return;
  }
  ulong d=trade.ResultDeal();
  if(d==0 || !HistoryDealSelect(d) || HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_IN ||
     HistoryDealGetInteger(d,DEAL_TYPE)!=DEAL_TYPE_BUY || (ulong)HistoryDealGetInteger(d,DEAL_MAGIC)!=InpMagic ||
     HistoryDealGetString(d,DEAL_SYMBOL)!=_Symbol || MathAbs(HistoryDealGetDouble(d,DEAL_VOLUME)-volume)>1e-8) {
   Invalid(323,"Addition fill cannot be reconciled.",true); return;
  }
  ulong pid=(ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID); int j=cycles[n].legs;
  if(j>=3 || pid==0 || CycleByPid(pid)>=0) { Invalid(324,"Addition requires a distinct hedging position.",true); return; }
  cycles[n].pids[j]=pid; cycles[n].fills[j]=HistoryDealGetDouble(d,DEAL_PRICE); cycles[n].volumes[j]=volume;
  cycles[n].expectedStops[j]=sl; cycles[n].legs++; cycles[n].adds++;
  Event("ADD_FILLED",n,"lot="+N(volume)+"; price="+N(cycles[n].fills[j])+"; sl="+N(sl),ret);
  CheckProtection(); SyncCycle();
 }
void EmergencyClose()
 {
  if(!closeEmergency || !CanRequest() || NowMs()-lastEmergencyMs<10000) return;
  lastEmergencyMs=NowMs();
  for(int i=PositionsTotal()-1;i>=0;i--) {
   ulong t=PositionGetTicket(i); if(t==0 || !OwnSelected()) continue;
   bool sent=trade.PositionClose(t); uint ret=trade.ResultRetcode();
   Event("EMERGENCY_CLOSE",active,"ticket="+U(t)+"; sent="+I(sent),ret);
  }
  SyncCycle();
 }
