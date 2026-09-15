#property strict
#property version "2.00"
#property description "XAU M30: original Hermes control plus two causal 1-2-3 pivot hypotheses. Tester only."
#include <Trade/Trade.mqh>
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

#ifndef HERMES_WITHDRAWAL_CORE_210
#define HERMES_WITHDRAWAL_CORE_210
// Caso 7 - saque de lucro (trava de ganho).
//
// Motivacao: no Caso 4 a 5%, o pico de patrimonio chegou a ser ~136x o
// deposito inicial antes de um unico tombo devolver ~54% dele. Tecnicamente
// a maior parte do dinheiro em risco naquele momento era LUCRO do proprio
// robo, nao capital original - mas o motor de risco% nao faz essa distincao:
// ele sempre arrisca a mesma fracao do patrimonio ATUAL, para sempre, entao
// o mesmo tombo proporcional se repete a cada novo pico, com o lucro que se
// acumulou virando a nova base arriscada.
//
// Mecanismo: a cada novo recorde de SALDO REALIZADO (fechamento de trade,
// nao patrimonio flutuante - saque so faz sentido sobre lucro ja
// concretizado), uma fracao do incremento (InpWithdrawFraction, padrao 50%)
// e contabilizada como "sacada" - deixa de contar para o calculo de risco%,
// mesmo sem remover dinheiro de verdade da conta do Testador (isso seria uma
// operacao de saque real, fora do escopo testavel aqui). A margem continua
// calculada sobre o patrimonio REAL da conta - o saque so afeta o quanto e
// arriscado por trade, nunca a margem disponivel de verdade.
//
// Duas funcoes puras, independentes:
//   WDUpdate      - atualiza o estado (pico realizado, total sacado) a cada
//                   saldo observado. So age em NOVO recorde; nunca desfaz um
//                   saque ja contabilizado se o saldo cair depois.
//   WDTradingCapital - devolve o capital efetivo para sizing (patrimonio
//                   menos o total sacado, nunca negativo).
struct WDState
{
   double realizedPeak;
   double bankedWithdrawn;
};

void WDUpdate(const double balance, const double withdrawFraction, WDState &st)
{
   if (!MathIsValidNumber(balance) || !MathIsValidNumber(withdrawFraction) ||
       withdrawFraction < 0.0 || withdrawFraction > 1.0 || !MathIsValidNumber(st.realizedPeak) ||
       balance <= st.realizedPeak)
      return;
   double delta = balance - st.realizedPeak;
   st.bankedWithdrawn += delta * withdrawFraction;
   st.realizedPeak = balance;
}

double WDTradingCapital(const double equity, const double bankedWithdrawn)
{
   if (!MathIsValidNumber(equity) || !MathIsValidNumber(bankedWithdrawn))
      return 0.0;
   return MathMax(0.0, equity - bankedWithdrawn);
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
 if(id<1 || id>7 || !DCSelectProfile(2,d,e,p)) return false;
 d.id=id; d.matchedControl=2; e.matchedControl=2;
 // Casos 4 (Referencia + risco), 5 (Colheita Rapida), 6 (freio por
 // rebaixamento) e 7 (saque de lucro), todos sobre o Caso 4: MESMO motor de
 // execucao, porem sizing por % do patrimonio em vez de lote fixo. O EA
 // sobrescreve d.riskPercent com InpRiskPercent logo apos esta selecao.
 const bool riskSized=(id==4 || id==5 || id==6 || id==7);
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
 if(id<1 || id>7) return HP_INVALID_CASE;
 if(id==1 || id>=4) return HP_DISABLED;   // Casos 1, 4, 5, 6 e 7 nao usam a rota de pivo
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
 if(id<1 || id>7) { out.setup=HP_INVALID_CASE; out.side=0; return; }
 if(out.original_gate==0) { out.path=HP_BASE; return; }
 if(out.extra_gate==0) { out.setup=0; out.side=1; out.path=HP_PIVOT; }
}
#endif


// Three predeclared M30 cases. Exact fixed lot and 5R in every case.
input int InpCase=1;
input double InpMaxMarginPct=20.0;
input double InpMaxLot=1.0;
input double InpFixedLot=1.00;
input double InpMinEntryATR=0.50;
input double InpMaxSpreadPoints=0;
input ulong InpDeviationPoints=20;
input ulong InpMagic=26120200;
input bool InpExportCSV=true;
input bool InpShowIndicators=false;
input bool InpExportOptimizationDetails=true;
input bool InpExportAllBars=true;
input string InpRunTag="R210_01";
// --- R210: sizing por risco (Casos 4 e 5) e Colheita Rapida (Caso 5) ---
input double InpRiskPercent=1.00;    // Casos 4/5: risco por trade em % do patrimonio (0<x<=2)
input double InpQHTargetR=1.00;      // Caso 5: alvo em R (multiplo do risco inicial)
input double InpQHVolFactor=1.50;    // Caso 5: surto de volume = tickvol >= fator*media(20)
input double InpQHRangeFactor=1.00;  // Caso 5: barra ampla = range >= fator*ATR
input double InpQHMinCloseLoc=0.60;  // Caso 5: fechamento minimo dentro do range [0..1]
input double InpQHMinADX=20.0;       // Caso 5: ADX minimo
input double InpQHMaxSpreadATR=0.10; // Caso 5: guarda de custo: spread <= fator*ATR
// --- Caso 6: freio de risco por rebaixamento (aplicado sobre o Caso 4) ---
input double InpDDBand1=15.0;  // Caso 6: rebaixamento (%) ate onde o risco fica cheio
input double InpDDMult1=0.50;  // Caso 6: multiplicador do risco entre a banda 1 e a banda 2
input double InpDDBand2=25.0;  // Caso 6: rebaixamento (%) a partir de onde o risco cai mais
input double InpDDMult2=0.25;  // Caso 6: multiplicador do risco acima da banda 2
// --- Caso 7: saque de lucro (fracao do novo recorde de saldo que "sai" do sizing) ---
input double InpWithdrawFraction=0.50; // Caso 7: fracao (0..1) do novo pico de saldo sacada a cada recorde

enum PE_GATE { G_NO_DATA=0,G_BASE,G_DIRECTION,G_DISTANCE,G_REGIME,G_POSITION,
 G_SPREAD,G_STOP,G_BROKER_STOPS,G_RISK,G_MARGIN_ERROR,G_MARGIN_BLOCK,G_REJECTED,G_FILLED,G_HALTED,G_ENTRY_FILTER,G_TARGET,G_COUNT };
enum PE_STAT {
 S_VALID=0,S_PROFIT,S_DEPOSIT,S_FINAL_BALANCE,S_MT5_TRADES,S_MT5_PF,S_EQUITY_DD_REL,S_EQUITY_DD_MONEY,S_EQUITY_DD_AT_MONEY,
 S_CYCLES_OPENED,S_CYCLES_CLOSED,S_WINS,S_LOSSES,S_ZERO,S_WIN_PCT,S_CYCLE_PF,S_CYCLE_NET,S_AVG_NET_R,
 S_MAX_LOSS_STREAK,S_AVG_HOLD,S_MAX_HOLD,S_SWAP,S_COSTS,S_MAX_LOTS,S_MAX_RISK,S_MAX_RISK_PCT,S_MAX_MARGIN,
 S_FIRST_EVAL,S_LAST_EVAL,S_FIRST_ENTRY,S_LAST_EXIT,S_BARS,S_SIGNALS,S_FIRST_READY,
 S_ORIGIN15_CYCLES,S_ORIGIN14_CYCLES,S_ORIGIN15_NET,S_ORIGIN14_NET,
 S_BE_ARMED,S_BE_CONFIRMED,S_BE_STOP_EXITS,S_PARTIAL_ARMED,S_PARTIAL_DONE,S_PARTIAL_DEFERRED,S_BE_DEFERRED,
 S_SESSION_DEFERS,S_STOPS_DEFERS,S_BE_ATTEMPTS,S_PARTIAL_ATTEMPTS,S_AMBIGUOUS_PARTIALS,S_ERROR_CODE,S_LAST_RETCODE,S_LAST_ERROR_TIME,
 S_RECONCILE,S_MONTH_EQ_RECONCILE,S_MONTH_BOOK_RECONCILE,S_UNMATCHED,S_MONTHS,S_POS_EQ_MONTHS,S_NEG_EQ_MONTHS,S_POS_BOOK_MONTHS,S_NEG_BOOK_MONTHS,
 S_MFE_AVG,S_MFE_WIN_AVG,S_MFE_LOSS_AVG,S_MAE_AVG,S_QUOTE_OBSERVATIONS,S_SHADOW_CONTROL_ELIGIBLE,
 S_FIXED_LOT,S_BE15_R,S_MODE,S_PROTECT14,S_BE_UNFULFILLED,S_PARTIAL_UNFULFILLED,S_EMPTY_PATHS,
 S_MONTH_DD_MAX,S_ADD_FILLS,S_ADD_CYCLES,S_ADD_NET,S_ADD_REJECTS,S_RISK_BLOCKS,S_STOP_FACTOR,
 S_REINVEST,S_ARM,S_INITIAL_LOTS_SUM,S_ADD_LOTS_SUM,S_PATTERN_BUYS,S_PATTERN_SELLS,S_ENTRY_POLICY,S_REINVEST_FRACTION,S_REINVEST_CAP,S_CAPITAL_MODE,S_MATCHED_CONTROL,S_DETAIL_EXPORT,S_BAR_ROWS,S_RISK_PERCENT,S_MARGIN_CAP_PERCENT,S_DONCHIAN_MODE,S_SOURCE_CONTROL180,S_FIXED_MODE,S_TARGET_MODE,S_TARGET_VALUE,S_TARGET_DISTANCE,S_NOMINAL_TARGET_R,S_TARGET_REJECTS,S_TARGET_ADJUSTMENTS,S_TARGET_FAILURES,S_FIXED_VOLUME_REJECTS,S_HP_CANDIDATES,S_HP_EXTRA_ELIGIBLE,S_HP_BASE_SELECTED,S_HP_PIVOT_SELECTED,S_HP_PIVOT_FILLS,S_HP_DATA_FAILURES,S_HP_POSITION_BLOCKS,S_HP_CATCHUP_IGNORED,S_COUNT };
const int MONTH_FIELDS=18;
const int SHADOW_FIELDS=8;
struct PECycle {
 int number,origin,side,legs,adds;
 int entryPath; HPSignal entryPivot;
 ulong pid,ticket,partialDeal,partialOrder;
 ulong pids[3]; double fills[3],volumes[3],expectedStops[3];
 datetime start,finish,partialTime,beTime;
 double quotedEntry,quotedTarget,targetDistance,targetProfitEstimate; int targetAdjustments;
 double entry,stop,target,volume,initialRisk,balanceBefore,beTrigger,liveStop,peakRisk,desiredStop;
 double gross,swap,costs,net,inVolume,outVolume,finalPrice,partialPrice,partialVolume;
 long finalReason;
 bool closed,partialEnabled,finalObserved,addPending; long addNextMs,addAttempts;
 PERequest be,part;
 EVOFeatures entryFeatures; int entryPolicy;
 PEPath path; double featureADXChange,featureADX,featureATR,featureDistance,featureSlope; datetime signalTime;
};
struct PEMonth {
 int key; long bars,signals,opened,closed,bes,partials;
 double cycleNet,bookedNet;
 datetime firstTick,lastTick;
 PEEquityPath path;
};
PEProfile profile; EVOProfile evo; EVOFeatures features; DCProfile dc;
HPState hpState; HPSignal hpSignal; HPDecision hpRoute;
bool hpDataReady=false; string hpStatus="NOT_STARTED"; int hpProcessedThisBar=0;
long hpCandidates=0,hpExtraEligible=0,hpBaseSelected=0,hpPivotSelected=0,hpPivotFills=0,hpDataFailures=0,hpPositionBlocks=0,hpCatchupIgnored=0;
ENUM_TIMEFRAMES signalTF=PERIOD_M30;
bool channelReady=false; double channelUpper=0,channelLower=0;
datetime channelOldest=0,channelNewest=0,channelClosedAt=0;
int channelBars=0; string channelStatus="NOT_REQUESTED";
double sizedLot=0,sizingRiskBudget=0,sizingMarginBudget=0,sizingMargin=0;
double ddPeakEquity=0; // Caso 6: maior patrimonio ja observado desde o inicio do run
WDState withdrawState; // Caso 7: pico de saldo realizado + total sacado ate agora
long targetRejects=0,targetAdjustments=0,targetFailures=0,fixedVolumeRejects=0;
double plannedTargetDistance=0,plannedTargetRiskRatio=0,plannedTargetProfit=0;
double minimumLotRiskMoney=0,minimumLotRiskPercent=0,minimumEquityForLot=0,minimumLotMargin=0;
CTrade trade;
PECycle cycles[];
PEMonth months[];
int active=-1;
int hEMA=INVALID_HANDLE,h50=INVALID_HANDLE,h200=INVALID_HANDLE,hADX=INVALID_HANDLE,hATR=INVALID_HANDLE;
int barsFile=INVALID_HANDLE,eventsFile=INVALID_HANDLE,optFile=INVALID_HANDLE,optMonths=INVALID_HANDLE,optShadow=INVALID_HANDLE,optFiles=INVALID_HANDLE;
string folder="",optFolder="",lastReason="";
bool ioFailure=false; long barRows=0;
bool initialized=false,integrity=true,haltEntries=false,closeEmergency=false,finalizing=false;
int errorCode=0,lastRetcode=0;
datetime firstEval=0,lastEval=0,firstReady=0,lastBar=0,lastErrorTime=0,nextMonth=0;
long barsSeen=0,signals=0,counters[G_COUNT],lastEmergencyMs=0;
long partialDefers=0,beDefers=0,sessionDefers=0,stopDefers=0,ambiguousPartials=0,unmatchedDeals=0;
int liveMonth=-1;
double priorEquity=0,priorBalance=0,oldSMA200=0,maxLots=0,maxRisk=0,maxRiskPct=0,maxMargin=0;
double initialDeposit=0,previousClose=0,pivotLevel=0,pivotSwing=0;
int pivotSide=0; datetime pivotTime=0,lastPivotUsed=0;
long addRejects=0,riskBlocks=0,patternBuys=0,patternSells=0;
bool sessionKnown=false; int sessionDay[128],sessionFrom[128],sessionTo[128],sessionCount=0;
ulong receivedPasses[];

string TS(const datetime t) { return t>0 ? TimeToString(t,TIME_DATE|TIME_SECONDS) : ""; }
string N(const double v) { return MathIsValidNumber(v) ? DoubleToString(v,8) : ""; }
string I(const long v) { return (string)v; }
string U(const ulong v) { return (string)v; }
long NowMs() { MqlTick q; if(SymbolInfoTick(_Symbol,q) && q.time_msc>0) return q.time_msc; return (long)TimeCurrent()*1000; }
string EntryName(const int k)
 {
  string names[10]={"BASE","ADX_SUBINDO","ADX25","MOMENTO_3_10","DIST_1ATR","ATR_SEM_CHOQUE",
    "PULLBACK_PROXIMO","RETOMADA_CEDO","PIVO_FILTRADO","ADX_MACD_DIST"};
  return k>=0 && k<10 ? names[k] : "INVALID";
 }
string DCName(const int id)
 {
  string names[7]={"HERMES_REFERENCIA","HERMES_PIVO_CONTINUIDADE","HERMES_PIVO_INICIO","HERMES_RISCO_REF","HERMES_COLHEITA_RAPIDA","HERMES_DD_THROTTLE","HERMES_SAQUE_LUCRO"};
  return id>=1 && id<=7 ? names[id-1] : "INVALID";
 }
