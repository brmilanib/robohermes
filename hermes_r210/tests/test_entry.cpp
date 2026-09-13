// Includes exact production OpenCycle with deterministic native API stubs.
#define main legacy_execution_tests
#include "test_execution.cpp"
#undef main
template<class T> void ZeroMemory(T &v){v=T{};}
EVOProfile evo{};EVOFeatures features{};
double pivotSwing=0,oldSMA200=3900,plannedTargetDistance=0,plannedTargetRiskRatio=0,plannedTargetProfit=0;
double sizedLot=0,sizingRiskBudget=0,sizingMarginBudget=0,sizingMargin=0,minimumLotRiskMoney=0,minimumLotMargin=0,minimumLotRiskPercent=0,minimumEquityForLot=0;
double InpFixedLot=1,InpMaxMarginPct=20,InpMaxLot=1,maxLots=0,InpQHTargetR=1;
long targetRejects=0,fixedVolumeRejects=0;datetime lastPivotUsed=0,pivotTime=0;int liveMonth=0;
HPDecision hpRoute{}; HPSignal hpSignal{}; long hpPivotFills=0;
void ObserveOpenPath(){}
#include "Open_Runtime.inc"
H1Signal prepare(int id){
 reset(1);DCSelectProfile(id,dc,evo,profile);InpCase=id;active=-1;positions.clear();cycles.clear();
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
