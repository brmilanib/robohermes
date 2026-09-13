// MT5 history adapter. No current candle OHLC enters the detector.
// Copy/validation is transactional: incomplete catch-up never corrupts state.
string HPPathName(const int path)
{ return path==HP_BASE ? "BASE" : (path==HP_PIVOT ? "PIVOT" : "NONE"); }
bool HPSyncClosedBars(const datetime decisionOpen)
{
 HPClearSignal(hpSignal); hpProcessedThisBar=0; hpStatus="HISTORY_PENDING";
 datetime latestClosed=iTime(_Symbol,signalTF,1);
 if(latestClosed<=0 || decisionOpen<=latestClosed) return false;
 MqlRates observed[]; ArraySetAsSeries(observed,false);
 bool seed=hpState.bars_processed==0;
 int copied=0;
 if(seed) copied=CopyRates(_Symbol,signalTF,1,210,observed);
 else {
  if(hpState.expected_open<=0 || hpState.expected_open>(long)latestClosed) {
   hpStatus="CHRONOLOGY_MISMATCH"; return false;
  }
  copied=CopyRates(_Symbol,signalTF,(datetime)hpState.expected_open,latestClosed,observed);
 }
 if(copied<1 || (seed && copied!=210)) return false;
 if(observed[copied-1].time!=latestClosed ||
    (!seed && (long)observed[0].time!=hpState.expected_open)) {
  hpStatus="INCOMPLETE_CATCHUP"; return false;
 }
 HPState trial=hpState; HPSignal current; HPClearSignal(current);
 long ignored=0;
 for(int i=0;i<copied;i++) {
  HPBar closed;
  closed.time=(long)observed[i].time; closed.open=observed[i].open;
  closed.high=observed[i].high; closed.low=observed[i].low; closed.close=observed[i].close;
  long witness=i+1<copied ? (long)observed[i+1].time : (long)decisionOpen;
  HPSignal candidate;
  if(!HPStep(trial,closed,witness,candidate)) { hpStatus="INVALID_HISTORY_OR_SEQUENCE"; return false; }
  if(i==copied-1) current=candidate;
  else if(candidate.buy && !seed) ignored++;
 }
 if(current.buy && (current.signal_time!=(long)latestClosed || current.available_time!=(long)decisionOpen)) {
  hpStatus="STALE_SIGNAL_REJECTED"; return false;
 }
 hpState=trial; hpSignal=current; hpProcessedThisBar=copied; hpCatchupIgnored+=ignored;
 hpStatus=seed ? "READY_SEED_210" : (copied>1 ? "READY_CATCHUP" : "READY");
 return true;
}
