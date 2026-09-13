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
