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