string ProfileName(const int id) { return DCName(id); }
string TFName(const int id) { return "M30"; }
string TargetUnitName() { return dc.targetMode==1 ? "QUOTE_PRICE" : (dc.targetMode==2 ? "MT5_POINT" : "INITIAL_STOP_R"); }
string TargetLabel() { return dc.targetMode==1 ? "20.00 unidades de preco" : (dc.targetMode==2 ? "20 pontos MT5" : (InpCase==5 ? DoubleToString(InpQHTargetR,2)+"R" : "5R")); }
bool LoadDonchian(const datetime cutoff)
 {
  channelReady=false; channelUpper=0; channelLower=0; channelBars=0;
  channelOldest=0; channelNewest=0; channelClosedAt=0; channelStatus="W1_HISTORY_PENDING";
  // Excludes the W1 candle containing the CLOSED trigger candle, never its own high.
  int containing=iBarShift(_Symbol,PERIOD_W1,cutoff,false);
  if(containing<0) return false;
  int shift=containing+1;
  MqlRates w[]; ArraySetAsSeries(w,true);
  int copied=CopyRates(_Symbol,PERIOD_W1,shift,52,w); channelBars=(int)MathMax(0,copied);
  if(copied!=52) return false;
  channelClosedAt=iTime(_Symbol,PERIOD_W1,shift-1);
  channelNewest=w[0].time; channelOldest=w[51].time;
  if(channelClosedAt<=channelNewest || channelClosedAt>cutoff) { channelStatus="NON_CAUSAL_WINDOW"; return false; }
  double hi[52],lo[52];
  for(int i=0;i<52;i++) {
   hi[i]=w[i].high; lo[i]=w[i].low;
   // A missing full week must be diagnosed; DST offsets remain allowed.
   if(i>0 && (w[i-1].time-w[i].time<5*86400 || w[i-1].time-w[i].time>9*86400)) {
    channelStatus="W1_GAP"; return false;
   }
  }
  channelReady=DCWindow(hi,lo,52,(long)channelClosedAt,(long)cutoff,channelUpper,channelLower);
  channelStatus=channelReady ? "READY" : "INVALID_W1_VALUES"; return channelReady;
 }
bool ValidRunTag()
 {
  int n=StringLen(InpRunTag); if(n<1 || n>32) return false;
  for(int i=0;i<n;i++) { ushort c=StringGetCharacter(InpRunTag,i);
   if(!((c>=48 && c<=57) || (c>=65 && c<=90) || (c>=97 && c<=122) || c==95)) return false;
  }
  return true;
 }
string RunRoot() { return "Hermes_Pivos_Lab_200\\"+InpRunTag; }
string Stamp() { string s=TimeToString(TimeLocal(),TIME_DATE|TIME_SECONDS); StringReplace(s,":","-"); StringReplace(s," ","_"); return s+"_"+U(GetMicrosecondCount()); }
string Q(string s) { StringReplace(s,"\"","\"\""); StringReplace(s,"\r"," "); StringReplace(s,"\n"," "); return "\""+s+"\""; }
void Cell(string &s,const string v) { if(s!="") s+=";"; s+=Q(v); }
void Row(const int f,const string s)
 { if(f!=INVALID_HANDLE && FileWriteString(f,s+"\r\n")==0) { ioFailure=true; Print("HP200 CSV write failed: ",GetLastError()); } }
int OpenText(const string f) { return FileOpen(f,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON,0,CP_UTF8); }
void KV(const int f,const string k,const string v) { string row=""; Cell(row,k); Cell(row,v); Row(f,row); }
int MonthIndex(const datetime t)
 {
  MqlDateTime dt; TimeToStruct(t,dt); int key=dt.year*100+dt.mon;
  for(int i=0;i<ArraySize(months);i++) if(months[i].key==key) return i;
  int n=ArraySize(months); ArrayResize(months,n+1); ZeroMemory(months[n]); months[n].key=key; return n;
 }
void Event(const string kind,const int index,const string detail,const long ret=0)
 {
  int number=index>=0 && index<ArraySize(cycles) ? cycles[index].number : 0;
  int origin=index>=0 && index<ArraySize(cycles) ? cycles[index].origin : 0;
  string s=""; Cell(s,TS(TimeCurrent())); Cell(s,I(InpCase)); Cell(s,I(number)); Cell(s,I(origin));
  Cell(s,kind); Cell(s,I(ret)); Cell(s,detail); Row(eventsFile,s);
  if(kind=="ERROR" || kind=="PARTIAL_DEFERRED" || kind=="BE_DEFERRED" || kind=="AMBIGUOUS_PARTIAL")
    Print("HP200 ",kind," case=",InpCase," cycle=",number," ret=",ret," ",detail);
 }
void Invalid(const int code,const string reason,const bool emergency=false)
 {
  integrity=false; haltEntries=true; closeEmergency=closeEmergency || emergency;
  if(errorCode==0) errorCode=code;
  if(reason!=lastReason) { lastReason=reason; Event("ERROR",active,reason,lastRetcode); }
 }
int CycleByPid(const ulong pid)
 { if(pid==0) return -1; for(int i=ArraySize(cycles)-1;i>=0;i--) for(int j=0;j<cycles[i].legs;j++) if(cycles[i].pids[j]==pid) return i; return -1; }
int LegByPid(const int n,const ulong pid)
 { for(int j=0;j<cycles[n].legs;j++) if(cycles[n].pids[j]==pid) return j; return -1; }
bool OwnSelected()
 {
  return PositionGetString(POSITION_SYMBOL)==_Symbol &&
   (CycleByPid((ulong)PositionGetInteger(POSITION_IDENTIFIER))>=0 || (ulong)PositionGetInteger(POSITION_MAGIC)==InpMagic);
 }
int OwnPositions(double &volume,ulong &ticket)
 {
  int count=0; volume=0; ticket=0;
  for(int i=PositionsTotal()-1;i>=0;i--) {
   ulong t=PositionGetTicket(i); if(t==0 || !OwnSelected()) continue;
   count++; volume+=PositionGetDouble(POSITION_VOLUME); ticket=t;
  }
  return count;
 }
bool SymbolExposure()
 {
  for(int i=PositionsTotal()-1;i>=0;i--) if(PositionGetSymbol(i)==_Symbol) return true;
  for(int i=OrdersTotal()-1;i>=0;i--) if(OrderGetTicket(i)>0 && OrderGetString(ORDER_SYMBOL)==_Symbol) return true;
  return false;
 }
bool OwnPendingOrder()
 {
  for(int i=OrdersTotal()-1;i>=0;i--) if(OrderGetTicket(i)>0 && OrderGetString(ORDER_SYMBOL)==_Symbol &&
   (ulong)OrderGetInteger(ORDER_MAGIC)==InpMagic) return true;
  return false;
 }
void TrackEquity()
 {
  datetime now=TimeCurrent(); if(now<=0) return;
  if(liveMonth<0 || now>=nextMonth) {
   liveMonth=MonthIndex(now);
   if(!months[liveMonth].path.initialized) { PEStartEquity(months[liveMonth].path,priorEquity,priorBalance); months[liveMonth].firstTick=now; }
   MqlDateTime dt; TimeToStruct(now,dt); dt.day=1; dt.hour=0; dt.min=0; dt.sec=0; dt.mon++;
   if(dt.mon>12) { dt.mon=1; dt.year++; } nextMonth=StructToTime(dt);
  }
  double eq=AccountInfoDouble(ACCOUNT_EQUITY),bal=AccountInfoDouble(ACCOUNT_BALANCE);
  if(!PEObserveEquity(months[liveMonth].path,eq,bal)) { Invalid(101,"Invalid monthly equity value."); return; }
  months[liveMonth].lastTick=now; priorEquity=eq; priorBalance=bal;
  if(MathIsValidNumber(eq) && eq>0) ddPeakEquity=MathMax(ddPeakEquity,eq); // Caso 6: pico p/ o freio de rebaixamento
  if(InpCase==7) WDUpdate(bal,InpWithdrawFraction,withdrawState); // Caso 7: saque sobre novo recorde de saldo REALIZADO
 }
bool ReadValue(const int h,const int buffer,const int shift,double &v)
 { double a[1]; if(shift<1 || CopyBuffer(h,buffer,shift,1,a)!=1 || a[0]==EMPTY_VALUE || !MathIsValidNumber(a[0])) return false; v=a[0]; return true; }
bool ReadSignal(H1Signal &s,datetime &signalTime)
 {
  int required=dc.weekly ? 55 : 209;
  if(Bars(_Symbol,signalTF)<required || BarsCalculated(hEMA)<required || BarsCalculated(hADX)<required || BarsCalculated(hATR)<required ||
     (!dc.weekly && BarsCalculated(h200)<209)) return false;
  MqlRates r[]; ArraySetAsSeries(r,true); if(CopyRates(_Symbol,signalTF,1,25,r)!=25) return false;
  signalTime=r[0].time; s.open=r[0].open; s.high=r[0].high; s.low=r[0].low; s.close=r[0].close;
  s.previousHigh=r[1].high; s.previousLow=r[1].low;
  if(!ReadValue(hEMA,0,1,s.ema) || !ReadValue(hATR,0,1,s.atr) ||
     !ReadValue(hADX,0,1,s.adx) || !ReadValue(hADX,1,1,s.plusDI) || !ReadValue(hADX,2,1,s.minusDI)) return false;
  if(!dc.weekly && (!ReadValue(h50,0,1,s.sma50) || !ReadValue(h200,0,1,s.sma200) ||
     !ReadValue(h50,0,6,s.oldSma50) || !ReadValue(h200,0,6,oldSMA200))) return false;
  s.lowest=r[0].low; s.highest=r[0].high; s.touched=false; s.priorTouched=false;
  for(int i=0;i<4;i++) {
   if(i<3) { s.lowest=MathMin(s.lowest,r[i].low); s.highest=MathMax(s.highest,r[i].high); }
   double ema=0; if(!ReadValue(hEMA,0,i+1,ema)) return false;
   if(r[i].low<=ema && r[i].high>=ema) { if(i<3) s.touched=true; if(i>=1) s.priorTouched=true; }
  }
  if(!ReadValue(hADX,0,2,s.oldADX)) return false;
  previousClose=r[1].close; ZeroMemory(features); features.previousClose=previousClose;
  double closes[25]; for(int j=0;j<25;j++) closes[j]=r[j].close;
  features.oscillatorValid=EVOOscillator(closes,25,features.fast310,features.previousFast310,features.signal310);
  if(s.atr>0) {
   features.trueRangeATR=MathMax(s.high-s.low,MathMax(MathAbs(s.high-previousClose),MathAbs(s.low-previousClose)))/s.atr;
   features.bodyATR=(s.close-s.open)/s.atr;
  }
  features.closeLocation=s.high>s.low ? (s.close-s.low)/(s.high-s.low) : .5;
  pivotSide=0; pivotTime=0;
  MqlRates pr[]; ArraySetAsSeries(pr,false);
  if(!dc.weekly && CopyRates(_Symbol,signalTF,1,86,pr)==86) {
   double hi[86],lo[86]; for(int k=0;k<86;k++) { hi[k]=pr[k].high; lo[k]=pr[k].low; }
   int key=-1; pivotSide=PEPivotSignal(hi,lo,86,s.close,previousClose,pivotLevel,pivotSwing,key);
   if(key>=0) pivotTime=pr[key].time;
  }
  channelStatus="NOT_USED_M30_PIVOT_PROTOCOL";
  return s.atr>0;
 }
// Caso 5 (Colheita Rapida): participacao (tick volume) e forma da barra de sinal
// (shift 1) mais as 20 barras anteriores para a media. So barras FECHADAS.
bool ReadQuickHarvest(const H1Signal &s,QHFeatures &f)
 {
  ZeroMemory(f);
  const int need=21;                       // barra de sinal + 20 barras para a media
  MqlRates r[]; ArraySetAsSeries(r,true);
  if(CopyRates(_Symbol,signalTF,1,need,r)!=need) return false;
  f.volNow=(double)r[0].tick_volume;
  double sum=0; for(int i=1;i<need;i++) sum+=(double)r[i].tick_volume;
  f.volAvg=(need>1) ? sum/(need-1) : 0;
  if(s.atr>0) { f.rangeATR=(r[0].high-r[0].low)/s.atr; f.bodyATR=(r[0].close-r[0].open)/s.atr; }
  f.closeLocation=(r[0].high>r[0].low) ? (r[0].close-r[0].low)/(r[0].high-r[0].low) : 0.5;
  f.valid=true; return true;
 }
// MT5 history adapter. No current candle OHLC enters the detector.
// Copy/validation is transactional: incomplete catch-up never corrupts state.
string HPPathName(const int path)
{ return path==HP_BASE ? "BASE" : (path==HP_PIVOT ? "PIVOT" : "NONE"); }
bool HPSyncClosedBars(const datetime decisionOpen)
{
 HPClearSignal(hpSignal); hpProcessedThisBar=0; hpStatus="HISTORY_PENDING";
 datetime latestClosed=iTime(_Symbol,signalTF,1);
 if(latestClosed<=0 || decisionOpen<=latestClosed) return false;
 MqlRates observed[]; ArraySetAsSeries(observed,false);
 bool seed=hpState.bars_processed==0;
 int copied=0;
 if(seed) copied=CopyRates(_Symbol,signalTF,1,210,observed);
 else {
  if(hpState.expected_open<=0 || hpState.expected_open>(long)latestClosed) {
   hpStatus="CHRONOLOGY_MISMATCH"; return false;
  }
  copied=CopyRates(_Symbol,signalTF,(datetime)hpState.expected_open,latestClosed,observed);
 }
 if(copied<1 || (seed && copied!=210)) return false;
 if(observed[copied-1].time!=latestClosed ||
    (!seed && (long)observed[0].time!=hpState.expected_open)) {
  hpStatus="INCOMPLETE_CATCHUP"; return false;
 }
 HPState trial=hpState; HPSignal current; HPClearSignal(current);
 long ignored=0;
 for(int i=0;i<copied;i++) {
  HPBar closed;
  closed.time=(long)observed[i].time; closed.open=observed[i].open;
  closed.high=observed[i].high; closed.low=observed[i].low; closed.close=observed[i].close;
  long witness=i+1<copied ? (long)observed[i+1].time : (long)decisionOpen;
  HPSignal candidate;
  if(!HPStep(trial,closed,witness,candidate)) { hpStatus="INVALID_HISTORY_OR_SEQUENCE"; return false; }
  if(i==copied-1) current=candidate;
  else if(candidate.buy && !seed) ignored++;
 }
 if(current.buy && (current.signal_time!=(long)latestClosed || current.available_time!=(long)decisionOpen)) {
  hpStatus="STALE_SIGNAL_REJECTED"; return false;
 }
 hpState=trial; hpSignal=current; hpProcessedThisBar=copied; hpCatchupIgnored+=ignored;
 hpStatus=seed ? "READY_SEED_210" : (copied>1 ? "READY_CATCHUP" : "READY");
 return true;
}


