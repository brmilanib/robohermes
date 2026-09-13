// Protocol mock, not an MT5 simulator. Includes exact production management bodies.
#include <cmath>
#include <cassert>
#include <algorithm>
#include <iostream>
#include <vector>
#include <string>
#include <map>
using std::vector;using std::string;using datetime=long;using uint=unsigned int;
template<class A,class B> double MathMax(A a,B b){return std::max(double(a),double(b));}
template<class A,class B> double MathMin(A a,B b){return std::min(double(a),double(b));}
double MathAbs(double x){return std::abs(x);}double MathFloor(double x){return std::floor(x);}
double MathCeil(double x){return std::ceil(x);}double MathRound(double x){return std::round(x);}
bool MathIsValidNumber(double x){return std::isfinite(x);}
double NormalizeDouble(double x,int d){double k=std::pow(10,d);return std::round(x*k)/k;}
template<class T> int ArraySize(const vector<T>& x){return x.size();}
template<class T> void ArrayResize(vector<T>& x,int n){x.resize(n);}
template<class T,size_t N,class V> void ArrayInitialize(T (&x)[N],V v){std::fill(x,x+N,T(v));}
#include "Core_Runtime.inc"
#include "Structures_Runtime.inc"
using ENUM_DAY_OF_WEEK=int;using ENUM_ORDER_TYPE=int;using ENUM_ORDER_TYPE_FILLING=int;
enum {POSITION_SYMBOL=1,POSITION_IDENTIFIER,POSITION_SL,POSITION_TP,POSITION_VOLUME,POSITION_TYPE,
 SYMBOL_FILLING_MODE,SYMBOL_TRADE_TICK_SIZE,SYMBOL_TRADE_STOPS_LEVEL,SYMBOL_TRADE_FREEZE_LEVEL,
 MQL_TRADE_ALLOWED,TERMINAL_TRADE_ALLOWED,ACCOUNT_TRADE_ALLOWED,ACCOUNT_TRADE_EXPERT,ACCOUNT_BALANCE,ACCOUNT_MARGIN_FREE,
 DEAL_POSITION_ID,DEAL_ENTRY,DEAL_REASON,DEAL_MAGIC,DEAL_VOLUME,DEAL_PRICE,DEAL_TIME,DEAL_TYPE,DEAL_SYMBOL,
 DEAL_PROFIT,DEAL_SWAP,DEAL_COMMISSION,DEAL_FEE,SYMBOL_VOLUME_MIN,SYMBOL_VOLUME_MAX,SYMBOL_VOLUME_STEP,ACCOUNT_EQUITY,ACCOUNT_MARGIN};
enum {ORDER_TYPE_BUY=0,ORDER_TYPE_SELL=1,POSITION_TYPE_BUY=0,POSITION_TYPE_SELL=1,DEAL_TYPE_BUY=0,DEAL_TYPE_SELL=1,
 DEAL_ENTRY_IN=0,DEAL_ENTRY_OUT=1,DEAL_ENTRY_OUT_BY=3,DEAL_REASON_EXPERT=3,TRADE_ACTION_DEAL=1,TRADE_ACTION_SLTP=6,
 SYMBOL_FILLING_FOK=1,SYMBOL_FILLING_IOC=2,ORDER_FILLING_FOK=1,ORDER_FILLING_IOC=2,ORDER_FILLING_RETURN=3,
 TRADE_RETCODE_DONE=10009};
