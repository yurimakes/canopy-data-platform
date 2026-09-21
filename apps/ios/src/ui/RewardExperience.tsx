import {rewardPresentation,type RewardComparison} from './rewardPresentation';
import {MODES} from '../types';
import Text from './AppText';
import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,Animated,Easing,Modal,Platform,ScrollView,View} from 'react-native';
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

function segmentDuration(start:string,end:string){const seconds=Math.max(0,Math.round((Date.parse(end)-Date.parse(start))/1000));return `${Math.floor(seconds/60)}분 ${seconds%60}초`;}

export function JourneyComplete({trip,onDetail,onWallet,previewComparison}:{trip:ServerTrip;onDetail():void;onWallet():void;previewComparison?:RewardComparison}){
  const [result,setResult]=useState<RewardComparison|null>(null),[error,setError]=useState(''),[celebrate,setCelebrate]=useState(false);
  const active=useRef(trip.trip_id);active.current=trip.trip_id;
  async function refresh(){const id=trip.trip_id;try{setError('');const next=previewComparison??await localAction('/comparison/'+id);if(active.current===id)setResult(next);}catch(e){setError(String(e));}}
  useEffect(()=>{setResult(null);setCelebrate(false);void refresh();},[trip.trip_id]);
  const reward=rewardPresentation(result),waiting=!!error||reward.waiting;
  useEffect(()=>{if(!waiting)return;const timer=setInterval(()=>void refresh(),10000);return()=>clearInterval(timer);},[waiting,trip.trip_id]);
  useEffect(()=>{if(reward.canCelebrate&&!celebratedTrips.has(trip.trip_id)){celebratedTrips.add(trip.trip_id);setCelebrate(true);}},[reward.canCelebrate,trip.trip_id]);
  const c=trip.confirmed_trip,seconds=trip.ended_at?Math.max(0,Math.round((Date.parse(trip.ended_at)-Date.parse(trip.started_at))/1000)):0;
  return <><View style={{alignItems:'center',gap:10,paddingTop:6,paddingBottom:8}}><Eyebrow>JOURNEY COMPLETE</Eyebrow><CanopyMascot pose="complete" animated height={155}/>
    <Text style={[S.title,{textAlign:'center'}]}>잘 도착했어요!</Text><Note>오늘도 더 가벼운 이동을 만들었어요.</Note></View>
    {trip.data_quality?.status==='partial'&&<Note>위치 기록이 일부 빠졌어요. 이번 여정은 보상에서 제외돼요.</Note>}{trip.is_mock&&<Note>합성 GPS 재생 테스트입니다. 실제 사용자가 이동한 기록이 아닙니다.</Note>}<Card><View style={S.row}><Stat label="이동 거리" value={c?km(c.total_distance_m):'—'}/><Stat label="소요 시간" value={seconds<60?`${seconds}초`:`${Math.floor(seconds/60)}분 ${seconds%60}초`}/><Stat label="탄소 배출" value={c?`${c.total_carbon_kg.toFixed(3)} kg`:'—'}/></View></Card>
    {!!trip.segments.length&&<Card><Text style={S.heading}>어떻게 이동했나요?</Text>{(trip.confirmed_segments??trip.segments).map((segment,i)=><View key={segment.segment_id} style={S.between}><View style={[S.row,{flex:1}]}><Text style={S.pill}>{String(i+1).padStart(2,'0')}</Text><Text style={S.label}>{MODES.find(m=>m.value===(segment.confirmed_mode??segment.mode))?.title??'확인 중'}</Text></View><Text style={S.note}>{km(segment.distance_m)} · {segmentDuration(segment.start_time,segment.end_time)}</Text></View>)}</Card>}
    {result?.baseline_kg!==undefined&&<View style={{backgroundColor:C.deep,borderRadius:24,padding:24,gap:18}}>
      <View style={S.between}><Text style={{color:'#cbe7d9',fontWeight:'600'}}>내가 줄인 탄소</Text><Icon name="leaf-outline" color="#b9e877"/></View>
      <Text style={{color:'white',fontSize:36,fontWeight:'800'}}>{((result.saved_kg??0)*1000).toFixed(1)} <Text style={{fontSize:17}}>g 절감</Text></Text>
      <View style={[S.between,{borderTopWidth:1,borderTopColor:'#366b5e',paddingTop:16}]}><Text style={{color:'#cbe7d9'}}>비교 기준</Text><Text style={{color:'white'}}>{(result.baseline_kg*1000).toFixed(1)} g</Text></View>
      <View style={S.between}><Text style={{color:'#cbe7d9'}}>실제 이동</Text><Text style={{color:'white'}}>{((result.actual_kg??0)*1000).toFixed(1)} g</Text></View>
      {!!result.source&&<Text style={{color:'#cbe7d9',fontSize:12,lineHeight:18}}>{result.source}</Text>}
      {result.development_only&&<Text style={{color:'#cbe7d9',fontSize:11}}>로컬 테스트 보상 · 기준 출처를 확인해주세요.</Text>}
    </View>}
    <Card><View style={S.between}><View style={S.row}><Icon name="gift-outline"/><Text style={S.heading}>이번에 모은 토큰</Text></View><Text style={S.pill}>{reward.label}</Text></View>
      {reward.canCelebrate?<><Text style={[S.metric,{fontSize:32}]}>+{reward.amount} T</Text><Note>적게 배출한 탄소가 작은 보상이 됐어요.</Note><Button title="적립 보상 확인" onPress={()=>setCelebrate(true)}/></>:<Note>{error?'잠시 연결이 끊겼어요. 다시 확인해주세요.':reward.message}</Note>}
      {waiting&&<Button title="다시 확인" quiet onPress={()=>void refresh()}/>}<Button title="토큰 내역 보기" quiet onPress={onWallet}/>
    </Card><Button title="이동 타임라인과 피드백" quiet onPress={onDetail}/>
    {celebrate&&<RewardCelebration amount={reward.amount} title={result?.title??"여정 보상"} onClose={()=>{setCelebrate(false);onWallet();}}/>}
  </>;
}