void Record(const PE_GATE gate,const int setup,const int origin,const H1Signal &s,const MqlTick &q,const datetime signalTime,
             const double sl=0,const double tp=0,const double risk=0,const string detail="")
 {
  counters[(int)gate]++;
  if(hpSignal.buy) {
   if(gate==G_POSITION && hpRoute.path==HP_PIVOT) hpPositionBlocks++;
   string candidate="signal="+TS((datetime)hpSignal.signal_time)+"; available="+TS((datetime)hpSignal.available_time);
   candidate+="; p1="+TS((datetime)hpSignal.p1_time)+"; p2="+TS((datetime)hpSignal.p2_time)+"; p3="+TS((datetime)hpSignal.p3_time);
   candidate+="; original_gate="+I(hpRoute.original_gate)+"; extra_gate="+I(hpRoute.extra_gate)+"; entry_path="+HPPathName(hpRoute.path)+"; gate="+EnumToString(gate);
   Event("PIVOT_CANDIDATE",active,candidate);
  }
  bool saveBar=InpExportAllBars || setup==0 || gate==G_NO_DATA || gate==G_HALTED ||
    (s.close>s.open && s.ema>s.sma50 && s.close>s.sma200) || gate==G_FILLED;
  string row="";
  if(saveBar && barsFile!=INVALID_HANDLE) {
  Cell(row,TS(TimeCurrent())); Cell(row,TS(signalTime)); Cell(row,I(InpCase)); Cell(row,I(origin)); Cell(row,EnumToString(gate));
  Cell(row,I(setup)); Cell(row,I(active>=0 ? cycles[active].number : 0));
  Cell(row,N(s.open)); Cell(row,N(s.high)); Cell(row,N(s.low)); Cell(row,N(s.close)); Cell(row,N(s.ema));
  Cell(row,N(s.sma50)); Cell(row,N(s.sma200)); Cell(row,N(s.oldSma50)); Cell(row,N(oldSMA200));
  Cell(row,N(s.adx)); Cell(row,N(s.plusDI)); Cell(row,N(s.minusDI)); Cell(row,N(s.atr));
  Cell(row,N(q.bid)); Cell(row,N(q.ask)); Cell(row,N(sl)); Cell(row,N(tp)); Cell(row,N(risk));
  Cell(row,N(AccountInfoDouble(ACCOUNT_BALANCE))); Cell(row,N(AccountInfoDouble(ACCOUNT_EQUITY))); Cell(row,detail);
  Cell(row,I(pivotSide)); Cell(row,N(pivotLevel)); Cell(row,N(pivotSwing)); Cell(row,TS(pivotTime));
  Cell(row,N(s.atr>0 ? (s.close-s.ema)/s.atr : 0)); Cell(row,N(s.atr>0 ? (s.sma200-oldSMA200)/s.atr : 0));
  Cell(row,N(s.oldADX)); Cell(row,N(previousClose));
  bool pc=pivotSide!=0 && s.adx>=20 && s.adx>s.oldADX &&
    (pivotSide==1 ? (s.plusDI>s.minusDI && s.close>s.open && s.close>s.ema) : (s.minusDI>s.plusDI && s.close<s.open && s.close<s.ema));
  int sd=0; bool baseOK=H1EvaluateProfile(s,B_PRIOR_PULLBACK,true,20.0,sd)==0 && sd==1 && PEDistance(q.ask,s.ema,s.atr,InpMinEntryATR);
  Cell(row,I(pc)); Cell(row,I(baseOK && s.sma200>oldSMA200)); Cell(row,I(baseOK));
  Cell(row,N(s.atr>0 ? (q.ask-q.bid)/s.atr : 0)); Cell(row,N(s.atr>0 ? (s.close-s.open)/s.atr : 0));
  Cell(row,I(evo.entryPolicy)); Cell(row,I(features.oscillatorValid)); Cell(row,N(features.fast310));
  Cell(row,N(features.previousFast310)); Cell(row,N(features.signal310)); Cell(row,N(features.trueRangeATR));
  Cell(row,N(features.closeLocation));
  Cell(row,TFName(InpCase)); Cell(row,I(dc.channelMode)); Cell(row,I(channelReady)); Cell(row,I(channelBars));
  Cell(row,N(channelUpper)); Cell(row,N(channelLower)); Cell(row,TS(channelOldest)); Cell(row,TS(channelNewest)); Cell(row,TS(channelClosedAt)); Cell(row,channelStatus);
  Cell(row,N(dc.riskPercent)); Cell(row,N(dc.fixedLot ? 0 : InpMaxMarginPct)); Cell(row,N(sizedLot)); Cell(row,N(sizingRiskBudget));
  Cell(row,N(sizingMarginBudget)); Cell(row,N(sizingMargin)); Cell(row,N(AccountInfoDouble(ACCOUNT_MARGIN_FREE)));
  Cell(row,N(AccountInfoDouble(ACCOUNT_MARGIN))); Cell(row,N(minimumLotRiskMoney)); Cell(row,N(minimumLotRiskPercent));
  Cell(row,N(minimumEquityForLot)); Cell(row,N(minimumLotMargin));
  Cell(row,I(dc.sourceControl180)); Cell(row,I(dc.matchedControl)); Cell(row,I(dc.fixedLot)); Cell(row,TargetUnitName());
  Cell(row,N(dc.targetMode==0 ? (InpCase==5 ? InpQHTargetR : 5) : 20)); Cell(row,N(plannedTargetDistance)); Cell(row,N(plannedTargetRiskRatio)); Cell(row,N(plannedTargetProfit));
  Cell(row,I(hpDataReady)); Cell(row,hpStatus); Cell(row,I(hpSignal.buy));
  Cell(row,I(hpRoute.original_gate)); Cell(row,I(hpRoute.extra_gate)); Cell(row,HPPathName(hpRoute.path));
  Cell(row,TS((datetime)hpSignal.signal_time)); Cell(row,TS((datetime)hpSignal.available_time));
  Cell(row,N(hpSignal.stop_f1)); Cell(row,N(hpSignal.reference_price)); Cell(row,N(hpSignal.pullback_f2));
  Cell(row,TS((datetime)hpSignal.p1_time)); Cell(row,TS((datetime)hpSignal.p2_time)); Cell(row,TS((datetime)hpSignal.p3_time));
  Cell(row,TS((datetime)hpSignal.p1_confirmation_time)); Cell(row,TS((datetime)hpSignal.p2_confirmation_time)); Cell(row,TS((datetime)hpSignal.p3_confirmation_time));
  Cell(row,TS((datetime)hpSignal.p1_available_time)); Cell(row,TS((datetime)hpSignal.p2_available_time)); Cell(row,TS((datetime)hpSignal.p3_available_time));
  Cell(row,TS((datetime)hpSignal.pattern_available_time)); Cell(row,I(hpProcessedThisBar));
  Cell(row,I(hpState.bars_processed)); Cell(row,TS((datetime)hpState.last_time)); Cell(row,TS((datetime)hpState.expected_open));
  Row(barsFile,row); barRows++;
  }
  if(barsSeen%24==0 && barsFile!=INVALID_HANDLE) FileFlush(barsFile);
  if(MQLInfoInteger(MQL_VISUAL_MODE)) Comment("HERMES PIVOS 2.00 | TESTADOR | ",ProfileName(InpCase),
   "\n",TFName(InpCase)," | Lote base ",DoubleToString(InpFixedLot,2)," | Alvo ",TargetLabel()," | Gestao por perfil",
   "\nCiclos ",ArraySize(cycles)," | ",EnumToString(gate)," | Origem ",origin,
   "\nIntegridade ",integrity ? "OK" : "ERRO: ver events.csv");
 }
void ObserveOpenPath()
 {
  if(active<0) return; double volume=0; ulong ticket=0;
  if(OwnPositions(volume,ticket)<1) return;
  MqlTick q; if(SymbolInfoTick(_Symbol,q) && !PEObserve(cycles[active].path,cycles[active].side==1 ? q.bid : q.ask)) Invalid(102,"Invalid quote for excursion measurement.");
 }
// Closing ownership follows POSITION_IDENTIFIER, including broker/tester exits with magic=0.
// At tester end history contains executed transactions only, not future market bars.
bool AggregateCycle(const int index)
 {
  datetime finish=finalizing ? TimeCurrent()+86400 : TimeCurrent();
  if(!HistorySelect(cycles[index].start,finish)) return false;
  cycles[index].gross=0; cycles[index].swap=0; cycles[index].costs=0;
  cycles[index].inVolume=0; cycles[index].outVolume=0; cycles[index].finish=0;
  for(int i=0;i<HistoryDealsTotal();i++) {
   ulong d=HistoryDealGetTicket(i);
   if(d==0 || HistoryDealGetString(d,DEAL_SYMBOL)!=_Symbol || CycleByPid((ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID))!=index) continue;
   long entry=HistoryDealGetInteger(d,DEAL_ENTRY),side=HistoryDealGetInteger(d,DEAL_TYPE);
   if(side!=DEAL_TYPE_BUY && side!=DEAL_TYPE_SELL) continue;
   cycles[index].gross+=HistoryDealGetDouble(d,DEAL_PROFIT); cycles[index].swap+=HistoryDealGetDouble(d,DEAL_SWAP);
   cycles[index].costs+=HistoryDealGetDouble(d,DEAL_COMMISSION)+HistoryDealGetDouble(d,DEAL_FEE);
   double v=HistoryDealGetDouble(d,DEAL_VOLUME);
   long openingType=cycles[index].side==1 ? DEAL_TYPE_BUY : DEAL_TYPE_SELL;
   if(entry==DEAL_ENTRY_IN && side==openingType) cycles[index].inVolume+=v;
   else if((entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY) && side!=openingType) {
    cycles[index].outVolume+=v; cycles[index].finish=(datetime)HistoryDealGetInteger(d,DEAL_TIME);
    cycles[index].finalPrice=HistoryDealGetDouble(d,DEAL_PRICE); cycles[index].finalReason=HistoryDealGetInteger(d,DEAL_REASON);
   } else return false;
  }
  cycles[index].net=cycles[index].gross+cycles[index].swap+cycles[index].costs;
  return cycles[index].inVolume>0;
 }
void FinishCycle(const int n)
 {
  if(cycles[n].closed) return;
  cycles[n].closed=true;
  // Include the real final fill, never an OHLC high after the position was closed.
  if(!cycles[n].finalObserved && cycles[n].finalPrice>0) {
   if(!PEObserve(cycles[n].path,cycles[n].finalPrice)) Invalid(103,"Invalid final excursion observation.");
   cycles[n].finalObserved=true;
  }
  int mi=MonthIndex(cycles[n].finish); months[mi].closed++; months[mi].cycleNet+=cycles[n].net;
  Event("CYCLE_CLOSED",n,"net="+N(cycles[n].net)+"; MFE_R="+N(cycles[n].path.maxR));
 }
void SyncCycle()
 {
  if(active<0) return; double volume=0; ulong ticket=0; int count=OwnPositions(volume,ticket);
  maxLots=MathMax(maxLots,volume); maxMargin=MathMax(maxMargin,AccountInfoDouble(ACCOUNT_MARGIN));
  if(count>0 || OwnPendingOrder()) return;
  int n=active;
  if(!AggregateCycle(n) || MathAbs(cycles[n].inVolume-cycles[n].outVolume)>1e-8) { Invalid(104,"Closed cycle cannot be reconciled by position identifier."); return; }
  FinishCycle(n); active=-1;
 }

// Execution is ticket-based. Volume changes are never blindly retried after
// an ambiguous reply. Baseline broker SL/TP remain while an amendment is deferred.
void LoadSessions()
 {
  sessionCount=0; sessionKnown=false;
  for(int d=0;d<7;d++) for(uint i=0;i<18;i++) {
   datetime from=0,to=0; if(!SymbolInfoSessionTrade(_Symbol,(ENUM_DAY_OF_WEEK)d,i,from,to)) break;
   if(sessionCount>=128) break;
   sessionKnown=true; sessionDay[sessionCount]=d; sessionFrom[sessionCount]=(int)((long)from%86400);
   sessionTo[sessionCount]=(int)((long)to%86400); sessionCount++;
  }
 }
bool SessionOpen()
 {
  if(!sessionKnown) return true; // server remains authoritative when schedule is unavailable
  MqlDateTime dt; TimeToStruct(TimeCurrent(),dt); int sec=dt.hour*3600+dt.min*60+dt.sec;
  for(int i=0;i<sessionCount;i++) {
   int a=sessionFrom[i],b=sessionTo[i],day=sessionDay[i];
   if(a==b && day==dt.day_of_week) return true;
   if(b>a && day==dt.day_of_week && sec>=a && sec<b) return true;
   if(b<a && ((day==dt.day_of_week && sec>=a) || ((day+1)%7==dt.day_of_week && sec<b))) return true;
  }
  return false;
 }
bool CanRequest()
 { return SessionOpen() && MQLInfoInteger(MQL_TRADE_ALLOWED) && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) &&
    AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) && AccountInfoInteger(ACCOUNT_TRADE_EXPERT); }
ENUM_ORDER_TYPE_FILLING Filling()
 {
  long flags=SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE);
  if((flags&SYMBOL_FILLING_FOK)!=0) return ORDER_FILLING_FOK;
  if((flags&SYMBOL_FILLING_IOC)!=0) return ORDER_FILLING_IOC;
  return ORDER_FILLING_RETURN;
 }
bool PositionForLeg(const int n,const int leg,ulong &ticket)
 {
  ticket=0;
  for(int i=PositionsTotal()-1;i>=0;i--) {
   ulong t=PositionGetTicket(i);
   if(t>0 && PositionGetString(POSITION_SYMBOL)==_Symbol &&
      (ulong)PositionGetInteger(POSITION_IDENTIFIER)==cycles[n].pids[leg]) { ticket=t; return true; }
  }
  return false;
 }
// Only narrows a configured fixed-distance TP. Never widens target or SL.
// The broker SL/TP stays attached during a rejected amendment. Failures halt
// entries and request a ticket-based protected close, recorded as invalid run.
void EnforceTargetCap()
 {
  if(active<0 || dc.targetMode==0 || closeEmergency) return;
  int n=active; ulong ticket=0; if(!PositionForLeg(n,0,ticket)) return;
  double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  double liveTarget=PositionGetDouble(POSITION_TP),sl=PositionGetDouble(POSITION_SL);
  double distance=cycles[n].side*(liveTarget-cycles[n].entry);
  double tolerance=MathMax(1e-10,tick*1e-7);
  if(liveTarget<=0 || distance<=0 || sl<=0) {
   targetFailures++; Invalid(330,"Invalid fixed-target protection after fill.",true); return;
  }
  if(distance<=cycles[n].targetDistance+tolerance) return;
  double allowed=0;
  if(!HermesTargetPrice(cycles[n].side,cycles[n].entry,cycles[n].targetDistance,tick,allowed)) {
   targetFailures++; Invalid(331,"Actual fill cannot represent requested target cap.",true); return;
  }
  MqlTick q;
  if(!CanRequest() || !SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<q.bid) {
   targetFailures++; Invalid(332,"Target cap cannot be confirmed; protected close requested.",true); return;
  }
  double cp=cycles[n].side==1 ? q.bid : q.ask;
  double minDistance=MathMax(SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL),SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL))*_Point;
  if(cycles[n].side*(allowed-cp)<minDistance || cycles[n].side*(cp-sl)<minDistance) {
   targetFailures++; Invalid(333,"Target cap amendment blocked by stops/freeze; protected close requested.",true); return;
  }
  MqlTradeRequest req={}; MqlTradeResult res={}; req.action=TRADE_ACTION_SLTP; req.position=ticket;
  req.symbol=_Symbol; req.magic=InpMagic; req.sl=sl; req.tp=NormalizeDouble(allowed,_Digits);
  bool sent=OrderSend(req,res);
  if(!PositionSelectByTicket(ticket)) { SyncCycle(); return; }
  double confirmed=PositionGetDouble(POSITION_TP);
  double confirmedDistance=cycles[n].side*(confirmed-cycles[n].entry);
  if(confirmed>0 && confirmedDistance>0 && confirmedDistance<=cycles[n].targetDistance+tolerance &&
     MathAbs(confirmed-req.tp)<=tolerance && MathAbs(PositionGetDouble(POSITION_SL)-sl)<=tolerance) {
   cycles[n].target=confirmed; cycles[n].targetAdjustments++; targetAdjustments++;
   Event("TARGET_CAP_CONFIRMED",n,"quoted_entry="+N(cycles[n].quotedEntry)+"; fill="+N(cycles[n].entry)+"; TP="+N(confirmed),res.retcode);
   return;
  }
  lastRetcode=(int)res.retcode; lastErrorTime=TimeCurrent(); targetFailures++;
  Event("TARGET_CAP_FAILED",n,"No second volume entry; SL remains; sent="+I(sent),res.retcode);
  Invalid(334,"TP amendment unconfirmed after fill; protected close requested.",true);
 }
double ActiveRisk()
 {
  if(active<0) return 0;
  double risk=0;
  for(int i=0;i<cycles[active].legs;i++) {
   ulong t=0; if(!PositionForLeg(active,i,t)) continue;
   double p=0,sl=PositionGetDouble(POSITION_SL);
   ENUM_ORDER_TYPE type=cycles[active].side==1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(sl<=0 || !OrderCalcProfit(type,_Symbol,PositionGetDouble(POSITION_VOLUME),cycles[active].fills[i],sl,p)) return -1;
   risk+=MathMax(0,-p); // BE is valid zero risk; locked gains do not finance extra risk here.
  }
  return risk;
 }
void CheckProtection()
 {
  if(active<0) return; int n=active; double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  EnforceTargetCap(); if(closeEmergency || active<0) return;
  for(int i=PositionsTotal()-1;i>=0;i--) {
   ulong ticket=PositionGetTicket(i); if(ticket==0 || !OwnSelected()) continue;
   int leg=LegByPid(n,(ulong)PositionGetInteger(POSITION_IDENTIFIER));
   if(leg<0) { Invalid(301,"Untracked position in active campaign.",true); return; }
   double sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP),v=PositionGetDouble(POSITION_VOLUME);
   if(PositionGetInteger(POSITION_TYPE)!=(cycles[n].side==1 ? POSITION_TYPE_BUY : POSITION_TYPE_SELL) || sl<=0 ||
      !PENear(tp,cycles[n].target,tick) || cycles[n].side*(sl-cycles[n].expectedStops[leg])<-tick*.51) {
    Invalid(302,"Missing, widened or unexpected SL/TP.",true); return;
   }
   if(cycles[n].side*(sl-cycles[n].desiredStop)>tick*.51) { Invalid(303,"SL exceeds the requested protection level."); return; }
   cycles[n].expectedStops[leg]=sl;
   double wanted=cycles[n].volumes[leg];
   bool halfAllowed=leg==0 && cycles[n].partialEnabled && cycles[n].part.attempts>0;
   if(MathAbs(v-wanted)>1e-8 && !(halfAllowed && MathAbs(v-wanted*.5)<1e-8)) {
    Invalid(304,"Unexpected remaining volume; no further volume request allowed."); return;
   }
  }
  double risk=ActiveRisk();
  if(risk<0) { Invalid(305,"Cannot value remaining stop risk.",true); return; }
  cycles[n].peakRisk=MathMax(cycles[n].peakRisk,risk); maxRisk=MathMax(maxRisk,risk);
  double balance=AccountInfoDouble(ACCOUNT_BALANCE); if(balance>0) maxRiskPct=MathMax(maxRiskPct,100*risk/balance);
  if(risk>cycles[n].initialRisk*profile.capRisk+.05) Invalid(306,"Stop-risk budget exceeded after fill.",true);
 }
