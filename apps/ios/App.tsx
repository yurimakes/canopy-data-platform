import React, { useEffect, useState, useRef } from 'react';
import { Alert, AppState, StatusBar, Linking } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import * as Network from 'expo-network';
import { getStorage, getUploader, getTripApi } from './src/backgroundLocationTask';
import { AuthScreen } from './src/ui/AuthScreen';
import { ServiceScreen } from './src/ui/ServiceScreen';
import { updateProfile,restoreProfile,logoutProfile } from './src/profileStore';
import type { Profile, PlannedRoute } from './src/service';
import { Collector } from './src/collector';
import { Storage } from './src/storage';
import { ports, foregroundOnly } from './src/location';
import { files } from './src/files';
import { exportTrip } from './src/exporter';
import type { Summary, GpsEvent } from './src/types';
import type { FeedbackInput, ServerTrip } from './src/tripApi';
import { loadRanking } from './src/rankingClient';
import type { RemotePanel, RankingView } from './src/ui/CommunityPanels';
let runtime: Promise<{db:Storage; collector:Collector}> | undefined;
function initialize() { return runtime ??= (async () => {
  const db = await getStorage();
  const identity = await db.identity();
  const collector=new Collector(db,identity,{...ports,startTrip:async identity=>{
    const remote=await ports.startTrip(identity);
    // 서버 Trip ID가 정해진 직후 UI 소유 프로필 저장. GPS 시작 도중 종료돼도 여정 목록 복구
    const context=await db.syncValue<{profile_id:string;route:PlannedRoute|null}>('ui:pending-journey');
    if(context){await db.saveSync('ui:trip:'+remote.trip_id,context);await db.saveSync('ui:pending-journey',null);}
    return remote;
  }}); await collector.refresh();
  return {db, collector};
})(); }
export default function App() {
  const [service,setService]=useState<Awaited<ReturnType<typeof initialize>>>();
  const [,redraw]=useState(0); const [trips,setTrips]=useState<Summary[]>([]);
  const [profile,setProfile]=useState<Profile|null>(null);
  const [ranking,setRanking]=useState<RemotePanel<RankingView>>({state:'unavailable'});
  const [entered,setEntered]=useState(false);
  const [route,setRoute]=useState<PlannedRoute|null>(null);
  const trackRef=useRef<{id:string;events:GpsEvent[]}>({id:'',events:[]});
  const [events,setEvents]=useState<GpsEvent[]>([]);
  const [ownedTrips,setOwnedTrips]=useState<Summary[]>([]);
  const [screen,setScreen]=useState<'user'|'developer'|null>(null);
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
    void initialize().then(async s=>{
      if(!alive)return;setService(s);s.collector.changed=()=>redraw(n=>n+1);
      const saved=await restoreProfile();if(!alive)return;
      if(saved){
        setProfile(saved);
        const active=s.collector.trip;
        if(active?.status==='recording'&&active.user_id===saved.id){setScreen(s.collector.collectionMode);setEntered(true);}
        else {const mode=saved.role==='developer'?'developer':'user';s.collector.selectCollectionMode(mode);setScreen(mode);}
        if(active?.user_id===saved.id){const meta=await s.db.syncValue<{route:PlannedRoute|null}>('ui:trip:'+active.trip_id);if(alive)setRoute(meta?.route??null);}
      }
    }).catch(e=>setError(String(e)));
    const timer=setInterval(()=>setNow(Date.now()),1000);
    const sub=AppState.addEventListener('change',state=>{void runtime?.then(s=>s.collector.appStateChanged(state));});
    return ()=>{alive=false;clearInterval(timer);sub.remove();void runtime?.then(s=>{s.collector.changed=()=>{};void s.collector.interrupt('화면 종료');});};
  },[]);
  useEffect(()=>{
    let alive=true;
    if(!entered||!profile){setRanking({state:'unavailable'});return ()=>{alive=false};}
    setRanking({state:'loading'});
    void loadRanking(profile.id).then(value=>{if(alive)setRanking(value);}).catch(()=>{if(alive)setRanking({state:'error',message:'랭킹을 불러오지 못했습니다.'});});
    return ()=>{alive=false};
  },[entered,profile?.id]);
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
        const list=await service!.db.list();
        const owned=list.filter(t=>t.user_id===profile?.id);
        const activeId=service!.collector.trip?.user_id===profile?.id?service!.collector.trip?.trip_id:undefined;
        const id=selectedTrip ?? activeId ?? owned[0]?.trip_id;
        const summary=id ? await service!.db.summary(id) : undefined;
        if(trackRef.current.id!==(id??''))trackRef.current={id:id??'',events:[]};
        const previous=trackRef.current.events;
        const extra=id?await service!.db.eventPage(id,previous.at(-1)?.sequence??0,2000):[];
        const track=extra.length?[...previous,...extra]:previous;trackRef.current.events=track;
        if(alive){setTrips(list);setOwnedTrips(owned);setEvents(track);}
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
  },[service,selectedTrip,profile?.id]);
  useEffect(()=>{if(service && c?.phase!=='recording' && c?.phase!=='starting') void service.db.list().then(setTrips).catch(e=>setError(String(e)));},[service,c?.phase]);
  const ownsCurrent=!!profile&&c?.trip?.user_id===profile.id;
  const latest=ownsCurrent?c?.latest:undefined;
  const trip=ownsCurrent?c?.trip:undefined; const seconds=trip ? Math.max(0,Math.floor(((trip.ended_at ? Date.parse(trip.ended_at) : trip.status==='recording' ? now : Date.parse(c?.latest?.received_at ?? trip.started_at))-Date.parse(trip.started_at))/1000)) : 0;
  const resultMatches=ownedTrips.some(t=>t.trip_id===resultTrip?.trip_id) && (selectedTrip?selectedTrip===resultTrip?.trip_id:(!trip || trip.trip_id===resultTrip?.trip_id)) && (resultTrip?.collection_mode??'developer')===screen;
  const duration=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
  function refreshRanking(){
    if(!profile)return;
    setRanking({state:'loading'});
    void loadRanking(profile.id).then(setRanking).catch(()=>setRanking({state:'error',message:'랭킹을 불러오지 못했습니다.'}));
  }
  async function share(id:string) {
    if(!service||sharing)return;setSharing(true);setError('');
    try{await exportTrip(service.db,files,id,'gps',ports.now());}catch(e){setError('내보내기 오류: '+String(e));}finally{setSharing(false);}
  }
  function chooseExport(offset=0) {
    // A native selection dialog keeps older recordings accessible without another page.
    const saved=ownedTrips.filter(t=>t.status!=='recording');
    Alert.alert('GPS JSONL 내보내기','저장된 측정을 선택하세요.',[
      ...saved.slice(offset,offset+5).map(t=>({text:new Date(t.started_at).toLocaleString('ko-KR')+' / '+t.gps_count+'개',onPress:()=>void share(t.trip_id)})),
      ...(saved.length>offset+5 ? [{text:'이전 기록 더 보기',onPress:()=>chooseExport(offset+5)}] : []),
      {text:'취소',style:'cancel'},
    ]);
  }
  async function shareEvent() {
    const event=(resultMatches?evidence?.sent:null) ?? latest;
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
    const saved=ownedTrips.filter(t=>t.server&&t.status!=='recording'&&(t.collection_mode??'developer')===screen);
    Alert.alert('이전 이동 결과',saved.length?'이동을 선택하면 서버에서 최신 결과를 조회합니다.':'저장된 이동이 없습니다.',[
      ...saved.slice(offset,offset+5).map(t=>({text:new Date(t.started_at).toLocaleString('ko-KR'),onPress:()=>{
        setSelectedTrip(t.trip_id);setServerTrip(undefined);setFeedbackPending(undefined);setTripError('');
        void getTripApi().then(api=>api.refresh(t.trip_id)).then(setServerTrip).catch(e=>setTripError(String(e)));
      }})),
      ...(saved.length>offset+5?[{text:'이전 기록 더 보기',onPress:()=>history(offset+5)}]:[]),{text:'취소',style:'cancel'},
    ]);
  }
  async function enter(p:Profile) {
    if(!service)return;
    const verified=await restoreProfile();
    if(!verified||verified.id!==p.id)throw Error('다시 로그인해주세요.');
    p=verified;
    if(c?.trip?.status==='recording'&&c.trip.user_id!==p.id)throw Error('측정 중인 계정으로 먼저 로그인해주세요.');
    await service.db.saveSync('ui:session',p);setProfile(p);
    if(c?.trip?.status!=='recording')c?.selectCollectionMode(p.role==='developer'?'developer':'user');
    setError('');setScreen(c?.collectionMode??'user');setEntered(true);
  }
  async function changeProfile(p:Profile){const saved=await updateProfile(p);await service?.db.saveSync('ui:session',saved);setProfile(saved);}
  async function startJourney(){
    if(!service||!c||!profile||['starting','recording','stopping'].includes(c.phase)||c.trip?.status==='recording')return;
    setError('');setTripError('');setSelectedTrip(undefined);setServerTrip(undefined);setResultTrip(undefined);setEvents([]);
    await service.db.saveSync('ui:pending-journey',{profile_id:profile.id,route});
    await c?.start();
  }
  function select(id:string){
    if(!ownedTrips.some(t=>t.trip_id===id))return;
    setSelectedTrip(id);setServerTrip(undefined);setResultTrip(undefined);setFeedbackPending(undefined);setTripError('');
    void service?.db.syncValue<{route:PlannedRoute|null}>('ui:trip:'+id).then(v=>setRoute(v?.route??null));
    void getTripApi().then(api=>api.refresh(id)).then(setServerTrip).catch(e=>setTripError(String(e)));
  }
  if(!entered||!profile||screen===null) return <SafeAreaProvider><StatusBar barStyle="dark-content"/><AuthScreen ready={!!c} error={error} savedProfile={profile} onContinue={()=>{if(profile)void enter(profile).catch(e=>setError(String(e)));}}
    onEnter={p=>{void enter(p).catch(e=>setError(String(e)));}}/></SafeAreaProvider>;
  return <SafeAreaProvider><StatusBar barStyle="dark-content"/><ServiceScreen key={profile.id}
    profile={profile} onProfile={changeProfile} route={route} onRoute={setRoute} events={events}
    trips={ownedTrips} onSelect={select} ranking={ranking} onRefreshCommunity={refreshRanking}
    onCollectionMode={mode=>{if(mode==='developer'&&profile.role!=='developer')return;c?.selectCollectionMode(mode);setScreen(c?.collectionMode??mode);}}
    collectionMode={screen} onBack={()=>{if(c?.trip?.status!=='recording' && !['starting','recording','stopping'].includes(c?.phase??''))void logoutProfile().then(()=>service?.db.saveSync('ui:session',null)).then(()=>{setProfile(null);setScreen(null);setEntered(false);setSelectedTrip(undefined);setRoute(null);setEvents([]);setOwnedTrips([]);}).catch(e=>setError(String(e))); }}
    ready={!!c} mode={c?.mode??null} phase={c?.phase??'idle'} count={ownsCurrent?c?.count??0:0} duration={duration}
    accuracy={latest?.accuracy??null} latestLabel={latest?.label} tripId={trip?.trip_id}
    error={error||c?.error||''} onMode={mode=>{void c?.selectMode(mode).catch(e=>setError(String(e)));}} onStart={()=>{void startJourney().catch(e=>setError(String(e)));}}
    onStop={()=>{void c?.stop().catch(e=>setError(String(e)));}} canExport={ownedTrips.some(t=>t.status!=='recording')}
    sharing={sharing} onExport={()=>chooseExport()} active={trip?.status==='recording'} backgroundRunning={c?.backgroundRunning}
    lastReceived={ownsCurrent?c?.lastReceived:undefined} sequence={latest?.sequence} pending={resultMatches?delivery?.pending:undefined} lastSuccess={resultMatches?delivery?.last_success:undefined}
    uploadError={uploadError} onResume={()=>{void c?.resume();}} onSettings={()=>{void Linking.openSettings();}}
    foregroundOnly={foregroundOnly} eventId={latest?.event_id} eventTime={latest?.event_time}
    confirmedEvent={resultMatches?evidence?.sent??undefined:undefined} retryCount={resultMatches?evidence?.head?.retry_count:undefined}
    resultTrip={resultMatches?resultTrip:undefined} sent={delivery?.sent} blocked={delivery?.blocked} onShareCheck={()=>{void shareCheck();}}
    canShareEvent={!!((resultMatches&&evidence?.sent)||latest)} onShareEvent={()=>{void shareEvent();}}
    serverTrip={resultMatches && serverTrip?.trip_id===resultTrip?.trip_id?serverTrip:undefined} tripError={tripError}
    feedbackPending={feedbackPending} onFeedback={feedback} onHistory={()=>history()}
    onRetryTrip={()=>{if(resultTrip)void getTripApi().then(api=>api.retry(resultTrip.trip_id)).catch(e=>setError(String(e)));}}
    onRetry={()=>{void service?.db.retryDelivery().then(async()=>{await (await getUploader()).tick();}).catch(e=>setError(String(e)));}}
    /></SafeAreaProvider>;
}
