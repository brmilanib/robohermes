#define main legacy_hermes_tests
#include "test_hermes.cpp"
#undef main

H1Signal good_signal()
{
 H1Signal s{}; s.open=109;s.close=112;s.high=113;s.low=108;
 s.previousHigh=111;s.ema=107;s.sma50=105;s.oldSma50=104;
 s.sma200=100;s.adx=20;s.plusDI=24;s.minusDI=18;s.atr=10;
 s.priorTouched=true;return s;
}
int main()
{
 DCProfile d{};EVOProfile e{};PEProfile p{};HPDecision out{};HPSignal pivot{};
 pivot.buy=true;EVOFeatures f{};f.oscillatorValid=true;f.fast310=2;f.previousFast310=1;
 H1Signal s=good_signal();
 for(int id=1;id<=3;id++) {
  assert(HPSelectProfile(id,d,e,p));assert(d.fixedLot&&!d.weekly&&d.targetMode==0);
  assert(d.matchedControl==2&&!p.reinvest&&!p.partial&&p.be15==0&&p.addFraction==0);
  HPRouteEntry(id,e,s,f,112,99,.5,true,pivot,out);
  assert(out.original_gate==0&&out.setup==0&&out.side==1&&out.path==HP_BASE);
  HPRouteEntry(id,e,s,f,112,99,.5,false,pivot,out);
  assert(out.setup==0&&out.path==HP_BASE); // Missing pivot data cannot suppress original.
 }
 assert(!HPSelectProfile(0,d,e,p)&&!HPSelectProfile(7,d,e,p));
 // R210: casos 4 (Referencia + risco), 5 (Colheita Rapida) e 6 (Caso 4 + freio
 // de rebaixamento) sao validos e usam sizing por risco (fixedLot=false,
 // riskPercent em (0,2] - o EA sobrescreve com InpRiskPercent, ate 5, depois).
 for(int id:{4,5,6}) {
  assert(HPSelectProfile(id,d,e,p));
  assert(!d.fixedLot && d.riskPercent>0.0 && d.riskPercent<=2.0 && d.targetMode==0);
  assert(d.matchedControl==2 && !p.reinvest && !p.partial && p.be15==0 && p.addFraction==0);
 }
 // Casos 4 e 6 usam exatamente as entradas do Caso 1 (rota base, pivo
 // desabilitado) - o Caso 6 so muda o SIZING (fora do escopo deste arquivo),
 // nunca a entrada/saida.
 for(int cid:{4,6}) {
  H1Signal z=good_signal();
  HPRouteEntry(cid,e,z,f,112,99,.5,true,pivot,out);
  assert(out.original_gate==0&&out.setup==0&&out.side==1&&out.path==HP_BASE&&out.extra_gate==HP_DISABLED);
  z.priorTouched=false;
  HPRouteEntry(cid,e,z,f,112,99,.5,true,pivot,out);
  assert(out.setup==NO_TOUCH&&out.path==HP_NONE&&out.extra_gate==HP_DISABLED);
 }
 HPSelectProfile(1,d,e,p);s.priorTouched=false;
 HPRouteEntry(1,e,s,f,112,99,.5,true,pivot,out);
 assert(out.setup==NO_TOUCH&&out.path==HP_NONE&&out.extra_gate==HP_DISABLED);
 for(int id:{2,3}) {
  HPRouteEntry(id,e,s,f,112,99,.5,true,pivot,out);
  assert(out.original_gate==NO_TOUCH&&out.setup==0&&out.path==HP_PIVOT&&out.side==1);
  pivot.buy=false;HPRouteEntry(id,e,s,f,112,99,.5,true,pivot,out);
  assert(out.setup==NO_TOUCH&&out.path==HP_NONE&&out.extra_gate==HP_NO_CANDIDATE);pivot.buy=true;
  HPRouteEntry(id,e,s,f,112,99,.5,false,pivot,out);assert(out.path==HP_NONE&&out.extra_gate==HP_DATA_PENDING);
 }
 // Only the two SMA200 conditions differ in the extra-entry variants.
 for(int condition=0;condition<2;condition++) {
  H1Signal x=s;x.sma200=condition==0?113:99;
  assert(HPExtraGate(2,x,f,112,99,.5,true,pivot)==HP_TREND200);
  assert(HPExtraGate(3,x,f,112,99,.5,true,pivot)==0);
 }
 assert(HPExtraGate(2,s,f,112,99,.5,true,pivot)==0); // ADX20 and .5ATR inclusive.
 H1Signal x=s;x.adx=19.999;assert(HPExtraGate(3,x,f,112,99,.5,true,pivot)==HP_ADX);
 x=s;x.plusDI=x.minusDI;assert(HPExtraGate(3,x,f,112,99,.5,true,pivot)==HP_DI);
 x=s;x.close=x.open;assert(HPExtraGate(3,x,f,112,99,.5,true,pivot)==HP_TRIGGER);
 x=s;x.sma50=x.oldSma50;assert(HPExtraGate(3,x,f,112,99,.5,true,pivot)==HP_TREND50);
 assert(HPExtraGate(3,s,f,111.999,99,.5,true,pivot)==HP_DISTANCE);
 f.fast310=f.previousFast310;assert(HPExtraGate(3,s,f,112,99,.5,true,pivot)==HP_OSCILLATOR);
 f.fast310=2;f.oscillatorValid=false;assert(HPExtraGate(3,s,f,112,99,.5,true,pivot)==HP_OSCILLATOR);
 // Exhaustive routing invariant: original acceptance is identical for case1.
 int comparisons=0;
 for(int candle:{-1,0,1})for(int touch:{0,1})for(int trend:{-1,0,1})for(double adx:{19.0,20.0,25.0})
 for(double dist:{.49,.5,.51})for(int rising:{0,1})for(int candidate:{0,1}) {
  x=good_signal();x.open=x.close-candle;x.priorTouched=touch;
  x.sma50=105;x.oldSma50=105-trend;x.adx=adx;pivot.buy=candidate;
  int side=0;double old200=rising?99:100,ask=x.ema+dist*x.atr;
  int baseline=EVOEvaluate(e,x,f,ask,old200,.5,false,side);
  for(int id:{1,2,3}) {
   HPRouteEntry(id,e,x,f,ask,old200,.5,true,pivot,out);
   assert(out.original_gate==baseline);
   if(id==1) assert(out.setup==baseline);
   if(baseline==0) assert(out.setup==0&&out.path==HP_BASE&&out.side==side);
   if(out.path==HP_PIVOT) assert(id!=1&&baseline!=0&&out.extra_gate==0&&out.side==1);
   comparisons++;
  }
 }
 std::cout<<"Production pivot routing: "<<comparisons<<" invariant checks, case1 parity, original priority, causal-data fallback, SMA200-only difference, strict/inclusive thresholds passed.\n";
}