void Defer(PERequest &r,const string kind,const long ret,const string detail)
 {
  PERejected(r,NowMs(),ret); lastRetcode=(int)ret; lastErrorTime=TimeCurrent();
  if(kind=="PARTIAL_DEFERRED") partialDefers++; else beDefers++;
  if(ret==10018) sessionDefers++; if(ret==10016 || ret==10029) stopDefers++;
  Event(kind,active,detail,ret);
 }
bool MoveStops(const double desired)
 {
  if(active<0) return false; int n=active; long now=NowMs();
  if(cycles[n].side*(desired-cycles[n].desiredStop)>1e-8) {
   cycles[n].desiredStop=desired; cycles[n].be.done=false; cycles[n].be.uncertain=false; PEArm(cycles[n].be,now);
  }
  bool all=true; double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  for(int leg=0;leg<cycles[n].legs;leg++) {
   ulong ticket=0; if(!PositionForLeg(n,leg,ticket)) continue;
   double sl=PositionGetDouble(POSITION_SL);
   if(cycles[n].side*(sl-desired)>=-tick*.5) { cycles[n].expectedStops[leg]=sl; continue; }
   all=false;
   if(!PERequestDue(cycles[n].be,now)) continue;
   if(cycles[n].be.attempts>=24) { cycles[n].be.uncertain=true; Invalid(310,"SL amendment retry budget exhausted."); return false; }
   if(!CanRequest()) { Defer(cycles[n].be,"BE_DEFERRED",10018,"Session or trading permission unavailable."); continue; }
   MqlTick q; if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<q.bid) continue;
   double cp=cycles[n].side==1 ? q.bid : q.ask;
   double distance=MathMax(SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL),SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL))*_Point+tick;
   if(cycles[n].side*(cp-desired)<distance || cycles[n].side*(cycles[n].target-cp)<distance ||
      (SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL)>0 && cycles[n].side*(cp-sl)<distance)) {
    Defer(cycles[n].be,"BE_DEFERRED",10029,"Stop/target freeze distance; original SL remains."); continue;
   }
   MqlTradeRequest req={}; MqlTradeResult res={}; req.action=TRADE_ACTION_SLTP; req.position=ticket;
   req.symbol=_Symbol; req.magic=InpMagic; req.sl=NormalizeDouble(desired,_Digits); req.tp=cycles[n].target;
   PEAttempt(cycles[n].be,now); bool sent=OrderSend(req,res); cycles[n].be.lastRet=res.retcode;
   bool exists=PositionSelectByTicket(ticket);
   if(exists && cycles[n].side*(PositionGetDouble(POSITION_SL)-desired)>=-tick*.5) {
    cycles[n].expectedStops[leg]=PositionGetDouble(POSITION_SL); cycles[n].be.nextTryMs=now;
    Event("SL_CONFIRMED",n,"ticket="+U(ticket)+"; sl="+N(desired),res.retcode);
   } else if(!exists) continue;
   else {
    int cls=PERetcodeClass(res.retcode);
    // An SLTP retry is idempotent and changes no volume; re-read before every retry.
    if(cls==3) { cycles[n].be.uncertain=true; Invalid(311,"Permanent/unknown SL amendment rejection."); }
    Defer(cycles[n].be,"BE_DEFERRED",res.retcode,"SL not yet confirmed; sent="+I(sent));
   }
  }
  all=true; int stillOpen=0;
  for(int leg=0;leg<cycles[n].legs;leg++) { ulong t=0; if(PositionForLeg(n,leg,t)) {
   stillOpen++; if(cycles[n].side*(PositionGetDouble(POSITION_SL)-desired)<-tick*.5) all=false;
  } }
  if(stillOpen==0) return false;
  if(all) {
   cycles[n].be.done=true;
   if(cycles[n].beTime==0 && cycles[n].side*(desired-cycles[n].entry)>=-tick*.5) {
    cycles[n].beTime=TimeCurrent(); months[MonthIndex(TimeCurrent())].bes++; Event("BE_CONFIRMED",n,"SL anchored to actual primary entry or better.");
   }
  }
  return all;
 }
bool ReconcilePartial()
 {
  if(active<0) return false; int n=active; if(cycles[n].part.done) return true;
  ulong ticket=0; if(!PositionForLeg(n,0,ticket)) return false;
  double live=PositionGetDouble(POSITION_VOLUME);
  if(PEVolumeState(cycles[n].volume,live)!=1 || cycles[n].part.attempts==0) return false;
  if(!HistorySelect(cycles[n].start,TimeCurrent())) return false;
  double volume=0,value=0; datetime when=0;
  for(int i=0;i<HistoryDealsTotal();i++) {
   ulong d=HistoryDealGetTicket(i);
   if((ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID)!=cycles[n].pid || HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_OUT ||
      HistoryDealGetInteger(d,DEAL_REASON)!=DEAL_REASON_EXPERT || (ulong)HistoryDealGetInteger(d,DEAL_MAGIC)!=InpMagic) continue;
   double v=HistoryDealGetDouble(d,DEAL_VOLUME); volume+=v; value+=v*HistoryDealGetDouble(d,DEAL_PRICE);
   when=(datetime)HistoryDealGetInteger(d,DEAL_TIME);
  }
  if(MathAbs(volume-cycles[n].volume*.5)>1e-8) { Invalid(312,"Partial remainder has no matching executed history."); return false; }
  cycles[n].part.done=true; cycles[n].part.uncertain=false; cycles[n].partialTime=when;
  cycles[n].partialVolume=volume; cycles[n].partialPrice=value/volume; months[MonthIndex(when)].partials++;
  PEArm(cycles[n].be,NowMs()); Event("PARTIAL_CONFIRMED",n,"volume="+N(volume)+"; price="+N(value/volume));
  return true;
 }
void TryPartial()
 {
  if(active<0) return; int n=active; long now=NowMs();
  if(ReconcilePartial()) { MoveStops(cycles[n].entry); return; }
  if(cycles[n].part.uncertain) {
   if(now-cycles[n].part.lastTryMs>60000) Invalid(313,"Unresolved partial reply; no duplicate reduction. Broker SL remains.");
   return;
  }
  if(!PERequestDue(cycles[n].part,now)) return;
  if(cycles[n].part.attempts>=24) { cycles[n].part.uncertain=true; Invalid(314,"Partial retry budget exhausted."); return; }
  MqlTick q; if(!SymbolInfoTick(_Symbol,q)) return;
  if(!PEPartialPriceReady(q.bid,cycles[n].entry,cycles[n].stop,cycles[n].target)) return;
  if(!CanRequest()) { Defer(cycles[n].part,"PARTIAL_DEFERRED",10018,"Session/permission unavailable."); return; }
  ulong ticket=0; if(!PositionForLeg(n,0,ticket) || PEVolumeState(cycles[n].volume,PositionGetDouble(POSITION_VOLUME))!=0) return;
  MqlTradeRequest req={}; MqlTradeResult res={}; req.action=TRADE_ACTION_DEAL; req.position=ticket;
  req.symbol=_Symbol; req.magic=InpMagic; req.type=ORDER_TYPE_SELL; req.price=q.bid;
  req.volume=cycles[n].volume*.5; req.type_filling=Filling(); req.deviation=InpDeviationPoints; req.comment="EV160-PARTIAL";
  PEAttempt(cycles[n].part,now); bool sent=OrderSend(req,res); cycles[n].partialDeal=res.deal; cycles[n].partialOrder=res.order;
  cycles[n].part.lastRet=res.retcode;
  if(ReconcilePartial()) { MoveStops(cycles[n].entry); return; }
  if(!PositionSelectByTicket(ticket)) return; // SL/TP may have closed the entire position meanwhile
  int cls=PERetcodeClass(res.retcode);
  if(cls==1 && res.deal==0) { Defer(cycles[n].part,"PARTIAL_DEFERRED",res.retcode,"Definitive rejection; sent="+I(sent)); return; }
  cycles[n].part.uncertain=true; ambiguousPartials++; lastRetcode=(int)res.retcode; lastErrorTime=TimeCurrent();
  Event("AMBIGUOUS_PARTIAL",n,"Await history/remaining-volume confirmation; never resend blindly.",res.retcode);
  if(cls==3) Invalid(315,"Permanent/unknown partial response.");
 }
void ManageProtection()
 {
  if(active<0) return; CheckProtection(); if(closeEmergency || active<0) return;
  int n=active; MqlTick q; if(!SymbolInfoTick(_Symbol,q)) return;
  if(cycles[n].partialEnabled) {
   if(PEPartialPriceReady(q.bid,cycles[n].entry,cycles[n].stop,cycles[n].target)) PEArm(cycles[n].part,NowMs());
   TryPartial();
  } else if(cycles[n].beTrigger>0) {
   double r=(q.bid-cycles[n].entry)/(cycles[n].entry-cycles[n].stop);
   if(r>=cycles[n].beTrigger) PEArm(cycles[n].be,NowMs());
   if(cycles[n].be.armed && !cycles[n].be.done) MoveStops(cycles[n].entry);
  }
  if(profile.arm==8 && cycles[n].be.armed && !cycles[n].be.done) MoveStops(cycles[n].desiredStop);
 }
void ManageAdd(const bool newBar,const bool recovery)
 {
  if(active<0 || haltEntries || closeEmergency || profile.addFraction<=0) return;
  int n=active; if(cycles[n].addPending || NowMs()<cycles[n].addNextMs) return;
  if(profile.arm!=8 && !newBar) return;
  MqlTick q; if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<q.bid) return;
  double distance=cycles[n].entry-cycles[n].stop,r=(q.bid-cycles[n].entry)/distance;
  if(!PEAddWindow(profile.arm,cycles[n].adds,r,recovery)) return;
  cycles[n].addNextMs=NowMs()+5000;
  if(!CanRequest() || OwnPendingOrder()) return;
  if(cycles[n].addAttempts>=24) { cycles[n].addPending=true; Event("ADD_CANCELLED",n,"24 rejected/submitted attempts reached."); return; }
  double v=0; ulong t=0; if(OwnPositions(v,t)!=cycles[n].legs) return;
  if(InpMaxSpreadPoints>0 && (q.ask-q.bid)/_Point>InpMaxSpreadPoints) return;
  double sl=cycles[n].stop;
  if(profile.arm==8) {
   sl=cycles[n].entry+cycles[n].adds*distance;
   sl=MathFloor(sl/SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE)+1e-9)*SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(!MoveStops(sl)) return; // lock primary/all existing legs before adding
  }
  double volume=cycles[n].volume*profile.addFraction;
  double stops=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
  if(q.bid-sl<stops || cycles[n].target-q.bid<stops) return;
  double loss=0,margin=0,existing=ActiveRisk();
  if(!OrderCalcProfit(ORDER_TYPE_BUY,_Symbol,volume,q.ask,sl,loss) || existing<0) { Invalid(320,"Cannot value proposed addition."); return; }
  if(!PERiskWithin(existing,MathMax(0,-loss),cycles[n].initialRisk,profile.capRisk)) { riskBlocks++; Event("ADD_RISK_BLOCK",n,"Nominal stop budget."); return; }
  if(!OrderCalcMargin(ORDER_TYPE_BUY,_Symbol,volume,q.ask,margin) || margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)) { Event("ADD_MARGIN_BLOCK",n,"Insufficient free margin."); return; }
  cycles[n].addAttempts++;
  bool sent=trade.Buy(volume,_Symbol,0,NormalizeDouble(sl,_Digits),cycles[n].target,"EV160-ADD-N"+I(cycles[n].number));
  uint ret=trade.ResultRetcode();
  if(!sent || ret!=TRADE_RETCODE_DONE) {
   addRejects++; lastRetcode=(int)ret; lastErrorTime=TimeCurrent(); Event("ADD_REJECTED",n,trade.ResultRetcodeDescription(),ret);
   cycles[n].addNextMs=NowMs()+PERetryDelayMs(ret);
   if(PERetcodeClass(ret)==2 || ret==TRADE_RETCODE_DONE) { cycles[n].addPending=true; Invalid(321,"Uncertain addition; no duplicate request.",true); }
   else if(PERetcodeClass(ret)==3) { cycles[n].addPending=true; Invalid(322,"Permanent addition rejection."); }
   return;
  }
  ulong d=trade.ResultDeal();
  if(d==0 || !HistoryDealSelect(d) || HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_IN ||
     HistoryDealGetInteger(d,DEAL_TYPE)!=DEAL_TYPE_BUY || (ulong)HistoryDealGetInteger(d,DEAL_MAGIC)!=InpMagic ||
     HistoryDealGetString(d,DEAL_SYMBOL)!=_Symbol || MathAbs(HistoryDealGetDouble(d,DEAL_VOLUME)-volume)>1e-8) {
   Invalid(323,"Addition fill cannot be reconciled.",true); return;
  }
  ulong pid=(ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID); int j=cycles[n].legs;
  if(j>=3 || pid==0 || CycleByPid(pid)>=0) { Invalid(324,"Addition requires a distinct hedging position.",true); return; }
  cycles[n].pids[j]=pid; cycles[n].fills[j]=HistoryDealGetDouble(d,DEAL_PRICE); cycles[n].volumes[j]=volume;
  cycles[n].expectedStops[j]=sl; cycles[n].legs++; cycles[n].adds++;
  Event("ADD_FILLED",n,"lot="+N(volume)+"; price="+N(cycles[n].fills[j])+"; sl="+N(sl),ret);
  CheckProtection(); SyncCycle();
 }
void EmergencyClose()
 {
  if(!closeEmergency || !CanRequest() || NowMs()-lastEmergencyMs<10000) return;
  lastEmergencyMs=NowMs();
  for(int i=PositionsTotal()-1;i>=0;i--) {
   ulong t=PositionGetTicket(i); if(t==0 || !OwnSelected()) continue;
   bool sent=trade.PositionClose(t); uint ret=trade.ResultRetcode();
   Event("EMERGENCY_CLOSE",active,"ticket="+U(t)+"; sent="+I(sent),ret);
  }
  SyncCycle();
 }


