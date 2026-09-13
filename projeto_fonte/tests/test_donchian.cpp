#include <cmath>
#include <cassert>
#include <algorithm>
#include <iostream>
#include <vector>
#include <limits>
template<class A,class B> double MathMax(A a,B b){return std::max(double(a),double(b));}
template<class A,class B> double MathMin(A a,B b){return std::min(double(a),double(b));}
double MathAbs(double x){return std::abs(x);} double MathFloor(double x){return std::floor(x);}
double MathCeil(double x){return std::ceil(x);} double MathRound(double x){return std::round(x);}
bool MathIsValidNumber(double x){return std::isfinite(x);}
#include "Core_Runtime.inc"
bool near(double a,double b){return std::abs(a-b)<1e-7;}
int main(){
 DCProfile d{};EVOProfile e{};PEProfile p{};
 assert(!DCSelectProfile(0,d,e,p)&&!DCSelectProfile(7,d,e,p));
 for(int id=1;id<=6;id++) {
  assert(DCSelectProfile(id,d,e,p));assert(d.weekly==(id>=5));
  assert(!d.originalCapital);assert(d.fixedLot==(id>=2&&id<=4));
  assert(p.addFraction==0&&!p.partial&&!p.protect14&&p.be15==0&&!p.reinvest&&p.arm==0);
  assert(near(d.minimumStopATR,1));assert(d.riskPercent==(d.fixedLot?0:2));
  assert(d.targetMode==(id==3?1:(id==4?2:0)));
  assert(d.sourceControl180==(id==5?8:(id==6?10:3)));
 }
 H1Signal s{};s.ema=105;s.sma50=100;s.oldSma50=99;s.sma200=90;s.open=103;s.close=108;s.previousHigh=107;
 s.priorTouched=true;s.adx=26;s.plusDI=25;s.minusDI=10;s.atr=4;s.lowest=102;s.highest=110;
 int side=0;assert(DCWeeklyGate(s,side)==0&&side==1);
 s.adx=25;assert(DCWeeklyGate(s,side)==ADX_LOW);s.adx=25.000001;
 s.sma200=500;s.sma50=500;s.oldSma50=1000;assert(DCWeeklyGate(s,side)==0); // no accidental weeklySMA200 filter
 s.priorTouched=false;assert(DCWeeklyGate(s,side)==NO_TOUCH);s.priorTouched=true;
 s.close=s.previousHigh;assert(DCWeeklyGate(s,side)==NO_TRIGGER);s.close=108;
 s.minusDI=25;assert(DCWeeklyGate(s,side)==DI_CONFLICT);s.minusDI=10;
 assert(DCChannelGate(0,false,0,0,0,0)==0);assert(DCChannelGate(1,false,110,100,120,80)==120);
 assert(DCChannelGate(1,true,100,95,120,80)==121);assert(DCChannelGate(1,true,101,95,120,80)==0);
 assert(DCChannelGate(2,true,120,119,120,80)==122);assert(DCChannelGate(2,true,121,120,120,80)==0);
 assert(DCChannelGate(2,true,122,121,120,80)==122); // no repeat breakout while already above the same channel
 std::vector<double> hi(52,120),lo(52,80);double upper=0,lower=0;
 hi[51]=130;lo[50]=75;
 assert(DCWindow(hi,lo,52,1000,1000,upper,lower)&&near(upper,130)&&near(lower,75));
 assert(!DCWindow(hi,lo,51,1000,1000,upper,lower));assert(!DCWindow(hi,lo,52,1001,1000,upper,lower));
 hi[1]=std::numeric_limits<double>::quiet_NaN();assert(!DCWindow(hi,lo,52,1000,1000,upper,lower));hi[1]=120;
 assert(DCStructuralStopAccepted(100,94,4,1.5));assert(!DCStructuralStopAccepted(100,94.1,4,1.5));
 assert(!DCStructuralStopAccepted(100,90,0,1.5));
 // Min lot risk: equity1000,1%risk,loss1000/lot => .01 exactly;2%=>.02.
 assert(near(DCRiskLot(1000,1000,0,1,20,1000,1000,.01,100,.01,1),.01));
 assert(near(DCRiskLot(1000,1000,0,2,20,1000,1000,.01,100,.01,1),.02));
 assert(DCRiskLot(1000,1000,0,1,20,1001,1000,.01,100,.01,1)==0);
 assert(DCRiskLot(1000,1000,0,1,20,1000,21000,.01,100,.01,1)==0); // minimum exceeds margin budget
 assert(DCRiskLot(1000,1000,201,1,20,1000,1000,.01,100,.01,1)==0); // total margin cap, not additional20%
 assert(DCRiskLot(1000,0,0,1,20,1000,1000,.01,100,.01,1)==0);
 assert(near(DCRiskLot(10000,10000,0,2,20,1000,1000,.01,100,.01,.1),.1));
 assert(DCRiskLot(10000,10000,0,3,20,1000,1000,.01,100,.01,1)==0);
 for(int a=1;a<80;a++)for(int b=1;b<50;b++) {
  double eq=100*a,used=eq*.05,free=eq-used,loss=30*b,margin=700*b;
  double v=DCRiskLot(eq,free,used,2,20,loss,margin,.01,100,.01,1);
  assert(v>=0&&v<=1+1e-7);assert(near(v/.01,std::round(v/.01)));
  assert(v==0||v>=.01);assert(v*loss<=eq*.02+1e-7);assert(v*margin<=std::min(free,eq*.2-used)+1e-7);
 }
 assert(PEDistance(110,100,10,1.0));assert(!PEDistance(109.99,100,10,1.0));
 // Control entry logic is the immutable R170case28, across4096 feature boundaries.
 EVOProfile old{};PEProfile oldp{};EVOSelectProfile(28,old,oldp);DCSelectProfile(1,d,e,p);EVOFeatures f{};
 for(int mask=0;mask<4096;mask++) {
  H1Signal q{};q.open=100;q.close=(mask&1)?110:99;q.previousHigh=(mask&2)?109:111;
  q.ema=(mask&4)?105:115;q.sma50=104;q.oldSma50=(mask&8)?103:105;q.sma200=(mask&16)?90:120;
  q.adx=(mask&32)?25:19;q.plusDI=(mask&64)?30:5;q.minusDI=15;q.atr=(mask&128)?4:20;
  q.priorTouched=(mask&256);q.touched=(mask&512);double ask=(mask&1024)?111:110;double old200=(mask&2048)?q.sma200-1:q.sma200+1;
  int a=0,b=0;assert(EVOEvaluate(old,q,f,ask,old200,.5,false,a)==EVOEvaluate(e,q,f,ask,old200,.5,false,b));assert(a==b);
 }
 std::cout<<"Donchian:6profiles;closed-window cutoff;weeklyADX/pullback;3871sizing boundaries;4096original control scenarios passed.\n";
}
