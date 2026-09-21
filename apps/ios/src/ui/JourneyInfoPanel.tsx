import Text from './AppText';
import Constants from 'expo-constants';
import React,{useEffect,useState} from 'react';
import {Pressable,ScrollView,View,useWindowDimensions} from 'react-native';
import {localAction} from '../communityClient';
import {gpsDistance,km} from '../service';
import {liveMotionLabel,liveSpeedKmh} from '../liveMotion';
import {MODES} from '../types';
import type {ServiceProps} from './ServiceScreen';
import {C,S,Note,Icon} from './theme';
export type JourneyInfoProps={replayDistance?:number;replayMode?:string;p:Pick<ServiceProps,'active'|'events'|'duration'|'tripId'>};
// Keep this panel outside the clipped map viewport. Its toggle must never scroll away.
export function JourneyInfoPanel({p,replayDistance,replayMode}:JourneyInfoProps){
 const [expanded,setExpanded]=useState(true),[prediction,setPrediction]=useState<{mode:string;observed_at:string}|null>(null);
 const [now,setNow]=useState(Date.now());
 useEffect(()=>{if(!p.active)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[p.active]);
 useEffect(()=>{setExpanded(true);},[p.tripId]);
 const speed=p.active?liveSpeedKmh(p.events,now):null;
 const speedText=speed==null?'수신 대기':`${speed.toFixed(1)} km/h`;
 const freshPrediction=prediction&&now-Date.parse(prediction.observed_at)<=30000&&now-Date.parse(prediction.observed_at)>=-5000;
 const mode=freshPrediction?(MODES.find(m=>m.value===prediction.mode)?.title??'이동 감지 중')+' (분석 중)':speed==null?'위치 수신 대기':liveMotionLabel(p.events);
 const busy=!!p.active,distance=busy?(replayDistance??gpsDistance(p.events)):0;
 const {height}=useWindowDimensions();
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
 return <View style={{flexShrink:0,zIndex:5,elevation:5,backgroundColor:C.white,borderRadius:28,paddingHorizontal:20,paddingBottom:expanded?12:8,boxShadow:'0 -6px 28px #183d3510'}}>
   <Pressable testID="journey-info-toggle" accessibilityRole="button" accessibilityLabel={expanded?'이동 정보 접기':'이동 정보 펼치기'} accessibilityState={{expanded}} onPress={()=>{setExpanded(value=>!value);}} style={{minHeight:48,justifyContent:'center',paddingVertical:8,gap:6}}>
    <View style={S.between}><Text style={{fontSize:13,fontWeight:'700',color:C.green}}>이동 정보</Text><View style={{flexDirection:'row',alignItems:'center',gap:4}}><Text style={{fontSize:13,fontWeight:'700',color:C.green}}>{expanded?'접기':'펼치기'}</Text><Icon name={expanded?'chevron-down':'chevron-up'} size={18}/></View></View>
    {!expanded&&<View style={{gap:3}}><Text style={{fontSize:13,color:C.ink}}>{p.duration} · {km(distance)} · {speedText}</Text><Text style={{fontSize:12,color:C.green}}>{busy?(replayMode??mode):'출발 전'}</Text></View>}
   </Pressable>
   {expanded&&<ScrollView style={{maxHeight:height*.30}} contentContainerStyle={{gap:10}} showsVerticalScrollIndicator><View style={S.between}><View style={{flex:1}}><Text style={S.note}>이동 시간</Text><Text style={[S.metric,{fontSize:27}]}>{busy?p.duration.replace(/^(\d+):(\d+)$/, '$1분 $2초'):'0분 00초'}</Text></View><View style={{flex:1,borderLeftWidth:1,borderColor:C.line,paddingLeft:20}}><Text style={S.note}>이동 거리</Text><Text style={[S.metric,{fontSize:27}]}>{km(distance)}</Text></View></View><View style={[S.between,{gap:8}]}><Text style={S.label}>현재 속도</Text><Text testID="journey-live-speed" style={[S.metric,{fontSize:24,flexShrink:1}]}>{speedText}</Text></View><View style={[S.between,{backgroundColor:'#f2f6ee',borderRadius:18,padding:12}]}><Text style={S.label}>현재 이동수단</Text><Text style={{color:C.green,fontWeight:'800',flexShrink:1,textAlign:'right'}}>{busy?(replayMode??mode):'출발 전'}</Text></View><Note>속도·거리는 GPS 추정값이에요. 위치가 오래 갱신되지 않으면 속도는 수신 대기로 표시돼요.</Note></ScrollView>}
  </View>;
}
