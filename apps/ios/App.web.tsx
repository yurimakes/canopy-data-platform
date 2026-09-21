import {FontGate} from './src/ui/FontGate';
import {locationError} from './src/locationError';
import React,{useEffect,useRef,useState} from 'react';
import Constants from 'expo-constants';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import {logoutProfile,updateProfile} from './src/profileStore';
import {session} from './src/accountSession';
import {accountConfig} from './src/accountConfig';
import {AuthScreen} from './src/ui/AuthScreen';
import {ServiceScreen} from './src/ui/ServiceScreen';
import {useCommunity,prepareJourney,localAction} from './src/communityClient';
import {SCHEMA,type GpsEvent,type Summary,type TransportMode} from './src/types';
import type {ServerTrip,FeedbackInput} from './src/tripApi';
import type {Profile,PlannedRoute} from './src/service';
import {webJourneyStore} from './src/webJourneyStore';

function CanopyApp(){
  const [profile,setProfile]=useState<Profile|null>(null),[route,setRoute]=useState<PlannedRoute|null>(null);
  const [collectionMode,setCollectionMode]=useState<'user'|'developer'>('user'),[mode,setMode]=useState<TransportMode|null>(null);
  const [phase,setPhase]=useState('idle'),[error,setError]=useState(''),[trips,setTrips]=useState<Summary[]>([]);
  const [selected,setSelected]=useState<Summary>(),[serverTrip,setServerTrip]=useState<ServerTrip>(),[events,setEvents]=useState<GpsEvent[]>([]);
  const [sent,setSent]=useState(0),[now,setNow]=useState(Date.now());
  const active=useRef<Summary|undefined>(undefined),points=useRef<GpsEvent[]>([]),ack=useRef(0),watch=useRef<number|undefined>(undefined);
  const flushing=useRef<Promise<void>|null>(null),selectedId=useRef('');
  const transitioning=useRef(false),recovering=useRef(false);
  const stopIntent=useRef<{ended_at:string;expected_last_sequence:number}|undefined>(undefined);
  function savedJourney(){if(!profile)throw Error('다시 로그인해주세요.');return webJourneyStore(localStorage,accountConfig().url,profile.id);}
  function persist(){if(active.current)savedJourney().write({trip:active.current,points:points.current,ack:ack.current,stop:stopIntent.current});}
  function unwatch(){if(watch.current!==undefined)navigator.geolocation.clearWatch(watch.current);watch.current=undefined;}
  function watchPosition(){unwatch();watch.current=navigator.geolocation.watchPosition(add,e=>setError(locationError(e)),{enableHighAccuracy:true,maximumAge:0,timeout:15000});}
  const community=useCommunity(profile?.id);
  async function call(path:string,body?:unknown){
    if(!Constants.expoConfig?.extra?.localOnly)throw Error('Start-Local.cmd로 로컬 앱을 실행해주세요.');
    return localAction(path,body);
  }
  function summary(t:ServerTrip):Summary{return {server:{api_url:accountConfig().url,request_id:t.trip_id},trip_id:t.trip_id,user_id:t.user_id,device_id:t.device_id,schema_version:SCHEMA,started_at:t.started_at,ended_at:t.ended_at,status:t.status==='collecting'?'recording':'completed',interruption_reason:null,recovered_at:null,foreground_only:true,collection_settings:{},environment:{platform:'web'},gps_count:0,first_event_time:null,last_event_time:null,last_saved_at:null,latest:null,collection_mode:collectionMode};}
  async function refreshHistory(){const r=await call('/trips');setTrips(r.trips.map(summary));}
  useEffect(()=>{if(!profile)return;void refreshHistory().catch(e=>setError(String(e)));const timer=setInterval(()=>{
    setNow(Date.now());const id=selectedId.current;if(id)void call('/trips/'+id).then(t=>{if(selectedId.current===id)setServerTrip(t);}).catch(e=>setError(String(e)));
  },1500);return()=>clearInterval(timer);},[profile?.id]);
  useEffect(()=>()=>{if(watch.current!==undefined)navigator.geolocation.clearWatch(watch.current);},[]);
  useEffect(()=>{if(!profile)return;let cancelled=false;recovering.current=true;
    void (async()=>{const saved=savedJourney().read();if(!saved)return;
      const t:ServerTrip=await call('/trips/'+saved.trip.trip_id);if(cancelled)return;
      points.current=saved.points;ack.current=saved.ack;stopIntent.current=saved.stop;setEvents(saved.points);setSent(saved.ack);setSelected(saved.trip);selectedId.current=t.trip_id;setServerTrip(t);
      if(t.status==='collecting'){active.current=saved.trip;setPhase(saved.stop?'interrupted':'recording');if(saved.stop)setError('이전 종료 요청을 다시 전송해야 합니다. 여정 종료를 눌러주세요.');else watchPosition();await flush();}
      else{savedJourney().clear();setSelected({...saved.trip,status:'completed',ended_at:t.ended_at});}
    })().catch(e=>setError(String(e))).finally(()=>{if(!cancelled)recovering.current=false;});
    return()=>{cancelled=true;unwatch();};
  },[profile?.id]);
  async function flush(){
    if(flushing.current)return flushing.current;
    flushing.current=(async()=>{while(ack.current<points.current.length){await call('/gps',points.current[ack.current]);ack.current++;persist();setSent(ack.current);}})();
    try{await flushing.current;}finally{flushing.current=null;}
  }
  function add(position:GeolocationPosition){
    const t=active.current;if(!t||position.timestamp<Date.parse(t.started_at))return;
    if(points.current.length&&position.timestamp<=Date.parse(points.current.at(-1)!.event_time))return;
    const c=position.coords;
    const row:GpsEvent={event_id:crypto.randomUUID(),trip_id:t.trip_id,user_id:t.user_id,device_id:t.device_id,schema_version:SCHEMA,sequence:points.current.length+1,event_time:new Date(position.timestamp).toISOString(),received_at:new Date().toISOString(),lat:c.latitude,lon:c.longitude,accuracy:c.accuracy,speed:c.speed,altitude_m:c.altitude,vertical_accuracy_m:c.altitudeAccuracy,course_deg:c.heading,source:'expo-location.foreground',quality_flags:[],label:collectionMode==='developer'?mode:null,collection_mode:collectionMode,raw_location:{timestamp:position.timestamp,coords:{latitude:c.latitude,longitude:c.longitude,accuracy:c.accuracy,altitude:c.altitude,altitudeAccuracy:c.altitudeAccuracy,heading:c.heading,speed:c.speed}}};
    points.current.push(row);try{persist();}catch{unwatch();setError('기기 저장 공간이 부족해 위치 수집을 멈췄어요. 이 창을 닫지 말고 전송을 다시 시도해주세요.');}
    setEvents([...points.current]);void flush().catch(e=>setError(String(e)));
  }
  function fresh():Promise<GeolocationPosition>{return new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,maximumAge:0,timeout:15000}));}
  async function start(direction:'outbound'|'return'='outbound'){
    if(active.current||transitioning.current||recovering.current)return;transitioning.current=true;setError('');setPhase('starting');
    try{
      if(savedJourney().read())throw Error('저장된 진행 여정이 있어요. 연결을 확인한 뒤 새로고침하여 복구해주세요.');
      await prepareJourney(route?.quoteId,direction);
      await fresh(); // 권한 확인 후 서버 여정 생성
      const device=localStorage.getItem('canopy.local.web-device')||crypto.randomUUID();localStorage.setItem('canopy.local.web-device',device);
      const t:ServerTrip=await call('/trips/start',{request_id:savedJourney().startId(()=>crypto.randomUUID()),device_id:device});
      active.current=summary(t);points.current=[];ack.current=0;setSent(0);setEvents([]);setSelected(active.current);setServerTrip(t);selectedId.current=t.trip_id;setPhase('recording');
      stopIntent.current=undefined;persist();savedJourney().started();watchPosition();
    }catch(e){setError(locationError(e));setPhase(active.current?'recording':'idle');}finally{transitioning.current=false;}
  }
  async function stop(){
    if(!active.current||transitioning.current)return;transitioning.current=true;setPhase('stopping');setError('');
    unwatch();
    try{
      if(!stopIntent.current)add(await fresh());await flush();if(ack.current!==points.current.length)throw Error('GPS 전송이 끝난 후 다시 종료해주세요.');
      if(points.current.length<2)throw Error('서로 다른 시각의 GPS가 최소 2개 필요합니다. 잠시 뒤 다시 종료해주세요.');
      stopIntent.current=stopIntent.current??{expected_last_sequence:ack.current,ended_at:points.current.at(-1)!.event_time};persist();
      const t:ServerTrip=await call('/trips/'+active.current.trip_id+'/stop',stopIntent.current);
      setSelected({...active.current,status:'completed',ended_at:t.ended_at,gps_count:points.current.length});setServerTrip(t);savedJourney().clear();active.current=undefined;setPhase('idle');await refreshHistory();
    }catch(e){setError(String(e));if(active.current){setPhase(stopIntent.current?'interrupted':'recording');if(!stopIntent.current)watchPosition();}}finally{transitioning.current=false;}
  }
  async function select(id:string){if(active.current)return;selectedId.current=id;setServerTrip(undefined);setSelected(trips.find(t=>t.trip_id===id));setEvents([]);setSent(0);setError('');const t=await call('/trips/'+id);if(selectedId.current!==id)return;setServerTrip(t);const rows=await call('/gps/'+id);if(selectedId.current!==id)return;setSelected({...summary(t),gps_count:rows.events.length});setEvents(rows.events);setSent(rows.events.length);}
  async function retryTrip(){const id=selectedId.current;if(!id)return;try{setError('');const t=await call('/trips/'+id);if(t.status==='failed')await call('/trips/'+id+'/stop',{retry:true,retry_request_id:crypto.randomUUID(),expected_last_sequence:t.expected_last_sequence,ended_at:t.ended_at});await select(id);}catch(e){setError(String(e));}}
  async function feedback(input:FeedbackInput){if(!selectedId.current)return;setServerTrip(await call('/trips/'+selectedId.current+'/feedback',{...input,request_id:crypto.randomUUID()}));}
  function download(){const url=URL.createObjectURL(new Blob([JSON.stringify({trip:selected,events},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=(selected?.trip_id||'trip')+'.json';a.click();URL.revokeObjectURL(url);}
  const duration=Math.max(0,Math.floor(((active.current?now:Date.parse(selected?.ended_at??'')||now)-Date.parse(selected?.started_at??''))/1000))||0;
  return <SafeAreaProvider style={{width:'100%',height:'100%',maxWidth:430,alignSelf:'center',marginHorizontal:'auto'}}>{!profile?<AuthScreen onEnter={p=>{setProfile(p);setCollectionMode(p.role==='developer'?'developer':'user');}}/>:
    <ServiceScreen {...community} profile={profile} onProfile={async p=>setProfile(await updateProfile(p))} route={route} onRoute={setRoute} trips={trips} events={events} onSelect={id=>void select(id).catch(e=>setError(String(e)))} collectionMode={collectionMode} onCollectionMode={setCollectionMode}
      onBack={()=>{if(active.current){setError('여정 종료 후 로그아웃해주세요.');return;}void logoutProfile().then(()=>{selectedId.current='';setProfile(null);setSelected(undefined);setServerTrip(undefined);setEvents([]);setTrips([]);setSent(0);setError('');setRoute(null);});}} mode={mode} phase={phase} active={!!active.current} ready={true} count={events.length} duration={`${Math.floor(duration/60)}:${String(duration%60).padStart(2,'0')}`} accuracy={events.at(-1)?.accuracy??null} error={error}
      onRetry={()=>void flush().catch(e=>setError(String(e)))} onRetryTrip={()=>void retryTrip()}
      onSettings={()=>setError('브라우저 주소창의 사이트 설정에서 위치 권한을 허용한 뒤 다시 시도해주세요.')}
      onMode={setMode} onStart={direction=>void start(direction)} onStop={()=>void stop()} onExport={download} canExport={events.length>0} sharing={false} onFeedback={feedback} serverTrip={serverTrip} resultTrip={selected} tripId={selected?.trip_id} pending={Math.max(0,events.length-sent)} sent={sent} foregroundOnly/>
  }</SafeAreaProvider>;
}

export default function App(){return <FontGate><CanopyApp/></FontGate>;}