struct MqlDateTime{int day_of_week=1,hour=12,min=0,sec=0;};
struct MqlTick{double bid=110,ask=110.1;long time_msc=100000;};
struct MqlTradeRequest{int action=0,type=0,type_filling=0;ulong position=0,magic=0,deviation=0;string symbol,comment;double sl=0,tp=0,price=0,volume=0;};
struct MqlTradeResult{uint retcode=0;ulong deal=0,order=0;};
struct Pos{ulong ticket,pid;double volume,sl,tp,entry;int side=0;};
struct Deal{ulong id,pid;int entry,type;double volume,price;double profit=0,swap=0,commission=0,fee=0;ulong magic=26120160;};
vector<PECycle> cycles;vector<PEMonth> months(1);vector<Pos> positions;vector<Deal> deals;
PEProfile profile; DCProfile dc{}; long targetFailures=0,targetAdjustments=0; int active=0;int selected=-1;MqlTick quote;int nextRet=10009;
int InpCase=1;
string folder="Olimpo_XAU_170\\R170_01\\CASO_1_ABC";
using ushort=unsigned short;
int StringLen(const string &s){return s.size();}
ushort StringGetCharacter(const string &s,int i){return (unsigned char)s.at(i);}
string ShortToString(ushort c){return string(1,(char)c);}
long clockMs=100000;bool permissions=true,integrity=true,haltEntries=false,closeEmergency=false,sessionKnown=false,finalizing=false;
int sessionCount=0,sessionDay[128],sessionFrom[128],sessionTo[128],errorCode=0,lastRetcode=0;
long lastEmergencyMs=0,lastErrorTime=0,partialDefers=0,beDefers=0,sessionDefers=0,stopDefers=0,ambiguousPartials=0,addRejects=0,riskBlocks=0;
double maxRisk=0,maxRiskPct=0,InpMaxSpreadPoints=0,_Point=.001;int _Digits=3;
double mockFreeMargin=100000,mockEquity=10000,mockUsedMargin=0,mockTick=.001,mockVolumeMin=.01,mockVolumeMax=100,mockVolumeStep=.01,mockMarginPerLot=1000,mockFillOffset=0;
long mockStops=0,mockFreeze=0;
ulong InpMagic=26120160,InpDeviationPoints=20;string _Symbol="XAUUSD";
int volumeRequests=0,slRequests=0;bool closeDuringAmendment=false;vector<MqlTradeRequest> requests;
string I(long x){return std::to_string(x);}string U(ulong x){return std::to_string(x);}string N(double x){return std::to_string(x);}
long NowMs(){return clockMs;}datetime TimeCurrent(){return clockMs/1000;}
void TimeToStruct(datetime,MqlDateTime &d){d={};}
bool SymbolInfoSessionTrade(string,int,uint,datetime&,datetime&){return false;}
bool MQLInfoInteger(int){return permissions;}bool TerminalInfoInteger(int){return permissions;}
long AccountInfoInteger(int){return permissions;}
double AccountInfoDouble(int key){if(key==ACCOUNT_BALANCE||key==ACCOUNT_EQUITY)return mockEquity;if(key==ACCOUNT_MARGIN)return mockUsedMargin;return mockFreeMargin;}
long SymbolInfoInteger(string,int key){if(key==SYMBOL_FILLING_MODE)return 3;if(key==SYMBOL_TRADE_STOPS_LEVEL)return mockStops;if(key==SYMBOL_TRADE_FREEZE_LEVEL)return mockFreeze;return 0;}
double SymbolInfoDouble(string,int key){if(key==SYMBOL_VOLUME_MIN)return mockVolumeMin;if(key==SYMBOL_VOLUME_MAX)return mockVolumeMax;if(key==SYMBOL_VOLUME_STEP)return mockVolumeStep;return mockTick;}
bool SymbolInfoTick(string,MqlTick &q){q=quote;return true;}
int PositionsTotal(){return positions.size();}
ulong PositionGetTicket(int i){selected=i;return i>=0&&i<int(positions.size())?positions[i].ticket:0;}
bool PositionSelectByTicket(ulong t){for(size_t i=0;i<positions.size();i++)if(positions[i].ticket==t){selected=i;return true;}selected=-1;return false;}
string PositionGetString(int){return _Symbol;}
long PositionGetInteger(int key){assert(selected>=0);return key==POSITION_IDENTIFIER?positions[selected].pid:positions[selected].side;}
double PositionGetDouble(int key){assert(selected>=0);Pos p=positions[selected];if(key==POSITION_SL)return p.sl;if(key==POSITION_TP)return p.tp;if(key==POSITION_VOLUME)return p.volume;return 0;}
int CycleByPid(ulong pid){for(int i=0;i<int(cycles.size());i++)for(int j=0;j<cycles[i].legs;j++)if(cycles[i].pids[j]==pid)return i;return -1;}
int LegByPid(int n,ulong pid){for(int i=0;i<cycles[n].legs;i++)if(cycles[n].pids[i]==pid)return i;return -1;}
bool OwnSelected(){return selected>=0;}
int OwnPositions(double &v,ulong &t){v=0;t=0;for(auto p:positions){v+=p.volume;t=p.ticket;}return positions.size();}
bool OwnPendingOrder(){return false;}
bool OrderCalcProfit(int type,string,double volume,double entry,double exit,double &p){p=(type==ORDER_TYPE_BUY?1:-1)*(exit-entry)*volume*100;return true;}
bool OrderCalcMargin(int,string,double volume,double,double &m){m=volume*mockMarginPerLot;return true;}
void Invalid(int code,const string&,bool emergency=false){integrity=false;haltEntries=true;closeEmergency|=emergency;if(!errorCode)errorCode=code;}
void Event(const string&,int,const string&,long=0){}
int MonthIndex(datetime){return 0;}
void SyncCycle(){if(positions.empty())active=-1;}
bool HistorySelect(datetime,datetime){return true;}int HistoryDealsTotal(){return deals.size();}
ulong HistoryDealGetTicket(int i){return deals[i].id;}
bool HistoryDealSelect(ulong id){for(auto d:deals)if(d.id==id)return true;return false;}
Deal get(ulong id){for(auto d:deals)if(d.id==id)return d;assert(false);return {};}
long HistoryDealGetInteger(ulong id,int key){Deal d=get(id);if(key==DEAL_POSITION_ID)return d.pid;if(key==DEAL_ENTRY)return d.entry;
 if(key==DEAL_REASON)return DEAL_REASON_EXPERT;if(key==DEAL_MAGIC)return d.magic;if(key==DEAL_TIME)return TimeCurrent();if(key==DEAL_TYPE)return d.type;return 0;}
