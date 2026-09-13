#ifndef XAU_ENTRY_CORE_170
#define XAU_ENTRY_CORE_170
// Fixed, predeclared research hypotheses. No fitting or future bars at runtime.
struct EVOProfile {
 int family,entryPolicy,capitalMode,matchedControl;
 double reinvestFraction,lotCap;
};
struct EVOFeatures {
 bool oscillatorValid;
 double fast310,previousFast310,signal310,previousClose,trueRangeATR,bodyATR,closeLocation;
};
bool EVOSelectProfile(const int id,EVOProfile &e,PEProfile &p)
 {
  if(id<1 || id>56) return false;
  int offset=id<=28 ? 0 : 28,slot=id-offset-1;
  e.family=offset==0 ? 15 : 14; e.entryPolicy=slot<20 ? slot%10 : 0;
  e.capitalMode=slot<10 ? 0 : 1; e.reinvestFraction=slot<10 ? 0 : .50; e.lotCap=slot<10 ? .10 : .30;
  e.matchedControl=offset+(slot<10 ? 1 : 11);
  if(slot>=20) {
   int grid=slot-19; // Grid indices 1..8; index0 (.50,.30) is the existing control.
   int fraction=grid/3,cap=grid%3;
   e.reinvestFraction=fraction==0 ? .50 : (fraction==1 ? .75 : 1.0);
   e.lotCap=cap==0 ? .30 : (cap==1 ? .50 : 1.0);
  }
  // Reuse the validated execution engine, with partials/BE/additions disabled.
  p.mode=e.family; p.arm=e.capitalMode==0 ? 0 : 11; p.pivotSide=0;
  p.be15=0; p.stopFactor=1; p.addFraction=0; p.capRisk=1;
  p.protect14=false; p.partial=false; p.reinvest=e.capitalMode!=0;
  return true;
 }
// close[0] is the most recently CLOSED bar; 25 bars suffice for SMA16(SMA3-SMA10).
bool EVOOscillator(const double &close[],const int count,double &fast,double &previous,double &signal)
 {
  fast=0; previous=0; signal=0;
  if(count<25) return false;
  for(int i=0;i<25;i++) if(!MathIsValidNumber(close[i]) || close[i]<=0) return false;
  for(int j=0;j<16;j++) {
   double shortSum=0,longSum=0;
   for(int k=0;k<10;k++) { longSum+=close[j+k]; if(k<3) shortSum+=close[j+k]; }
   double diff=shortSum/3.0-longSum/10.0;
   if(j==0) fast=diff; if(j==1) previous=diff; signal+=diff/16.0;
  }
  return true;
 }
double EVOCapitalLot(const double base,const double deposit,const double balance,
                     const double fraction,const double cap,const double step)
 {
  if(!MathIsValidNumber(base) || !MathIsValidNumber(deposit) || !MathIsValidNumber(balance) ||
     !MathIsValidNumber(fraction) || !MathIsValidNumber(cap) || !MathIsValidNumber(step) ||
     base<=0 || deposit<=0 || balance<=0 || fraction<0 || fraction>1 || cap<base || step<=0) return 0;
  double raw=base*(1+fraction*MathMax(0,balance-deposit)/deposit);
  return MathFloor(MathMin(raw,cap)/step+1e-8)*step;
 }
// 0 accepted; original H1 gate codes 1..15; 100+ identify the new filters.
int EVOEvaluate(const EVOProfile &e,const H1Signal &s,const EVOFeatures &f,
                 const double ask,const double old200,const double minimumDistance,
                 const bool freshConfirmedBullPivot,int &side)
 {
  side=0; if(s.atr<=0 || ask<=0) return 100;
  int gate=0;
  if(e.entryPolicy==7 || e.entryPolicy==8) {
   if(!(s.ema>s.sma50 && s.sma50>s.oldSma50 && s.close>s.sma200)) return NO_TREND;
   if(s.adx<20) return ADX_LOW;
   if(s.plusDI<=s.minusDI) return DI_CONFLICT;
   if(!(s.close>s.open && s.close>s.ema)) return NO_TRIGGER;
   if(e.entryPolicy==7) {
    if(!s.priorTouched) return NO_TOUCH;
    if(!(s.close>f.previousClose && f.bodyATR>=.20)) return 107;
    if(!f.oscillatorValid || f.fast310<=f.previousFast310) return 103;
   } else {
    if(!freshConfirmedBullPivot) return 108;
    if(s.adx<=s.oldADX) return 101;
   }
   side=1;
  } else {
   gate=H1EvaluateProfile(s,B_PRIOR_PULLBACK,true,20.0,side);
   if(gate!=0) return gate;
   if(side!=1) return 109;
  }
  double minimum=e.entryPolicy==6 ? .25 : minimumDistance;
  if(!PEDistance(ask,s.ema,s.atr,minimum)) return 110;
  if(e.family==15 && s.sma200<=old200) return 111;
  if((e.entryPolicy==1 || e.entryPolicy==9) && s.adx<=s.oldADX) return 101;
  if(e.entryPolicy==2 && s.adx<25) return 102;
  if((e.entryPolicy==3 || e.entryPolicy==9) &&
    (!f.oscillatorValid || f.fast310<=f.previousFast310 || f.fast310<=f.signal310)) return 103;
  if((e.entryPolicy==4 || e.entryPolicy==9) && (ask-s.ema)/s.atr>1.0+1e-8) return 104;
  if(e.entryPolicy==5 && f.trueRangeATR>1.8+1e-8) return 105;
  return 0;
 }
#endif
