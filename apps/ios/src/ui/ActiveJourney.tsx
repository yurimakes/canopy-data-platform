import Text from './AppText';
import Constants from 'expo-constants';
import React,{useEffect,useState} from 'react';
import {Pressable,View,LayoutAnimation} from 'react-native';
import {CanopyMascot} from './CanopyMascot';
import JourneyMap from './JourneyMap';
import {PopulationPreview} from './PopulationPreview';
import {journeyProgress,metersBetween} from '../journeyGeometry';
import {localAction} from '../communityClient';
import {gpsDistance,km} from '../service';
import {liveMotionLabel,liveSpeedKmh} from '../liveMotion';
import {MODES} from '../types';
import type {ServiceProps} from './ServiceScreen';
import {C,S,Note,Icon} from './theme';
export function ActiveJourney({p,direction,replayDistance,replayMode}:{replayDistance?:number;replayMode?:string;p:Pick<ServiceProps,'active'|'events'|'route'|'duration'|'tripId'|'baseline'>;direction:'outbound'|'return'}){
 const [expanded,setExpanded]=useState(true),[prediction,setPrediction]=useState<{mode:string;observed_at:string}|null>(null);
 const [now,setNow]=useState(Date.now());
 useEffect(()=>{if(!p.active)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[p.active]);
 useEffect(()=>{setExpanded(true);},[p.tripId]);
 const speed=p.active?liveSpeedKmh(p.events,now):null;
 const speedText=speed==null?'수신 대기':`${speed.toFixed(1)} km/h`;
 const freshPrediction=prediction&&now-Date.parse(prediction.observed_at)<=30000&&now-Date.parse(prediction.observed_at)>=-5000;
 const mode=freshPrediction?(MODES.find(m=>m.value===prediction.mode)?.title??'이동 감지 중')+' (분석 중)':speed==null?'위치 수신 대기':liveMotionLabel(p.events);
 const busy=!!p.active,points=p.events.map(e=>({latitude:e.lat,longitude:e.lon,name:'현재 위치'}));
 const last=points.at(-1),progress=journeyProgress(p.route,busy?last:undefined),distance=busy?(replayDistance??gpsDistance(p.events)):0;
 useEffect(()=>{
  let alive=true,timer:ReturnType<typeof setTimeout>|undefined;setPrediction(null);
  if(!busy||!p.tripId)return;
  const local=!!Constants.expoConfig?.extra?.localOnly;
  const refresh=async()=>{
   try{const v=await localAction((local?'/predictions/':'/trips/')+p.tripId);if(alive)setPrediction(local&&v.mode?{mode:v.mode,observed_at:v.observed_at??new Date().toISOString()}:v.live_prediction??null);}
   catch{if(alive)setPrediction(null);}
   finally{if(alive)timer=setTimeout(refresh,3000);}
  };
  void refresh();return()=>{alive=false;if(timer)clearTimeout(timer);};
 },[p.tripId,busy]);
 return <View style={{gap:0,...(busy?{flex:1,minHeight:0,overflow:'hidden'}:{})}}>
  <View style={{flexShrink:0,padding:12,paddingBottom:10,backgroundColor:C.white,borderTopLeftRadius:28,borderTopRightRadius:28,zIndex:1}}>
   <View style={S.between}><Text style={{fontSize:11,letterSpacing:1.3,fontWeight:'700',color:C.green}}>{direction==='return'?'ON MY WAY HOME':'MY GREEN COMMUTE'}</Text><Text style={S.pill}>{busy?'이동 중':'출발 준비'}</Text></View>
   <View style={{height: 64,marginHorizontal:18,justifyContent:'flex-end',paddingBottom:12}}>
    <View style={{height:5,backgroundColor:'#e6ede4',borderRadius:5}}><View style={{height:5,width:`${progress*100}%`,backgroundColor:C.green,borderRadius:5}}/></View>
    <View style={{position:'absolute',left:`${progress*100}%`,bottom:4,width:58,height:58,marginLeft:-29}}><CanopyMascot pose={busy?'walk':'start'} height={58} animated={busy}/></View>
   </View>
   <View style={S.between}><View style={{maxWidth:'46%',flexDirection:'row',alignItems:'center',gap:6}}><Icon name={direction==='return'?'business-outline':'home-outline'} size={20}/><Text numberOfLines={1} style={[S.label,{flexShrink:1,fontSize:12}]}>{p.route?.from.name??'출발지'}</Text></View><View style={{maxWidth:'46%',flexDirection:'row',alignItems:'center',gap:6}}><Icon name={direction==='return'?'home-outline':'business-outline'} size={20}/><Text numberOfLines={1} style={[S.label,{flexShrink:1,fontSize:12}]}>{p.route?.to.name??'자유 여정'}</Text></View></View>
   <Text style={[S.note,{textAlign:'center',marginTop:10,fontSize:11}]}>{!p.route?'목적지 없이 자유롭게 기록해요':busy&&last?`목적지까지 직선거리 ${km(metersBetween(last,p.route.to))} · 약 ${Math.round(progress*100)}% 접근`:'위치를 받으면 목적지까지의 진행 상황이 표시돼요'}</Text>
  </View>
  {!busy&&(p.route?<PopulationPreview route={p.route} baseline={p.baseline}/>:<View style={{padding:16}}><Note>자유 여정은 출발·도착지를 아직 알 수 없어 KTDB 기준을 미리 계산할 수 없어요. 출발 전에 기준을 보려면 경로를 선택해주세요.</Note></View>)}

  <View style={{overflow:'hidden',...(busy?{flex:1,flexBasis:0,minHeight:0}:{height:300})}}><View style={{position:'absolute',inset:0}}><JourneyMap points={busy?points:[]} route={p.route} fill/></View></View>
  <View style={{flexShrink:0,zIndex:5,elevation:5,backgroundColor:C.white,borderRadius:28,paddingHorizontal:20,paddingBottom:expanded?12:8,boxShadow:'0 -6px 28px #183d3510'}}>
   <Pressable testID="journey-info-toggle" accessibilityRole="button" accessibilityLabel={expanded?'이동 정보 접기':'이동 정보 펼치기'} accessibilityState={{expanded}} onPress={()=>{LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);setExpanded(value=>!value);}} style={{minHeight:48,justifyContent:'center',paddingVertical:8,gap:6}}>
    <View style={S.between}><Text style={{fontSize:13,fontWeight:'700',color:C.green}}>이동 정보</Text><View style={{flexDirection:'row',alignItems:'center',gap:4}}><Text style={{fontSize:13,fontWeight:'700',color:C.green}}>{expanded?'접기':'펼치기'}</Text><Icon name={expanded?'chevron-down':'chevron-up'} size={18}/></View></View>
    {!expanded&&<View style={{gap:3}}><Text style={{fontSize:13,color:C.ink}}>{p.duration} · {km(distance)} · {speedText}</Text><Text style={{fontSize:12,color:C.green}}>{busy?(replayMode??mode):'출발 전'}</Text></View>}
   </Pressable>
   {expanded&&<View style={{gap:10}}><View style={S.between}><View style={{flex:1}}><Text style={S.note}>이동 시간</Text><Text style={[S.metric,{fontSize:27}]}>{busy?p.duration.replace(/^(\d+):(\d+)$/, '$1분 $2초'):'0분 00초'}</Text></View><View style={{flex:1,borderLeftWidth:1,borderColor:C.line,paddingLeft:20}}><Text style={S.note}>이동 거리</Text><Text style={[S.metric,{fontSize:27}]}>{km(distance)}</Text></View></View><View style={[S.between,{gap:8}]}><Text style={S.label}>현재 속도</Text><Text testID="journey-live-speed" style={[S.metric,{fontSize:24,flexShrink:1}]}>{speedText}</Text></View><View style={[S.between,{backgroundColor:'#f2f6ee',borderRadius:18,padding:12}]}><Text style={S.label}>현재 이동수단</Text><Text style={{color:C.green,fontWeight:'800',flexShrink:1,textAlign:'right'}}>{busy?(replayMode??mode):'출발 전'}</Text></View><Note>속도·거리는 GPS 추정값이에요. 위치가 오래 갱신되지 않으면 속도는 수신 대기로 표시돼요.</Note></View>}
  </View>

 </View>;
}
