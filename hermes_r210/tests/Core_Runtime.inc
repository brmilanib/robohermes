#ifndef XAU_H1_CORE
#define XAU_H1_CORE
// Shared, platform-independent decision rules; shift 1 is always CLOSED.
enum H1_VARIANT { ALIGNMENT_A=0, PRICE_FILTER_B=1 };
enum H1_SIZE { FIXED_LOT=0, PERCENT_RISK=1 };
enum H1_PROFILE { BASE_A=0, BASE_B=1, B_PRIOR_PULLBACK=2, B_PRIOR_ADX_RISING=3 };
enum H1_GATE { READY=0, NO_TREND, ADX_LOW, DI_CONFLICT, NO_TOUCH, NO_TRIGGER };
struct H1Signal
  {
   double open,close,previousHigh,previousLow;
   double ema,sma50,sma200,oldSma50,adx,plusDI,minusDI,atr;
   double lowest,highest;
   bool touched;
   double high,low,oldADX;
   bool priorTouched;
  };

H1_GATE H1Evaluate(const H1Signal &s,const H1_VARIANT variant,
                   const bool useADX,const double minADX,int &side)
  {
   side=0;
   bool buy=(s.ema>s.sma50 && s.sma50>s.oldSma50);
   bool sell=(s.ema<s.sma50 && s.sma50<s.oldSma50);
   if(variant==ALIGNMENT_A)
     { buy=buy && s.sma50>s.sma200; sell=sell && s.sma50<s.sma200; }
   else
     { buy=buy && s.close>s.sma200; sell=sell && s.close<s.sma200; }
   if(!buy && !sell) return NO_TREND;
   if(useADX && s.adx<minADX) return ADX_LOW;
   if(useADX && ((buy && s.plusDI<=s.minusDI) || (sell && s.minusDI<=s.plusDI)))
      return DI_CONFLICT;
   if(!s.touched) return NO_TOUCH;
   if(buy && s.close>s.open && s.close>s.ema && s.close>s.previousHigh) side=1;
   if(sell && s.close<s.open && s.close<s.ema && s.close<s.previousLow) side=-1;
   return side==0 ? NO_TRIGGER : READY;
  }

H1_VARIANT ProfileVariant(const H1_PROFILE profile)
  { return profile==BASE_A ? ALIGNMENT_A : PRICE_FILTER_B; }

int H1EvaluateProfile(const H1Signal &s,const H1_PROFILE profile,
                     const bool useADX,const double minADX,int &side)
  {
   H1Signal selected=s;
   if(profile==B_PRIOR_PULLBACK || profile==B_PRIOR_ADX_RISING)
      selected.touched=s.priorTouched;
   int gate=(int)H1Evaluate(selected,ProfileVariant(profile),useADX,minADX,side);
   if(gate!=0) return gate;
   if(profile==B_PRIOR_ADX_RISING && useADX && s.adx<=s.oldADX)
     { side=0; return 15; }
   return 0;
  }

bool H1Levels(const int side,const double entry,const H1Signal &s,
              const double bufferATR,const double minATR,const double maxATR,
              const double reward,const double tick,double &sl,double &tp)
  {
   sl=0; tp=0;
   if((side!=1 && side!=-1) || s.atr<=0 || tick<=0 || entry<=0) return false;
   double raw=(side==1 ? s.lowest-bufferATR*s.atr : s.highest+bufferATR*s.atr);
   sl=(side==1 ? MathFloor(raw/tick+1e-9) : MathCeil(raw/tick-1e-9))*tick;
   double distance=side*(entry-sl);
   if(sl<=0 || distance<=0 || distance<s.atr*minATR-1e-8 || distance>s.atr*maxATR+1e-8)
      return false;
   raw=entry+side*reward*distance;
   tp=(side==1 ? MathCeil(raw/tick-1e-9) : MathFloor(raw/tick+1e-9))*tick;
   return tp>0;
  }