PE_GATE OpenCycle(const int origin,const int side,const H1Signal &s,const MqlTick &q,const datetime signalTime,
                  double &sl,double &tp,double &risk,string &detail)
 {
  double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),entry=side==1 ? q.ask : q.bid;
  H1Signal setup=s; if(evo.entryPolicy==8) { setup.lowest=pivotSwing; setup.highest=pivotSwing; }
  double reward=(InpCase==5 ? InpQHTargetR : 5.0);   // Caso 5: alvo curto em R
  if(!H1Levels(side,entry,setup,.20,1.0,2.5,reward,tick,sl,tp)) return G_STOP;
  // Original structural stop is retained in every case.
  if(dc.minimumStopATR>1.0 && !DCStructuralStopAccepted(entry,sl,s.atr,dc.minimumStopATR)) {
   detail="Structural stop below required ATR distance; not widened."; return G_STOP;
  }
  if(dc.targetMode>0) {
   double distance=HermesTargetDistance(dc.targetMode,_Point);
   if(!HermesTargetPrice(side,entry,distance,tick,tp)) {
    targetRejects++; detail="Target below one tick, invalid units or non-representable target; no widening."; return G_TARGET;
   }
  }
  plannedTargetDistance=side*(tp-entry); plannedTargetRiskRatio=plannedTargetDistance/MathAbs(entry-sl);
  sl=NormalizeDouble(sl,_Digits); tp=NormalizeDouble(tp,_Digits);
  double minstop=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
  double closePrice=side==1 ? q.bid : q.ask;
  if(side*(closePrice-sl)<minstop || side*(tp-closePrice)<minstop || sl<=0 || tp<=0) {
   detail="Broker stop distance not met; target and structural stop were not enlarged.";
   if(dc.targetMode>0) targetRejects++;
   return G_BROKER_STOPS;
  }
  double mn=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),mx=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX),step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
  if(!MathIsValidNumber(mn) || !MathIsValidNumber(mx) || !MathIsValidNumber(step) || mn<=0 || mx<mn || step<=0) return G_RISK;
  double volume=InpFixedLot,profit=0,margin=0;
  ENUM_ORDER_TYPE type=side==1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
  if(dc.fixedLot) {
   sizingMarginBudget=AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(!HermesExactLot(volume,mn,mx,step)) {
    fixedVolumeRejects++; detail="Exact fixed lot incompatible with symbol min/max/step; NOT reduced."; return G_RISK;
   }
  } else {
   double referenceLoss=0,referenceMargin=0;
   if(!OrderCalcProfit(type,_Symbol,mn,entry,sl,referenceLoss) || referenceLoss>=0) return G_RISK;
   if(!OrderCalcMargin(type,_Symbol,mn,entry,referenceMargin)) return G_MARGIN_ERROR;
   double eq=AccountInfoDouble(ACCOUNT_EQUITY),free=AccountInfoDouble(ACCOUNT_MARGIN_FREE),used=AccountInfoDouble(ACCOUNT_MARGIN);
   minimumLotRiskMoney=-referenceLoss; minimumLotMargin=referenceMargin;
   minimumLotRiskPercent=eq>0 ? 100*(-referenceLoss)/eq : 0;
   minimumEquityForLot=MathMax((-referenceLoss)*100.0/dc.riskPercent,(used+referenceMargin)*100.0/InpMaxMarginPct);
   double effRiskPercent=dc.riskPercent;
   // Caso 6 apenas: o mesmo risco% do Caso 4, modulado pelo freio de
   // rebaixamento (DDThrottleCore.mqh). Casos 4/5/7 nunca entram aqui - o
   // multiplicador so existe quando InpCase==6, preservando os demais
   // byte-a-byte no comportamento de sizing.
   if(InpCase==6) effRiskPercent*=DDThrottleMultiplier(eq,ddPeakEquity,InpDDBand1,InpDDMult1,InpDDBand2,InpDDMult2);
   // Caso 7 apenas: risco% calculado sobre o capital de risco (patrimonio
   // menos o total ja "sacado" - WithdrawalCore.mqh), nao sobre o patrimonio
   // real. A margem abaixo continua usando eq/free/used REAIS - o saque muda
   // só quanto se arrisca por trade, nunca a margem de fato disponivel.
   double sizingEquityBase=(InpCase==7) ? WDTradingCapital(eq,withdrawState.bankedWithdrawn) : eq;
   sizingRiskBudget=sizingEquityBase*effRiskPercent/100.0;
   sizingMarginBudget=MathMin(free,MathMax(0,eq*InpMaxMarginPct/100.0-used));
   if(InpCase>=4) {
    // Casos 4/5/6: sizing por risco SEM o teto de 2% do DCRiskLot (permite ate
    // 5% conscientemente). Replica a mesma formula do DCRiskLot, reaproveitando
    // os orcamentos ja calculados acima (sizingRiskBudget ja vem com o freio do
    // Caso 6 aplicado, se for o caso); margem% e volume maximo do simbolo
    // continuam limitando. DonchianCore.mqh permanece intocado (core auditado
    // do R200) — este ramo existe aqui, nao ali, porque so os Casos 4/5/6 podem
    // ultrapassar o teto de 2% do DCRiskLot.
    double lossPerLot=-referenceLoss/mn,marginPerLot=referenceMargin/mn;
    double raw=(sizingMarginBudget>0 && lossPerLot>0) ? MathMin(mx,sizingRiskBudget/lossPerLot) : 0;
    if(marginPerLot>0) raw=MathMin(raw,sizingMarginBudget/marginPerLot);
    volume=MathFloor(raw/step+1e-9)*step;
    if(sizingMarginBudget<=0 || volume<mn-1e-9 || volume*lossPerLot>sizingRiskBudget+1e-7 || volume*marginPerLot>sizingMarginBudget+1e-7) volume=0;
   } else {
    volume=DCRiskLot(eq,free,used,dc.riskPercent,InpMaxMarginPct,-referenceLoss/mn,referenceMargin/mn,mn,mx,step,InpMaxLot);
   }
   if(volume<=0) { detail="Volume below broker minimum within risk/margin budgets; no forced minimum."; riskBlocks++; return G_RISK; }
   // Contract margin may be tiered. Revalue the proposed volume and step down using native values.
   for(int tries=0;tries<8;tries++) {
    if(!OrderCalcProfit(type,_Symbol,volume,entry,sl,profit) || profit>=0) return G_RISK;
    if(!OrderCalcMargin(type,_Symbol,volume,entry,margin)) return G_MARGIN_ERROR;
    if(-profit<=sizingRiskBudget+1e-7 && margin<=sizingMarginBudget+1e-7) break;
    double ratio=MathMin(sizingRiskBudget/(-profit),margin>0 ? sizingMarginBudget/margin : 1.0);
    volume=MathFloor(MathMin(volume-step,volume*ratio)/step+1e-9)*step;
    if(volume<mn-1e-9) { riskBlocks++; return G_RISK; }
   }
  }
  sizedLot=volume;
  if(H1Volume(FIXED_LOT,volume,1,1,mn,mx,step)<=0) return G_RISK;
  if(!OrderCalcProfit(type,_Symbol,volume,entry,sl,profit) || profit>=0) return G_RISK;
  risk=-profit;
  if(!OrderCalcMargin(type,_Symbol,volume,entry,margin)) return G_MARGIN_ERROR;
  sizingMargin=margin;
  if(!dc.fixedLot && risk>sizingRiskBudget+1e-7) { riskBlocks++; return G_RISK; }
  if(!HermesMarginAvailable(margin,AccountInfoDouble(ACCOUNT_MARGIN_FREE)) || (!dc.fixedLot && margin>sizingMarginBudget+1e-7)) {
   detail="Required margin="+N(margin)+"; free="+N(AccountInfoDouble(ACCOUNT_MARGIN_FREE))+"; fixed lot is not reduced.";
   return G_MARGIN_BLOCK;
  }
  if(!OrderCalcProfit(type,_Symbol,volume,entry,tp,plannedTargetProfit)) { detail="Cannot value target profit."; return G_TARGET; }
  double balance=AccountInfoDouble(ACCOUNT_BALANCE); int number=ArraySize(cycles)+1;
  string comment="HP200-O"+I(origin)+"-N"+I(number);
  bool sent=side==1 ? trade.Buy(volume,_Symbol,0,sl,tp,comment) : trade.Sell(volume,_Symbol,0,sl,tp,comment);
  uint ret=trade.ResultRetcode(); detail="ret="+I(ret)+"; deal="+U(trade.ResultDeal())+"; "+trade.ResultRetcodeDescription();
  if(!sent || ret!=TRADE_RETCODE_DONE) {
   lastRetcode=(int)ret; lastErrorTime=TimeCurrent(); Event("ENTRY_REJECTED",-1,detail,ret);
   if(PERetcodeClass(ret)==2 || ret==TRADE_RETCODE_DONE) Invalid(201,"Initial order uncertain; no duplicate entry allowed.",true);
   return G_REJECTED;
  }
  ulong deal=trade.ResultDeal();
  if(deal==0 || !HistoryDealSelect(deal) || HistoryDealGetString(deal,DEAL_SYMBOL)!=_Symbol ||
     (ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=InpMagic || HistoryDealGetInteger(deal,DEAL_ENTRY)!=DEAL_ENTRY_IN ||
     HistoryDealGetInteger(deal,DEAL_TYPE)!=(side==1 ? DEAL_TYPE_BUY : DEAL_TYPE_SELL)) { Invalid(202,"Entry fill identity missing.",true); return G_HALTED; }
  int n=ArraySize(cycles); ArrayResize(cycles,n+1); ZeroMemory(cycles[n]); active=n;
  cycles[n].entryPath=hpRoute.path;
  if(hpRoute.path==HP_PIVOT) cycles[n].entryPivot=hpSignal;
  cycles[n].number=number; cycles[n].origin=origin; cycles[n].side=side; cycles[n].legs=1;
  cycles[n].pid=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID); cycles[n].pids[0]=cycles[n].pid;
  cycles[n].start=(datetime)HistoryDealGetInteger(deal,DEAL_TIME); cycles[n].signalTime=signalTime;
  cycles[n].quotedEntry=entry; cycles[n].quotedTarget=tp; cycles[n].targetDistance=HermesTargetDistance(dc.targetMode,_Point);
  cycles[n].entry=HistoryDealGetDouble(deal,DEAL_PRICE); cycles[n].volume=HistoryDealGetDouble(deal,DEAL_VOLUME);
  cycles[n].fills[0]=cycles[n].entry; cycles[n].volumes[0]=cycles[n].volume; cycles[n].expectedStops[0]=sl;
  cycles[n].stop=sl; cycles[n].liveStop=sl; cycles[n].desiredStop=sl; cycles[n].target=tp; cycles[n].balanceBefore=balance;
  cycles[n].partialEnabled=profile.partial || (origin==14 && profile.protect14);
  cycles[n].beTrigger=cycles[n].partialEnabled ? 1.0 : ((profile.mode==0 && origin!=15) ? 0 : profile.be15);
  cycles[n].path.entry=cycles[n].entry; cycles[n].path.stop=sl; cycles[n].path.side=side;
  cycles[n].entryPolicy=evo.entryPolicy; cycles[n].entryFeatures=features;
  cycles[n].featureADXChange=s.adx-s.oldADX; cycles[n].featureADX=s.adx; cycles[n].featureATR=s.atr;
  cycles[n].featureDistance=(entry-s.ema)/s.atr; cycles[n].featureSlope=(s.sma200-oldSMA200)/s.atr;
  if(cycles[n].pid==0 || side*(cycles[n].entry-sl)<=0 || MathAbs(cycles[n].volume-volume)>1e-8)
    Invalid(203,"Initial fill does not match planned volume/stop.",true);
  if(!OrderCalcProfit(type,_Symbol,volume,cycles[n].entry,sl,profit) || profit>=0) Invalid(204,"Cannot value initial risk.",true);
  else { cycles[n].initialRisk=-profit; cycles[n].peakRisk=-profit; maxRisk=MathMax(maxRisk,-profit); if(balance>0) maxRiskPct=MathMax(maxRiskPct,-profit/balance*100); }
  maxLots=MathMax(maxLots,volume); MonthIndex(cycles[n].start); months[liveMonth].opened++;
  if(evo.entryPolicy==8) lastPivotUsed=pivotTime;
  detail+="; entry_path="; detail+=(hpRoute.path==HP_PIVOT ? "PIVOT" : "BASE");
  detail+="; original_gate="+I(hpRoute.original_gate)+"; extra_gate="+I(hpRoute.extra_gate);
  if(hpRoute.path==HP_PIVOT) {
   hpPivotFills++;
   detail+="; pivot_signal_time="+I(hpSignal.signal_time)+"; p1_time="+I(hpSignal.p1_time)+"; p2_time="+I(hpSignal.p2_time)+"; p3_time="+I(hpSignal.p3_time);
  }
  Event("ENTRY_FILLED",n,detail); ObserveOpenPath(); EnforceTargetCap();
  if(!closeEmergency && PositionForLeg(n,0,deal)) {
   double estimate=0;
   if(OrderCalcProfit(type,_Symbol,cycles[n].volume,cycles[n].entry,cycles[n].target,estimate)) cycles[n].targetProfitEstimate=estimate;
  }
  CheckProtection(); SyncCycle(); return G_FILLED;
 }
void OnTick()
 {
  if(!initialized) return;
  TrackEquity(); ObserveOpenPath(); SyncCycle();
  if(closeEmergency) { EmergencyClose(); TrackEquity(); return; }
  ManageProtection(); TrackEquity(); SyncCycle();
  datetime bar=iTime(_Symbol,signalTF,0); bool newBar=bar>0 && bar!=lastBar;
  if(!newBar) { if(profile.arm==8) ManageAdd(false,false); return; }
  lastBar=bar; lastEval=TimeCurrent(); if(firstEval==0) firstEval=lastEval;
  barsSeen++; int mi=MonthIndex(TimeCurrent()); months[mi].bars++;
  hpRoute.original_gate=-1; hpRoute.extra_gate=HP_DATA_PENDING; hpRoute.setup=-1; hpRoute.side=0; hpRoute.path=HP_NONE;
  hpDataReady=HPSyncClosedBars(bar);
  if(!hpDataReady) hpDataFailures++;
  if(hpSignal.buy) hpCandidates++;
  H1Signal s; ZeroMemory(s); MqlTick q; ZeroMemory(q); datetime signalTime=0;
  sizedLot=0; sizingRiskBudget=0; sizingMarginBudget=0; sizingMargin=0;
  plannedTargetDistance=0; plannedTargetRiskRatio=0; plannedTargetProfit=0;
  minimumLotRiskMoney=0; minimumLotRiskPercent=0; minimumEquityForLot=0; minimumLotMargin=0;
  channelReady=false; channelBars=0; channelUpper=0; channelLower=0; channelOldest=0; channelNewest=0; channelClosedAt=0; channelStatus="SIGNAL_DATA_PENDING";
  if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<q.bid || !ReadSignal(s,signalTime)) { Record(G_NO_DATA,-1,0,s,q,signalTime); return; }
  if(dc.channelMode>0 && !channelReady) { Record(G_NO_DATA,120,evo.family,s,q,signalTime,0,0,0,channelStatus); return; }
  if(firstReady==0 && (dc.channelMode==0 || channelReady)) firstReady=TimeCurrent();
  int side=0;
  double minimumEntryDistance=InpMinEntryATR;
  if(InpCase==5) {
   // Caso 5 (Colheita Rapida): rota propria por surto de volume/range.
   QHFeatures qhf; bool qok=ReadQuickHarvest(s,qhf); int qside=0;
   int qgate=qok ? QHGate(s,qhf,q.ask,q.bid,s.atr,InpQHMinADX,InpQHVolFactor,InpQHRangeFactor,
                          InpQHMinCloseLoc,InpMinEntryATR,InpQHMaxSpreadATR,qside) : QH_DATA;
   hpRoute.original_gate=qgate; hpRoute.extra_gate=HP_DISABLED;
   hpRoute.setup=(qgate==QH_READY ? 0 : qgate); hpRoute.side=qside;
   hpRoute.path=(qgate==QH_READY ? HP_BASE : HP_NONE);
  } else {
   HPRouteEntry(InpCase,evo,s,features,q.ask,oldSMA200,minimumEntryDistance,
                hpDataReady,hpSignal,hpRoute);
  }
  int setup=hpRoute.setup; side=hpRoute.side;
  if(hpRoute.extra_gate==0) hpExtraEligible++;
  if(hpRoute.path==HP_BASE) hpBaseSelected++;
  if(hpRoute.path==HP_PIVOT) hpPivotSelected++;
  bool pivotOK=pivotSide!=0 && pivotTime!=lastPivotUsed && s.adx>=20 && s.adx>s.oldADX &&
    (pivotSide==1 ? (s.plusDI>s.minusDI && s.close>s.open && s.close>s.ema) : (s.minusDI>s.plusDI && s.close<s.open && s.close<s.ema));
  if(pivotOK) { if(pivotSide==1) patternBuys++; else patternSells++; }
  if(setup==0) { signals++; months[mi].signals++; }
  if(haltEntries) { Record(G_HALTED,setup,0,s,q,signalTime); return; }
  bool recovery=s.close>s.open && s.close>previousClose && s.adx>=20 && s.plusDI>s.minusDI && s.close>s.sma200 &&
    s.ema>s.sma50 && s.sma50>s.oldSma50 && (cyclesSizeOrigin15() ? s.sma200>oldSMA200 : true);
  if(active>=0) { ManageAdd(true,recovery); Record(G_POSITION,setup,active>=0 ? cycles[active].origin : 0,s,q,signalTime); return; }
  if(SymbolExposure()) { Record(G_POSITION,setup,0,s,q,signalTime); return; }
  if(InpMaxSpreadPoints>0 && (q.ask-q.bid)/_Point>InpMaxSpreadPoints) { Record(G_SPREAD,setup,0,s,q,signalTime); return; }
  int origin=evo.family;
  if(setup!=0) {
   PE_GATE gate=setup==120 ? G_NO_DATA : setup==110 ? G_DISTANCE : (setup==111 ? G_REGIME : (setup==109 ? G_DIRECTION : (setup>=100 ? G_ENTRY_FILTER : G_BASE)));
   Record(gate,setup,origin,s,q,signalTime); return;
  }
  double sl=0,tp=0,risk=0; string detail=""; PE_GATE result=OpenCycle(origin,side,s,q,signalTime,sl,tp,risk,detail);
  Record(result,setup,origin,s,q,signalTime,sl,tp,risk,detail); if(closeEmergency) EmergencyClose(); TrackEquity();
 }
