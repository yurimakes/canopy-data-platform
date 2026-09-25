import Text from './AppText';
import React,{useState,useEffect} from 'react';
import {liveSpeedKmh} from '../liveMotion';
import {View} from 'react-native';
import {JourneyInfoPanel} from './JourneyInfoPanel';
import {TripProgressMascot} from './TripProgressMascot';
import JourneyMap from './JourneyMap';
import {journeyProgress,metersBetween} from '../journeyGeometry';
import {km} from '../service';
import type {ServiceProps} from './ServiceScreen';
import {C,S,Note,Icon} from './theme';
export function ActiveJourney({p,direction,replayDistance,replayMode,showInfo=true}:{showInfo?:boolean;replayDistance?:number;replayMode?:string;p:Pick<ServiceProps,'active'|'events'|'route'|'duration'|'tripId'|'baseline'>;direction:'outbound'|'return'}){
 const [now,setNow]=useState(Date.now());
 useEffect(()=>{if(!p.active)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[p.active]);
 const speed=liveSpeedKmh(p.events,now),walking=!!p.active&&speed!=null&&speed>0.5;
 const busy=!!p.active,points=p.events.map(e=>({latitude:e.lat,longitude:e.lon,name:'현재 위치'}));
 const last=points.at(-1),progress=journeyProgress(p.route,busy?last:undefined);
 return <View style={{gap:0,...(busy?{flex:1,minHeight:0}:{})}}>
  <View style={{flexShrink:0,padding:12,paddingBottom:10,backgroundColor:C.white,borderTopLeftRadius:28,borderTopRightRadius:28,zIndex:1}}>
   <View style={S.between}><Text style={{fontSize:11,letterSpacing:1.3,fontWeight:'700',color:C.green}}>{direction==='return'?'집으로 가는 길':'오늘의 초록 여정'}</Text><Text style={S.pill}>{busy?'이동 중':'출발 준비'}</Text></View>
   <View style={{height: 64,marginHorizontal:18,justifyContent:'flex-end',paddingBottom:12}}>
    <View style={{height:5,backgroundColor:'#e6ede4',borderRadius:5}}><View style={{height:5,width:`${progress*100}%`,backgroundColor:C.green,borderRadius:5}}/></View>
    <View style={{position:'absolute',left:`${progress*100}%`,bottom:4,width:58,height:58,marginLeft:-29}}><TripProgressMascot active={busy}/></View>
   </View>
   <View style={S.between}><View style={{maxWidth:'46%',flexDirection:'row',alignItems:'center',gap:6}}><Icon name={direction==='return'?'business-outline':'home-outline'} size={20}/><Text numberOfLines={1} style={[S.label,{flexShrink:1,fontSize:12}]}>{p.route?.from.name??'출발지'}</Text></View><View style={{maxWidth:'46%',flexDirection:'row',alignItems:'center',gap:6}}><Icon name={direction==='return'?'home-outline':'business-outline'} size={20}/><Text numberOfLines={1} style={[S.label,{flexShrink:1,fontSize:12}]}>{p.route?.to.name??'자유 여정'}</Text></View></View>
   <Text style={[S.note,{textAlign:'center',marginTop:10,fontSize:11}]}>{!p.route?'자유롭게 이동하세요':busy&&last?`목적지까지 직선거리 ${km(metersBetween(last,p.route.to))} · 약 ${Math.round(progress*100)}% 접근`:busy?'위치 신호를 기다리고 있어요':'출발 준비가 되었어요'}</Text>
  </View>

  <View style={{overflow:'hidden',borderBottomLeftRadius:24,borderBottomRightRadius:24,...(busy?{flex:1,flexBasis:0,minHeight:0}:{height:300})}}><View style={{position:'absolute',inset:0}}><JourneyMap walking={walking} points={busy?points:[]} route={p.route} fill/></View></View>
  {showInfo&&<JourneyInfoPanel p={p} replayDistance={replayDistance} replayMode={replayMode}/>}

 </View>;
}
