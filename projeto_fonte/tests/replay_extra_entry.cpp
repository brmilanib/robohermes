// Protocol replay of exported, closed snapshots. Not a trade/PnL simulation.
#define main legacy_hermes_tests
#include "test_hermes.cpp"
#undef main
int main()
{
 H1Signal s{};EVOFeatures f{};HPSignal hp{};hp.buy=true;
 int id=0,valid=0;
 while(std::cin>>id>>s.open>>s.close>>s.ema>>s.sma50>>s.oldSma50>>s.sma200>>s.adx>>s.plusDI>>s.minusDI>>s.atr) {
  double old200=0,ask=0,stop=0;std::cin>>old200>>ask>>valid>>f.fast310>>f.previousFast310>>stop;
  f.oscillatorValid=valid;s.lowest=stop+.2*s.atr;
  int gate=HPExtraGate(id,s,f,ask,old200,.5,true,hp);
  double sl=0,tp=0;bool structural=H1Levels(1,ask,s,.2,1,2.5,5,.001,sl,tp);
  std::cout<<gate<<" "<<(structural?1:0)<<"\n";
 }
}
