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
