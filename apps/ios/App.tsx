import React, { useEffect, useState } from 'react';
import { Alert, AppState, StatusBar, Linking } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import * as Network from 'expo-network';
import { getStorage, getUploader, getTripApi } from './src/backgroundLocationTask';
import { MeasurementScreen } from './src/ui/MeasurementScreen';
import { Collector } from './src/collector';
import { Storage } from './src/storage';
import { ports, foregroundOnly } from './src/location';
import { files } from './src/files';
import { exportTrip } from './src/exporter';
import type { Summary } from './src/types';
import type { ServerTrip } from './src/tripApi';
let runtime: Promise<{db:Storage; collector:Collector}> | undefined;
function initialize() { return runtime ??= (async () => {
  const db = await getStorage();
  const identity = await db.identity();
  const collector=new Collector(db,identity,ports); await collector.refresh();
  return {db, collector};
})(); }
export default function App() {
  const [service,setService]=useState<Awaited<ReturnType<typeof initialize>>>();
  const [,redraw]=useState(0); const [trips,setTrips]=useState<Summary[]>([]);
  const [error,setError]=useState(''); const [sharing,setSharing]=useState(false);
  const [now,setNow]=useState(Date.now()); const c=service?.collector;
  const [delivery,setDelivery]=useState<{pending:number;blocked:number;sent:number;last_success:string|null}>();
  const [uploadError,setUploadError]=useState('');
  const [resultTrip,setResultTrip]=useState<Summary>();
  const [serverTrip,setServerTrip]=useState<ServerTrip>();
  const [tripError,setTripError]=useState('');
  const [evidence,setEvidence]=useState<Awaited<ReturnType<Storage['deliveryEvidence']>>>();
  useEffect(() => {
    let alive=true;
    void initialize().then(s=>{ if(!alive)return; setService(s); s.collector.changed=()=>redraw(n=>n+1); }).catch(e=>setError(String(e)));
    const timer=setInterval(()=>setNow(Date.now()),1000);
    const sub=AppState.addEventListener('change',state=>{void runtime?.then(s=>s.collector.appStateChanged(state));});
    return ()=>{alive=false;clearInterval(timer);sub.remove();void runtime?.then(s=>{s.collector.changed=()=>{};void s.collector.interrupt('화면 종료');});};
  },[]);
  useEffect(()=>{
    if(!service)return;
    let alive=true,refreshing=false;
    async function tick(wake=false){
      if(refreshing)return;refreshing=true;
      try {
        if(wake)await service!.db.wakeDelivery();
        await service!.collector.refresh();
        const uploader=await getUploader(); await uploader.tick();
        const tripApi=await getTripApi(); await tripApi.tick(wake);
        const id=service!.collector.trip?.trip_id ?? (await service!.db.list())[0]?.trip_id;
        const summary=id ? await service!.db.summary(id) : undefined;
        const status=await service!.db.deliveryStatus(id??null);
        const proof=await service!.db.deliveryEvidence(id??null);
        const remote=id ? await tripApi.result(id) : null;
        if(alive){setServerTrip(remote?.result);setTripError(remote?.error??tripApi.error);}
        if(alive){setResultTrip(summary);setDelivery(status);setEvidence(proof);setUploadError(proof.head?.last_error || uploader.error);}
      }catch(e){if(alive)setError(String(e));}finally{refreshing=false;}
    }
    void tick(true);
    const timer=setInterval(()=>{if(AppState.currentState==='active')void tick();},3000);
    const app=AppState.addEventListener('change',state=>{if(state==='active')void tick(true);});
    const network=Network.addNetworkStateListener(state=>{if(state.isConnected && state.isInternetReachable!==false)void tick(true);});
    return ()=>{alive=false;clearInterval(timer);app.remove();network.remove();};
  },[service]);
  useEffect(()=>{if(service && c?.phase!=='recording' && c?.phase!=='starting') void service.db.list().then(setTrips).catch(e=>setError(String(e)));},[service,c?.phase]);
  const trip=c?.trip; const seconds=trip ? Math.max(0,Math.floor(((trip.ended_at ? Date.parse(trip.ended_at) : trip.status==='recording' ? now : Date.parse(c?.latest?.received_at ?? trip.started_at))-Date.parse(trip.started_at))/1000)) : 0;
  const resultMatches=!trip || trip.trip_id===resultTrip?.trip_id;
  const duration=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
  async function share(id:string) {
    if(!service||sharing)return;setSharing(true);setError('');
    try{await exportTrip(service.db,files,id,'gps',ports.now());}catch(e){setError('내보내기 오류: '+String(e));}finally{setSharing(false);}
  }
  function chooseExport(offset=0) {
    // A native selection dialog keeps older recordings accessible without another page.
    const saved=trips.filter(t=>t.status!=='recording');
    Alert.alert('GPS JSONL 내보내기','저장된 측정을 선택하세요.',[
      ...saved.slice(offset,offset+5).map(t=>({text:new Date(t.started_at).toLocaleString('ko-KR')+' · '+t.gps_count+'개',onPress:()=>void share(t.trip_id)})),
      ...(saved.length>offset+5 ? [{text:'이전 기록 더 보기',onPress:()=>chooseExport(offset+5)}] : []),
      {text:'취소',style:'cancel'},
    ]);
  }
  async function shareEvent() {
    const event=(resultMatches?evidence?.sent:null) ?? c?.latest;
    if(!event || sharing)return;
    setSharing(true);
    try {
      const file=await files.open(`${event.event_id}.gps.json`);
      try {await file.append(JSON.stringify(event,null,2)+'\n');} finally {await file.close();}
      await files.share(file.uri,'metadata');
    }catch(e){setError('GPS 한 건 공유 오류: '+String(e));}finally{setSharing(false);}
  }
  async function shareCheck() {
    if(!service || !resultTrip || sharing)return;
    setSharing(true);
    try {
      const report=await service.db.tripReport(resultTrip.trip_id);
      const file=await files.open(`${resultTrip.trip_id}.trip-check.json`);
      try {await file.append(JSON.stringify(report,null,2)+'\n');}finally{await file.close();}
      await files.share(file.uri,'metadata');
    }catch(e){setError('측정 결과 공유 오류: '+String(e));}finally{setSharing(false);}
  }
  return <SafeAreaProvider><StatusBar barStyle="dark-content"/><MeasurementScreen
    ready={!!c} mode={c?.mode??null} phase={c?.phase??'idle'} count={c?.count??0} duration={duration}
    accuracy={c?.latest?.accuracy??null} latestLabel={c?.latest?.label} tripId={trip?.trip_id}
    error={error||c?.error||''} onMode={mode=>{void c?.selectMode(mode).catch(e=>setError(String(e)));}} onStart={()=>{void c?.start();}}
    onStop={()=>{void c?.stop().catch(e=>setError(String(e)));}} canExport={trips.some(t=>t.status!=='recording')}
    sharing={sharing} onExport={()=>chooseExport()} active={trip?.status==='recording'} backgroundRunning={c?.backgroundRunning}
    lastReceived={c?.lastReceived} sequence={c?.latest?.sequence} pending={resultMatches?delivery?.pending:undefined} lastSuccess={resultMatches?delivery?.last_success:undefined}
    uploadError={uploadError} onResume={()=>{void c?.resume();}} onSettings={()=>{void Linking.openSettings();}}
    foregroundOnly={foregroundOnly} eventId={c?.latest?.event_id} eventTime={c?.latest?.event_time}
    confirmedEvent={resultMatches?evidence?.sent??undefined:undefined} retryCount={resultMatches?evidence?.head?.retry_count:undefined}
    resultTrip={resultMatches?resultTrip:undefined} sent={delivery?.sent} blocked={delivery?.blocked} onShareCheck={()=>{void shareCheck();}}
    canShareEvent={!!((resultMatches&&evidence?.sent)||c?.latest)} onShareEvent={()=>{void shareEvent();}}
    serverTrip={serverTrip?.trip_id===resultTrip?.trip_id?serverTrip:undefined} tripError={tripError}
    onRetryTrip={()=>{if(resultTrip)void getTripApi().then(api=>api.retry(resultTrip.trip_id)).catch(e=>setError(String(e)));}}
    onRetry={()=>{void service?.db.retryDelivery().then(async()=>{await (await getUploader()).tick();}).catch(e=>setError(String(e)));}}
    /></SafeAreaProvider>;
}