bool cyclesSizeOrigin15() { return active>=0 && cycles[active].origin==15; }
bool WriteParameters()
 {
  int f=OpenText(folder+"\\parameters.txt"); if(f==INVALID_HANDLE) return false;
  KV(f,"EA","Hermes_Pivos_Lab_200"); KV(f,"version","2.00"); KV(f,"case",I(InpCase)); KV(f,"profile",ProfileName(InpCase));
  KV(f,"run_tag",InpRunTag); KV(f,"symbol",_Symbol); KV(f,"currency",AccountInfoString(ACCOUNT_CURRENCY));
  KV(f,"signal_tf",TFName(InpCase)); KV(f,"source_control170","28"); KV(f,"source_control180",I(dc.sourceControl180)); KV(f,"matched_control190",I(dc.matchedControl));
  KV(f,"risk_percent",N(dc.riskPercent)); KV(f,"margin_cap_percent",dc.fixedLot ? "no_extra_percent_cap_free_margin_only" : N(InpMaxMarginPct));
  KV(f,"max_lot",dc.fixedLot ? N(InpFixedLot) : N(InpMaxLot)); KV(f,"initial_lot_reference",N(InpFixedLot));
  KV(f,"fixed_lot_mode",I(dc.fixedLot)); KV(f,"capital_mode",dc.fixedLot ? "EXACT_FIXED_LOT" : "EQUITY_RISK_2PCT");
  KV(f,"target_unit",TargetUnitName()); KV(f,"target_unit_code",I(dc.targetMode)); KV(f,"target_value",dc.targetMode==0 ? "5" : "20");
  KV(f,"resolved_target_distance_price",N(HermesTargetDistance(dc.targetMode,_Point)));
  KV(f,"target_R",dc.targetMode==0 ? "5" : "variable_target_divided_by_original_stop"); KV(f,"partial_enabled","0"); KV(f,"BE_trigger_R","0"); KV(f,"max_adds","0");
  KV(f,"case_protocol","1 HERMES_REFERENCIA;2 HERMES_PIVO_CONTINUIDADE;3 HERMES_PIVO_INICIO. All M30, exact fixed lot, target5R, no partial/BE/add/reinvestment.");
  KV(f,"reference_source_sha256","0ddbee937fc4b5af16510987f84d72e126012e0a080b61ef18530a80275d8e35");
  KV(f,"reference_EA","Olimpo_Consistencia_Lab_190 case2");
  KV(f,"native_compilation_or_backtest_by_assistant","false; native user validation pending");
  KV(f,"M30_entry","Original Hermes rules: EMA21>SMA50; rising SMA50/SMA200; close>SMA200; ADX14>=20; +DI>-DI; prior EMA touch; bullish close above EMA21 and prior high; ask-EMA>=minimum_distance_ATR. Always original first.");
  KV(f,"extra_entry_common","Fresh causal confirmed LONG 1-2-3 neckline cross; bullish closed candle above EMA21; EMA21>SMA50 and SMA50>SMA50[6]; ADX14>=20; +DI>-DI; valid SMA3-SMA10 oscillator greater than its previous value; ask-EMA>=minimum_distance_ATR.");
  KV(f,"extra_entry_case2","Also close>SMA200 and SMA200>SMA200[6].");
  KV(f,"extra_entry_case3","Only the two SMA200 conditions are omitted for the extra entry; original entry rules unchanged.");
  KV(f,"entry_priority","Extra only when original EVOEvaluate fails. An original signal later rejected by stop/margin/spread does not fall back to another entry. One position; pivot event consumed even while blocked.");
  KV(f,"pivot_algorithm","HERMES_PIVOS_2x2_V1; strict 2-left/2-right extrema; tied extrema excluded; double-extreme candle resets alternating sequence; L1-H-L2 with L1<L2<H; closed crossing of H; known before trigger open; invalidated by low<=L1. Geometric L1 is NOT execution stop.");
  KV(f,"pivot_time_rule","Pivots available at next observed opening after second right candle; breakout evaluated only using references known at breakout-bar open; no open-candle OHLC used.");
  KV(f,"pivot_seed","210 closed bars seeded chronologically once; only latest signal may be traded; subsequent closed bars caught up continuously, including occupied periods; historical catch-up signals discarded. Seed boundary may differ from a catalog started in 2022.");
  KV(f,"pivot_data_failure","Extra entries blocked only; original reference remains eligible. State not advanced on incomplete/invalid copy; next bar retries chronological catch-up. No synthetic history.");
  KV(f,"minimum_structural_stop_ATR",N(dc.minimumStopATR));
  KV(f,"stop","Original: minimum low of closed signal plus 2 prior bars minus .20ATR14; entry-stop must be1..2.5ATR or reject. No widening and no replacing stop with geometric L1.");
  KV(f,"sizing","Every case exact InpFixedLot=1.00 default; native free-margin and volume constraints; unavailable lot rejected, never silently reduced. InpMaxMarginPct/InpMaxLot are retained compatibility inputs and unused in these fixed-lot cases.");
  KV(f,"target_execution","Original H1Levels5R quoted-entry target with attached server SL/TP. Tick rounding and actual slippage retained from reference; fills/costs can change realized R. No partial, no BE, no averaging or pyramiding.");
  KV(f,"minimum_distance_ATR",N(InpMinEntryATR)); KV(f,"all_bars",I(InpExportAllBars));
  KV(f,"channel_mode","0_not_used");
  KV(f,"warmup","Original minimum209 bars unchanged; extra pivot seed needs210 closed bars plus current opening witness. Signal indicator failure remains G_NO_DATA.");
  KV(f,"entry_frequency","One decision per new M30 bar, only closed inputs. Extra candidates are hypotheses, not guaranteed fills or profits.");
  KV(f,"account_margin_mode",I(AccountInfoInteger(ACCOUNT_MARGIN_MODE))); KV(f,"leverage",I(AccountInfoInteger(ACCOUNT_LEVERAGE)));
  KV(f,"account_stopout_mode",I(AccountInfoInteger(ACCOUNT_MARGIN_SO_MODE)));
  KV(f,"account_margin_call_level",N(AccountInfoDouble(ACCOUNT_MARGIN_SO_CALL)));
  KV(f,"account_stopout_level",N(AccountInfoDouble(ACCOUNT_MARGIN_SO_SO)));
  KV(f,"initial_deposit",N(initialDeposit)); KV(f,"point",N(_Point)); KV(f,"tick_size",N(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE)));
  KV(f,"contract_size",N(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE)));
  KV(f,"tick_value_profit",N(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE_PROFIT))); KV(f,"tick_value_loss",N(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE_LOSS)));
  KV(f,"volume_min",N(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN))); KV(f,"volume_max",N(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX))); KV(f,"volume_step",N(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP)));
  KV(f,"margin_initial",N(SymbolInfoDouble(_Symbol,SYMBOL_MARGIN_INITIAL))); KV(f,"margin_maintenance",N(SymbolInfoDouble(_Symbol,SYMBOL_MARGIN_MAINTENANCE))); KV(f,"trade_calc_mode",I(SymbolInfoInteger(_Symbol,SYMBOL_TRADE_CALC_MODE)));
  KV(f,"magic",U(InpMagic)); KV(f,"deviation_points",U(InpDeviationPoints)); KV(f,"max_spread_points",N(InpMaxSpreadPoints));
  KV(f,"scope","Strategy Tester only; predeclared hypotheses, no fitted future outcomes. Profit unknown; native report needed for dates/tick quality/model/latency.");
  FileClose(f); return !ioFailure;
 }
int OnInit()
 {
  if(!MQLInfoInteger(MQL_TESTER)) { Print("Use Ctrl+R. EA de pesquisa, exclusivo do Testador de Estrategias."); return INIT_FAILED; }
  if(!HPSelectProfile(InpCase,dc,evo,profile) || !ValidRunTag()) return INIT_PARAMETERS_INCORRECT;
  // R210: Casos 4 e 5 usam sizing por risco; o percentual vem do input.
  if(InpCase>=4) {
   if(!MathIsValidNumber(InpRiskPercent) || InpRiskPercent<=0 || InpRiskPercent>5.0) return INIT_PARAMETERS_INCORRECT;
   if(InpRiskPercent>2.0) Print("AVISO: risco por trade ",DoubleToString(InpRiskPercent,2),"% acima de 2%. O risco de ruina cresce rapido; use conscientemente.");
   dc.riskPercent=InpRiskPercent;
  }
  if(InpCase==6) {
   if(!MathIsValidNumber(InpDDBand1) || !MathIsValidNumber(InpDDBand2) || !MathIsValidNumber(InpDDMult1) || !MathIsValidNumber(InpDDMult2) ||
      InpDDBand1<0 || InpDDBand2<=InpDDBand1 || InpDDMult1<=0 || InpDDMult1>1.0 || InpDDMult2<=0 || InpDDMult2>InpDDMult1)
    return INIT_PARAMETERS_INCORRECT;
  }
  if(InpCase==7) {
   if(!MathIsValidNumber(InpWithdrawFraction) || InpWithdrawFraction<0.0 || InpWithdrawFraction>1.0)
    return INIT_PARAMETERS_INCORRECT;
  }
  if(InpCase==5) {
   if(!MathIsValidNumber(InpQHTargetR) || InpQHTargetR<=0 || InpQHTargetR>5 ||
      !MathIsValidNumber(InpQHVolFactor) || InpQHVolFactor<1.0 ||
      !MathIsValidNumber(InpQHRangeFactor) || InpQHRangeFactor<=0 ||
      !MathIsValidNumber(InpQHMinCloseLoc) || InpQHMinCloseLoc<0 || InpQHMinCloseLoc>1 ||
      !MathIsValidNumber(InpQHMinADX) || InpQHMinADX<0 ||
      !MathIsValidNumber(InpQHMaxSpreadATR) || InpQHMaxSpreadATR<=0) return INIT_PARAMETERS_INCORRECT;
  }
  signalTF=PERIOD_M30; HPCoreReset(hpState); HPClearSignal(hpSignal);
  if(_Period!=signalTF) { Print("Caso ",InpCase," exige ",TFName(InpCase)," no testador."); return INIT_PARAMETERS_INCORRECT; }
  if(!MathIsValidNumber(InpMaxMarginPct) || InpMaxMarginPct<=0 || InpMaxMarginPct>50 ||
     !MathIsValidNumber(InpMaxLot) || InpMaxLot<=0) return INIT_PARAMETERS_INCORRECT;
  string symbol=_Symbol; StringToUpper(symbol); if(StringFind(symbol,"XAU")<0 && StringFind(symbol,"GOLD")<0) return INIT_PARAMETERS_INCORRECT;
  if((profile.reinvest && evo.lotCap<InpFixedLot) || !MathIsValidNumber(InpFixedLot) || InpFixedLot<=0 || !MathIsValidNumber(InpMinEntryATR) || InpMinEntryATR<0 || InpMinEntryATR>3 ||
    !MathIsValidNumber(InpMaxSpreadPoints) || InpMaxSpreadPoints<0) return INIT_PARAMETERS_INCORRECT;
  double mn=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),mx=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX),step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
  if(!MathIsValidNumber(mn) || !MathIsValidNumber(mx) || !MathIsValidNumber(step) || mn<=0 || mx<mn || step<=0) return INIT_PARAMETERS_INCORRECT;
  if(dc.fixedLot && !HermesExactLot(InpFixedLot,mn,mx,step))
   Print("Lote fixo incompativel; sinais serao registrados como recusados, sem reduzir volume.");
  if(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE)<=0) return INIT_PARAMETERS_INCORRECT;
  if(profile.addFraction>0 && AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING) {
   Print("Perfis com adicoes exigem conta HEDGE no testador; nao executados em NETTING."); return INIT_PARAMETERS_INCORRECT;
  }
  initialDeposit=AccountInfoDouble(ACCOUNT_BALANCE); LoadSessions();
  TesterHideIndicators(true); hEMA=iMA(_Symbol,signalTF,21,0,MODE_EMA,PRICE_CLOSE);
  if(!dc.weekly) { h50=iMA(_Symbol,signalTF,50,0,MODE_SMA,PRICE_CLOSE); h200=iMA(_Symbol,signalTF,200,0,MODE_SMA,PRICE_CLOSE); }
  hADX=iADX(_Symbol,signalTF,14); hATR=iATR(_Symbol,signalTF,14);
  if(hEMA==INVALID_HANDLE || (!dc.weekly && (h50==INVALID_HANDLE || h200==INVALID_HANDLE)) || hADX==INVALID_HANDLE || hATR==INVALID_HANDLE) return INIT_FAILED;
  trade.SetExpertMagicNumber(InpMagic); trade.SetDeviationInPoints(InpDeviationPoints); trade.SetAsyncMode(false); trade.SetTypeFillingBySymbol(_Symbol);
  ArrayInitialize(counters,0); priorEquity=AccountInfoDouble(ACCOUNT_EQUITY); priorBalance=AccountInfoDouble(ACCOUNT_BALANCE);
  ddPeakEquity=priorEquity;
  withdrawState.realizedPeak=priorBalance; withdrawState.bankedWithdrawn=0;
  MqlRates warmup[]; int required=dc.weekly ? 55 : 209;
  int count=CopyRates(_Symbol,signalTF,0,required,warmup);
  if(count<required) Print("Aquecimento incompleto ",count,"/",required,". Verifique G_NO_DATA.");

  if(InpExportCSV && (!MQLInfoInteger(MQL_OPTIMIZATION) || InpExportOptimizationDetails)) {
   FolderCreate("Hermes_Pivos_Lab_200",FILE_COMMON); FolderCreate(RunRoot(),FILE_COMMON);
   folder=RunRoot()+"\\CASO_"+I(InpCase)+"_"+TFName(InpCase)+"_"+Stamp();
   if(!FolderCreate(folder,FILE_COMMON)) return INIT_FAILED;
   barsFile=OpenText(folder+"\\bars.csv"); eventsFile=OpenText(folder+"\\events.csv");
   if(barsFile==INVALID_HANDLE || eventsFile==INVALID_HANDLE || !WriteParameters()) return INIT_FAILED;
   Row(eventsFile,"time_server;case;cycle;origin_case140;event;retcode;detail");
   Row(barsFile,"event_time;signal_time;case;origin_case140;gate;setup_gate;cycle;open;high;low;close;ema21;sma50;sma200;old_sma50;old_sma200;adx;plus_di;minus_di;atr;bid;ask;sl;tp;risk_money;balance;equity;detail;pivot_side;pivot_break_level;pivot_stop_swing;pivot_time;distance_atr;sma200_slope_atr;previous_adx;previous_close;pivot_pattern_eligible;original15_candidate;original14_candidate;spread_atr;body_atr;entry_policy;oscillator_valid;fast310;previous_fast310;signal310;true_range_atr;close_location;signal_tf;donchian_mode;donchian_ready;donchian_bars;donchian_upper;donchian_lower;donchian_oldest_open;donchian_newest_open;donchian_latest_close;donchian_status;risk_percent;margin_cap_percent;planned_lot;risk_budget;margin_budget;planned_margin;free_margin;used_margin;minimum_lot_risk_money;minimum_lot_risk_percent;minimum_equity_for_minimum_lot;minimum_lot_margin;source_control180;matched_control190;fixed_lot_mode;target_unit;target_value;planned_target_distance_price;planned_target_R;planned_target_gross_profit;hp_data_ready;hp_status;hp_candidate;hp_original_gate;hp_extra_gate;selected_entry_path;hp_signal_time;hp_available_time;hp_p1_price;hp_p2_price;hp_p3_price;hp_p1_time;hp_p2_time;hp_p3_time;hp_p1_confirmation_time;hp_p2_confirmation_time;hp_p3_confirmation_time;hp_p1_available_time;hp_p2_available_time;hp_p3_available_time;hp_pattern_available_time;hp_processed_this_bar;hp_total_processed;hp_last_processed_open;hp_expected_next_open");
   Print("RELATORIOS: ",TerminalInfoString(TERMINAL_COMMONDATA_PATH),"\\Files\\",folder);
  }
  if(InpShowIndicators && MQLInfoInteger(MQL_VISUAL_MODE)) {
   ChartIndicatorAdd(0,0,hEMA); if(!dc.weekly) { ChartIndicatorAdd(0,0,h50); ChartIndicatorAdd(0,0,h200); }
   ChartIndicatorAdd(0,(int)ChartGetInteger(0,CHART_WINDOWS_TOTAL),hADX); ChartIndicatorAdd(0,(int)ChartGetInteger(0,CHART_WINDOWS_TOTAL),hATR);
  }
  if(ioFailure) return INIT_FAILED;
  initialized=true; Print("Hermes Pivos 2.00: ",ProfileName(InpCase),". Hipotese fixa; detalhes por caso."); return INIT_SUCCEEDED;
 }