double HistoryDealGetDouble(ulong id,int key){auto d=get(id);if(key==DEAL_VOLUME)return d.volume;if(key==DEAL_PRICE)return d.price;
 if(key==DEAL_PROFIT)return d.profit;if(key==DEAL_SWAP)return d.swap;if(key==DEAL_COMMISSION)return d.commission;if(key==DEAL_FEE)return d.fee;return 0;}
string HistoryDealGetString(ulong,int){return _Symbol;}
bool OrderSend(const MqlTradeRequest &r,MqlTradeResult &out){
 requests.push_back(r);out.retcode=nextRet;
 if(r.action==TRADE_ACTION_DEAL)volumeRequests++;else slRequests++;
 if(nextRet!=10009)return nextRet!=10012;
 assert(r.symbol==_Symbol&&r.magic==InpMagic&&r.position>0);
 if(!PositionSelectByTicket(r.position))return true;
 if(r.action==TRADE_ACTION_SLTP && closeDuringAmendment){positions.clear();selected=-1;return true;}
 if(r.action==TRADE_ACTION_SLTP){positions[selected].sl=r.sl;positions[selected].tp=r.tp;}
 else {assert(r.type==ORDER_TYPE_SELL);assert(r.volume>0&&r.volume<positions[selected].volume+1e-8);
  positions[selected].volume-=r.volume;out.order=500+deals.size();out.deal=out.order;
  deals.push_back({out.deal,positions[selected].pid,DEAL_ENTRY_OUT,DEAL_TYPE_SELL,r.volume,quote.bid});
 }
 return true;
}
struct CTrade{
 ulong resultDeal=0;uint ret=10009;
 bool Buy(double v,string,double,double sl,double tp,string){volumeRequests++;ret=nextRet;if(ret!=10009)return false;
  ulong id=200+positions.size();positions.push_back({id,id,v,sl,tp,quote.ask+mockFillOffset,0});resultDeal=800+deals.size();
  deals.push_back({resultDeal,id,DEAL_ENTRY_IN,DEAL_TYPE_BUY,v,quote.ask+mockFillOffset});return true;}
 bool Sell(double,string,double,double,double,string){assert(false);return false;}
 uint ResultRetcode(){return ret;}ulong ResultDeal(){return resultDeal;}string ResultRetcodeDescription(){return "mock";}
 bool PositionClose(ulong t){if(PositionSelectByTicket(t))positions.erase(positions.begin()+selected);return true;}
} trade;
#include "Execution_Runtime.inc"
#include "History_Runtime.inc"
#include "Reports_Runtime.inc"
void reset(int id){
 dc={}; closeDuringAmendment=false; targetFailures=targetAdjustments=0; InpCase=id;cycles.assign(1,{});months.assign(1,{});positions.clear();deals.clear();requests.clear();PESelectProfile(id,profile);
 mockFreeMargin=100000;mockEquity=10000;mockUsedMargin=0;mockTick=.001;mockVolumeMin=.01;mockVolumeMax=100;mockVolumeStep=.01;mockMarginPerLot=1000;mockFillOffset=0;mockStops=mockFreeze=0;
 auto &c=cycles[0];c.number=1;c.origin=profile.mode;c.side=1;c.legs=1;c.entry=100;c.stop=90;c.target=150;c.volume=.1;c.initialRisk=100;
 c.pid=111;c.pids[0]=111;c.fills[0]=100;c.volumes[0]=.1;c.expectedStops[0]=90;c.desiredStop=90;c.start=100;
 c.partialEnabled=profile.partial;c.beTrigger=profile.partial?1:profile.be15;
 positions.push_back({111,111,.1,90,150,100,0});
 active=0;clockMs=100000;permissions=true;integrity=true;haltEntries=false;closeEmergency=false;sessionKnown=false;sessionCount=0;errorCode=0;
 nextRet=10009;volumeRequests=slRequests=0;quote={110,110.1,100000};
}
bool near(double a,double b){return std::abs(a-b)<1e-7;}
int main(){
 reset(7);ManageProtection();assert(cycles[0].part.done&&cycles[0].be.done&&near(positions[0].volume,.05));
 assert(near(positions[0].sl,100)&&volumeRequests==1&&slRequests==1&&integrity);assert(near(ActiveRisk(),0));
 for(int i=0;i<100;i++){clockMs++;ManageProtection();}assert(volumeRequests==1&&slRequests==1);
 reset(7);nextRet=10018;ManageProtection();assert(volumeRequests==1&&!cycles[0].part.done&&!haltEntries);
 for(int i=0;i<100;i++){clockMs+=10;ManageProtection();}assert(volumeRequests==1);
 clockMs+=60000;nextRet=10009;ManageProtection();assert(cycles[0].part.done&&volumeRequests==2&&integrity);
 reset(7);nextRet=10012;ManageProtection();assert(cycles[0].part.uncertain&&volumeRequests==1);
 clockMs+=70000;ManageProtection();assert(haltEntries&&volumeRequests==1&&near(positions[0].sl,90));
 reset(7);permissions=false;for(int i=0;i<100;i++)ManageProtection();assert(volumeRequests==0&&near(positions[0].volume,.1));
 reset(4);quote={120,120.1,100000};ManageProtection();assert(cycles[0].be.done&&near(positions[0].sl,100)&&integrity);
 reset(4);PEArm(cycles[0].be,NowMs());quote={100.0001,100.1,100000};ManageProtection();assert(slRequests==0&&near(positions[0].sl,90));
 reset(9);quote={110.1,110.2,100000};ManageAdd(false,false);assert(cycles[0].adds==1&&near(positions[0].sl,100)&&integrity);
 clockMs+=10000;quote={120.1,120.2,clockMs};ManageAdd(false,false);assert(cycles[0].adds==2&&positions.size()==3&&integrity);
 double sum=0;for(auto p:positions){sum+=p.volume;assert(near(p.sl,110));}assert(near(sum,.2));
 clockMs+=10000;ManageAdd(false,false);assert(cycles[0].adds==2&&volumeRequests==2);
 reset(11);quote={95,95.1,100000};ManageAdd(true,false);assert(volumeRequests==0);
 clockMs+=10000;ManageAdd(true,true);assert(cycles[0].adds==1&&positions.size()==2&&integrity);
 assert(near(ActiveRisk(),151)&&near(positions[1].sl,90));clockMs+=10000;ManageAdd(true,true);assert(volumeRequests==1);
 reset(11);quote={93,93.1,100000};ManageAdd(true,true);assert(volumeRequests==0);
 reset(1);positions[0].sl=89;CheckProtection();assert(closeEmergency&&errorCode==302);
 reset(29);cycles[0].side=-1;cycles[0].stop=110;cycles[0].desiredStop=110;cycles[0].expectedStops[0]=110;cycles[0].target=50;
 positions[0].side=1;positions[0].sl=110;positions[0].tp=50;CheckProtection();assert(integrity&&near(ActiveRisk(),100));
 reset(1);deals.push_back({2,111,DEAL_ENTRY_IN,DEAL_TYPE_BUY,.1,100});
 deals.push_back({3,111,DEAL_ENTRY_OUT,DEAL_TYPE_SELL,.1,110,100,-5,0,0,0});
 finalizing=true;assert(AggregateCycle(0));assert(near(cycles[0].net,95)&&near(cycles[0].inVolume,cycles[0].outVolume));
 deals.pop_back();assert(AggregateCycle(0));assert(!near(cycles[0].inVolume,cycles[0].outVolume));
 reset(1);positions.clear();PEArm(cycles[0].be,NowMs());assert(!MoveStops(100));assert(cycles[0].beTime==0);
 reset(1);cycles[0].closed=true;cycles[0].net=95;cycles[0].path.reached[2]=cycles[0].path.returned[2]=true;
 months[0].key=202501;PEStartEquity(months[0].path,1000,1000);PEObserveEquity(months[0].path,1200,1200);
 vector<double> stats(S_COUNT+G_COUNT,0),payload;BuildPayload(stats,payload);
 assert(PayloadValid(payload)&&payload.size()==size_t(S_COUNT+G_COUNT+1+18+40+1+folder.size()));
 assert(PayloadFolder(payload)==folder);
 auto original=payload;payload.back()=999;assert(!PayloadValid(payload));payload=original;
 int base=S_COUNT+G_COUNT;assert(payload[base]==1&&payload[base+1+3]==200);
 assert(payload[base+1+18+2*8+5]==1); // eventual winning control returned after 2R
 payload.pop_back();assert(!PayloadValid(payload));
 // Production TP-cap amendments: actual fill below quote must shorten target.
 reset(1);dc.targetMode=1;cycles[0].targetDistance=20;cycles[0].quotedEntry=100.1;
 cycles[0].target=120.1;positions[0].tp=120.1;quote={100,100.1,100000};
 EnforceTargetCap();assert(integrity&&slRequests==1&&volumeRequests==0);
 assert(near(cycles[0].target,120)&&near(positions[0].tp,120)&&near(positions[0].sl,90));
 assert(targetAdjustments==1);EnforceTargetCap();assert(slRequests==1); // no repeated amendment
 reset(1);dc.targetMode=1;cycles[0].targetDistance=20;cycles[0].entry=100.2;
 cycles[0].target=120;positions[0].tp=120;EnforceTargetCap();assert(slRequests==0&&near(positions[0].tp,120)); // never widen
 reset(1);dc.targetMode=2;cycles[0].targetDistance=.02;cycles[0].target=100.03;positions[0].tp=100.03;quote={100,100.001,100000};
 EnforceTargetCap();assert(integrity&&near(positions[0].tp,100.02)&&slRequests==1);
 reset(1);dc.targetMode=1;cycles[0].targetDistance=20;cycles[0].target=120.1;positions[0].tp=120.1;nextRet=10012;
 EnforceTargetCap();assert(closeEmergency&&!integrity&&targetFailures==1&&near(positions[0].sl,90)&&volumeRequests==0);
 EnforceTargetCap();assert(slRequests==1); // ambiguous modification is not blindly retried
 reset(1);dc.targetMode=1;cycles[0].targetDistance=20;cycles[0].target=120.1;positions[0].tp=120.1;permissions=false;
 EnforceTargetCap();assert(closeEmergency&&!integrity&&slRequests==0&&near(positions[0].sl,90));
 reset(1);dc.targetMode=1;cycles[0].targetDistance=20;cycles[0].target=120.1;positions[0].tp=120.1;closeDuringAmendment=true;
 ManageProtection();assert(active==-1&&positions.empty()&&integrity&&slRequests==1);
 std::cout<<"Target cap: quote-price/native-point units; fill correction; no widening; SL preserved; idempotency; uncertain reply close path passed.\n";
 std::cout<<"Execution: confirmed half+BE, idempotency, session deferral, ambiguous replies, stop freeze, two-step pyramid, bounded averaging, short risk passed.\n";
 return 0;
}
