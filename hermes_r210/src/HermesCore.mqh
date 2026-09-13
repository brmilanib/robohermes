#ifndef OLIMPO_HERMES_CORE_190
#define OLIMPO_HERMES_CORE_190
// Target mode: 0=5 initial quoted stop distances, 1=20 quote-price units,
// 2=20 native SYMBOL_POINT units. A point is not a pip or a dollar profit.
double HermesTargetDistance(const int mode,const double point)
 {
  if(mode==1) return 20.0;
  if(mode==2 && MathIsValidNumber(point) && point>0) return 20.0*point;
  return 0;
 }
bool HermesTargetPrice(const int side,const double entry,const double distance,const double tick,double &target)
 {
  target=0;
  if((side!=1 && side!=-1) || !MathIsValidNumber(entry) || !MathIsValidNumber(distance) ||
     !MathIsValidNumber(tick) || entry<=0 || tick<=0 || distance<tick) return false;
  double raw=entry+side*distance;
  if(!MathIsValidNumber(raw) || raw<=0) return false;
  // Round toward entry, never increase the requested target distance.
  target=(side==1 ? MathFloor(raw/tick+1e-9) : MathCeil(raw/tick-1e-9))*tick;
  double tolerance=MathMax(1e-10,tick*1e-7);
  if(side*(target-entry)>distance+tolerance) target-=side*tick;
  double actual=side*(target-entry);
  return target>0 && actual>=tick-tolerance && actual<=distance+tolerance;
 }
// Fixed lot means exact or denied; it is never silently reduced to fit capital.
bool HermesExactLot(const double requested,const double minimum,const double maximum,const double step)
 {
  if(!MathIsValidNumber(requested) || !MathIsValidNumber(minimum) || !MathIsValidNumber(maximum) ||
     !MathIsValidNumber(step) || requested<=0 || minimum<=0 || maximum<minimum || step<=0 ||
     requested<minimum-1e-9 || requested>maximum+1e-9) return false;
  return MathAbs(requested-MathRound(requested/step)*step)<1e-8;
 }
bool HermesMarginAvailable(const double required,const double freeMargin)
 {
  return MathIsValidNumber(required) && MathIsValidNumber(freeMargin) && required>=0 &&
         freeMargin>0 && required<=freeMargin;
 }
#endif