bool IsTimeStat(const int i)
 { return i==S_FIRST_EVAL || i==S_LAST_EVAL || i==S_FIRST_ENTRY || i==S_LAST_EXIT || i==S_FIRST_READY || i==S_LAST_ERROR_TIME; }
int StatNames(string &names[])
 {
  return StringSplit("valid_run;profit;deposit;final_balance;mt5_trades;mt5_profit_factor;equity_dd_relative_percent;equity_dd_max_money;equity_percent_at_max_money_dd;cycles_opened;cycles_closed;cycle_wins;cycle_losses;cycle_zero;cycle_win_percent;cycle_profit_factor;cycle_net;average_net_R_initial;max_consecutive_losses;average_hold_hours;max_hold_hours;swap;commission_and_fees;max_open_lots;max_stop_risk_money;max_stop_risk_percent;max_margin;first_evaluation;last_evaluation;first_entry;last_exit;bars_seen;signals_before_filters;first_ready;origin15_cycles;origin14_cycles;origin15_net;origin14_net;BE_armed;BE_confirmed;BE_stop_exits;partial_armed;partial_done;partial_deferrals;BE_deferrals;session_deferrals;stop_freeze_deferrals;BE_requests;partial_requests;ambiguous_partials;error_code;last_retcode;last_error_time;reconcile_difference;monthly_equity_reconcile_difference;monthly_booked_reconcile_difference;unmatched_deals;months_observed;positive_equity_months;negative_equity_months;positive_booked_months;negative_booked_months;mean_MFE_R;mean_winner_MFE_R;mean_loser_MFE_R;mean_MAE_R;path_quote_observations;shadow_original_control;fixed_lot;BE_trigger_R;origin_mode;protect14;BE_unfulfilled;partial_unfulfilled;empty_paths;maximum_monthly_DD_percent;add_fills;cycles_with_add;net_cycles_with_add;add_rejections;risk_blocks;initial_stop_factor;reinvestment_enabled;management_arm;initial_lots_sum;add_lots_sum;pivot_buy_candidates;pivot_sell_candidates;entry_policy;reinvestment_fraction;reinvestment_lot_cap;capital_mode;matched_control190;detail_export_enabled;exported_bar_rows;risk_percent;margin_cap_percent;donchian_mode;source_control180;fixed_lot_mode;target_unit_code;target_value;fixed_target_distance_price;nominal_target_R;target_rejections;target_cap_adjustments;target_cap_failures;fixed_volume_rejections;hp_candidates;hp_extra_eligible;hp_base_selected;hp_pivot_selected;hp_pivot_fills;hp_data_failure_bars;hp_extra_position_blocks;hp_historical_catchup_candidates_discarded",';',names);
 }
string MonthHeader()
 { return "month_server;equity_start;equity_end;equity_change;balance_start;balance_end;booked_net;cycle_net_by_exit;equity_dd_relative_percent;equity_dd_money;evaluated_bars;signals;opened_cycles;closed_cycles;BE_confirmed;partial_exits;first_tick;last_tick"; }
void MonthValues(const int i,double &v[])
 {
  v[0]=months[i].key; v[1]=months[i].path.startEquity; v[2]=months[i].path.endEquity; v[3]=v[2]-v[1];
  v[4]=months[i].path.startBalance; v[5]=months[i].path.endBalance; v[6]=months[i].bookedNet; v[7]=months[i].cycleNet;
  v[8]=months[i].path.maxRelativeDD; v[9]=months[i].path.maxMoneyDD; v[10]=months[i].bars; v[11]=months[i].signals;
  v[12]=months[i].opened; v[13]=months[i].closed; v[14]=months[i].bes; v[15]=months[i].partials;
  v[16]=(double)months[i].firstTick; v[17]=(double)months[i].lastTick;
 }
string MonthCSV(const double &data[],const int start)
 {
  string s=""; for(int j=0;j<MONTH_FIELDS;j++) {
   double v=data[start+j];
   if(j==0) { int k=(int)v; Cell(s,I(k/100)+"-"+((k%100)<10 ? "0" : "")+I(k%100)); }
   else Cell(s,j>=16 ? TS((datetime)v) : N(v));
  } return s;
 }
// Eight fields per threshold: threshold,closed,reached,returned,loser_returned,
// winner_returned,zero_returned,sum_first_return_quote_R. Observations, NOT BE fills.
void ShadowValues(const int t,double &v[])
 {
  ArrayInitialize(v,0); v[0]=PEThreshold(t);
  if(InpCase!=1) return;
  for(int i=0;i<ArraySize(cycles);i++) if(cycles[i].closed) {
   v[1]++; if(cycles[i].path.reached[t]) v[2]++;
   if(!cycles[i].path.returned[t]) continue;
   v[3]++; if(cycles[i].net<0) v[4]++; else if(cycles[i].net>0) v[5]++; else v[6]++;
   v[7]+=cycles[i].path.returnQuoteR[t];
  }
 }
string ShadowHeader()
 { return "threshold_R;control_cycles;threshold_reached;returned_to_entry;losers_returned;winners_returned;zero_returned;sum_first_return_quote_R"; }
void ExportDeals()
 {
  if(!HistorySelect(0,TimeCurrent()+86400)) { Invalid(401,"Cannot read final deal history."); return; }
  for(int i=0;i<ArraySize(months);i++) months[i].bookedNet=0;
  int f=folder!="" ? OpenText(folder+"\\deals.csv") : INVALID_HANDLE;
  if(folder!="" && f==INVALID_HANDLE) Invalid(402,"Cannot write deals.csv.");
  Row(f,"time_server;cycle;origin_case140;deal;order;position_id;entry_type;side;reason;volume;price;profit;commission;swap;fee;net_deal;magic;comment");
  for(int i=0;i<HistoryDealsTotal();i++) {
   ulong d=HistoryDealGetTicket(i); if(d==0 || HistoryDealGetString(d,DEAL_SYMBOL)!=_Symbol) continue;
   int n=CycleByPid((ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID));
   if(n<0) { if((ulong)HistoryDealGetInteger(d,DEAL_MAGIC)==InpMagic) unmatchedDeals++; continue; }
   double profit=HistoryDealGetDouble(d,DEAL_PROFIT),swap=HistoryDealGetDouble(d,DEAL_SWAP);
   double fee=HistoryDealGetDouble(d,DEAL_FEE),commission=HistoryDealGetDouble(d,DEAL_COMMISSION);
   datetime time=(datetime)HistoryDealGetInteger(d,DEAL_TIME); months[MonthIndex(time)].bookedNet+=profit+swap+fee+commission;
   string s=""; Cell(s,TS(time)); Cell(s,I(cycles[n].number)); Cell(s,I(cycles[n].origin)); Cell(s,U(d));
   Cell(s,I(HistoryDealGetInteger(d,DEAL_ORDER))); Cell(s,I(HistoryDealGetInteger(d,DEAL_POSITION_ID)));
   Cell(s,EnumToString((ENUM_DEAL_ENTRY)HistoryDealGetInteger(d,DEAL_ENTRY)));
   Cell(s,EnumToString((ENUM_DEAL_TYPE)HistoryDealGetInteger(d,DEAL_TYPE)));
   Cell(s,EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(d,DEAL_REASON)));
   Cell(s,N(HistoryDealGetDouble(d,DEAL_VOLUME))); Cell(s,N(HistoryDealGetDouble(d,DEAL_PRICE)));
   Cell(s,N(profit)); Cell(s,N(commission)); Cell(s,N(swap)); Cell(s,N(fee)); Cell(s,N(profit+commission+swap+fee));
   Cell(s,I(HistoryDealGetInteger(d,DEAL_MAGIC))); Cell(s,HistoryDealGetString(d,DEAL_COMMENT)); Row(f,s);
  }
  if(f!=INVALID_HANDLE) FileClose(f);
 }
void ExportDetails()
 {
  if(folder=="") return;
  int f=OpenText(folder+"\\cycles.csv"); if(f==INVALID_HANDLE) { Invalid(403,"Cannot write cycles.csv."); return; }
  Row(f,"cycle;origin_case140;side;entry_time;exit_time;signal_time;closed;initial_entry;initial_stop;target;initial_lot;initial_risk;peak_stop_risk;balance_before;net;gross;swap;commission_fees;net_R_initial;hold_hours;legs;adds;position0;position1;position2;add1_price;add1_lot;add2_price;add2_lot;BE_trigger_R;BE_armed;BE_confirmed_time;partial_armed;partial_time;partial_lot;partial_price;MFE_R;MAE_R;quote_observations;exit_reason;ADX_entry;ATR_entry;entry_distance_ATR;SMA200_slope_ATR;entry_policy;oscillator_valid;fast310_entry;previous_fast310_entry;signal310_entry;ADX_change_entry;TR_ATR_entry;body_ATR_entry;close_location_entry;source_control180;matched_control190;fixed_lot_mode;target_unit;target_value;requested_target_distance_price;quoted_entry;quoted_target;actual_target_distance_price;actual_target_R;estimated_target_gross_profit;target_cap_adjustments;selected_entry_path;hp_signal_time;hp_available_time;hp_p1_price;hp_p2_price;hp_p3_price;hp_p1_time;hp_p2_time;hp_p3_time;hp_pattern_available_time");
  for(int i=0;i<ArraySize(cycles);i++) {
   PECycle c=cycles[i]; string s=""; Cell(s,I(c.number)); Cell(s,I(c.origin)); Cell(s,I(c.side));
   Cell(s,TS(c.start)); Cell(s,TS(c.finish)); Cell(s,TS(c.signalTime)); Cell(s,I(c.closed));
   Cell(s,N(c.entry)); Cell(s,N(c.stop)); Cell(s,N(c.target)); Cell(s,N(c.volume)); Cell(s,N(c.initialRisk)); Cell(s,N(c.peakRisk));
   Cell(s,N(c.balanceBefore)); Cell(s,N(c.net)); Cell(s,N(c.gross)); Cell(s,N(c.swap)); Cell(s,N(c.costs));
   Cell(s,c.initialRisk>0 ? N(c.net/c.initialRisk) : ""); Cell(s,c.finish>0 ? N((c.finish-c.start)/3600.0) : "");
   Cell(s,I(c.legs)); Cell(s,I(c.adds)); for(int j=0;j<3;j++) Cell(s,U(c.pids[j]));
   for(int j=1;j<3;j++) { Cell(s,N(c.fills[j])); Cell(s,N(c.volumes[j])); }
   Cell(s,N(c.beTrigger)); Cell(s,I(c.be.armed)); Cell(s,TS(c.beTime)); Cell(s,I(c.part.armed));
   Cell(s,TS(c.partialTime)); Cell(s,N(c.partialVolume)); Cell(s,N(c.partialPrice));
   Cell(s,N(c.path.maxR)); Cell(s,N(c.path.minR)); Cell(s,I(c.path.observations)); Cell(s,EnumToString((ENUM_DEAL_REASON)c.finalReason));
   Cell(s,N(c.featureADX)); Cell(s,N(c.featureATR)); Cell(s,N(c.featureDistance)); Cell(s,N(c.featureSlope));
   Cell(s,I(c.entryPolicy)); Cell(s,I(c.entryFeatures.oscillatorValid)); Cell(s,N(c.entryFeatures.fast310));
   Cell(s,N(c.entryFeatures.previousFast310)); Cell(s,N(c.entryFeatures.signal310)); Cell(s,N(c.featureADXChange));
   Cell(s,N(c.entryFeatures.trueRangeATR)); Cell(s,N(c.entryFeatures.bodyATR)); Cell(s,N(c.entryFeatures.closeLocation));
   Cell(s,I(dc.sourceControl180)); Cell(s,I(dc.matchedControl)); Cell(s,I(dc.fixedLot)); Cell(s,TargetUnitName());
   Cell(s,N(dc.targetMode==0 ? 5 : 20)); Cell(s,N(c.targetDistance)); Cell(s,N(c.quotedEntry)); Cell(s,N(c.quotedTarget));
   Cell(s,N(c.side*(c.target-c.entry))); Cell(s,MathAbs(c.entry-c.stop)>0 ? N(c.side*(c.target-c.entry)/MathAbs(c.entry-c.stop)) : "");
   Cell(s,N(c.targetProfitEstimate)); Cell(s,I(c.targetAdjustments));
   Cell(s,HPPathName(c.entryPath)); Cell(s,TS((datetime)c.entryPivot.signal_time)); Cell(s,TS((datetime)c.entryPivot.available_time));
   Cell(s,N(c.entryPivot.stop_f1)); Cell(s,N(c.entryPivot.reference_price)); Cell(s,N(c.entryPivot.pullback_f2));
   Cell(s,TS((datetime)c.entryPivot.p1_time)); Cell(s,TS((datetime)c.entryPivot.p2_time)); Cell(s,TS((datetime)c.entryPivot.p3_time));
   Cell(s,TS((datetime)c.entryPivot.pattern_available_time)); Row(f,s);
  }
  FileClose(f);
  f=OpenText(folder+"\\months.csv"); if(f==INVALID_HANDLE) { Invalid(404,"Cannot write months.csv."); return; }
  Row(f,MonthHeader()); for(int i=0;i<ArraySize(months);i++) { double v[18]; MonthValues(i,v); Row(f,MonthCSV(v,0)); } FileClose(f);
  f=OpenText(folder+"\\breakeven_paths.csv"); if(f==INVALID_HANDLE) { Invalid(405,"Cannot write breakeven_paths.csv."); return; }
  Row(f,"cycle;original_control;threshold_R;threshold_reached;returned_after_threshold;first_return_quote_R;net_original;MFE_R;MAE_R");
  for(int i=0;i<ArraySize(cycles);i++) for(int t=0;t<5;t++) {
   string s=""; Cell(s,I(cycles[i].number)); Cell(s,I(InpCase==1)); Cell(s,N(PEThreshold(t)));
   Cell(s,I(cycles[i].path.reached[t])); Cell(s,I(cycles[i].path.returned[t]));
   Cell(s,cycles[i].path.returned[t] ? N(cycles[i].path.returnQuoteR[t]) : "");
   Cell(s,N(cycles[i].net)); Cell(s,N(cycles[i].path.maxR)); Cell(s,N(cycles[i].path.minR)); Row(f,s);
  } FileClose(f);
 }
// Numeric frame carries statistics and ASCII relative-folder index, never raw future prices.
void BuildPayload(const double &stats[],double &payload[])
 {
  int base=S_COUNT+G_COUNT,n=ArraySize(months),len=StringLen(folder);
  int tail=base+1+n*MONTH_FIELDS+5*SHADOW_FIELDS; ArrayResize(payload,tail+1+len);
  for(int i=0;i<base;i++) payload[i]=stats[i]; payload[base]=n;
  for(int m=0;m<n;m++) { double v[18]; MonthValues(m,v); for(int j=0;j<18;j++) payload[base+1+m*18+j]=v[j]; }
  int at=base+1+n*18;
  for(int t=0;t<5;t++) { double v[8]; ShadowValues(t,v); for(int j=0;j<8;j++) payload[at+t*8+j]=v[j]; }
  payload[tail]=len; for(int j=0;j<len;j++) payload[tail+1+j]=StringGetCharacter(folder,j);
 }
bool PayloadValid(const double &p[])
 {
  int base=S_COUNT+G_COUNT; if(ArraySize(p)<base+1 || !MathIsValidNumber(p[base]) || p[base]<0 || p[base]>1200) return false;
  int n=(int)p[base]; if(p[base]!=n) return false;
  int tail=base+1+n*18+40;
  if(ArraySize(p)<tail+1 || !MathIsValidNumber(p[tail]) || p[tail]<0 || p[tail]>512) return false;
  int len=(int)p[tail]; if(p[tail]!=len || ArraySize(p)!=tail+1+len) return false;
  for(int i=0;i<len;i++) if(!MathIsValidNumber(p[tail+1+i]) || p[tail+1+i]<32 || p[tail+1+i]>126 || p[tail+1+i]!=(int)p[tail+1+i]) return false;
  return true;
 }
string PayloadFolder(const double &p[])
 {
  if(!PayloadValid(p)) return "";
  int tail=S_COUNT+G_COUNT+1+(int)p[S_COUNT+G_COUNT]*18+40; string name="";
  for(int i=0;i<(int)p[tail];i++) name+=ShortToString((ushort)p[tail+1+i]); return name;
 }
