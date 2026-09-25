import {PreviewIcon} from './PreviewIcon';
import {displaySegments,recordedDuration} from '../displaySegments';
import {rewardPresentation,type RewardComparison} from './rewardPresentation';
import {MODES} from '../types';
import Text from './AppText';
import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,Animated,Easing,Modal,Platform,Pressable,ScrollView,View} from 'react-native';
import {Button,Card,C,Icon,Note,S,Stat} from './theme';
import {CanopyMascot} from './CanopyMascot';
import * as Haptics from 'expo-haptics';
import {SafeAreaView} from 'react-native-safe-area-context';
import {Eyebrow,Disclosure,useReducedMotion} from './DesignPrimitives';
import {localAction} from '../communityClient';
import Constants from 'expo-constants';
import type {ServerTrip} from '../tripApi';
import {km} from '../service';

export function RewardCelebration({amount,title,onClose,confirmLabel='확인 · 지갑 보기',headline='오늘의 이동이\n보상이 되었어요.'}:{amount:number;title:string;onClose():void;confirmLabel?:string;headline?:string}){
 const enter=useRef(new Animated.Value(0)).current,fly=useRef(new Animated.Value(0)).current;
 const coin=useRef<View>(null),wallet=useRef<View>(null),[destination,setDestination]=useState({x:0,y:180});
 const [count,setCount]=useState(0),[sending,setSending]=useState(false),reduced=useReducedMotion();
 useEffect(()=>{enter.setValue(0);const l=enter.addListener(({value})=>setCount(Math.round(value*amount*100)/100));const a=Animated.timing(enter,{toValue:1,duration:reduced?0:1000,easing:Easing.out(Easing.cubic),useNativeDriver:false});a.start();if(!reduced)void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(()=>{});return()=>{a.stop();enter.removeListener(l);};},[amount,reduced]);
 const confirming=useRef(false);
 function confirm(){if(confirming.current)return;confirming.current=true;setSending(true);if(reduced){onClose();return;}coin.current?.measureInWindow((x,y,w,h)=>wallet.current?.measureInWindow((wx,wy,ww,wh)=>{setDestination({x:wx+ww/2-x-w/2,y:wy+wh/2-y-h/2});}));Animated.sequence([Animated.delay(60),Animated.timing(fly,{toValue:1,duration:650,easing:Easing.inOut(Easing.cubic),useNativeDriver:Platform.OS!=='web'})]).start(({finished})=>{if(finished){void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(()=>{});onClose();}});}
 useEffect(()=>()=>{fly.stopAnimation();},[]);
 return <Modal transparent visible animationType="fade" onRequestClose={onClose}><SafeAreaView style={{flex:1,backgroundColor:'#082A24'}}><ScrollView contentContainerStyle={{flexGrow:1,justifyContent:'center',padding:28,gap:20,alignItems:'center'}}>
  <Eyebrow light>YOUR MOVE. YOUR REWARD.</Eyebrow>
  <Text style={{fontSize:29,lineHeight:40,color:'white',fontWeight:'700',textAlign:'center'}}>{headline}</Text>
  <View ref={coin} collapsable={false} style={{height:205,width:205,zIndex:10}}><Animated.View style={{flex:1,opacity:fly.interpolate({inputRange:[0,.85,1],outputRange:[1,1,0]}),transform:[{translateX:fly.interpolate({inputRange:[0,1],outputRange:[0,destination.x]})},{translateY:fly.interpolate({inputRange:[0,1],outputRange:[0,destination.y]})},{scale:fly.interpolate({inputRange:[0,.35,1],outputRange:[1,1.1,.08]})}]}}><CanopyMascot pose="coin" height={205} animated/></Animated.View></View>
  <Text accessibilityLiveRegion="polite" style={{fontSize:58,fontWeight:'700',letterSpacing:-2,color:C.leaf}}>+{count.toLocaleString('ko-KR',{maximumFractionDigits:2})}<Text style={{fontSize:26}}> T</Text></Text>
  <Text style={{fontSize:14,color:'#C2D8CD',textAlign:'center'}}>{title}</Text>
  <View ref={wallet} collapsable={false} style={{borderWidth:1,borderColor:'#537364',borderRadius:20,padding:18,flexDirection:'row',alignItems:'center',gap:12,width:'100%',backgroundColor:'#193E32'}}><Icon name="wallet-outline" color={C.leaf} size={30}/><View style={{flex:1}}><Text style={{color:'white',fontWeight:'700'}}>내 캐노피 지갑</Text><Text style={{color:'#C2D8CD',fontSize:12,marginTop:4}}>{sending?'토큰이 도착했어요':'적립 완료'}</Text></View><Icon name="checkmark-circle" color={C.leaf}/></View>
  <View style={{width:'100%'}}><Button title={sending?'토큰을 담고 있어요':confirmLabel} quiet busy={sending} onPress={confirm}/></View>
 </ScrollView></SafeAreaView></Modal>;
}
const celebratedTrips=new Set<string>();


