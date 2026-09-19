import React,{useEffect,useState} from 'react';
import {Pressable,Text,View,useWindowDimensions,LayoutAnimation} from 'react-native';
import {CanopyMascot} from './CanopyMascot';
import JourneyMap from './JourneyMap';
import {PopulationPreview} from './PopulationPreview';
import {journeyProgress,metersBetween} from '../journeyGeometry';
import {localAction} from '../communityClient';
import {gpsDistance,km} from '../service';
import {MODES} from '../types';
import type {ServiceProps} from './ServiceScreen';
import {C,S,Note,Icon} from './theme';
export function ActiveJourney({p,direction,replayDistance,replayMode}:{replayDistance?:number;replayMode?:string;p:Pick<ServiceProps,'active'|'events'|'route'|'duration'|'tripId'>;direction:'outbound'|'return'}){
 const [expanded,setExpanded]=useState(false),[mode,setMode]=useState('이동 감지 중');
 const {height}=useWindowDimensions();
 const busy=!!p.active,points=p.events.map(e=>({latitude:e.lat,longitude:e.lon,name:'현재 위치'}));
 const last=points.at(-1),progress=journeyProgress(p.route,busy?last:undefined),distance=busy?(replayDistance??gpsDistance(p.events)):0;
 useEffect(()=>{let alive=true;setMode('이동 감지 중');if(!busy||!p.tripId)return;const refresh=()=>localAction('/predictions/'+p.tripId).then(v=>{if(alive)setMode(MODES.find(m=>m.value===v.mode)?.title??'이동 감지 중');}).catch(()=>{if(alive)setMode('분석 연결 확인 중');});void refresh();const timer=setInterval(refresh,2000);return()=>{alive=false;clearInterval(timer);};},[p.tripId,busy]);
 return <View style={{gap:0,...(busy?{height:Math.max(430,height-220)}:{})}}>
  <View style={{padding:16,paddingBottom:12,backgroundColor:C.white,borderTopLeftRadius:28,borderTopRightRadius:28,zIndex:1}}>
   <View style={S.between}><Text style={{fontSize:11,letterSpacing:1.3,fontWeight:'700',color:C.green}}>{direction==='return'?'ON MY WAY HOME':'MY GREEN COMMUTE'}</Text><Text style={S.pill}>{busy?'이동 중':'출발 준비'}</Text></View>
   <View style={{height:78,marginHorizontal:18,justifyContent:'flex-end',paddingBottom:12}}>
    <View style={{height:5,backgroundColor:'#e6ede4',borderRadius:5}}><View style={{height:5,width:`${progress*100}%`,backgroundColor:C.green,borderRadius:5}}/></View>
    <View style={{position:'absolute',left:`${progress*100}%`,bottom:8,width:66,height:66,marginLeft:-33}}><CanopyMascot pose={busy?'run':'start'} height={66} animated={busy}/></View>
   </View>
   <View style={S.between}><View style={{maxWidth:'46%',flexDirection:'row',alignItems:'center',gap:6}}><Icon name={direction==='return'?'business-outline':'home-outline'} size={20}/><Text numberOfLines={1} style={[S.label,{flexShrink:1,fontSize:12}]}>{p.route?.from.name??'출발지'}</Text></View><View style={{maxWidth:'46%',flexDirection:'row',alignItems:'center',gap:6}}><Icon name={direction==='return'?'home-outline':'business-outline'} size={20}/><Text numberOfLines={1} style={[S.label,{flexShrink:1,fontSize:12}]}>{p.route?.to.name??'자유 여정'}</Text></View></View>
   <Text style={[S.note,{textAlign:'center',marginTop:10,fontSize:11}]}>{!p.route?'목적지 없이 자유롭게 기록해요':busy&&last?`목적지까지 직선거리 ${km(metersBetween(last,p.route.to))} · 약 ${Math.round(progress*100)}% 접근`:'위치를 받으면 목적지까지의 진행 상황이 표시돼요'}</Text>
  </View>
  <View style={{overflow:'hidden',borderBottomLeftRadius:28,borderBottomRightRadius:28,...(busy?{flex:1}:{})}}><JourneyMap points={busy?points:[]} route={p.route} height={busy?Math.max(240,height-390):340}/></View>
  <View style={{...(busy?{position:'absolute',bottom:0,left:0,right:0}:{marginTop:-24}),backgroundColor:C.white,borderRadius:28,paddingHorizontal:20,paddingBottom:expanded?22:8,boxShadow:'0 -6px 28px #183d3510'}}>
   <Pressable accessibilityRole="button" accessibilityLabel={expanded?'이동 정보 숨기기':'이동 정보 펼치기'} accessibilityState={{expanded}} onPress={()=>{LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);setExpanded(!expanded);}} style={{alignItems:'center',padding:15,gap:5}}><View style={{width:36,height:4,borderRadius:4,backgroundColor:'#b5c9bd'}}/>{!expanded&&<Text style={{fontSize:11,color:C.muted}}>이동 정보 보기</Text>}</Pressable>
   {expanded&&<View style={{gap:18}}><View style={S.between}><View style={{flex:1}}><Text style={S.note}>이동 시간</Text><Text style={[S.metric,{fontSize:27}]}>{busy?p.duration:'00:00'}</Text></View><View style={{flex:1,borderLeftWidth:1,borderColor:C.line,paddingLeft:20}}><Text style={S.note}>이동 거리</Text><Text style={[S.metric,{fontSize:27}]}>{km(distance)}</Text></View></View><View style={[S.between,{backgroundColor:'#f2f6ee',borderRadius:18,padding:16}]}><Text style={S.label}>현재 이동수단</Text><Text style={{color:C.green,fontWeight:'800'}}>{busy?(replayMode??mode):'출발 전'}</Text></View><Note>이동 중 거리는 GPS 추정값이며, 종료 후 확정됩니다.</Note></View>}
  </View>
  {!busy&&p.route&&<View style={{marginTop:18}}><PopulationPreview route={p.route}/></View>}
 </View>;
}
