import React, { useEffect, useState } from 'react';
import { Alert, AppState, StatusBar, Linking } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import * as Network from 'expo-network';
import { getStorage, getUploader, getTripApi } from './src/backgroundLocationTask';
import { EntryScreen, MeasurementScreen } from './src/ui/MeasurementScreen';
import { Collector } from './src/collector';
import { Storage } from './src/storage';
import { ports, foregroundOnly } from './src/location';
import { files } from './src/files';
import { exportTrip } from './src/exporter';
import type { Summary } from './src/types';
import type { FeedbackInput, ServerTrip } from './src/tripApi';
import { getEngagementApi } from './src/engagementRuntime';
import { MissionRankingScreen } from './src/ui/MissionRankingScreen';
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
  const [screen,setScreen]=useState<'user'|'developer'|null>(null);
  const [userSection,setUserSection]=useState<'trip'|'missions'|'ranking'>('trip');
  const [error,setError]=useState(''); const [sharing,setSharing]=useState(false);
  const [now,setNow]=useState(Date.now()); const c=service?.collector;
  const [delivery,setDelivery]=useState<{pending:number;blocked:number;sent:number;last_success:string|null}>();
  const [uploadError,setUploadError]=useState('');
  const [resultTrip,setResultTrip]=useState<Summary>();
  const [serverTrip,setServerTrip]=useState<ServerTrip>();
  const [tripError,setTripError]=useState('');
  const [feedbackPending,setFeedbackPending]=useState<FeedbackInput>();
  const [selectedTrip,setSelectedTrip]=useState<string>();
  const [evidence,setEvidence]=useState<Awaited<ReturnType<Storage['deliveryEvidence']>>>();
  useEffect(() => {
    let alive=true;
    void initialize().then(s=>{ if(!alive)return; setService(s); if(s.collector.trip?.status==='recording')setScreen(s.collector.collectionMode); s.collector.changed=()=>redraw(n=>n+1); }).catch(e=>setError(String(e)));
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
        const id=selectedTrip ?? service!.collector.trip?.trip_id ?? (await service!.db.list())[0]?.trip_id;
        const summary=id ? await service!.db.summary(id) : undefined;
        const status=await service!.db.deliveryStatus(id??null);
        const proof=await service!.db.deliveryEvidence(id??null);
        const remote=id ? await tripApi.result(id) : null;
        if(alive){setServerTrip(remote?.result);setFeedbackPending(remote?.feedback);setTripError(remote?.error??tripApi.error);}
        if(alive){setResultTrip(summary);setDelivery(status);setEvidence(proof);setUploadError(proof.head?.last_error || uploader.error);}
      }catch(e){if(alive)setError(String(e));}finally{refreshing=false;}
    }
    void tick(true);
    const timer=setInterval(()=>{if(AppState.currentState==='active')void tick();},3000);
    const app=AppState.addEventListener('change',state=>{if(state==='active')void tick(true);});
    const network=Network.addNetworkStateListener(state=>{if(state.isConnected && state.isInternetReachable!==false)void tick(true);});
    return ()=>{alive=false;clearInterval(timer);app.remove();network.remove();};
  },[service,selectedTrip]);
  useEffect(()=>{if(service && c?.phase!=='recording' && c?.phase!=='starting') void service.db.list().then(setTrips).catch(e=>setError(String(e)));},[service,c?.phase]);
  const trip=c?.trip; const seconds=trip ? Math.max(0,Math.floor(((trip.ended_at ? Date.parse(trip.ended_at) : trip.status==='recording' ? now : Date.parse(c?.latest?.received_at ?? trip.started_at))-Date.parse(trip.started_at))/1000)) : 0;
  const resultMatches=(selectedTrip?selectedTrip===resultTrip?.trip_id:(!trip || trip.trip_id===resultTrip?.trip_id)) && (resultTrip?.collection_mode??'developer')===screen;
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
  async function feedback(input:FeedbackInput) {
    if(!resultTrip)throw Error('Trip 결과가 없습니다.');
    const api=await getTripApi();
    try {setServerTrip(await api.sendFeedback(resultTrip.trip_id,input));setTripError('');}
    finally {
      const state=await api.result(resultTrip.trip_id);
      setFeedbackPending(state?.feedback);
      if(state?.result)setServerTrip(state.result);
      setTripError(state?.error??'');
    }
  }
  function history(offset=0) {
    const saved=trips.filter(t=>t.server&&t.status!=='recording'&&(t.collection_mode??'developer')===screen);
    Alert.alert('이전 이동 결과',saved.length?'이동을 선택하면 서버에서 최신 결과를 조회합니다.':'저장된 이동이 없습니다.',[
      ...saved.slice(offset,offset+5).map(t=>({text:new Date(t.started_at).toLocaleString('ko-KR'),onPress:()=>{
        setSelectedTrip(t.trip_id);setServerTrip(undefined);setFeedbackPending(undefined);setTripError('');
        void getTripApi().then(api=>api.refresh(t.trip_id)).then(setServerTrip).catch(e=>setTripError(String(e)));
      }})),
      ...(saved.length>offset+5?[{text:'이전 기록 더 보기',onPress:()=>history(offset+5)}]:[]),{text:'취소',style:'cancel'},
    ]);
  }
  if(screen===null) return <SafeAreaProvider><StatusBar barStyle="dark-content"/><EntryScreen ready={!!c} error={error}
    onEnter={mode=>{if(c){c.selectCollectionMode(mode);setError('');setUserSection('trip');setScreen(c.collectionMode);}}}/></SafeAreaProvider>;
  if(screen==='user'&&userSection!=='trip') return <SafeAreaProvider><StatusBar barStyle="dark-content"/>
    <MissionRankingScreen api={getEngagementApi()} initialTab={userSection} onBack={()=>setUserSection('trip')}/>
  </SafeAreaProvider>;
  return <SafeAreaProvider><StatusBar barStyle="dark-content"/><MeasurementScreen
    collectionMode={screen} onBack={()=>{if(c?.trip?.status!=='recording' && !['starting','recording','stopping'].includes(c?.phase??''))setScreen(null);}}
    ready={!!c} mode={c?.mode??null} phase={c?.phase??'idle'} count={c?.count??0} duration={duration}
    accuracy={c?.latest?.accuracy??null} latestLabel={c?.latest?.label} tripId={trip?.trip_id}
    error={error||c?.error||''} onMode={mode=>{void c?.selectMode(mode).catch(e=>setError(String(e)));}} onStart={()=>{setSelectedTrip(undefined);void c?.start();}}
    onStop={()=>{void c?.stop().catch(e=>setError(String(e)));}} canExport={trips.some(t=>t.status!=='recording')}
    sharing={sharing} onExport={()=>chooseExport()} active={trip?.status==='recording'} backgroundRunning={c?.backgroundRunning}
    lastReceived={c?.lastReceived} sequence={c?.latest?.sequence} pending={resultMatches?delivery?.pending:undefined} lastSuccess={resultMatches?delivery?.last_success:undefined}
    uploadError={uploadError} onResume={()=>{void c?.resume();}} onSettings={()=>{void Linking.openSettings();}}
    foregroundOnly={foregroundOnly} eventId={c?.latest?.event_id} eventTime={c?.latest?.event_time}
    confirmedEvent={resultMatches?evidence?.sent??undefined:undefined} retryCount={resultMatches?evidence?.head?.retry_count:undefined}
    resultTrip={resultMatches?resultTrip:undefined} sent={delivery?.sent} blocked={delivery?.blocked} onShareCheck={()=>{void shareCheck();}}
    canShareEvent={!!((resultMatches&&evidence?.sent)||c?.latest)} onShareEvent={()=>{void shareEvent();}}
    serverTrip={resultMatches && serverTrip?.trip_id===resultTrip?.trip_id?serverTrip:undefined} tripError={tripError}
    feedbackPending={feedbackPending} onFeedback={feedback} onHistory={()=>history()}
    onOpenMissions={()=>setUserSection('missions')} onOpenRanking={()=>setUserSection('ranking')}
    onRetryTrip={()=>{if(resultTrip)void getTripApi().then(api=>api.retry(resultTrip.trip_id)).catch(e=>setError(String(e)));}}
    onRetry={()=>{void service?.db.retryDelivery().then(async()=>{await (await getUploader()).tick();}).catch(e=>setError(String(e)));}}
    /></SafeAreaProvider>;
}
