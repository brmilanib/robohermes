#include <cmath>
#include <cassert>
#include <algorithm>
#include <iostream>
#include <vector>
#include <fstream>
using std::vector;
template<class A,class B> double MathMax(A a,B b){return std::max(double(a),double(b));}
template<class A,class B> double MathMin(A a,B b){return std::min(double(a),double(b));}
double MathAbs(double x){return std::abs(x);} double MathFloor(double x){return std::floor(x);}
double MathCeil(double x){return std::ceil(x);} double MathRound(double x){return std::round(x);}
bool MathIsValidNumber(double x){return std::isfinite(x);}
#include "Core_Runtime.inc"
bool near(double a,double b){return std::abs(a-b)<1e-7;}
int main(){
 PEProfile p{}; assert(!PESelectProfile(0,p));assert(!PESelectProfile(31,p));
 for(int id=1;id<=30;id++){
  assert(PESelectProfile(id,p));
  if(id<=24){assert(p.mode==(id<=12?15:14));assert(p.arm==(id-1)%12);}
  if(id>=25&&id<=27){assert(p.mode==0&&p.protect14);assert(near(p.be15,1.5+.5*(id-25)));}
  if(id>=28){assert(p.mode==30);assert(p.pivotSide==(id==28?1:id==29?-1:0));}
 }
 PESelectProfile(1,p);assert(PEChooseOrigin(p,210,200)==15);assert(PEChooseOrigin(p,200,210)==0);
 PESelectProfile(13,p);assert(PEChooseOrigin(p,200,210)==14);
 PESelectProfile(26,p);assert(PEChooseOrigin(p,210,200)==15);assert(PEChooseOrigin(p,200,210)==14);
 assert(PEHalfVolumes(.10,.01,100,.01));assert(!PEHalfVolumes(.10,.1,100,.1));
 assert(near(PEReinvestLot(.1,1000,1000,.3,.01),.1));
 assert(near(PEReinvestLot(.1,1000,2000,.3,.01),.15));
 assert(near(PEReinvestLot(.1,1000,1500,.3,.01),.12));
 assert(near(PEReinvestLot(.1,1000,500,.3,.01),.1));
 assert(near(PEReinvestLot(.1,1000,20000,.3,.01),.3));
 assert(PEAddWindow(8,0,1.1,false));assert(!PEAddWindow(8,0,1.3,false));assert(!PEAddWindow(8,2,3,false));
 assert(PEAddWindow(10,0,-.5,true));assert(!PEAddWindow(10,0,-.8,true));assert(!PEAddWindow(10,0,-.5,false));assert(!PEAddWindow(10,1,-.5,true));
 assert(PERiskWithin(100,60,100,1.6));assert(!PERiskWithin(100,61,100,1.6));
 assert(PEVolumeState(.1,.05)==1&&PEVolumeState(.1,.07)==-1);
 PERequest req{}; PEArm(req,100);assert(PERequestDue(req,100));PEAttempt(req,100);assert(!PERequestDue(req,101));
 PERejected(req,100,10018);assert(!PERequestDue(req,60099));assert(PERequestDue(req,60100));
 req.uncertain=true;assert(!PERequestDue(req,9999999));assert(PERetcodeClass(10012)==2);
 assert(!PECanMoveBE(100.5,100,150,1,0,.01));assert(PECanMoveBE(102,100,150,1,0,.01));
 PEPath path{};path.side=1;path.entry=100;path.stop=90;
 assert(PEObserve(path,120));assert(PEObserve(path,99));assert(PEObserve(path,150));
 assert(near(path.maxR,5)&&path.reached[2]&&path.returned[2]&&!path.returned[4]); // 2R BE could remove this eventual winner
 assert(near(path.returnQuoteR[2],-.1));
 PEPath shortp{};shortp.side=-1;shortp.entry=100;shortp.stop=110;PEObserve(shortp,80);PEObserve(shortp,102);
 assert(near(shortp.maxR,2)&&shortp.returned[2]);
 PEEquityPath equity{};PEStartEquity(equity,1000,1000);PEObserveEquity(equity,1200,1000);PEObserveEquity(equity,900,1000);
 assert(near(equity.maxRelativeDD,25)&&near(equity.maxMoneyDD,300));
 // Causal 5-swing reversal: low10, high20, lower low8, lower high18, higher low12, breakout19.
 vector<double> center={14,13,10,13,17,20,16,12,8,12,16,18,16,14,12,14,16,19};
 vector<double> hi,lo;for(double x:center){hi.push_back(x+.1);lo.push_back(x-.1);}
 double level=0,swing=0;int key=-1;
 assert(PEPivotSignal(hi,lo,18,19,16,level,swing,key)==1);assert(key==14&&near(swing,11.9));
 assert(PEPivotSignal(hi,lo,16,14,12,level,swing,key)==0); // higher low not confirmed yet
 vector<double> inverseHi,inverseLo;for(size_t i=0;i<hi.size();i++){inverseHi.push_back(40-lo[i]);inverseLo.push_back(40-hi[i]);}
 assert(PEPivotSignal(inverseHi,inverseLo,18,21,24,level,swing,key)==-1);
 // Same immutable core for the preserved originals; no future bars used in decision core.
 H1Signal s{};s.ema=105;s.sma50=100;s.oldSma50=99;s.sma200=90;s.open=103;s.close=108;s.previousHigh=107;
 s.priorTouched=true;s.adx=22;s.plusDI=25;s.minusDI=10;s.atr=4;s.lowest=102;s.highest=110;
 int side=0;assert(H1EvaluateProfile(s,B_PRIOR_PULLBACK,true,20,side)==0&&side==1);
 double sl=0,tp=0;assert(H1Levels(1,108,s,.2,1,2.5,5,.01,sl,tp));assert(near(sl,101.2)&&near(tp,142));
 std::cout<<"Core: profile matrix, lot/risk boundaries, BE paths, causal pivots, original entry and monthly DD passed.\n";
}
