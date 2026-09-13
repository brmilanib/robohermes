// Testa a decisao pura do Caso 5 (Colheita Rapida). Nao e simulacao de mercado.
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
#include "../src/QuickHarvestCore.mqh"

static H1Signal ok_signal(){
 H1Signal s{}; s.open=100; s.close=103; s.high=103.2; s.low=99.8;
 s.ema=100.5; s.sma50=99; s.adx=25; s.plusDI=26; s.minusDI=15; s.atr=2.0;
 return s;
}
static QHFeatures ok_features(){
 QHFeatures f{}; f.valid=true; f.volNow=200; f.volAvg=100;
 f.rangeATR=1.5; f.closeLocation=0.9; f.bodyATR=1.5; return f;
}
int main(){
 const double atr=2.0, minADX=20, volF=1.5, rangeF=1.0, minLoc=0.6, minDist=0.5, maxSpread=0.10;
 const double ask=101.6, bid=101.5;   // dist=1.1 ATR (>=0.5), spread=0.1 (<=0.10*2=0.2)
 int side=-1;
 H1Signal s=ok_signal(); QHFeatures f=ok_features();

 // 1. Setup completo -> pronto para comprar.
 assert(QHGate(s,f,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_READY && side==1);

 // 2. Cada rejeicao, isolada (uma condicao quebrada por vez).
 { H1Signal x=s; x.ema=x.sma50;   assert(QHGate(x,f,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_TREND && side==0); }
 { H1Signal x=s; x.close=x.ema-0.1;assert(QHGate(x,f,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_TREND); }
 { H1Signal x=s; x.adx=19.9;      assert(QHGate(x,f,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_ADX); }
 { H1Signal x=s; x.plusDI=x.minusDI;assert(QHGate(x,f,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_DI); }
 { H1Signal x=s; x.open=x.close;  assert(QHGate(x,f,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_TRIGGER); }
 { QHFeatures g=f; g.volNow=g.volAvg*1.49;assert(QHGate(s,g,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_VOLUME); }
 { QHFeatures g=f; g.volAvg=0;    assert(QHGate(s,g,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_VOLUME); }
 { QHFeatures g=f; g.rangeATR=0.99;assert(QHGate(s,g,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_RANGE); }
 { QHFeatures g=f; g.closeLocation=0.59;assert(QHGate(s,g,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_LOCATION); }
 { double a2=s.ema+0.49*atr,b2=a2-0.05;assert(QHGate(s,f,a2,b2,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_DISTANCE); }

 // 3. Guarda de custo: spread grande frente ao ATR barra a entrada.
 { double wideBid=ask-0.5*atr; assert(QHGate(s,f,ask,wideBid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_SPREAD); }

 // 4. Dados invalidos.
 { QHFeatures g=f; g.valid=false;assert(QHGate(s,g,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_DATA); }
 { assert(QHGate(s,f,ask,bid,0.0,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_DATA); }

 // 5. Limiares inclusivos (exatamente no limite -> passa).
 { QHFeatures g=f; g.volNow=g.volAvg*1.5; g.closeLocation=0.6; g.rangeATR=1.0;
   assert(QHGate(s,g,ask,bid,atr,minADX,volF,rangeF,minLoc,minDist,maxSpread,side)==QH_READY && side==1); }

 std::cout<<"QuickHarvest (Caso 5): pronto, 10 rejeicoes isoladas, guarda de custo, dados invalidos e limiares inclusivos passaram.\n";
 return 0;
}
