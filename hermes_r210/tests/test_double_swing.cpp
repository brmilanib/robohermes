// Testa a decisao pura do Caso 10 (duplo topo/fundo + EMA5/21/50, M2).
// Nao e simulacao de mercado.
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
#include "../src/DoubleSwingCore.mqh"

int main(){
 const double nan=std::numeric_limits<double>::quiet_NaN();
 // Fundo duplo: fractal recente (idx2=100.0) e fractal antigo (idx6=100.3,
 // dentro de 0.5*ATR=1.0 de tolerancia); neckline = maior high entre eles
 // (idx3..5) = 112.
 std::vector<double> lows {105,103,100.0,102,104,103,100.3,102,104,106};
 std::vector<double> highs{108,107,106.0,110,112,111,106.0,108,109,110};
 const double ema5=111.0, ema21=109.0, ema50=107.0;   // 5>21>50: tendencia de compra
 const double atr=2.0, tolATR=0.50, minDist=0.50, maxSpread=0.10;
 double stop=0, neck=0; int side=0;

 // 1. Setup completo -> pronto para comprar.
 assert(DSGate(ema5,ema21,ema50,112.5,lows,highs,10,atr,tolATR,minDist,112.6,112.45,maxSpread,stop,neck,side)
        ==DS_READY && side==1 && stop==100.0 && neck==112.0);

 // 2. Tendencia nao alinhada (qualquer ordem que nao seja 5>21>50 ou 5<21<50).
 assert(DSGate(109.0,111.0,107.0,112.5,lows,highs,10,atr,tolATR,minDist,112.6,112.45,maxSpread,stop,neck,side)==DS_TREND);

 // 3. So um fractal na janela (encolhe pra n=6, so cabe o fractal do idx2).
 assert(DSGate(ema5,ema21,ema50,101.0,lows,highs,6,atr,tolATR,minDist,102.0,101.9,maxSpread,stop,neck,side)==DS_NO_SWINGS);

 // 4. Fractais fora de tolerancia (diferenca > 0.5*ATR=1.0).
 { std::vector<double> l2=lows; l2[6]=98.5; // |100.0-98.5|=1.5 > 1.0
   assert(DSGate(ema5,ema21,ema50,112.5,l2,highs,10,atr,tolATR,minDist,112.6,112.45,maxSpread,stop,neck,side)==DS_TOLERANCE); }

 // 5. Tolerancia no limite exato (1.0, valores inteiros p/ nao depender de
 //    arredondamento de ponto flutuante) -> passa (inclusiva).
 { std::vector<double> l2=lows; l2[6]=101.0; // |100.0-101.0|=1.0 == limite
   assert(DSGate(ema5,ema21,ema50,112.5,l2,highs,10,atr,tolATR,minDist,112.6,112.45,maxSpread,stop,neck,side)==DS_READY); }

 // 6. Barra de sinal nao rompeu a neckline (112.0): igual conta como NAO rompeu (estrito).
 assert(DSGate(ema5,ema21,ema50,112.0,lows,highs,10,atr,tolATR,minDist,112.6,112.45,maxSpread,stop,neck,side)==DS_NO_BREAK);
 assert(DSGate(ema5,ema21,ema50,111.9,lows,highs,10,atr,tolATR,minDist,112.6,112.45,maxSpread,stop,neck,side)==DS_NO_BREAK);

 // 7. Impulso minimo desde a EMA5 nao atingido (precisa ask-ema5>=0.5*2=1.0).
 assert(DSGate(ema5,ema21,ema50,112.5,lows,highs,10,atr,tolATR,minDist,111.9,111.8,maxSpread,stop,neck,side)==DS_DISTANCE);

 // 8. Spread grande demais (guarda de custo obrigatoria: ask-bid<=0.1*2=0.2).
 assert(DSGate(ema5,ema21,ema50,112.5,lows,highs,10,atr,tolATR,minDist,112.6,112.3,maxSpread,stop,neck,side)==DS_SPREAD);

 // 9. Dados invalidos.
 assert(DSGate(nan,ema21,ema50,112.5,lows,highs,10,atr,tolATR,minDist,112.6,112.45,maxSpread,stop,neck,side)==DS_DATA);
 assert(DSGate(ema5,ema21,ema50,112.5,lows,highs,10,0.0,tolATR,minDist,112.6,112.45,maxSpread,stop,neck,side)==DS_DATA);
 assert(DSGate(ema5,ema21,ema50,112.5,lows,highs,10,atr,tolATR,minDist,111.0,112.0,maxSpread,stop,neck,side)==DS_DATA); // ask<bid
 assert(DSGate(ema5,ema21,ema50,112.5,lows,highs,3,atr,tolATR,minDist,112.6,112.45,maxSpread,stop,neck,side)==DS_DATA); // n<5

 // 10. Topo duplo (venda), espelho do teste 1: fractais HIGH em vez de LOW,
 //     neckline = MENOR low entre eles, tendencia invertida (5<21<50).
 //     ema5-bid>=1.0 -> bid<=103.0; spread<=0.2 -> ask<=bid+0.2.
 { std::vector<double> lowsS {105,107,112.0,110,108,109,112.3,110,109,107};
   std::vector<double> highsS{108,109,115.0,111,109,110,115.0,111,112,113};
   const double e5=104.0, e21=106.0, e50=108.0;   // 5<21<50: tendencia de venda
   // fractal idx2=115.0 (alto), fractal idx6=115.0 (alto, dif=0<=1.0);
   // neckline = menor low entre idx3..5 = min(110,108,109) = 108.
   assert(DSGate(e5,e21,e50,107.5,lowsS,highsS,10,atr,tolATR,minDist,103.0,102.9,maxSpread,stop,neck,side)
          ==DS_READY && side==-1 && stop==115.0 && neck==108.0); }

 std::cout<<"Duplo topo/fundo + EMA (Caso 10): compra, venda, tendencia desalinhada, "
            "fractal unico, tolerancia (fora/limite), rompimento (falta/exato), "
            "distancia, spread, dados invalidos passaram.\n";
 return 0;
}