export function JourneyComplete({trip,onDetail,onWallet,onHome,previewComparison}:{trip:ServerTrip;onDetail():void;onWallet():void;onHome?():void;previewComparison?:RewardComparison}){
  const [result,setResult]=useState<RewardComparison|null>(null),[error,setError]=useState(''),[celebrate,setCelebrate]=useState(false);
  const active=useRef(trip.trip_id);active.current=trip.trip_id;
  async function refresh(){const id=trip.trip_id;try{setError('');const next=previewComparison??await localAction('/comparison/'+id);if(active.current===id)setResult(next);}catch(e){setError(String(e));}}
  useEffect(()=>{setResult(null);setCelebrate(false);void refresh();},[trip.trip_id]);
  const reward=rewardPresentation(result),waiting=!!error||reward.waiting;
  useEffect(()=>{if(!waiting)return;const timer=setInterval(()=>void refresh(),10000);return()=>clearInterval(timer);},[waiting,trip.trip_id]);
  useEffect(()=>{if(!previewComparison&&reward.canCelebrate&&!celebratedTrips.has(trip.trip_id)){celebratedTrips.add(trip.trip_id);setCelebrate(true);}},[reward.canCelebrate,trip.trip_id]);
  const [expanded,setExpanded]=useState(true),[explain,setExplain]=useState(false);
  const c=trip.confirmed_trip,seconds=trip.ended_at?Math.max(0,Math.round((Date.parse(trip.ended_at)-Date.parse(trip.started_at))/1000)):0;
  const segments=displaySegments(trip.confirmed_segments??trip.segments);
  const distance=trip.observed_distance_m??c?.total_distance_m??(segments.length?segments.reduce((sum,s)=>sum+s.distance_m,0):null);
  const actual=c?.total_carbon_kg??result?.actual_kg;
  const baseline=result?.baseline_kg;
  const comparable=typeof baseline==='number'&&Number.isFinite(baseline)&&baseline>0&&typeof actual==='number';
  const saved=comparable?baseline!-actual!:null;
  const reduction=comparable?Math.round((saved!/baseline!)*100):null;
  const label=(mode:string)=>MODES.find(m=>m.value===mode)?.title??'확인 중';
  const modeIcon=(mode:string)=>mode==='walk'?'sneaker-move':mode==='bike'?'bicycle':mode==='bus'?'bus':mode==='car'?'car':'train';
  return <>
   <View style={{alignItems:'center',paddingTop:8,paddingBottom:8,gap:10}}><CanopyMascot pose="complete" animated height={175}/><Text style={[S.title,{fontSize:28,textAlign:'center'}]}>오늘도 한 걸음 해냈어요!</Text><Note>{segments.map(s=>label(s.confirmed_mode??s.mode)).join(' → ')||'이번 여정의 이동 기록'}</Note></View>
   {(trip.estimated_duration_seconds??0)>0?<Note>위치 신호가 부족한 구간은 앞뒤 이동수단을 바탕으로 연결했어요. 일부 구간의 시간은 추정이며, 탄소량은 분석 가능한 구간만 계산했어요.</Note>:trip.mode_detection_status==='partial'&&<Note>위치 기록이 부족해 일부 구간의 이동수단을 분석하지 못했어요. 탄소량은 분석 가능한 구간만 계산했어요.</Note>}{trip.mode_detection_status==='insufficient_data'&&<Note>이동수단을 판단할 만큼 위치 기록이 모이지 않았어요.</Note>}{trip.data_quality?.status==='partial'&&<Note>위치 기록이 일부 빠졌어요. 이번 여정은 보상에서 제외돼요.</Note>}
   {trip.is_mock&&<Note>합성 GPS 테스트 여정입니다.</Note>}
   <View style={{backgroundColor:'white',borderWidth:1,borderColor:C.line,borderRadius:27,padding:20,gap:20}}>
    <View style={S.between}><Text style={S.heading}>이번 여정 요약</Text><Text style={[S.pill,{fontSize:10}]}>분석 완료</Text></View>
    <View style={{flexDirection:'row',gap:18}}>
     <View style={{flex:1,gap:9}}><Note>이번 탄소 배출</Note><Text style={{fontSize:32,fontFamily:'Jua',color:C.ink}}>{actual==null?'—':actual.toFixed(2)} <Text style={{fontSize:13}}>kg</Text></Text><Note>CO₂e</Note></View>
     <View style={{flex:1,borderLeftWidth:1,borderColor:C.line,paddingLeft:18,gap:9}}><Note>{result?.source||(result?.planned_baseline_kg!=null?'출발 전 KTDB 기준':waiting?'비교 기준 확인 중':'비교 결과 없음')}</Note><Text style={{fontSize:30,fontFamily:'Jua',color:C.ink}}>{saved==null?(result?.planned_baseline_kg?.toFixed(2)??'—'):Math.abs(saved).toFixed(2)} <Text style={{fontSize:12}}>{saved==null?(result?.planned_baseline_kg!=null?'kg 예상':''):saved>=0?'kg 절감':'kg 더 배출'}</Text></Text>{reduction!=null&&<Text style={[S.pill,{fontSize:10}]}>{Math.abs(reduction)}% {reduction>=0?'덜':'더'} 배출했어요</Text>}</View>
    </View>
    {result?.comparison_message&&<Note>{result.comparison_message}</Note>}
    {result?.comparison_scope==='observed_segments'&&<Note>분석 가능한 구간의 거리와 탄소량만 비교했어요. 전체 여정의 감축량은 아니에요.</Note>}
    {comparable&&<View style={{gap:8}}><View accessibilityRole="progressbar" accessibilityValue={{min:0,max:100,now:Math.round(Math.min(1,actual!/baseline!)*100)}} style={{height:10,borderRadius:10,backgroundColor:'#E8EDDF',overflow:'hidden'}}><View style={{height:10,borderRadius:10,backgroundColor:'#63866B',width:`${Math.min(1,Math.max(0,actual!/baseline!))*100}%`}}/></View><View style={S.between}><Text style={{fontSize:10,color:C.muted}}>실제 {actual!.toFixed(2)} kg</Text><Text style={{fontSize:10,color:C.muted}}>비교 기준 {baseline!.toFixed(2)} kg</Text></View></View>}
    <Pressable accessibilityRole="button" accessibilityState={{expanded:explain}} onPress={()=>setExplain(!explain)} style={[S.row,{minHeight:44}]}><PreviewIcon name="info" size={17}/><Text style={[S.note,{flex:1,fontSize:11}]}>어떤 기준으로 비교하나요?</Text><Icon name={explain?'chevron-up':'chevron-forward'} size={16}/></Pressable>
    {explain&&<Note>{result?.source?`비교 기준: ${result.source}. 이 기준의 배출량과 이번 여정의 배출량을 비교하며, 표시값은 반올림했어요.`:'서버에서 비교 기준을 확인하고 있어요. 개인 기준과 KTDB 기준은 서로 다르며, 확인되지 않은 감축량은 표시하지 않습니다.'}</Note>}
    <View style={{flexDirection:'row',borderTopWidth:1,borderBottomWidth:1,borderColor:C.line,paddingVertical:20}}><View style={{flex:1,alignItems:'center',gap:7}}><PreviewIcon name="timer"/><Note>이동 시간</Note><Text style={S.metric}>{Math.floor(seconds/60)}<Text style={{fontSize:12}}>분 {seconds%60}초</Text></Text></View><View style={{flex:1,alignItems:'center',gap:7,borderLeftWidth:1,borderColor:C.line}}><PreviewIcon name="map-pin"/><Note>이동 거리</Note><Text style={S.metric}>{distance==null?'—':(distance/1000).toFixed(2)}<Text style={{fontSize:12}}> km</Text></Text></View></View>
    <Pressable accessibilityRole="button" accessibilityState={{expanded}} onPress={()=>setExpanded(!expanded)} style={[S.between,{minHeight:44}]}><Text style={[S.note,{fontSize:11}]}>감지된 이동수단</Text><View style={[S.row,{flex:1,justifyContent:'flex-end',gap:5}]}><Text style={{flexShrink:1,fontSize:11,color:C.ink,textAlign:'right'}}>{segments.map(s=>label(s.confirmed_mode??s.mode)).join(' → ')}</Text><Icon name={expanded?'chevron-up':'chevron-down'} size={14}/></View></Pressable>
    {expanded&&<View style={{gap:12}}>{segments.map(segment=>{const mode=segment.confirmed_mode??segment.mode;return <View key={segment.segment_id} style={{flexDirection:'row',alignItems:'center',gap:10,padding:13,borderRadius:19,backgroundColor:mode==='rail'?'#EDF2ED':'#F3F5E9'}}><View style={{width:37,height:37,borderRadius:14,alignItems:'center',justifyContent:'center',backgroundColor:'#E7EDD9'}}><PreviewIcon name={modeIcon(mode)} size={23}/></View><View style={{flex:1,gap:5}}><Text style={S.label}>{label(mode)}</Text><Text style={{fontSize:10,color:C.muted}}>{recordedDuration(segment.recordedSeconds)} · {km(segment.distance_m)}</Text>{segment.gapSeconds>0&&<Text style={{fontSize:10,color:C.muted}}>일부 위치 기록 누락</Text>}</View><View style={{alignItems:'flex-end',gap:3}}><Text style={{fontSize:16,fontFamily:'Jua',color:C.deep}}>{segment.carbon_kg==null?'—':(segment.carbon_kg*1000).toFixed(1)} <Text style={{fontSize:10}}>g</Text></Text><Text style={{fontSize:9,color:C.muted}}>CO₂e</Text></View></View>;})}</View>}
   </View>
   <Pressable accessibilityRole="button" onPress={onWallet} style={{backgroundColor:'#ECF1D8',borderRadius:23,padding:18,flexDirection:'row',alignItems:'center',gap:14}}><PreviewIcon name="coins" size={34} color="#947528"/><View style={{flex:1,gap:4}}><Note>이번 여정 보상</Note><Text style={{fontFamily:'Jua',fontSize:29,color:C.deep}}>{waiting?'확인 중':`+${reward.amount} T`}</Text></View><Text style={{fontSize:11,color:C.muted}}>{reward.label}</Text><Icon name="chevron-forward" size={17}/></Pressable>
   {!reward.canCelebrate&&<Note>{error?'보상을 확인하지 못했어요. 다시 확인해주세요.':reward.message}</Note>}
   {waiting&&<Button title="보상 다시 확인" quiet onPress={()=>void refresh()}/>}
   {onHome&&<Button title="홈으로 돌아가기" onPress={onHome}/>}
   {result?.development_only&&<Note>로컬 테스트 보상 · 기준 출처를 확인해주세요.</Note>}
   <Button title="이동 상세와 피드백" quiet onPress={onDetail}/>
   {celebrate&&<RewardCelebration amount={reward.amount} title={result?.title??'이번 여정 보상'} onClose={()=>{setCelebrate(false);onWallet();}}/>}
  </>;
}
