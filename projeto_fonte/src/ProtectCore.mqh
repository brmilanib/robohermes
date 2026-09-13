#ifndef XAU_PROTECT_CORE_150
#define XAU_PROTECT_CORE_150
// Platform-independent decisions, shared unchanged with the local C++ tests.
// Original entry core is XAU_H1_Core.mqh; only CLOSED bars are read by the EA.
struct PEProfile { int mode,arm,pivotSide; double be15,stopFactor,addFraction,capRisk; bool protect14,partial,reinvest; };
// mode15/14=original family; 0=coordinated; 30=new confirmed-pivot hypothesis.
double PEThreshold(const int i)
  {
   if(i==0) return 1.0; if(i==1) return 1.5; if(i==2) return 2.0;
   if(i==3) return 2.5; return 3.0;
  }
bool PESelectProfile(const int id,PEProfile &p)
  {
   p.mode=15; p.arm=0; p.be15=0; p.protect14=false; p.partial=false;
   p.stopFactor=1; p.addFraction=0; p.capRisk=1; p.reinvest=false; p.pivotSide=0;
   if(id<1 || id>30) return false;
   if(id<=24) {
    p.mode=(id<=12 ? 15 : 14); p.arm=(id-1)%12;
    if(p.arm>=1 && p.arm<=5) p.be15=PEThreshold(p.arm-1);
    p.partial=(p.arm==6); p.reinvest=(p.arm==11);
    if(p.arm==7 || p.arm==8) p.stopFactor=1.25;
    if(p.arm==8 || p.arm==9) p.addFraction=.5;
    if(p.arm==10) p.addFraction=1;
    if(p.arm==9) p.capRisk=1.3;
    if(p.arm==10) p.capRisk=1.6;
   } else if(id<=27) { p.mode=0; p.be15=PEThreshold(id-24); p.protect14=true; }
   else { p.mode=30; p.pivotSide=(id==28 ? 1 : (id==29 ? -1 : 0)); }
   return true;
  }
// Base setup and ATR-distance filter must have passed before this selection.
int PEChooseOrigin(const PEProfile &p,const double sma200,const double oldSma200)
  {
   if(!MathIsValidNumber(sma200) || !MathIsValidNumber(oldSma200) || sma200<=0 || oldSma200<=0) return 0;
   bool rising=sma200>oldSma200;
   if(p.mode==14) return 14;
   if(p.mode==15) return rising ? 15 : 0;
   return rising ? 15 : 14;
  }
bool PEDistance(const double ask,const double ema,const double atr,const double minimum)
  {
   return MathIsValidNumber(ask) && MathIsValidNumber(ema) && MathIsValidNumber(atr) &&
     MathIsValidNumber(minimum) && ask>0 && ema>0 && atr>0 && minimum>=0 &&
     ask-ema>=minimum*atr-1e-8;
  }
bool PEHalfVolumes(const double volume,const double minimum,const double maximum,const double step)
  {
   return H1Volume(FIXED_LOT,volume,1,1,minimum,maximum,step)>0 &&
          H1Volume(FIXED_LOT,volume*0.5,1,1,minimum,maximum,step)>0;
  }
bool PENear(const double a,const double b,const double tick)
  { return tick>0 && MathAbs(a-b)<tick*0.5; }
bool PECanMoveBE(const double bid,const double entry,const double target,
                 const double stops,const double freeze,const double tick)
  {
   if(!MathIsValidNumber(bid) || !MathIsValidNumber(entry) || !MathIsValidNumber(target) ||
      bid<=0 || entry<=0 || target<=entry || stops<0 || freeze<0 || tick<=0) return false;
   double distance=MathMax(stops,freeze)+tick;
   return bid-entry>=distance-1e-8 && target-bid>=distance-1e-8;
  }
bool PEPartialPriceReady(const double bid,const double entry,const double originalStop,const double target)
  { return originalStop>0 && entry>originalStop && bid>=entry+(entry-originalStop)-1e-8 && bid<target; }
// 0 unchanged; 1 planned half remains; 2 completely closed; -1 unexpected reduction.
int PEVolumeState(const double initial,const double live)
  {
   if(initial<=0 || live<0) return -1;
   if(live<1e-8) return 2;
   if(MathAbs(live-initial)<1e-8) return 0;
   if(MathAbs(live-initial*0.5)<1e-8) return 1;
   return -1;
  }
// Numeric MT5 retcodes, documented in REFERENCIAS.md.
// Ambiguous replies MUST NOT cause blind retries of a volume-changing request.
// 0 success; 1 definitive temporary rejection; 2 ambiguous/pending; 3 permanent/unknown.
int PERetcodeClass(const long ret)
  {
   if(ret==10009 || ret==10025) return 0;
   if(ret==10004 || ret==10015 || ret==10016 || ret==10017 || ret==10018 ||
      ret==10020 || ret==10021 || ret==10024 || ret==10026 || ret==10027 || ret==10029) return 1;
   if(ret==10008 || ret==10010 || ret==10012 || ret==10028 || ret==10031 || ret==10039) return 2;
   return 3;
  }
long PERetryDelayMs(const long ret)
  {
   if(ret==10018 || ret==10017 || ret==10026 || ret==10027) return 60000;
   if(ret==10024) return 30000;
   if(ret==10029 || ret==10016) return 10000;
   return 5000;
  }
struct PERequest
  {
   bool armed,done,uncertain;
   long attempts,firstArmMs,lastTryMs,nextTryMs,lastRet;
  };
