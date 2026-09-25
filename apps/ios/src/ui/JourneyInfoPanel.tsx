import Text from './AppText';
import Constants from 'expo-constants';
import React,{useEffect,useState} from 'react';
import {Pressable,ScrollView,View,useWindowDimensions} from 'react-native';
import {localAction} from '../communityClient';
import {gpsDistance,km} from '../service';
import {liveSpeedKmh} from '../liveMotion';
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
 const predictedTitle=freshPrediction?MODES.find(m=>m.value===prediction.mode)?.title:undefined;
 const mode=predictedTitle?predictedTitle+' · 확인 중':'이동수단 분석 대기';
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
   {expanded&&<ScrollView style={{maxHeight:height*.30}} contentContainerStyle={{gap:12,paddingBottom:4}} showsVerticalScrollIndicator>
    <View style={[S.between,{paddingVertical:4}]}><View style={[S.row,{gap:7,flex:1}]}><View style={{width:7,height:7,borderRadius:4,backgroundColor:busy?C.green:C.muted}}/><Text style={{fontSize:13,color:C.green,fontWeight:'700',flexShrink:1}}>{busy?(replayMode??mode):'출발 전'}</Text></View><View style={{backgroundColor:C.mint,borderRadius:10,paddingHorizontal:10,paddingVertical:6}}><Text testID="journey-live-speed" style={{fontSize:13,color:C.deep,fontWeight:'700'}}>{speedText}</Text></View></View>
    <View style={{flexDirection:'row',gap:10}}><View style={{flex:1,padding:14,borderRadius:18,backgroundColor:C.paper,gap:6}}><Text style={{fontSize:11,color:C.muted}}>이동 시간</Text><Text adjustsFontSizeToFit numberOfLines={1} style={[S.metric,{fontSize:25}]}>{busy?p.duration.replace(/^(\d+):(\d+)$/, '$1분 $2초'):'0분 00초'}</Text></View><View style={{flex:1,padding:14,borderRadius:18,backgroundColor:C.paper,gap:6}}><Text style={{fontSize:11,color:C.muted}}>이동 거리</Text><Text adjustsFontSizeToFit numberOfLines={1} style={[S.metric,{fontSize:25}]}>{km(distance)}</Text></View></View>
    {busy&&p.events.length>0&&now-Date.parse(p.events[p.events.length-1].event_time)>15000&&<Note>새 위치 신호를 기다리고 있어요. 위치가 다시 수집되면 분석을 이어갑니다.</Note>}<Text style={{fontSize:10,lineHeight:16,color:C.muted}}>속도·거리는 위치 신호를 바탕으로 계산해요.</Text>
   </ScrollView>}
  </View>;
}
