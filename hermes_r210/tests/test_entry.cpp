// Includes exact production OpenCycle with deterministic native API stubs.
#define main legacy_execution_tests
#include "test_execution.cpp"
#undef main
template<class T> void ZeroMemory(T &v){v=T{};}
EVOProfile evo{};EVOFeatures features{};
double pivotSwing=0,oldSMA200=3900,plannedTargetDistance=0,plannedTargetRiskRatio=0,plannedTargetProfit=0;
double sizedLot=0,sizingRiskBudget=0,sizingMarginBudget=0,sizingMargin=0,minimumLotRiskMoney=0,minimumLotMargin=0,minimumLotRiskPercent=0,minimumEquityForLot=0;
double InpFixedLot=1,InpMaxMarginPct=20,InpMaxLot=1,maxLots=0,InpQHTargetR=1;
double InpDDBand1=15.0,InpDDMult1=0.50,InpDDBand2=25.0,InpDDMult2=0.25,ddPeakEquity=0;
long targetRejects=0,fixedVolumeRejects=0;datetime lastPivotUsed=0,pivotTime=0;int liveMonth=0;
HPDecision hpRoute{}; HPSignal hpSignal{}; long hpPivotFills=0;
void ObserveOpenPath(){}
#include "Open_Runtime.inc"
H1Signal prepare(int id){
 // 'id' aqui indexa o espaco interno do DCSelectProfile (1-6, perfis Donchian
 // legados), NAO o Caso Hermes. InpCase fica travado em 1 (fora do ramo novo
 // InpCase>=4) para nao colidir com o sizing de risco dos Casos 4/5; os
 // chamadores que testam roteamento real (HPSelectProfile) sobrescrevem
 // InpCase explicitamente logo em seguida.
 reset(1);DCSelectProfile(id,dc,evo,profile);InpCase=1;active=-1;positions.clear();cycles.clear();
 targetRejects=fixedVolumeRejects=0;sizedLot=plannedTargetDistance=plannedTargetRiskRatio=plannedTargetProfit=0;
 sizingRiskBudget=sizingMarginBudget=0;quote={4000,4000.2,100000};mockFreeMargin=10000;mockMarginPerLot=8000;
 H1Signal s{};s.open=3990;s.close=4000;s.lowest=3988;s.highest=4001;s.atr=10;s.ema=3990;s.sma200=3901;s.adx=26;s.oldADX=25;
 return s;
}
int main(){
 double sl=0,tp=0,risk=0;string detail;H1Signal s=prepare(3);
 assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(cycles[0].volume,1)&&near(positions[0].volume,1)&&near(tp,4020.2));
 assert(near(sl,3986)&&near(risk,1420)&&risk>mockEquity*.02&&sizingMargin>mockEquity*.20);
 assert(near(plannedTargetProfit,2000)&&volumeRequests==1&&slRequests==0); // no hidden sizing reduction
 s=prepare(2);assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(cycles[0].volume,1)&&near(tp,4071.2)&&near(sl,3986));
 s=prepare(4);assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(tp,4000.22)&&near(plannedTargetProfit,2)&&near(cycles[0].volume,1));
 assert(quote.ask-quote.bid>.02); // spread greater than target is not a broker TP impossibility
 s=prepare(3);mockFreeMargin=7999.99;assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_MARGIN_BLOCK);
 assert(volumeRequests==0&&cycles.empty()&&near(sizedLot,1));
 s=prepare(3);mockVolumeStep=.03;assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_RISK);
 assert(volumeRequests==0&&fixedVolumeRejects==1);
 s=prepare(4);mockTick=.1;assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_TARGET);
 assert(volumeRequests==0&&targetRejects==1);
 s=prepare(4);mockStops=1000;assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_BROKER_STOPS);
 assert(volumeRequests==0&&targetRejects==1);
 s=prepare(1);assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(cycles[0].volume,.14)&&risk<=200&&near(tp,4071.2));
 for(int id:{5,6}){s=prepare(id);assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);assert(integrity&&near(cycles[0].volume,.14)&&risk<=200);}
 // R210: Casos 4/5 usam a mesma formula do DCRiskLot, mas SEM o teto interno
 // de riskPercent<=2 (DCRiskLot recusa >2% com volume=0/G_RISK; e' assim que
 // os Casos 1-3 continuam protegidos). Em 2% o novo ramo bate exatamente com
 // o DCRiskLot original; acima de 2% (so' liberado para InpCase>=4) o volume
 // cresce proporcionalmente em vez de ser recusado.
 s=prepare(1);InpCase=4;dc.riskPercent=2.0;
 assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(cycles[0].volume,.14)&&near(risk,198.8)); // igual ao teto antigo de 2%
 s=prepare(1);InpCase=4;dc.riskPercent=3.0;
 assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(cycles[0].volume,.21)&&near(risk,298.2)); // 3%: acima do teto do DCRiskLot original
 s=prepare(1);InpCase=1;dc.riskPercent=3.0; // Casos 1-3 continuam via DCRiskLot: >2% e' recusado, nao alargado.
 assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_RISK&&volumeRequests==0);
 // R210: Caso 6 (Caso 4 + freio de risco por rebaixamento, DDThrottleCore.mqh).
 // Caso 4 precisa ficar IMUNE a ddPeakEquity - so o Caso 6 le esse estado.
 s=prepare(1);InpCase=4;dc.riskPercent=2.0;ddPeakEquity=999999; // "drawdown" gigante nao deve importar
 assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(cycles[0].volume,.14)&&near(risk,198.8)); // identico ao teste em 2% sem freio
 // Caso 6: risco nominal 4% + pico de 12000 sobre equity mockada de 10000
 // (DD=16.67%, entre banda1=15% e banda2=25%) -> multiplicador 0.5 -> risco
 // efetivo 2%, EXATAMENTE igual ao teste do Caso 4 a 2% acima - prova que o
 // freio de fato reduz o risco dentro do OpenCycle real, nao so na funcao pura.
 s=prepare(1);InpCase=6;dc.riskPercent=4.0;ddPeakEquity=12000;
 assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(cycles[0].volume,.14)&&near(risk,198.8));
 s=prepare(3);mockFillOffset=-.01;assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(cycles[0].target-cycles[0].entry,20)&&targetAdjustments==1&&slRequests==1&&volumeRequests==1);
 s=prepare(3);mockFillOffset=.01;assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
 assert(integrity&&near(cycles[0].target-cycles[0].entry,19.99)&&targetAdjustments==0&&slRequests==0);
 s=prepare(3);s.lowest=3998;assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_STOP&&volumeRequests==0);
 s=prepare(3);s.lowest=3950;assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_STOP&&volumeRequests==0);
 // The three release profiles use the exact same execution and structural stop.
 for(int id:{1,2,3}) {
  s=prepare(2);assert(HPSelectProfile(id,dc,evo,profile));InpCase=id;
  hpRoute.path=id==1?HP_BASE:HP_PIVOT;hpRoute.original_gate=id==1?0:NO_TOUCH;hpRoute.extra_gate=0;
  hpSignal.buy=true;hpSignal.stop_f1=3700;hpSignal.reference_price=3998;hpSignal.pullback_f2=3980;
  assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_FILLED);
  assert(near(sl,3986)&&near(tp,4071.2)&&near(cycles[0].volume,1));
  assert(cycles[0].entryPath==hpRoute.path&&cycles[0].beTrigger==0&&!cycles[0].partialEnabled);
  if(id!=1) assert(cycles[0].entryPivot.stop_f1==3700&&sl!=3700); // Geometry never widens execution stop.
  s=prepare(2);assert(HPSelectProfile(id,dc,evo,profile));mockFreeMargin=7999.99;
  assert(OpenCycle(15,1,s,quote,70,sl,tp,risk,detail)==G_MARGIN_BLOCK&&volumeRequests==0);
 }
 std::cout<<"OpenCycle production body: exact1lot; 20price/20points/5R; native margin refusal; no20pct hidden cap; risk controls; tick/stops rejection; structuralSL; fill adjustment passed.\n";
}