double OnTester()
 {
  if(!initialized) return -1e100;
  finalizing=true; SyncCycle(); TrackEquity();
  // Rebuild all P&L from the executed final history, including forced tester exits
  // that may arrive without another OnTick and may carry magic zero.
  for(int i=0;i<ArraySize(cycles);i++) {
   bool ok=AggregateCycle(i); cycles[i].closed=ok && MathAbs(cycles[i].inVolume-cycles[i].outVolume)<1e-8 && cycles[i].finish>0;
   if(!cycles[i].closed) Invalid(406,"Open/unreconciled campaign at tester end.");
   if(cycles[i].closed && !cycles[i].finalObserved) { PEObserve(cycles[i].path,cycles[i].finalPrice); cycles[i].finalObserved=true; }
  }
  for(int m=0;m<ArraySize(months);m++) { months[m].closed=0; months[m].cycleNet=0; }
  for(int i=0;i<ArraySize(cycles);i++) if(cycles[i].closed) { int m=MonthIndex(cycles[i].finish); months[m].closed++; months[m].cycleNet+=cycles[i].net; }
  if(firstReady==0) Invalid(407,"No complete indicator snapshot available.");
  ExportDeals();
  double data[S_COUNT+G_COUNT]; ArrayInitialize(data,0);
  data[S_PROFIT]=TesterStatistics(STAT_PROFIT); data[S_DEPOSIT]=TesterStatistics(STAT_INITIAL_DEPOSIT);
  data[S_FINAL_BALANCE]=data[S_DEPOSIT]+data[S_PROFIT]; data[S_MT5_TRADES]=TesterStatistics(STAT_TRADES);
  data[S_MT5_PF]=TesterStatistics(STAT_PROFIT_FACTOR); data[S_EQUITY_DD_REL]=TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
  data[S_EQUITY_DD_MONEY]=TesterStatistics(STAT_EQUITY_DD); data[S_EQUITY_DD_AT_MONEY]=TesterStatistics(STAT_EQUITYDD_PERCENT);
  data[S_CYCLES_OPENED]=ArraySize(cycles); double winning=0,losing=0; int streak=0;
  for(int i=0;i<ArraySize(cycles);i++) {
   PECycle c=cycles[i]; data[S_BE_ARMED]+=c.be.armed; data[S_BE_CONFIRMED]+=c.beTime>0;
   data[S_PARTIAL_ARMED]+=c.part.armed; data[S_PARTIAL_DONE]+=c.part.done;
   data[S_BE_ATTEMPTS]+=c.be.attempts; data[S_PARTIAL_ATTEMPTS]+=c.part.attempts;
   if(c.be.armed && !c.be.done) data[S_BE_UNFULFILLED]++;
   if(c.part.armed && !c.part.done) data[S_PARTIAL_UNFULFILLED]++;
   data[S_INITIAL_LOTS_SUM]+=c.volume; for(int j=1;j<c.legs;j++) data[S_ADD_LOTS_SUM]+=c.volumes[j];
   data[S_ADD_FILLS]+=c.adds;
   if(c.path.observations==0) data[S_EMPTY_PATHS]++;
   if(!c.closed) continue;
   data[S_CYCLES_CLOSED]++; data[S_CYCLE_NET]+=c.net; data[S_SWAP]+=c.swap; data[S_COSTS]+=c.costs;
   if(c.origin==15) { data[S_ORIGIN15_CYCLES]++; data[S_ORIGIN15_NET]+=c.net; }
   if(c.origin==14) { data[S_ORIGIN14_CYCLES]++; data[S_ORIGIN14_NET]+=c.net; }
   if(c.adds>0) { data[S_ADD_CYCLES]++; data[S_ADD_NET]+=c.net; }
   if(c.net>0) { data[S_WINS]++; winning+=c.net; streak=0; data[S_MFE_WIN_AVG]+=c.path.maxR; }
   else if(c.net<0) { data[S_LOSSES]++; losing-=c.net; streak++; data[S_MFE_LOSS_AVG]+=c.path.maxR; }
   else { data[S_ZERO]++; streak=0; }
   data[S_MAX_LOSS_STREAK]=MathMax(data[S_MAX_LOSS_STREAK],streak);
   if(c.initialRisk>0) data[S_AVG_NET_R]+=c.net/c.initialRisk;
   double hold=(c.finish-c.start)/3600.0; data[S_AVG_HOLD]+=hold; data[S_MAX_HOLD]=MathMax(data[S_MAX_HOLD],hold);
   data[S_MFE_AVG]+=c.path.maxR; data[S_MAE_AVG]+=c.path.minR; data[S_QUOTE_OBSERVATIONS]+=c.path.observations;
   if(c.beTime>0 && c.finalReason==DEAL_REASON_SL) data[S_BE_STOP_EXITS]++;
   if(data[S_FIRST_ENTRY]==0 || c.start<data[S_FIRST_ENTRY]) data[S_FIRST_ENTRY]=(double)c.start;
   data[S_LAST_EXIT]=MathMax(data[S_LAST_EXIT],(double)c.finish);
  }
  double n=data[S_CYCLES_CLOSED];
  if(n>0) { data[S_WIN_PCT]=100*data[S_WINS]/n; data[S_AVG_NET_R]/=n; data[S_AVG_HOLD]/=n; data[S_MFE_AVG]/=n; data[S_MAE_AVG]/=n; }
  if(data[S_WINS]>0) data[S_MFE_WIN_AVG]/=data[S_WINS]; if(data[S_LOSSES]>0) data[S_MFE_LOSS_AVG]/=data[S_LOSSES];
  data[S_CYCLE_PF]=losing>0 ? winning/losing : (winning>0 ? DBL_MAX : 0);
  data[S_MAX_LOTS]=maxLots; data[S_MAX_RISK]=maxRisk; data[S_MAX_RISK_PCT]=maxRiskPct; data[S_MAX_MARGIN]=maxMargin;
  data[S_FIRST_EVAL]=(double)firstEval; data[S_LAST_EVAL]=(double)lastEval; data[S_FIRST_READY]=(double)firstReady;
  data[S_BARS]=barsSeen; data[S_SIGNALS]=signals; data[S_PARTIAL_DEFERRED]=partialDefers; data[S_BE_DEFERRED]=beDefers;
  data[S_SESSION_DEFERS]=sessionDefers; data[S_STOPS_DEFERS]=stopDefers; data[S_AMBIGUOUS_PARTIALS]=ambiguousPartials;
  data[S_UNMATCHED]=unmatchedDeals; data[S_RECONCILE]=data[S_PROFIT]-data[S_CYCLE_NET];
  double eq=0,book=0;
  for(int m=0;m<ArraySize(months);m++) {
   book+=months[m].bookedNet; if(!months[m].path.initialized) continue;
   data[S_MONTHS]++; double delta=months[m].path.endEquity-months[m].path.startEquity; eq+=delta;
   if(delta>.005) data[S_POS_EQ_MONTHS]++; if(delta<-.005) data[S_NEG_EQ_MONTHS]++;
   if(months[m].bookedNet>.005) data[S_POS_BOOK_MONTHS]++; if(months[m].bookedNet<-.005) data[S_NEG_BOOK_MONTHS]++;
   data[S_MONTH_DD_MAX]=MathMax(data[S_MONTH_DD_MAX],months[m].path.maxRelativeDD);
  }
  data[S_MONTH_EQ_RECONCILE]=data[S_PROFIT]-eq; data[S_MONTH_BOOK_RECONCILE]=data[S_PROFIT]-book;
  if(MathAbs(data[S_RECONCILE])>.01 || MathAbs(data[S_MONTH_EQ_RECONCILE])>.01 || MathAbs(data[S_MONTH_BOOK_RECONCILE])>.01 ||
     data[S_UNMATCHED]>0 || data[S_CYCLES_CLOSED]!=data[S_CYCLES_OPENED]) Invalid(408,"Native/cycle/month totals do not reconcile.");
  data[S_SHADOW_CONTROL_ELIGIBLE]=(InpCase==1) ? 1 : 0;
  data[S_FIXED_LOT]=dc.fixedLot ? InpFixedLot : 0; data[S_BE15_R]=profile.be15; data[S_MODE]=profile.mode; data[S_PROTECT14]=profile.protect14;
  data[S_ADD_REJECTS]=addRejects; data[S_RISK_BLOCKS]=riskBlocks; data[S_STOP_FACTOR]=profile.stopFactor;
  data[S_REINVEST]=profile.reinvest; data[S_ARM]=profile.arm; data[S_PATTERN_BUYS]=patternBuys; data[S_PATTERN_SELLS]=patternSells;
  data[S_ENTRY_POLICY]=evo.entryPolicy; data[S_REINVEST_FRACTION]=evo.reinvestFraction;
  data[S_REINVEST_CAP]=dc.fixedLot ? InpFixedLot : InpMaxLot; data[S_CAPITAL_MODE]=evo.capitalMode;
  data[S_RISK_PERCENT]=dc.riskPercent; data[S_MARGIN_CAP_PERCENT]=dc.fixedLot ? 0 : InpMaxMarginPct; data[S_DONCHIAN_MODE]=dc.channelMode;
  data[S_SOURCE_CONTROL180]=dc.sourceControl180; data[S_FIXED_MODE]=dc.fixedLot; data[S_TARGET_MODE]=dc.targetMode;
  data[S_TARGET_VALUE]=dc.targetMode==0 ? 5 : 20; data[S_TARGET_DISTANCE]=HermesTargetDistance(dc.targetMode,_Point);
  data[S_NOMINAL_TARGET_R]=dc.targetMode==0 ? 5 : 0; data[S_TARGET_REJECTS]=targetRejects; data[S_TARGET_ADJUSTMENTS]=targetAdjustments;
  data[S_TARGET_FAILURES]=targetFailures; data[S_FIXED_VOLUME_REJECTS]=fixedVolumeRejects;
  data[S_HP_CANDIDATES]=hpCandidates; data[S_HP_EXTRA_ELIGIBLE]=hpExtraEligible;
  data[S_HP_BASE_SELECTED]=hpBaseSelected; data[S_HP_PIVOT_SELECTED]=hpPivotSelected; data[S_HP_PIVOT_FILLS]=hpPivotFills;
  data[S_HP_DATA_FAILURES]=hpDataFailures; data[S_HP_POSITION_BLOCKS]=hpPositionBlocks; data[S_HP_CATCHUP_IGNORED]=hpCatchupIgnored;
  data[S_MATCHED_CONTROL]=dc.matchedControl; data[S_DETAIL_EXPORT]=folder!=""; data[S_BAR_ROWS]=barRows;
  ExportDetails(); if(ioFailure) Invalid(410,"Detail CSV write failure.");
  data[S_ERROR_CODE]=errorCode; data[S_LAST_RETCODE]=lastRetcode; data[S_LAST_ERROR_TIME]=(double)lastErrorTime;
  data[S_VALID]=integrity ? 1 : 0; for(int i=0;i<G_COUNT;i++) data[S_COUNT+i]=counters[i];
  if(folder!="") {
   int f=OpenText(folder+"\\summary.csv");
   if(f==INVALID_HANDLE) { Invalid(409,"Cannot write summary.csv."); data[S_VALID]=0; }
   else { Row(f,"metric;value"); KV(f,"version","2.00"); KV(f,"case",I(InpCase)); KV(f,"name",ProfileName(InpCase));
    KV(f,"signal_tf",TFName(InpCase)); string names[]; StatNames(names);
    for(int i=0;i<S_COUNT;i++) KV(f,names[i],IsTimeStat(i) ? TS((datetime)data[i]) : N(data[i]));
    for(int i=0;i<G_COUNT;i++) KV(f,EnumToString((PE_GATE)i),N(data[S_COUNT+i])); FileClose(f);
   }
  }
  if(ioFailure) { Invalid(410,"CSV write failure."); data[S_VALID]=0; data[S_ERROR_CODE]=errorCode; }
  if(MQLInfoInteger(MQL_OPTIMIZATION)) { double payload[]; BuildPayload(data,payload); if(!FrameAdd("HP200",InpCase,data[S_PROFIT],payload)) Print("FrameAdd failed: ",GetLastError()); }
  Print("HP200 ",ProfileName(InpCase)," lucro=",data[S_PROFIT]," ciclos=",n," valid_run=",integrity);
  return integrity ? data[S_PROFIT] : -1e100;
 }
int OnTesterInit()
 {
  string names[]; if(StatNames(names)!=S_COUNT) { Print("STAT SCHEMA ERROR"); return INIT_FAILED; }
  if(!ValidRunTag()) return INIT_PARAMETERS_INCORRECT;
  if(!InpExportCSV) return INIT_SUCCEEDED;
  FolderCreate("Hermes_Pivos_Lab_200",FILE_COMMON); FolderCreate(RunRoot(),FILE_COMMON); optFolder=RunRoot()+"\\OTIMIZACAO_"+Stamp();
  if(!FolderCreate(optFolder,FILE_COMMON)) return INIT_FAILED;
  optFile=OpenText(optFolder+"\\comparacao.csv"); optMonths=OpenText(optFolder+"\\meses_comparacao.csv");
  optShadow=OpenText(optFolder+"\\breakeven_comparacao.csv"); optFiles=OpenText(optFolder+"\\arquivos_comparacao.csv");
  if(optFile==INVALID_HANDLE || optMonths==INVALID_HANDLE || optShadow==INVALID_HANDLE || optFiles==INVALID_HANDLE) return INIT_FAILED;
  string header="pass;case;name;signal_tf"; for(int i=0;i<S_COUNT;i++) header+=";"+names[i];
  for(int i=0;i<G_COUNT;i++) header+=";"+EnumToString((PE_GATE)i); Row(optFile,header);
  Row(optMonths,"pass;case;name;"+MonthHeader()); Row(optShadow,"pass;case;name;valid_run;"+ShadowHeader());
  Row(optFiles,"pass;case;name;relative_details_folder;details_exported");
  if(ioFailure) return INIT_FAILED;
  Print("COMPARACAO AUTOMATICA: ",TerminalInfoString(TERMINAL_COMMONDATA_PATH),"\\Files\\",optFolder); return INIT_SUCCEEDED;
 }
void DrainFrames()
 {
  ulong pass=0; long id=0; string name=""; double value=0,data[];
  while(FrameNext(pass,name,id,value,data)) {
   if(name!="HP200" || optFile==INVALID_HANDLE || !PayloadValid(data) || id<1 || id>3) continue;
   bool seen=false; for(int i=0;i<ArraySize(receivedPasses);i++) if(receivedPasses[i]==pass) seen=true; if(seen) continue;
   int n=ArraySize(receivedPasses); ArrayResize(receivedPasses,n+1); receivedPasses[n]=pass;
   string prefix=""; Cell(prefix,U(pass)); Cell(prefix,I(id)); Cell(prefix,ProfileName((int)id));
   string row=prefix; Cell(row,PayloadFolder(data)); Cell(row,N(data[S_DETAIL_EXPORT])); Row(optFiles,row);
   row=prefix; Cell(row,TFName((int)id));
   for(int i=0;i<S_COUNT+G_COUNT;i++) Cell(row,IsTimeStat(i) ? TS((datetime)data[i]) : N(data[i])); Row(optFile,row);
   int base=S_COUNT+G_COUNT,mc=(int)data[base];
   for(int m=0;m<mc;m++) Row(optMonths,prefix+";"+MonthCSV(data,base+1+m*18));
   if(id==1) for(int t=0;t<5;t++) {
    row=prefix; Cell(row,N(data[S_VALID]));
    for(int j=0;j<8;j++) Cell(row,N(data[base+1+mc*18+t*8+j])); Row(optShadow,row);
   }
   FileFlush(optFile); FileFlush(optMonths); FileFlush(optShadow); FileFlush(optFiles);
  }
 }
void OnTesterPass() { DrainFrames(); }
void OnTesterDeinit()
 {
  DrainFrames(); if(optFile!=INVALID_HANDLE) FileClose(optFile); if(optMonths!=INVALID_HANDLE) FileClose(optMonths);
  if(optFiles!=INVALID_HANDLE) FileClose(optFiles); optFiles=INVALID_HANDLE;
  if(optShadow!=INVALID_HANDLE) FileClose(optShadow); optFile=INVALID_HANDLE; optMonths=INVALID_HANDLE; optShadow=INVALID_HANDLE;
  Print("HP200 comparacoes recebidas: ",ArraySize(receivedPasses),". Confira com as passagens concluidas.");
 }


void OnDeinit(const int reason)
 {
  if(barsFile!=INVALID_HANDLE) FileClose(barsFile); if(eventsFile!=INVALID_HANDLE) FileClose(eventsFile);
  if(hEMA!=INVALID_HANDLE) IndicatorRelease(hEMA); if(h50!=INVALID_HANDLE) IndicatorRelease(h50); if(h200!=INVALID_HANDLE) IndicatorRelease(h200);
  if(hADX!=INVALID_HANDLE) IndicatorRelease(hADX); if(hATR!=INVALID_HANDLE) IndicatorRelease(hATR); Comment("");
 }