double H1Volume(const H1_SIZE mode,const double fixedLot,const double budget,
                const double lossPerLot,const double minimum,const double maximum,const double step)
  {
   if(lossPerLot<=0 || step<=0 || minimum<=0 || maximum<minimum) return 0;
   if(mode==FIXED_LOT)
     {
      if(fixedLot<minimum-1e-9 || fixedLot>maximum+1e-9) return 0;
      if(MathAbs(fixedLot/step-MathRound(fixedLot/step))>1e-7) return 0;
      return fixedLot;
     }
   if(budget<=0) return 0;
   double volume=MathFloor(MathMin(budget/lossPerLot,maximum)/step+1e-9)*step;
   if(volume<minimum-1e-9 || volume*lossPerLot>budget+1e-7) return 0;
   return volume;
  }
#endif

#ifndef HERMES_QUICKHARVEST_CORE_210
#define HERMES_QUICKHARVEST_CORE_210
// Caso 5 - "Colheita Rapida" (quick harvest).
// Hipotese: numa barra M30 de ALTA PARTICIPACAO (surto de volume + range amplo)
// dentro de uma tendencia de curto prazo, ha continuacao curta. Entra na barra
// de surto, mira um alvo pequeno em R (InpQHTargetR, ex.: 1R) e sai rapido.
// Objetivo de projeto: ganhos menores e mais frequentes, com risco NORMALIZADO
// (sizing por %), para NAO depender de o ativo fazer um movimento gigante.
//
// Funcao pura, testavel fora do MT5. So le barras FECHADAS (a barra de sinal e
// shift 1) e a cotacao/spread do instante da decisao. Nenhuma entrada usa
// preco futuro, contagem de trades ou resultado conhecido depois.
//
// AVISO DE DADOS: em XAUUSD (CFD/spot) o volume REAL normalmente nao existe;
// usamos TICK VOLUME (numero de ticks) como proxy de participacao. O tick
// volume depende do modo de modelagem do Testador. Isso e uma limitacao real.
//
// AVISO DE CUSTO: alvo curto e MUITO sensivel a spread/comissao/slippage. Por
// isso a guarda de spread (maxSpreadATR) e OBRIGATORIA e o backtest precisa
// rodar com custos realistas, senao o resultado e ficcao. Ver MUDANCAS_R210.md.

enum QH_GATE
{
   QH_READY=0,
   QH_TREND=300,     // sem tendencia curta de alta (EMA21>SMA50 e Close>EMA21)
   QH_ADX,           // ADX abaixo do minimo
   QH_DI,            // +DI nao domina -DI
   QH_TRIGGER,       // barra de sinal nao e de alta (Close<=Open)
   QH_VOLUME,        // sem surto de participacao (tick volume)
   QH_RANGE,         // barra estreita demais (range < rangeFactor*ATR)
   QH_LOCATION,      // fechamento nao ficou na parte alta do range
   QH_DISTANCE,      // preco colado demais na EMA (sem impulso minimo)
   QH_SPREAD,        // spread grande demais para um alvo curto (guarda de custo)
   QH_DATA,          // dados insuficientes/invalidos
   QH_DISABLED       // caso != 5
};

struct QHFeatures
{
   bool valid;           // features calculadas com barras suficientes
   double volNow;        // tick volume da barra de sinal [1]
   double volAvg;        // media do tick volume das N barras anteriores
   double rangeATR;      // (High-Low)/ATR da barra de sinal
   double closeLocation; // (Close-Low)/(High-Low) da barra de sinal, em [0,1]
   double bodyATR;       // (Close-Open)/ATR da barra de sinal
};

