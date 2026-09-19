import Text from './AppText';
import React,{useEffect,useState} from 'react';
import {Pressable,View,useWindowDimensions,LayoutAnimation} from 'react-native';
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
 const [expanded,setExpanded]=useState(true),[mode,setMode]=useState('이동 감지 중');
 const [mapHeight,setMapHeight]=useState(250);
 const busy=!!p.active,points=p.events.map(e=>({latitude:e.lat,longitude:e.lon,name:'현재 위치'}));
 const last=points.at(-1),progress=journeyProgress(p.route,busy?last:undefined),distance=busy?(replayDistance??gpsDistance(p.events)):0;
 useEffect(()=>{let alive=true;setMode('이동 감지 중');if(!busy||!p.tripId)return;const refresh=()=>localAction('/predictions/'+p.tripId).then(v=>{if(alive)setMode(MODES.find(m=>m.value===v.mode)?.title??'이동 감지 중');}).catch(()=>{if(alive)setMode('분석 연결 확인 중');});void refresh();const timer=setInterval(refresh,2000);return()=>{alive=false;clearInterval(timer);};},[p.tripId,busy]);
 return <View style={{gap:0,...(busy?{flex:1,minHeight:0}:{})}}>
  <View style={{padding:12,paddingBottom:10,backgroundColor:C.white,borderTopLeftRadius:28,borderTopRightRadius:28,zIndex:1}}>
   <View style={S.between}><Text style={{fontSize:11,letterSpacing:1.3,fontWeight:'700',color:C.green}}>{direction==='return'?'ON MY WAY HOME':'MY GREEN COMMUTE'}</Text><Text style={S.pill}>{busy?'이동 중':'출발 준비'}</Text></View>
   <View style={{height: 64,marginHorizontal:18,justifyContent:'flex-end',paddingBottom:12}}>
    <View style={{height:5,backgroundColor:'#e6ede4',borderRadius:5}}><View style={{height:5,width:`${progress*100}%`,backgroundColor:C.green,borderRadius:5}}/></View>
    <View style={{position:'absolute',left:`${progress*100}%`,bottom:4,width:58,height:58,marginLeft:-29}}><CanopyMascot pose={busy?'run':'start'} height={58} animated={busy}/></View>
   </View>
   <View style={S.between}><View style={{maxWidth:'46%',flexDirection:'row',alignItems:'center',gap:6}}><Icon name={direction==='return'?'business-outline':'home-outline'} size={20}/><Text numberOfLines={1} style={[S.label,{flexShrink:1,fontSize:12}]}>{p.route?.from.name??'출발지'}</Text></View><View style={{maxWidth:'46%',flexDirection:'row',alignItems:'center',gap:6}}><Icon name={direction==='return'?'home-outline':'business-outline'} size={20}/><Text numberOfLines={1} style={[S.label,{flexShrink:1,fontSize:12}]}>{p.route?.to.name??'자유 여정'}</Text></View></View>
   <Text style={[S.note,{textAlign:'center',marginTop:10,fontSize:11}]}>{!p.route?'목적지 없이 자유롭게 기록해요':busy&&last?`목적지까지 직선거리 ${km(metersBetween(last,p.route.to))} · 약 ${Math.round(progress*100)}% 접근`:'위치를 받으면 목적지까지의 진행 상황이 표시돼요'}</Text>
  </View>
  <View onLayout={e=>{if(busy)setMapHeight(e.nativeEvent.layout.height);}} style={{overflow:'hidden',...(busy?{flex:1,minHeight:80}:{})}}><JourneyMap points={busy?points:[]} route={p.route} height={busy?mapHeight:300}/></View>
  <View style={{flexShrink:0,zIndex:5,elevation:5,backgroundColor:C.white,borderRadius:28,paddingHorizontal:20,paddingBottom:expanded?12:8,boxShadow:'0 -6px 28px #183d3510'}}>
   <Pressable accessibilityRole="button" accessibilityLabel={expanded?'이동 정보 숨기기':'이동 정보 펼치기'} accessibilityState={{expanded}} onPress={()=>{LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);setExpanded(!expanded);}} style={{alignItems:'center',padding:10,gap:5}}><View style={{width:36,height:4,borderRadius:4,backgroundColor:'#b5c9bd'}}/>{!expanded&&<Text style={{fontSize:11,color:C.muted}}>이동 정보 보기</Text>}</Pressable>
   {expanded&&<View style={{gap:10}}><View style={S.between}><View style={{flex:1}}><Text style={S.note}>이동 시간</Text><Text style={[S.metric,{fontSize:27}]}>{busy?p.duration.replace(/^(\d+):(\d+)$/, '$1분 $2초'):'0분 00초'}</Text></View><View style={{flex:1,borderLeftWidth:1,borderColor:C.line,paddingLeft:20}}><Text style={S.note}>이동 거리</Text><Text style={[S.metric,{fontSize:27}]}>{km(distance)}</Text></View></View><View style={[S.between,{backgroundColor:'#f2f6ee',borderRadius:18,padding:12}]}><Text style={S.label}>현재 이동수단</Text><Text style={{color:C.green,fontWeight:'800'}}>{busy?(replayMode??mode):'출발 전'}</Text></View><Note>이동 중 거리는 GPS 추정값이며, 종료 후 확정됩니다.</Note></View>}
  </View>
  {!busy&&p.route&&<View style={{marginTop:18}}><PopulationPreview route={p.route}/></View>}
 </View>;
}
