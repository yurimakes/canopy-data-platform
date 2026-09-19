import React,{useEffect,useRef,useState} from 'react';
import Constants from 'expo-constants';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import {logoutProfile,updateProfile} from './src/profileStore';
import {session} from './src/accountSession';
import {accountConfig} from './src/accountConfig';
import {AuthScreen} from './src/ui/AuthScreen';
import {ServiceScreen} from './src/ui/ServiceScreen';
import {useCommunity,prepareJourney} from './src/communityClient';
import {SCHEMA,type GpsEvent,type Summary,type TransportMode} from './src/types';
import type {ServerTrip,FeedbackInput} from './src/tripApi';
import type {Profile,PlannedRoute} from './src/service';

export default function App(){
  const [profile,setProfile]=useState<Profile|null>(null),[route,setRoute]=useState<PlannedRoute|null>(null);
  const [collectionMode,setCollectionMode]=useState<'user'|'developer'>('user'),[mode,setMode]=useState<TransportMode|null>(null);
  const [phase,setPhase]=useState('idle'),[error,setError]=useState(''),[trips,setTrips]=useState<Summary[]>([]);
  const [selected,setSelected]=useState<Summary>(),[serverTrip,setServerTrip]=useState<ServerTrip>(),[events,setEvents]=useState<GpsEvent[]>([]);
  const [sent,setSent]=useState(0),[now,setNow]=useState(Date.now());
  const active=useRef<Summary|undefined>(undefined),points=useRef<GpsEvent[]>([]),ack=useRef(0),watch=useRef<number|undefined>(undefined);
  const flushing=useRef<Promise<void>|null>(null),selectedId=useRef('');
  const community=useCommunity(profile?.id);
  async function call(path:string,body?:unknown){
    if(!Constants.expoConfig?.extra?.localOnly)throw Error('Start-Local.cmd로 로컬 앱을 실행해주세요.');
    const saved=session();if(!saved)throw Error('다시 로그인해주세요.');
    const response=await fetch(accountConfig().url.replace(/\/$/,'')+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+saved.access_token,'x-functions-key':Constants.expoConfig?.extra?.gpsFunctionKey||''},...(body===undefined?{}:{body:JSON.stringify(body)})});
    const result=await response.json();if(!response.ok)throw Error(result.message??'요청 실패');return result;
  }
  function summary(t:ServerTrip):Summary{return {server:{api_url:accountConfig().url,request_id:t.trip_id},trip_id:t.trip_id,user_id:t.user_id,device_id:t.device_id,schema_version:SCHEMA,started_at:t.started_at,ended_at:t.ended_at,status:t.status==='collecting'?'recording':'completed',interruption_reason:null,recovered_at:null,foreground_only:true,collection_settings:{},environment:{platform:'web'},gps_count:0,first_event_time:null,last_event_time:null,last_saved_at:null,latest:null,collection_mode:collectionMode};}
  async function refreshHistory(){const r=await call('/trips');setTrips(r.trips.map(summary));}
  useEffect(()=>{if(!profile)return;void refreshHistory().catch(e=>setError(String(e)));const timer=setInterval(()=>{
    setNow(Date.now());if(selectedId.current)void call('/trips/'+selectedId.current).then(setServerTrip).catch(e=>setError(String(e)));
  },1500);return()=>clearInterval(timer);},[profile?.id]);
  useEffect(()=>()=>{if(watch.current!==undefined)navigator.geolocation.clearWatch(watch.current);},[]);
  async function flush(){
    if(flushing.current)return flushing.current;
    flushing.current=(async()=>{while(ack.current<points.current.length){await call('/gps',points.current[ack.current]);ack.current++;setSent(ack.current);}})();
    try{await flushing.current;}finally{flushing.current=null;}
  }
  function add(position:GeolocationPosition){
    const t=active.current;if(!t||position.timestamp<Date.parse(t.started_at))return;
    if(points.current.length&&position.timestamp<=Date.parse(points.current.at(-1)!.event_time))return;
    const c=position.coords;
    const row:GpsEvent={event_id:crypto.randomUUID(),trip_id:t.trip_id,user_id:t.user_id,device_id:t.device_id,schema_version:SCHEMA,sequence:points.current.length+1,event_time:new Date(position.timestamp).toISOString(),received_at:new Date().toISOString(),lat:c.latitude,lon:c.longitude,accuracy:c.accuracy,speed:c.speed,altitude_m:c.altitude,vertical_accuracy_m:c.altitudeAccuracy,course_deg:c.heading,source:'expo-location.foreground',quality_flags:[],label:collectionMode==='developer'?mode:null,collection_mode:collectionMode,raw_location:{timestamp:position.timestamp,coords:{latitude:c.latitude,longitude:c.longitude,accuracy:c.accuracy,altitude:c.altitude,altitudeAccuracy:c.altitudeAccuracy,heading:c.heading,speed:c.speed}}};
    points.current.push(row);setEvents([...points.current]);void flush().catch(e=>setError(String(e)));
  }
  function fresh():Promise<GeolocationPosition>{return new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,maximumAge:0,timeout:15000}));}
  async function start(){
    if(active.current)return;setError('');setPhase('starting');
    try{
      await prepareJourney(route?.quoteId);
      await fresh(); // 권한 확인 후 서버 여정 생성
      const device=localStorage.getItem('canopy.local.web-device')||crypto.randomUUID();localStorage.setItem('canopy.local.web-device',device);
      const t:ServerTrip=await call('/trips/start',{request_id:crypto.randomUUID(),device_id:device});
      active.current=summary(t);points.current=[];ack.current=0;setSent(0);setEvents([]);setSelected(active.current);setServerTrip(t);selectedId.current=t.trip_id;setPhase('recording');
      watch.current=navigator.geolocation.watchPosition(add,e=>setError(e.message),{enableHighAccuracy:true,maximumAge:0,timeout:15000});
    }catch(e){setError(String(e));setPhase(active.current?'recording':'idle');}
  }
  async function stop(){
    if(!active.current)return;setPhase('stopping');setError('');
    if(watch.current!==undefined)navigator.geolocation.clearWatch(watch.current);
    try{
      add(await fresh());await flush();if(ack.current!==points.current.length)throw Error('GPS 전송이 끝난 후 다시 종료해주세요.');
      if(points.current.length<2)throw Error('서로 다른 시각의 GPS가 최소 2개 필요합니다. 잠시 뒤 다시 종료해주세요.');
      const t:ServerTrip=await call('/trips/'+active.current.trip_id+'/stop',{expected_last_sequence:ack.current,ended_at:points.current.at(-1)!.event_time});
      setSelected({...active.current,status:'completed',ended_at:t.ended_at,gps_count:points.current.length});setServerTrip(t);active.current=undefined;setPhase('idle');await refreshHistory();
    }catch(e){setError(String(e));setPhase('recording');}
  }
  async function select(id:string){if(active.current)return;selectedId.current=id;const t=await call('/trips/'+id);setServerTrip(t);const rows=await call('/gps/'+id);setSelected({...summary(t),gps_count:rows.events.length});setEvents(rows.events);setSent(rows.events.length);}
  async function feedback(input:FeedbackInput){if(!selectedId.current)return;setServerTrip(await call('/trips/'+selectedId.current+'/feedback',{...input,request_id:crypto.randomUUID()}));}
  function download(){const url=URL.createObjectURL(new Blob([JSON.stringify({trip:selected,events},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=(selected?.trip_id||'trip')+'.json';a.click();URL.revokeObjectURL(url);}
  const duration=Math.max(0,Math.floor(((active.current?now:Date.parse(selected?.ended_at??'')||now)-Date.parse(selected?.started_at??''))/1000))||0;
  return <SafeAreaProvider style={{width:'100%',height:'100%',maxWidth:430,alignSelf:'center',marginHorizontal:'auto'}}>{!profile?<AuthScreen onEnter={p=>{setProfile(p);setCollectionMode(p.role==='developer'?'developer':'user');}}/>:
    <ServiceScreen {...community} profile={profile} onProfile={async p=>setProfile(await updateProfile(p))} route={route} onRoute={setRoute} trips={trips} events={events} onSelect={id=>void select(id).catch(e=>setError(String(e)))} collectionMode={collectionMode} onCollectionMode={setCollectionMode}
      onBack={()=>{if(active.current){setError('여정 종료 후 로그아웃해주세요.');return;}void logoutProfile().then(()=>{selectedId.current='';setProfile(null);setSelected(undefined);setServerTrip(undefined);setEvents([]);setTrips([]);setSent(0);setError('');setRoute(null);});}} mode={mode} phase={phase} active={!!active.current} ready={true} count={events.length} duration={`${Math.floor(duration/60)}:${String(duration%60).padStart(2,'0')}`} accuracy={events.at(-1)?.accuracy??null} error={error}
      onMode={setMode} onStart={()=>void start()} onStop={()=>void stop()} onExport={download} canExport={events.length>0} sharing={false} onFeedback={feedback} serverTrip={serverTrip} resultTrip={selected} tripId={selected?.trip_id} pending={Math.max(0,events.length-sent)} sent={sent} foregroundOnly/>
  }</SafeAreaProvider>;
}
