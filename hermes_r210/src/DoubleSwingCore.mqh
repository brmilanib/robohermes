#ifndef HERMES_DOUBLESWING_CORE_210
#define HERMES_DOUBLESWING_CORE_210
// Caso 10 - "Duplo Topo/Fundo + EMA 5/21/50" (M2). Baseado num setup manual
// do proprietario: as 3 EMAs alinhadas definem a tendencia; dentro de um
// pullback contra essa tendencia, dois fundos (compra) ou dois topos (venda)
// COMPARAVEIS - um fractal de 2 barras de cada lado, a mesma tecnica do
// detector de pivo do projeto (PivotCore.mqh) - formam a estrutura. O
// rompimento, no FECHAMENTO da barra de sinal, da maior alta entre os dois
// fundos (compra) ou da menor baixa entre os dois topos (venda) - a
// "neckline" - dispara a entrada NA MESMA direcao da tendencia (continuacao,
// nao reversao). Stop alem do extremo mais distante do par (o motor de
// H1Levels ja existente aplica o buffer de 0.20*ATR de sempre). Alvo fixo em
// multiplos do risco inicial (InpDSTargetR, padrao 3R).
//
// Funcao pura, testavel fora do MT5. So le barras FECHADAS: lows[]/highs[]
// em ordem DECRESCENTE de tempo (indice 0 = barra imediatamente ANTERIOR a
// barra de sinal, mesma convencao ArraySetAsSeries do resto do projeto);
// closeSignal e' o fechamento da propria barra de sinal, passado separado -
// ela nunca faz parte da estrutura que rompe.

enum DS_GATE
{
   DS_READY=0,
   DS_DATA=500,     // dados invalidos (janela curta demais, ATR<=0, NaN)
   DS_TREND,        // EMA5/21/50 nao alinhadas em nenhuma direcao
   DS_NO_SWINGS,    // nao achou dois fractais na janela
   DS_TOLERANCE,    // os dois fractais nao sao "duplos" (fora da tolerancia)
   DS_NO_BREAK,     // barra de sinal nao rompeu a neckline
   DS_DISTANCE,     // impulso minimo desde a EMA5 nao atingido
   DS_SPREAD        // spread grande demais (guarda de custo obrigatoria)
};

// Acha o fractal LOW mais recente e o anterior a ele em lows[0..n-1] (ordem
// decrescente de tempo). aIdx = mais recente, bIdx = mais antigo. neckline =
// maior high entre os dois (exclusive das pontas). false se nao achou dois.
bool DSFindDoubleLow(const double &lows[],const double &highs[],const int n,
                     int &aIdx,int &bIdx,double &neckline)
{
   aIdx=-1; bIdx=-1;
   for(int i=2;i<=n-3;i++)
     {
      bool isFractal=true;
      for(int j=i-2;j<=i+2;j++) if(j!=i && lows[j]<=lows[i]) { isFractal=false; break; }
      if(!isFractal) continue;
      if(aIdx<0) aIdx=i;
      else { bIdx=i; break; }
     }
   if(aIdx<0 || bIdx<0) return false;
   neckline=highs[aIdx+1];
   for(int k=aIdx+2;k<bIdx;k++) neckline=MathMax(neckline,highs[k]);
   return true;
}
// Espelho para topo duplo (venda): fractal HIGH, neckline = menor low entre eles.
bool DSFindDoubleHigh(const double &lows[],const double &highs[],const int n,
                      int &aIdx,int &bIdx,double &neckline)
{
   aIdx=-1; bIdx=-1;
   for(int i=2;i<=n-3;i++)
     {
      bool isFractal=true;
      for(int j=i-2;j<=i+2;j++) if(j!=i && highs[j]>=highs[i]) { isFractal=false; break; }
      if(!isFractal) continue;
      if(aIdx<0) aIdx=i;
      else { bIdx=i; break; }
     }
   if(aIdx<0 || bIdx<0) return false;
   neckline=lows[aIdx+1];
   for(int k=aIdx+2;k<bIdx;k++) neckline=MathMin(neckline,lows[k]);
   return true;
}

// side: +1 (compra, fundo duplo) ou -1 (venda, topo duplo) na saida. stop =
// extremo mais distante do par (SEM buffer - quem aplica o buffer de
// 0.20*ATR e' o H1Levels ja existente, reaproveitado por fora desta funcao).
int DSGate(const double ema5,const double ema21,const double ema50,
           const double closeSignal,const double &lows[],const double &highs[],const int n,
           const double atr,const double toleranceATR,const double minEntryDistATR,
           const double ask,const double bid,const double maxSpreadATR,
           double &stop,double &neckline,int &side)
{
   side=0; stop=0; neckline=0;
   if(n<5 || atr<=0 || !MathIsValidNumber(ema5) || !MathIsValidNumber(ema21) ||
      !MathIsValidNumber(ema50) || !MathIsValidNumber(closeSignal) ||
      !MathIsValidNumber(ask) || !MathIsValidNumber(bid) || ask<bid) return DS_DATA;

   bool buyTrend=ema5>ema21 && ema21>ema50;
   bool sellTrend=ema5<ema21 && ema21<ema50;
   if(!buyTrend && !sellTrend) return DS_TREND;

   int aIdx=-1,bIdx=-1; double neck=0;
   if(buyTrend)
     {
      if(!DSFindDoubleLow(lows,highs,n,aIdx,bIdx,neck)) return DS_NO_SWINGS;
      if(toleranceATR<=0 || MathAbs(lows[aIdx]-lows[bIdx])>toleranceATR*atr+1e-8) return DS_TOLERANCE;
      if(!(closeSignal>neck)) return DS_NO_BREAK;
      if(!(ask-ema5>=minEntryDistATR*atr-1e-8)) return DS_DISTANCE;
      if(!(maxSpreadATR>0 && (ask-bid)<=maxSpreadATR*atr+1e-8)) return DS_SPREAD;
      side=1; stop=MathMin(lows[aIdx],lows[bIdx]); neckline=neck;
      return DS_READY;
     }
   else
     {
      if(!DSFindDoubleHigh(lows,highs,n,aIdx,bIdx,neck)) return DS_NO_SWINGS;
      if(toleranceATR<=0 || MathAbs(highs[aIdx]-highs[bIdx])>toleranceATR*atr+1e-8) return DS_TOLERANCE;
      if(!(closeSignal<neck)) return DS_NO_BREAK;
      if(!(ema5-bid>=minEntryDistATR*atr-1e-8)) return DS_DISTANCE;
      if(!(maxSpreadATR>0 && (ask-bid)<=maxSpreadATR*atr+1e-8)) return DS_SPREAD;
      side=-1; stop=MathMax(highs[aIdx],highs[bIdx]); neckline=neck;
      return DS_READY;
     }
}
#endif
