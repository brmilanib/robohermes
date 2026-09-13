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
 assert(near(HermesTargetDistance(1,.001),20));assert(near(HermesTargetDistance(2,.001),.020));
 assert(near(HermesTargetDistance(2,.01),.20));assert(HermesTargetDistance(0,.001)==0);
 double target=0;assert(HermesTargetPrice(1,4000,20,.001,target)&&near(target,4020));
 assert(HermesTargetPrice(1,4000,.02,.001,target)&&near(target,4000.02));
 assert(!HermesTargetPrice(1,4000,.02,.1,target));assert(!HermesTargetPrice(1,4000,20,0,target));
 assert(!HermesTargetPrice(1,4000,std::numeric_limits<double>::quiet_NaN(),.01,target));
 int boundaries=0;
 for(int i=1;i<=500;i++)for(double tick:{.001,.01,.1})for(int side:{-1,1})for(double dist:{.02,.2,20.0}) {
  double entry=1700.0+i*.000137;
  bool ok=HermesTargetPrice(side,entry,dist,tick,target);
  if(ok){assert(side*(target-entry)<=dist+1e-8);assert(side*(target-entry)>=tick-1e-8);assert(near(target/tick,std::round(target/tick)));}
  if(dist<tick)assert(!ok);boundaries++;
 }
 assert(HermesExactLot(1,.01,100,.01));assert(HermesExactLot(1,.1,10,.1));
 assert(!HermesExactLot(1,.01,.5,.01));assert(!HermesExactLot(1,.03,100,.03));
 assert(!HermesExactLot(1,2,100,.01));assert(!HermesExactLot(1,.01,100,0));
 assert(HermesMarginAvailable(4000,4000));assert(!HermesMarginAvailable(4000,3999.99));
 assert(HermesMarginAvailable(8000,10000)); // exactlot may use80% freeequity: no hidden20%cap
 assert(!HermesMarginAvailable(-1,10000));assert(!HermesMarginAvailable(0,0));
 std::cout<<"Hermes: "<<boundaries<<"target-rounding boundaries, native units, exact lot, margin refusal passed.\n";
 return 0;
}
