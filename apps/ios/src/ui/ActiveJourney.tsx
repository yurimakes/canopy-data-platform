import Text from './AppText';
import React from 'react';
import {View} from 'react-native';
import {JourneyInfoPanel} from './JourneyInfoPanel';
import {CanopyMascot} from './CanopyMascot';
import JourneyMap from './JourneyMap';
import {PopulationPreview} from './PopulationPreview';
import {journeyProgress,metersBetween} from '../journeyGeometry';
import {km} from '../service';
import type {ServiceProps} from './ServiceScreen';
import {C,S,Note,Icon} from './theme';
export function ActiveJourney({p,direction,replayDistance,replayMode,showInfo=true}:{showInfo?:boolean;replayDistance?:number;replayMode?:string;p:Pick<ServiceProps,'active'|'events'|'route'|'duration'|'tripId'|'baseline'>;direction:'outbound'|'return'}){
 const busy=!!p.active,points=p.events.map(e=>({latitude:e.lat,longitude:e.lon,name:'현재 위치'}));
 const last=points.at(-1),progress=journeyProgress(p.route,busy?last:undefined);
 return <View style={{gap:0,...(busy?{flex:1,minHeight:0}:{})}}>
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
  {showInfo&&<JourneyInfoPanel p={p} replayDistance={replayDistance} replayMode={replayMode}/>}

 </View>;
}
