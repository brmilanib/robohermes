#include <cassert>
#include <string>
#include <vector>
#include <iostream>
using std::string;using datetime=long;
#include "../src/PivotCore.mqh"
enum {HP_NONE=0,HP_BASE=1,HP_PIVOT=2};
struct MqlRates {long time;double open,high,low,close;};
HPState hpState;HPSignal hpSignal;int hpProcessedThisBar=0,signalTF=30;
long hpCatchupIgnored=0;string hpStatus,_Symbol="XAUUSD";
std::vector<MqlRates> history;int current=210;
bool incomplete=false,wrong_first=false;
template<class T> void ArraySetAsSeries(T&,bool){}
long iTime(const string&,int,int shift){return history.at(current-shift).time;}
int CopyRates(const string&,int,int shift,int count,std::vector<MqlRates> &out)
{
 int first=current-shift-count+1;if(first<0)return -1;
 out.assign(history.begin()+first,history.begin()+current-shift+1);
 if(incomplete)out.pop_back();return out.size();
}
int CopyRates(const string&,int,long first,long last,std::vector<MqlRates> &out)
{
 out.clear();for(const auto &b:history)if(b.time>=first&&b.time<=last)out.push_back(b);
 if(incomplete&&!out.empty())out.pop_back();
 if(wrong_first&&!out.empty())out.erase(out.begin());
 return out.size();
}
#include "PivotAdapter_Runtime.inc"
int main()
{
 for(int i=0;i<280;i++) {
  // A harmless observed gap is retained as a timestamp gap, never fabricated.
  long t=10000+i*1800+(i>=212?172800:0);
  double p=100+(i%11);history.push_back({t,p,p+2,p-2,p+.5});
 }
 HPCoreReset(hpState);incomplete=true;
 assert(!HPSyncClosedBars(iTime(_Symbol,30,0))&&hpState.bars_processed==0&&!hpSignal.buy);
 incomplete=false;auto original=history[205];history[205].high=-1;
 assert(!HPSyncClosedBars(iTime(_Symbol,30,0))&&hpState.bars_processed==0);
 history[205]=original;
 assert(HPSyncClosedBars(iTime(_Symbol,30,0)));
 assert(hpState.bars_processed==210&&hpState.last_time==history[209].time&&hpState.expected_open==history[210].time);
 assert(hpProcessedThisBar==210&&hpStatus=="READY_SEED_210");
 // The current/open bar's OHLC can be invalid: it is not read as a closed input.
 auto open=history[210];history[210].high=-999;
 HPState initial=hpState;HPCoreReset(hpState);
 assert(HPSyncClosedBars(iTime(_Symbol,30,0))&&hpState.last_time==initial.last_time);
 history[210]=open;
 current=214;wrong_first=true;long previous=hpState.last_time;
 assert(!HPSyncClosedBars(iTime(_Symbol,30,0))&&hpState.last_time==previous&&!hpSignal.buy);
 wrong_first=false;incomplete=true;
 assert(!HPSyncClosedBars(iTime(_Symbol,30,0))&&hpState.last_time==previous);
 incomplete=false;
 assert(HPSyncClosedBars(iTime(_Symbol,30,0))&&hpProcessedThisBar==4);
 assert(hpState.bars_processed==214&&hpState.last_time==history[213].time&&hpState.expected_open==history[214].time);
 assert(!hpSignal.buy || (hpSignal.signal_time==history[213].time&&hpSignal.available_time==history[214].time));
 // Adapter catch-up is identical to direct chronological closed-bar feeding.
 HPState direct;HPCoreReset(direct);HPSignal expected;
 for(int i=0;i<214;i++) {
  HPBar b{history[i].time,history[i].open,history[i].high,history[i].low,history[i].close};
  assert(HPStep(direct,b,history[i+1].time,expected));
 }
 assert(hpState.events_long==direct.events_long&&hpState.pivots_high==direct.pivots_high&&hpState.patterns_long==direct.patterns_long);
 assert(hpSignal.buy==expected.buy&&hpSignal.signal_time==expected.signal_time);
 current=215;assert(HPSyncClosedBars(iTime(_Symbol,30,0))&&hpProcessedThisBar==1);
 assert(!HPSyncClosedBars(iTime(_Symbol,30,0))&&!hpSignal.buy); // No duplicate signal at same decision.
 std::cout<<"Production MT5 history adapter: closed210 seed, no open OHLC, ordered catch-up, observed gaps, transactional copy failures and latest-only signal passed.\n";
}
