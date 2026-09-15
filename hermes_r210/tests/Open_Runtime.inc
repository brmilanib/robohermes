PE_GATE OpenCycle(const int origin,const int side,const H1Signal &s,const MqlTick &q,const datetime signalTime,
                  double &sl,double &tp,double &risk,string &detail)
 {
  double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),entry=side==1 ? q.ask : q.bid;
  H1Signal setup=s; if(evo.entryPolicy==8) { setup.lowest=pivotSwing; setup.highest=pivotSwing; }
  double reward=(InpCase==5 ? InpQHTargetR : (InpCase==8 ? InpBETargetR : 5.0));   // Caso 5: alvo curto em R; Caso 8: 3R padrao
  if(!H1Levels(side,entry,setup,.20,1.0,2.5,reward,tick,sl,tp)) return G_STOP;
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
   double effRiskPercent=dc.riskPercent;
   // Caso 6 apenas: o mesmo risco% do Caso 4, modulado pelo freio de
   // rebaixamento (DDThrottleCore.mqh). Casos 4/5/7 nunca entram aqui - o
   // multiplicador so existe quando InpCase==6, preservando os demais
   // byte-a-byte no comportamento de sizing.
   if(InpCase==6) effRiskPercent*=DDThrottleMultiplier(eq,ddPeakEquity,InpDDBand1,InpDDMult1,InpDDBand2,InpDDMult2);
   // Caso 7 apenas: risco% calculado sobre o capital de risco (patrimonio
   // menos o total ja "sacado" - WithdrawalCore.mqh), nao sobre o patrimonio
   // real. A margem abaixo continua usando eq/free/used REAIS - o saque muda
   // só quanto se arrisca por trade, nunca a margem de fato disponivel.
   double sizingEquityBase=(InpCase==7) ? WDTradingCapital(eq,withdrawState.bankedWithdrawn) : eq;
   sizingRiskBudget=sizingEquityBase*effRiskPercent/100.0;
   sizingMarginBudget=MathMin(free,MathMax(0,eq*InpMaxMarginPct/100.0-used));
   if(InpCase>=4) {
    // Casos 4/5/6: sizing por risco SEM o teto de 2% do DCRiskLot (permite ate
    // 5% conscientemente). Replica a mesma formula do DCRiskLot, reaproveitando
    // os orcamentos ja calculados acima (sizingRiskBudget ja vem com o freio do
    // Caso 6 aplicado, se for o caso); margem% e volume maximo do simbolo
    // continuam limitando. DonchianCore.mqh permanece intocado (core auditado
    // do R200) — este ramo existe aqui, nao ali, porque so os Casos 4/5/6 podem
    // ultrapassar o teto de 2% do DCRiskLot.
    double lossPerLot=-referenceLoss/mn,marginPerLot=referenceMargin/mn;
    double raw=(sizingMarginBudget>0 && lossPerLot>0) ? MathMin(mx,sizingRiskBudget/lossPerLot) : 0;
    if(marginPerLot>0) raw=MathMin(raw,sizingMarginBudget/marginPerLot);
    volume=MathFloor(raw/step+1e-9)*step;
    if(sizingMarginBudget<=0 || volume<mn-1e-9 || volume*lossPerLot>sizingRiskBudget+1e-7 || volume*marginPerLot>sizingMarginBudget+1e-7) volume=0;
   } else {
    volume=DCRiskLot(eq,free,used,dc.riskPercent,InpMaxMarginPct,-referenceLoss/mn,referenceMargin/mn,mn,mx,step,InpMaxLot);
   }
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
