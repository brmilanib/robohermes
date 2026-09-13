#include "../src/PivotCore.mqh"
#include <cassert>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

static HPBar bar(int i, double price)
{
   HPBar b;
   b.time=1000L+1800L*i;
   b.open=price; b.high=price+0.4; b.low=price-0.4; b.close=price;
   return b;
}

static std::vector<HPBar> simple_long()
{
   const double prices[]={12,11,10,11,12,15,14,13,12,13,14,15.5,15};
   std::vector<HPBar> v;
   for(int i=0;i<13;++i) v.push_back(bar(i,prices[i]));
   return v;
}

static std::vector<HPSignal> replay(const std::vector<HPBar> &bars,
                                   HPState &state)
{
   HPCoreReset(state);
   std::vector<HPSignal> result;
   for(std::size_t i=0;i+1<bars.size();++i)
   {
      HPSignal sig;
      assert(HPStep(state,bars[i],bars[i+1].time,sig));
      if(sig.buy) result.push_back(sig);
   }
   return result;
}

static HPPivot pivot(int type, double price, long origin)
{
   HPPivot p;
   p.type=type; p.price=price; p.origin_time=origin;
   p.confirmation_bar_time=origin+3600; p.available_time=origin+5400;
   return p;
}

static void unit_tests()
{
   HPState state;
   std::vector<HPBar> bars=simple_long();
   std::vector<HPSignal> events=replay(bars,state);
   assert(events.size()==1);
   const HPSignal first=events[0];
   assert(first.signal_time==bars[11].time);
   assert(first.available_time==bars[12].time);
   assert(first.p1_time==bars[2].time && first.p2_time==bars[5].time);
   assert(first.p3_time==bars[8].time);
   assert(first.reference_price==15.4 && first.stop_f1==9.6);
   assert(first.pullback_f2==11.6);
   assert(first.pattern_available_time==bars[11].time);
   assert(first.p3_confirmation_time==bars[10].time);
   assert(first.p3_available_time<=first.signal_time);

   // No signal or confirmed pivot is manufactured by the last witness bar.
   for(std::size_t cut=2;cut<bars.size();++cut)
   {
      std::vector<HPBar> prefix(bars.begin(),bars.begin()+cut);
      HPState prefix_state;
      std::vector<HPSignal> got=replay(prefix,prefix_state);
      std::size_t expected=0;
      for(const HPSignal &e:events)
         if(e.available_time<=prefix.back().time) ++expected;
      assert(got.size()==expected);
      assert(prefix_state.bars_processed==static_cast<long>(cut)-1);
   }

   // Touching F1 on the breakout candle invalidates even a high closing price.
   bars=simple_long(); bars[11].low=9.6;
   assert(replay(bars,state).empty());

   // A previous invalidation remains invalidated on a later crossing.
   bars=simple_long(); bars[11].low=9.5; bars[11].close=14;
   bars[12]=bar(12,15.5); bars.push_back(bar(13,15.7));
   assert(replay(bars,state).empty());

   // Crossing while P3 is being confirmed is too early, never retroactive.
   bars=simple_long(); bars[10]=bar(10,15.5); bars[11]=bar(11,15.6);
   assert(replay(bars,state).empty());

   // Re-crossing the same neckline emits only once for that pattern snapshot.
   bars=simple_long();
   bars[12]=bar(12,15.0); bars.push_back(bar(13,15.6));
   bars.push_back(bar(14,15.7));
   assert(replay(bars,state).size()==1);

   // Tied low at P1 prevents that pivot and the downstream pattern.
   bars=simple_long(); bars[1].low=bars[2].low;
   assert(replay(bars,state).empty());
   assert(state.tie_low_windows>=1);

   // An ambiguous outside bar confirms both extremes but resets sequencing.
   HPCoreReset(state);
   HPPivot p=pivot(-1,1,100);
   HPExposePivot(state,p,p.available_time);
   p=pivot(1,5,200); HPExposePivot(state,p,p.available_time);
   p=pivot(-1,2,300); HPExposePivot(state,p,p.available_time);
   assert(state.active_pattern && state.alternating_count==3);
   HPSignal signal;
   for(int i=0;i<5;++i)
   {
      HPBar b=bar(i,3);
      if(i==2) { b.high=10; b.low=0; }
      assert(HPStep(state,b,b.time+1800,signal));
   }
   assert(state.double_extremes==1);
   assert(state.alternating_count==0 && !state.active_pattern);
   assert(state.pivots_high==1 && state.pivots_low==1);

   // Same-side pivots only replace a MORE extreme reference. An ignored one
   // cannot revive a consumed pattern; a genuinely new snapshot can.
   HPCoreReset(state);
   p=pivot(-1,1,100); HPExposePivot(state,p,p.available_time);
   p=pivot(1,5,200); HPExposePivot(state,p,p.available_time);
   p=pivot(-1,3,300); HPExposePivot(state,p,p.available_time);
   state.active_invalid=true;
   p=pivot(-1,4,400); HPExposePivot(state,p,p.available_time);
   assert(state.p3.origin_time==300 && state.active_invalid);
   p=pivot(-1,2,500); HPExposePivot(state,p,p.available_time);
   assert(state.p3.origin_time==500 && !state.active_invalid);
   assert(state.patterns_long==2);

   // Wrong times, missing witnesses and invalid OHLC fail before mutation.
   HPCoreReset(state);
   HPBar b=bar(0,10);
   assert(HPStep(state,b,bar(1,10).time,signal));
   const long saved_time=state.last_time, saved_expected=state.expected_open;
   assert(!HPStep(state,b,bar(1,10).time,signal));
   assert(!signal.buy && state.bars_processed==1);
   b=bar(2,10);
   assert(!HPStep(state,b,b.time+1800,signal));
   b=bar(1,10);
   assert(!HPStep(state,b,b.time,signal));
   b.low=11;
   assert(!HPStep(state,b,b.time+1800,signal));
   b=bar(1,10); b.close=std::numeric_limits<double>::quiet_NaN();
   assert(!HPStep(state,b,b.time+1800,signal));
   b=bar(1,10); b.high=std::numeric_limits<double>::infinity();
   assert(!HPStep(state,b,b.time+1800,signal));
   assert(state.last_time==saved_time && state.expected_open==saved_expected);
   assert(state.bars_processed==1 && state.window_count==1);
   // An actual market closure gap is valid, if explicitly witnessed.
   b=bar(1,10);
   const long reopened=b.time+86400;
   assert(HPStep(state,b,reopened,signal));
   b.time=reopened;
   assert(HPStep(state,b,reopened+1800,signal));

   std::cout << "UNIT_PASS: causal_confirmation, prefix, same_bar_invalidation, "
             << "persistent_invalidation, no_retroactive_break, one_event, ties, "
             << "double_extreme_reset, same_side_replacement, invalid_input, gaps\n";
}