bool PERequestDue(const PERequest &r,const long now)
  { return r.armed && !r.done && !r.uncertain && now>=r.nextTryMs; }
void PEArm(PERequest &r,const long now)
  { if(!r.armed) { r.armed=true; r.firstArmMs=now; } }
void PEAttempt(PERequest &r,const long now)
  { r.attempts++; r.lastTryMs=now; r.nextTryMs=now+5000; }
void PERejected(PERequest &r,const long now,const long ret)
  { r.lastRet=ret; r.nextTryMs=now+PERetryDelayMs(ret); }
// Reached/returned flags are observational; they are not simulated BE fills.
struct PEPath
  {
   double entry,stop,maxR,minR; int side;
   long observations;
   bool reached[5],returned[5];
   double returnQuoteR[5];
  };
bool PEObserve(PEPath &p,const double bid)
  {
   if(!MathIsValidNumber(bid) || bid<=0 || p.side*p.entry<=p.side*p.stop || p.stop<=0) return false;
   double r=p.side*(bid-p.entry)/MathAbs(p.entry-p.stop);
   p.maxR=MathMax(p.maxR,r); p.minR=MathMin(p.minR,r); p.observations++;
   for(int i=0;i<5;i++)
     {
      if(r>=PEThreshold(i)-1e-8) p.reached[i]=true;
      if(p.reached[i] && !p.returned[i] && r<=0)
        { p.returned[i]=true; p.returnQuoteR[i]=r; }
     }
   return true;
  }
// Monthly mark-to-market starts from the preceding month's last observed equity.
struct PEEquityPath
  {
   bool initialized;
   double startEquity,endEquity,startBalance,endBalance,peak,maxRelativeDD,maxMoneyDD;
  };
void PEStartEquity(PEEquityPath &p,const double equity,const double balance)
  {
   p.initialized=true; p.startEquity=equity; p.endEquity=equity;
   p.startBalance=balance; p.endBalance=balance; p.peak=equity;
   p.maxRelativeDD=0; p.maxMoneyDD=0;
  }
bool PEObserveEquity(PEEquityPath &p,const double equity,const double balance)
  {
   if(!p.initialized || !MathIsValidNumber(equity) || !MathIsValidNumber(balance)) return false;
   p.endEquity=equity; p.endBalance=balance; p.peak=MathMax(p.peak,equity);
   p.maxMoneyDD=MathMax(p.maxMoneyDD,p.peak-equity);
   if(p.peak>0) p.maxRelativeDD=MathMax(p.maxRelativeDD,100*(p.peak-equity)/p.peak);
   return true;
  }
// Positive, realised profit only; volume is rounded DOWN and capped. No floating-profit sizing.
double PEReinvestLot(const double base,const double deposit,const double balance,const double cap,const double step)
 { if(base<=0 || deposit<=0 || cap<base || step<=0) return 0;
   double effective=base*(1+.5*MathMax(0,balance-deposit)/deposit);
   return MathFloor(MathMin(cap,effective)/step+1e-8)*step;
 }
bool PERiskWithin(const double current,const double extra,const double original,const double multiple)
 { return MathIsValidNumber(current) && MathIsValidNumber(extra) && current>=0 && extra>=0 && original>0 &&
    multiple>=1 && current+extra<=original*multiple+.01; }
bool PEAddWindow(const int arm,const int filled,const double r,const bool closedRecovery)
 {
  if(arm==8) return filled<2 && r>=filled+1-1e-8 && r<=filled+1.25+1e-8;
  if(arm==9 || arm==10) return filled==0 && closedRecovery && r>=-.65-1e-8 && r<=-.35+1e-8;
  return false;
 }
// Arrays below are ordered oldest to newest and contain only CLOSED candles.
// A pivot requires two complete bars on each side. Consecutive same-kind pivots
// collapse to the more extreme one; ambiguous outside bars are ignored.
struct PEPivot { int index,kind; double price; };
int PEPivotSignal(const double &high[],const double &low[],const int count,
                   const double close,const double previousClose,double &level,double &swing,int &key)
 {
  PEPivot p[128]; int n=0; level=0; swing=0; key=-1;
  if(count<9 || count>128) return 0;
  for(int i=2;i<count-2;i++) {
   bool top=true,bottom=true;
   for(int j=-2;j<=2;j++) if(j!=0) { if(high[i]<=high[i+j]) top=false; if(low[i]>=low[i+j]) bottom=false; }
   if(top==bottom) continue;
   int kind=top ? 1 : -1; double price=top ? high[i] : low[i];
   if(n>0 && p[n-1].kind==kind) { if(kind*price>kind*p[n-1].price) { p[n-1].price=price; p[n-1].index=i; } continue; }
   p[n].index=i; p[n].kind=kind; p[n].price=price; n++;
  }
  if(n<5) return 0;
  int a=n-5,b=n-4,c=n-3,d=n-2,e=n-1;
  if(p[a].kind==-1 && p[c].price<p[a].price && p[d].price<p[b].price && p[e].price>p[c].price &&
     close>p[d].price && previousClose<=p[d].price) {
   level=p[d].price; swing=p[e].price; key=p[e].index; return 1;
  }
  if(p[a].kind==1 && p[c].price>p[a].price && p[d].price>p[b].price && p[e].price<p[c].price &&
     close<p[d].price && previousClose>=p[d].price) {
   level=p[d].price; swing=p[e].price; key=p[e].index; return -1;
  }
  return 0;
 }
bool PEInSession(const int second,const int start,const int finish)
 { if(start==finish) return true; return finish>start ? (second>=start && second<finish) : (second>=start || second<finish); }
#endif
