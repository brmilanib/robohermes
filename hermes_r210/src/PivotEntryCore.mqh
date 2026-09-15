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
 if(id<1 || id>8 || !DCSelectProfile(2,d,e,p)) return false;
 d.id=id; d.matchedControl=2; e.matchedControl=2;
 // Casos 4 (Referencia + risco), 5 (Colheita Rapida), 6 (freio por
 // rebaixamento), 7 (saque de lucro) e 8 (breakeven+alvo 3R), todos sobre o
 // Caso 4: MESMO motor de execucao, porem sizing por % do patrimonio em vez
 // de lote fixo. O EA sobrescreve d.riskPercent com InpRiskPercent (e, so no
 // Caso 8, p.be15 com InpBETriggerR) logo apos esta selecao.
 const bool riskSized=(id==4 || id==5 || id==6 || id==7 || id==8);
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
 if(id<1 || id>8) return HP_INVALID_CASE;
 if(id==1 || id>=4) return HP_DISABLED;   // Casos 1, 4, 5, 6, 7 e 8 nao usam a rota de pivo
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
 if(id<1 || id>8) { out.setup=HP_INVALID_CASE; out.side=0; return; }
 if(out.original_gate==0) { out.path=HP_BASE; return; }
 if(out.extra_gate==0) { out.setup=0; out.side=1; out.path=HP_PIVOT; }
}
#endif