static std::vector<HPBar> read_fixture(const std::string &path)
{
   std::ifstream stream(path);
   if(!stream) throw std::runtime_error("Cannot read fixture: "+path);
   std::string line;
   std::getline(stream,line); // time;open;high;low;close
   std::vector<HPBar> result;
   while(std::getline(stream,line))
   {
      std::istringstream row(line);
      std::vector<std::string> parts;
      std::string part;
      while(std::getline(row,part,';')) parts.push_back(part);
      if(parts.size()!=5) throw std::runtime_error("Malformed fixture row");
      HPBar b;
      b.time=std::stol(parts[0]); b.open=std::stod(parts[1]);
      b.high=std::stod(parts[2]); b.low=std::stod(parts[3]);
      b.close=std::stod(parts[4]);
      result.push_back(b);
   }
   return result;
}

int main(int argc, char **argv)
{
   unit_tests();
   if(argc==1) return 0;
   if(argc!=4) { std::cerr << "fixture.csv events.csv counts.csv\n"; return 2; }
   const std::vector<HPBar> bars=read_fixture(argv[1]);
   HPState state;
   const std::vector<HPSignal> events=replay(bars,state);
   std::ofstream out(argv[2]);
   out << "signal_time;available_time;reference_price;stop_f1;pullback_f2;"
       << "p1_time;p2_time;p3_time;p1_available_time;p2_available_time;"
       << "p3_available_time;pattern_available_time\n";
   out << std::setprecision(17);
   for(const HPSignal &s:events)
      out << s.signal_time << ';' << s.available_time << ';'
          << s.reference_price << ';' << s.stop_f1 << ';' << s.pullback_f2
          << ';' << s.p1_time << ';' << s.p2_time << ';' << s.p3_time
          << ';' << s.p1_available_time << ';' << s.p2_available_time
          << ';' << s.p3_available_time << ';' << s.pattern_available_time << '\n';
   std::ofstream counts(argv[3]);
   counts << "metric;value\n" << "bars_processed;" << state.bars_processed << '\n'
          << "pivots_high;" << state.pivots_high << '\n'
          << "pivots_low;" << state.pivots_low << '\n'
          << "double_extremes;" << state.double_extremes << '\n'
          << "tie_high_windows;" << state.tie_high_windows << '\n'
          << "tie_low_windows;" << state.tie_low_windows << '\n'
          << "patterns_long;" << state.patterns_long << '\n'
          << "patterns_short;" << state.patterns_short << '\n'
          << "events_long;" << state.events_long << '\n'
          << "events_short_reference_only;" << state.events_short_reference_only << '\n';
   std::cout << "REPLAY: " << bars.size() << " observed bars; "
             << events.size() << " LONG 1-2-3 events\n";
}