// side recebe 1 quando QH_READY (somente compras nesta versao).
int QHGate(const H1Signal &s,const QHFeatures &f,
           const double ask,const double bid,const double atr,
           const double minADX,const double volFactor,const double rangeFactor,
           const double minCloseLoc,const double minEntryDistATR,
           const double maxSpreadATR,int &side)
{
   side=0;
   if(!f.valid || !MathIsValidNumber(ask) || !MathIsValidNumber(bid) ||
      !MathIsValidNumber(atr) || atr<=0 || ask<=0 || bid<=0 || ask<bid) return QH_DATA;
   if(!MathIsValidNumber(s.ema) || !MathIsValidNumber(s.sma50) || s.ema<=0 || s.sma50<=0) return QH_DATA;

   // 1. Tendencia curta de alta (direcional, porem mais leve que o Caso 1:
   //    exige alinhamento EMA21/SMA50 e preco acima da EMA, sem SMA200/pullback).
   if(!(s.ema>s.sma50 && s.close>s.ema)) return QH_TREND;
   if(!(s.adx>=minADX)) return QH_ADX;
   if(!(s.plusDI>s.minusDI)) return QH_DI;

   // 2. Barra de gatilho de alta.
   if(!(s.close>s.open)) return QH_TRIGGER;

   // 3. Surto de participacao: tick volume acima da media recente.
   if(!(f.volAvg>0 && f.volNow>=volFactor*f.volAvg)) return QH_VOLUME;

   // 4. Barra ampla (movimento real, nao ruido).
   if(!(f.rangeATR>=rangeFactor)) return QH_RANGE;

   // 5. Fechou na parte alta do range (comprador dominou a barra).
   if(!(f.closeLocation>=minCloseLoc)) return QH_LOCATION;

   // 6. Impulso minimo acima da EMA (nao entrar sem extensao alguma).
   if(!(ask-s.ema>=minEntryDistATR*atr-1e-8)) return QH_DISTANCE;

   // 7. GUARDA DE CUSTO OBRIGATORIA: spread pequeno frente ao ATR. Sem isto,
   //    um alvo curto e comido pelo custo de transacao.
   if(!(maxSpreadATR>0 && (ask-bid)<=maxSpreadATR*atr+1e-8)) return QH_SPREAD;

   side=1;
   return QH_READY;
}
#endif

