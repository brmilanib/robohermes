struct PECycle {
 int number,origin,side,legs,adds;
 int entryPath; HPSignal entryPivot;
 ulong pid,ticket,partialDeal,partialOrder;
 ulong pids[3]; double fills[3],volumes[3],expectedStops[3];
 datetime start,finish,partialTime,beTime;
 double quotedEntry,quotedTarget,targetDistance,targetProfitEstimate; int targetAdjustments;
 double entry,stop,target,volume,initialRisk,balanceBefore,beTrigger,liveStop,peakRisk,desiredStop;
 double gross,swap,costs,net,inVolume,outVolume,finalPrice,partialPrice,partialVolume;
 long finalReason;
 bool closed,partialEnabled,finalObserved,addPending; long addNextMs,addAttempts;
 PERequest be,part;
 EVOFeatures entryFeatures; int entryPolicy;
 PEPath path; double featureADXChange,featureADX,featureATR,featureDistance,featureSlope; datetime signalTime;
};
struct PEMonth {
 int key; long bars,signals,opened,closed,bes,partials;
 double cycleNet,bookedNet;
 datetime firstTick,lastTick;
 PEEquityPath path;
};