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