#ifndef HERMES_DD_THROTTLE_CORE_210
#define HERMES_DD_THROTTLE_CORE_210
// Caso 6 - freio de risco por rebaixamento (drawdown throttle).
//
// Motivacao: no Caso 4, subir o risco% aumenta o lucro muito mais rapido do
// que aumenta a dor (2%->5% e so 2.5x de risco mas ~14.6x de lucro no sweep
// testado) - mas o Fator de Recuperacao piora a cada degrau (3.87->1.51),
// porque sizing por % do patrimonio compoe geometricamente nos dois sentidos.
// Nao existe ajuste dentro da formula do Caso 4 que quebre esse acoplamento;
// este e um mecanismo DIFERENTE, isolado como Caso 6, comparado contra o
// Caso 4 no mesmo risco-base, nunca substituindo-o.
//
// Ideia: reduzir o risco% EFETIVO quando o patrimonio esta em rebaixamento
// contra o maior pico ja visto, e restaurar o risco cheio assim que um novo
// pico e feito. So muda o VOLUME; nenhuma entrada/saida e alterada.
//
// Funcao pura: (patrimonio atual, pico ja visto, duas bandas de rebaixamento
// e seus multiplicadores) -> multiplicador em (0,1] a aplicar sobre o risco%
// normal. Dados invalidos ou configuracao invalida (bandas fora de ordem,
// multiplicadores fora de (0,1] ou nao-decrescentes) devolvem 0 - o chao de
// seguranca e nao operar, nunca ampliar risco por engano de configuracao.
double DDThrottleMultiplier(const double equity, const double peakEquity,
                            const double band1Pct, const double mult1,
                            const double band2Pct, const double mult2)
{
   if (!MathIsValidNumber(equity) || !MathIsValidNumber(peakEquity) || equity <= 0 || peakEquity <= 0)
      return 0;
   if (!MathIsValidNumber(band1Pct) || !MathIsValidNumber(band2Pct) ||
       !MathIsValidNumber(mult1) || !MathIsValidNumber(mult2) ||
       band1Pct < 0 || band2Pct <= band1Pct ||
       mult1 <= 0 || mult1 > 1.0 || mult2 <= 0 || mult2 > mult1)
      return 0;
   if (equity >= peakEquity) return 1.0;
   double ddPct = 100.0 * (peakEquity - equity) / peakEquity;
   if (ddPct <= band1Pct) return 1.0;
   if (ddPct <= band2Pct) return mult1;
   return mult2;
}
#endif

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
int PEPivotSignal(const std::vector<double> &high,const std::vector<double> &low,const int count,
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
bool EVOOscillator(const std::vector<double> &close,const int count,double &fast,double &previous,double &signal)
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
bool DCWindow(const std::vector<double> &high,const std::vector<double> &low,const int count,
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

#ifndef OLIMPO_HERMES_CORE_190
#define OLIMPO_HERMES_CORE_190
// Target mode: 0=5 initial quoted stop distances, 1=20 quote-price units,
// 2=20 native SYMBOL_POINT units. A point is not a pip or a dollar profit.
double HermesTargetDistance(const int mode,const double point)
 {
  if(mode==1) return 20.0;
  if(mode==2 && MathIsValidNumber(point) && point>0) return 20.0*point;
  return 0;
 }
bool HermesTargetPrice(const int side,const double entry,const double distance,const double tick,double &target)
 {
  target=0;
  if((side!=1 && side!=-1) || !MathIsValidNumber(entry) || !MathIsValidNumber(distance) ||
     !MathIsValidNumber(tick) || entry<=0 || tick<=0 || distance<tick) return false;
  double raw=entry+side*distance;
  if(!MathIsValidNumber(raw) || raw<=0) return false;
  // Round toward entry, never increase the requested target distance.
  target=(side==1 ? MathFloor(raw/tick+1e-9) : MathCeil(raw/tick-1e-9))*tick;
  double tolerance=MathMax(1e-10,tick*1e-7);
  if(side*(target-entry)>distance+tolerance) target-=side*tick;
  double actual=side*(target-entry);
  return target>0 && actual>=tick-tolerance && actual<=distance+tolerance;
 }
// Fixed lot means exact or denied; it is never silently reduced to fit capital.
bool HermesExactLot(const double requested,const double minimum,const double maximum,const double step)
 {
  if(!MathIsValidNumber(requested) || !MathIsValidNumber(minimum) || !MathIsValidNumber(maximum) ||
     !MathIsValidNumber(step) || requested<=0 || minimum<=0 || maximum<minimum || step<=0 ||
     requested<minimum-1e-9 || requested>maximum+1e-9) return false;
  return MathAbs(requested-MathRound(requested/step)*step)<1e-8;
 }
bool HermesMarginAvailable(const double required,const double freeMargin)
 {
  return MathIsValidNumber(required) && MathIsValidNumber(freeMargin) && required>=0 &&
         freeMargin>0 && required<=freeMargin;
 }
#endif

#ifndef HERMES_PIVOT_CORE_MQH
#define HERMES_PIVOT_CORE_MQH

// Causal geometric detector, not an order or portfolio engine.
// Matches HERMES_PIVOS_2x2_V1 (catalogar_pivos.py) LONG 1-2-3 events.
// No STL, allocation, MQL indicator handles, current-bar prices or market calls.
// Feed every CLOSED observed bar once, plus the next observed opening time.
// A next-open witness never grants access to that next bar's OHLC.
// Return false: invalid OHLC, duplicate/out-of-order or skipped input; state
// remains unchanged. Return true: accepted; inspect signal.buy for a trigger.
// Price ties are excluded. A double-extreme bar resets 1-2-3 sequencing.
// Replays must begin from the same historical origin to match the catalog.

struct HPBar
{
   long time;
   double open;
   double high;
   double low;
   double close;
};

struct HPPivot
{
   int type;                         // +1 HIGH, -1 LOW
   double price;
   long origin_time;
   long confirmation_bar_time;
   long available_time;              // opening after the second right bar
};

struct HPSignal
{
   bool buy;
   long signal_time;                 // closed breakout bar's opening
   long available_time;              // first possible decision/entry opening
   double reference_price;           // neckline, confirmed P2 HIGH
   double stop_f1;                    // P1 LOW, geometric invalidation level
   double pullback_f2;                // P3 LOW, higher low (not a chosen stop)
   long p1_time;
   long p2_time;
   long p3_time;
   long p1_confirmation_time;
   long p2_confirmation_time;
   long p3_confirmation_time;
   long p1_available_time;
   long p2_available_time;
   long p3_available_time;
   long pattern_available_time;
};

struct HPState
{
   HPBar window[5];
   int window_count;
   HPPivot alternating[3];
   int alternating_count;
   HPPivot p1;
   HPPivot p2;
   HPPivot p3;
   bool active_pattern;
   bool active_long;
   bool active_invalid;               // includes a pattern already triggered
   long pattern_available_time;
   long expected_open;
   long last_time;
   long bars_processed;
   long pivots_high;
   long pivots_low;
   long double_extremes;
   long tie_high_windows;
   long tie_low_windows;
   long patterns_long;
   long patterns_short;
   long events_long;
   long events_short_reference_only;
};

void HPClearPivot(HPPivot &p)
{
   p.type=0; p.price=0; p.origin_time=0;
   p.confirmation_bar_time=0; p.available_time=0;
}

void HPClearSignal(HPSignal &s)
{
   s.buy=false; s.signal_time=0; s.available_time=0;
   s.reference_price=0; s.stop_f1=0; s.pullback_f2=0;
   s.p1_time=0; s.p2_time=0; s.p3_time=0;
   s.p1_confirmation_time=0; s.p2_confirmation_time=0;
   s.p3_confirmation_time=0;
   s.p1_available_time=0; s.p2_available_time=0; s.p3_available_time=0;
   s.pattern_available_time=0;
}

void HPCoreReset(HPState &s)
{
   s.window_count=0; s.alternating_count=0;
   for(int i=0; i<5; ++i)
   {
      s.window[i].time=0; s.window[i].open=0; s.window[i].high=0;
      s.window[i].low=0; s.window[i].close=0;
   }
   for(int i=0; i<3; ++i) HPClearPivot(s.alternating[i]);
   HPClearPivot(s.p1); HPClearPivot(s.p2); HPClearPivot(s.p3);
   s.active_pattern=false; s.active_long=false; s.active_invalid=false;
   s.pattern_available_time=0; s.expected_open=0; s.last_time=0;
   s.bars_processed=0;
   s.pivots_high=0; s.pivots_low=0; s.double_extremes=0;
   s.tie_high_windows=0; s.tie_low_windows=0;
   s.patterns_long=0; s.patterns_short=0;
   s.events_long=0; s.events_short_reference_only=0;
}

bool HPFinite(const double x)
{
   // These finite bounds cover any meaningful quoted market price and reject
   // +/-infinity and NaN without compiler-specific math functions.
   return x==x && x>-1.0e100 && x<1.0e100;
}

bool HPValidBar(const HPBar &b)
{
   return HPFinite(b.open) && HPFinite(b.high) && HPFinite(b.low)
      && HPFinite(b.close) && b.low<=b.open && b.low<=b.close
      && b.high>=b.open && b.high>=b.close && b.high>=b.low;
}

void HPExposePivot(HPState &s, const HPPivot &p, const long next_open)
{
   bool changed=false;
   const int count=s.alternating_count;
   if(count==0 || s.alternating[count-1].type!=p.type)
   {
      if(count<3)
      {
         s.alternating[count]=p;
         ++s.alternating_count;
      }
      else
      {
         s.alternating[0]=s.alternating[1];
         s.alternating[1]=s.alternating[2];
         s.alternating[2]=p;
      }
      changed=true;
   }
   else if((p.type==1 && p.price>s.alternating[count-1].price)
      || (p.type==-1 && p.price<s.alternating[count-1].price))
   {
      s.alternating[count-1]=p;
      changed=true;
   }
   if(!changed) return;
   s.active_pattern=false; s.active_invalid=false;
   if(s.alternating_count!=3) return;
   s.p1=s.alternating[0]; s.p2=s.alternating[1]; s.p3=s.alternating[2];
   const bool is_long=s.p1.type==-1 && s.p1.price<s.p3.price
      && s.p3.price<s.p2.price;
   const bool is_short=s.p1.type==1 && s.p1.price>s.p3.price
      && s.p3.price>s.p2.price;
   if(!is_long && !is_short) return;
   s.active_pattern=true; s.active_long=is_long;
   s.pattern_available_time=next_open;
   if(is_long) ++s.patterns_long;
   else ++s.patterns_short;
}

void HPEmitLong(const HPState &s, const HPBar &b, const long next_open,
                HPSignal &signal)
{
   signal.buy=true; signal.signal_time=b.time; signal.available_time=next_open;
   signal.reference_price=s.p2.price;
   signal.stop_f1=s.p1.price; signal.pullback_f2=s.p3.price;
   signal.p1_time=s.p1.origin_time; signal.p2_time=s.p2.origin_time;
   signal.p3_time=s.p3.origin_time;
   signal.p1_confirmation_time=s.p1.confirmation_bar_time;
   signal.p2_confirmation_time=s.p2.confirmation_bar_time;
   signal.p3_confirmation_time=s.p3.confirmation_bar_time;
   signal.p1_available_time=s.p1.available_time;
   signal.p2_available_time=s.p2.available_time;
   signal.p3_available_time=s.p3.available_time;
   signal.pattern_available_time=s.pattern_available_time;
}

bool HPStep(HPState &s, const HPBar &closed, const long next_open,
            HPSignal &signal)
{
   HPClearSignal(signal);
   if(!HPValidBar(closed) || next_open<=closed.time) return false;
   if(s.bars_processed>0 && closed.time!=s.expected_open) return false;

   // Evaluate the just-closed bar using only references already available at
   // its opening. A newly confirmed pivot must not change this bar's signal.
   if(s.window_count>0 && s.active_pattern)
   {
      const double previous_close=s.window[s.window_count-1].close;
      bool broke=false;
      if(s.active_long)
      {
         if(closed.low<=s.p1.price) s.active_invalid=true;
         broke=previous_close<=s.p2.price && s.p2.price<closed.close;
      }
      else
      {
         if(closed.high>=s.p1.price) s.active_invalid=true;
         broke=previous_close>=s.p2.price && s.p2.price>closed.close;
      }
      const bool known_at_open=s.pattern_available_time<=closed.time
         && s.p2.available_time<=closed.time;
      if(broke && !s.active_invalid && known_at_open)
      {
         if(s.active_long)
         {
            HPEmitLong(s,closed,next_open,signal);
            ++s.events_long;
         }
         else ++s.events_short_reference_only;
         s.active_invalid=true;        // exactly one event per pattern snapshot
      }
   }

   if(s.window_count<5)
   {
      s.window[s.window_count]=closed;
      ++s.window_count;
   }
   else
   {
      for(int i=0; i<4; ++i) s.window[i]=s.window[i+1];
      s.window[4]=closed;
   }
   s.expected_open=next_open; s.last_time=closed.time; ++s.bars_processed;
   if(s.window_count<5) return true;

   const HPBar center=s.window[2];
   bool strict_high=true, strict_low=true, max_high=true, min_low=true;
   for(int i=0; i<5; ++i)
   {
      if(i==2) continue;
      if(center.high<=s.window[i].high) strict_high=false;
      if(center.low>=s.window[i].low) strict_low=false;
      if(center.high<s.window[i].high) max_high=false;
      if(center.low>s.window[i].low) min_low=false;
   }
   if(max_high && !strict_high) ++s.tie_high_windows;
   if(min_low && !strict_low) ++s.tie_low_windows;
   if(strict_high) ++s.pivots_high;
   if(strict_low) ++s.pivots_low;

   if(strict_high && strict_low)
   {
      ++s.double_extremes;
      s.alternating_count=0;
      s.active_pattern=false; s.active_invalid=false;
      return true;
   }
   if(!strict_high && !strict_low) return true;
   HPPivot pivot;
   pivot.type=strict_high ? 1 : -1;
   pivot.price=strict_high ? center.high : center.low;
   pivot.origin_time=center.time;
   pivot.confirmation_bar_time=closed.time;
   pivot.available_time=next_open;
   HPExposePivot(s,pivot,next_open);
   return true;
}

#endif

#ifndef HERMES_PIVOT_ENTRY_CORE_200
#define HERMES_PIVOT_ENTRY_CORE_200

// Production routing shared by the EA and portable decision tests.
// No entry count, loss outcome, future price or calendar outcome is an input.
enum HP_ENTRY_PATH { HP_NONE=0, HP_BASE=1, HP_PIVOT=2 };
enum HP_EXTRA_GATE { HP_EXTRA_READY=0, HP_DISABLED=200, HP_DATA_PENDING,
 HP_NO_CANDIDATE, HP_TREND50, HP_TREND200, HP_ADX, HP_DI, HP_TRIGGER,
 HP_OSCILLATOR, HP_DISTANCE, HP_INVALID_CASE };
struct HPDecision
{
 int original_gate,extra_gate,setup,side,path;
};
bool HPSelectProfile(const int id,DCProfile &d,EVOProfile &e,PEProfile &p)
{
 if(id<1 || id>6 || !DCSelectProfile(2,d,e,p)) return false;
 d.id=id; d.matchedControl=2; e.matchedControl=2;
 // Casos 4 (Referencia + risco), 5 (Colheita Rapida) e 6 (freio por
 // rebaixamento sobre o Caso 4): MESMO motor de execucao, porem sizing por %
 // do patrimonio em vez de lote fixo. O EA sobrescreve d.riskPercent com
 // InpRiskPercent logo apos esta selecao.
 const bool riskSized=(id==4 || id==5 || id==6);
 if(riskSized) { d.fixedLot=false; if(!(d.riskPercent>0.0 && d.riskPercent<=2.0)) d.riskPercent=1.0; }
 // A referencia herdada e volume (exato ou por risco), 5R, so compra, uma perna.
 return (riskSized ? !d.fixedLot : d.fixedLot) && !d.weekly && d.targetMode==0 && d.channelMode==0
    && e.entryPolicy==0 && e.family==15 && !p.reinvest && !p.partial
    && !p.protect14 && p.be15==0 && p.addFraction==0 && p.arm==0;
}
int HPExtraGate(const int id,const H1Signal &s,const EVOFeatures &f,
                const double ask,const double old200,const double minimumDistance,
                const bool pivotDataReady,const HPSignal &pivot)
{
 if(id<1 || id>6) return HP_INVALID_CASE;
 if(id==1 || id>=4) return HP_DISABLED;   // Casos 1, 4, 5 e 6 nao usam a rota de pivo
 if(!pivotDataReady) return HP_DATA_PENDING;
 if(!pivot.buy) return HP_NO_CANDIDATE;
 if(!(s.ema>s.sma50 && s.sma50>s.oldSma50)) return HP_TREND50;
 // This is the ONLY difference between the two extra-entry variants.
 if(id==2 && !(s.close>s.sma200 && s.sma200>old200)) return HP_TREND200;
 if(!(s.adx>=20.0)) return HP_ADX;
 if(!(s.plusDI>s.minusDI)) return HP_DI;
 if(!(s.close>s.open && s.close>s.ema)) return HP_TRIGGER;
 if(!f.oscillatorValid || !(f.fast310>f.previousFast310)) return HP_OSCILLATOR;
 if(!PEDistance(ask,s.ema,s.atr,minimumDistance)) return HP_DISTANCE;
 return HP_EXTRA_READY;
}
void HPRouteEntry(const int id,const EVOProfile &e,const H1Signal &s,const EVOFeatures &f,
                  const double ask,const double old200,const double minimumDistance,
                  const bool pivotDataReady,const HPSignal &pivot,HPDecision &out)
{
 out.side=0; out.path=HP_NONE;
 out.original_gate=EVOEvaluate(e,s,f,ask,old200,minimumDistance,false,out.side);
 out.extra_gate=HPExtraGate(id,s,f,ask,old200,minimumDistance,pivotDataReady,pivot);
 out.setup=out.original_gate;
 if(id<1 || id>6) { out.setup=HP_INVALID_CASE; out.side=0; return; }
 if(out.original_gate==0) { out.path=HP_BASE; return; }
 if(out.extra_gate==0) { out.setup=0; out.side=1; out.path=HP_PIVOT; }
}
#endif
