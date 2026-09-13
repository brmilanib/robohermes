#ifndef APOLO_DONCHIAN_CORE_180
#define APOLO_DONCHIAN_CORE_180
// Predeclared hypotheses. All inputs are CLOSED-bar snapshots.
struct DCProfile {
 int id,channelMode,matchedControl,sourceControl180,targetMode;
 bool weekly,originalCapital,fixedLot;
 double riskPercent,minimumStopATR;
};
bool DCSelectProfile(const int id,DCProfile &d,EVOProfile &e,PEProfile &p)
 {
  if(id<1 || id>6 || !EVOSelectProfile(28,e,p)) return false;
  d.id=id; d.weekly=id>=5; d.originalCapital=false; d.fixedLot=id>=2 && id<=4;
  d.channelMode=id==6 ? 1 : 0;
  d.riskPercent=d.fixedLot ? 0.0 : 2.0; d.minimumStopATR=1.0;
  d.targetMode=id==3 ? 1 : (id==4 ? 2 : 0);
  d.sourceControl180=id==5 ? 8 : (id==6 ? 10 : 3);
  d.matchedControl=(id==3 || id==4) ? 2 : (id>=5 ? 5 : 1);
  e.capitalMode=d.fixedLot ? 3 : 2; e.reinvestFraction=0; p.reinvest=false; p.arm=0;
  e.matchedControl=d.matchedControl;
  return true;
 }
// Entire window must be completed BEFORE the trigger candle starts.
// The containing W1 bar is excluded, also when evaluating the final M30 bar of a week.
bool DCWindow(const double &high[],const double &low[],const int count,
              const long newestClose,const long cutoff,double &upper,double &lower)
 {
  upper=0; lower=0;
  if(count!=52 || newestClose<=0 || newestClose>cutoff) return false;
  for(int i=0;i<52;i++) {
   if(!MathIsValidNumber(high[i]) || !MathIsValidNumber(low[i]) || low[i]<=0 || high[i]<low[i]) return false;
   if(i==0) { upper=high[i]; lower=low[i]; }
   else { upper=MathMax(upper,high[i]); lower=MathMin(lower,low[i]); }
  }
  return upper>lower;
 }
int DCChannelGate(const int mode,const bool ready,const double close,const double previousClose,
                  const double upper,const double lower)
 {
  if(mode==0) return 0;
  if(!ready || upper<=lower || lower<=0) return 120;
  if(mode==1) return close>(upper+lower)/2.0 ? 0 : 121;
  if(mode==2) return close>upper && previousClose<=upper ? 0 : 122;
  return 123;
 }
int DCWeeklyGate(const H1Signal &s,int &side)
 {
  side=0;
  if(s.atr<=0 || s.ema<=0) return 120;
  if(s.adx<=25.0) return ADX_LOW;
  if(s.plusDI<=s.minusDI) return DI_CONFLICT;
  if(!s.priorTouched) return NO_TOUCH;
  if(!(s.close>s.open && s.close>s.ema && s.close>s.previousHigh)) return NO_TRIGGER;
  side=1; return 0;
 }
bool DCStructuralStopAccepted(const double entry,const double stop,const double atr,const double minimumATR)
 {
  if(!MathIsValidNumber(entry) || !MathIsValidNumber(stop) || !MathIsValidNumber(atr) || !MathIsValidNumber(minimumATR) || atr<=0) return false;
  return MathAbs(entry-stop)/atr+1e-8>=minimumATR;
 }
// Risk is stop-distance risk before slippage, gaps, commission and swap.
// Floor only: never force the minimum lot when it exceeds either budget.
double DCRiskLot(const double equity,const double freeMargin,const double currentMargin,
  const double riskPercent,const double marginPercent,const double lossPerLot,const double marginPerLot,
  const double minimum,const double maximum,const double step,const double hardLotCap)
 {
  double values[11]={equity,freeMargin,currentMargin,riskPercent,marginPercent,lossPerLot,marginPerLot,minimum,maximum,step,hardLotCap};
  for(int i=0;i<11;i++) if(!MathIsValidNumber(values[i])) return 0;
  if(equity<=0 || freeMargin<=0 || currentMargin<0 || riskPercent<=0 || riskPercent>2 ||
     marginPercent<=0 || marginPercent>50 || lossPerLot<=0 || marginPerLot<0 || minimum<=0 ||
     maximum<minimum || step<=0 || hardLotCap<=0) return 0;
  double budget=equity*riskPercent/100.0;
  double available=MathMin(freeMargin,MathMax(0,equity*marginPercent/100.0-currentMargin));
  if(available<=0) return 0;
  double raw=MathMin(maximum,MathMin(hardLotCap,budget/lossPerLot));
  if(marginPerLot>0) raw=MathMin(raw,available/marginPerLot);
  double volume=MathFloor(raw/step+1e-9)*step;
  if(volume<minimum-1e-9 || volume*lossPerLot>budget+1e-7 || volume*marginPerLot>available+1e-7) return 0;
  return volume;
 }
#endif
