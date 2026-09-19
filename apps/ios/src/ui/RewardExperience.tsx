import {MODES} from '../types';
import Text from './AppText';
import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,Animated,Easing,Modal,Platform,ScrollView,View} from 'react-native';
import {Button,Card,C,Icon,Note,S,Stat} from './theme';
import {CanopyMascot} from './CanopyMascot';
import {localAction} from '../communityClient';
import Constants from 'expo-constants';
import type {ServerTrip} from '../tripApi';
import {km} from '../service';

export function RewardCelebration({amount,title,onClose}:{amount:number;title:string;onClose():void}){
  const progress=useRef(new Animated.Value(0)).current;
  const [count,setCount]=useState(0);
  useEffect(()=>{let alive=true;const listener=progress.addListener(({value})=>setCount(Math.round(value*amount*100)/100));
    let animation:Animated.CompositeAnimation|undefined;
    void AccessibilityInfo.isReduceMotionEnabled().then(reduce=>{if(!alive)return;if(reduce)progress.setValue(1);else{
      animation=Animated.timing(progress,{toValue:1,duration:1400,easing:Easing.out(Easing.cubic),useNativeDriver:false});animation.start();
    }}).catch(()=>progress.setValue(1));return()=>{alive=false;animation?.stop();progress.removeListener(listener);};},[amount]);
  return <Modal transparent visible animationType="fade" onRequestClose={onClose}><ScrollView style={{flex:1,backgroundColor:'#092c26d9'}} contentContainerStyle={{flexGrow:1,justifyContent:'center',padding:24}}>
    <View style={{backgroundColor:C.paper,borderRadius:32,padding:20,gap:16,alignItems:'center',width:'100%',maxWidth:420,alignSelf:'center'}}>
      <Text style={S.pill}>REWARD RECEIVED</Text>
      <View style={{height:230,width:'100%',justifyContent:'center'}}><CanopyMascot pose="complete" height={190}/>
        <View style={{position:'absolute',right:0,bottom:0,width:110,height:110}}><CanopyMascot pose="coin" height={110}/></View>
      </View>
      <Text style={[S.title,{textAlign:'center'}]}>작은 실천이 쌓였어요!</Text><Text style={[S.metric,{fontSize:42,color:C.green}]}>+{count.toLocaleString('ko-KR',{maximumFractionDigits:2})} T</Text>
      <Text style={[S.label,{textAlign:'center'}]}>{title}</Text><Note>지갑에 적립을 완료했어요.</Note>
      <View style={{width:'100%',marginTop:6}}><Button title="좋아요!" onPress={onClose}/></View>
    </View>
  </ScrollView></Modal>;
}

function segmentDuration(start:string,end:string){const seconds=Math.max(0,Math.round((Date.parse(end)-Date.parse(start))/1000));return `${Math.floor(seconds/60)}분 ${seconds%60}초`;}

export function JourneyComplete({trip,onDetail,onWallet}:{trip:ServerTrip;onDetail():void;onWallet():void}){
  const [result,setResult]=useState<any>(null),[error,setError]=useState(''),[celebrate,setCelebrate]=useState(false);
  const active=useRef(trip.trip_id);active.current=trip.trip_id;
  async function refresh(){const id=trip.trip_id;try{setError('');const next=await localAction('/comparison/'+id);if(active.current===id)setResult(next);}catch(e){setError(String(e));}}
  useEffect(()=>{setResult(null);setCelebrate(false);if(Constants.expoConfig?.extra?.localOnly)void refresh();else setResult({status:'unavailable',message:'여정 보상 서버 연결이 필요합니다.'});},[trip.trip_id]);
  const c=trip.confirmed_trip,seconds=trip.ended_at?Math.max(0,Math.round((Date.parse(trip.ended_at)-Date.parse(trip.started_at))/1000)):0;
  return <><View style={{alignItems:'center',gap:10,paddingTop:6,paddingBottom:8}}><Text style={S.pill}>TODAY'S GREEN JOURNEY</Text><CanopyMascot pose="complete" height={175}/>
    <Text style={[S.title,{textAlign:'center'}]}>오늘도, 지구와 한 걸음.</Text><Note>여정을 안전하게 마쳤어요. 수고하셨어요!</Note></View>
    {trip.is_mock&&<Note>합성 GPS 재생 테스트입니다. 실제 사용자가 이동한 기록이 아닙니다.</Note>}<Card><View style={S.row}><Stat label="이동 거리" value={c?km(c.total_distance_m):'—'}/><Stat label="소요 시간" value={seconds<60?`${seconds}초`:`${Math.floor(seconds/60)}분 ${seconds%60}초`}/><Stat label="탄소 배출" value={c?`${c.total_carbon_kg.toFixed(3)} kg`:'—'}/></View></Card>
    {!!trip.segments.length&&<Card><Text style={S.heading}>이번 여정의 이동수단</Text>{(trip.confirmed_segments??trip.segments).map((segment,i)=><View key={segment.segment_id} style={S.between}><View style={[S.row,{flex:1}]}><Text style={S.pill}>{String(i+1).padStart(2,'0')}</Text><Text style={S.label}>{MODES.find(m=>m.value===(segment.confirmed_mode??segment.mode))?.title??'확인 중'}</Text></View><Text style={S.note}>{km(segment.distance_m)} · {segmentDuration(segment.start_time,segment.end_time)}</Text></View>)}</Card>}
    {result?.baseline_kg!==undefined&&<View style={{backgroundColor:C.deep,borderRadius:24,padding:24,gap:18}}>
      <View style={S.between}><Text style={{color:'#cbe7d9',fontWeight:'600'}}>같은 경로, 더 가벼운 탄소</Text><Icon name="leaf-outline" color="#b9e877"/></View>
      <Text style={{color:'white',fontSize:36,fontWeight:'800'}}>{(result.saved_kg*1000).toFixed(1)} <Text style={{fontSize:17}}>g 절감</Text></Text>
      <View style={[S.between,{borderTopWidth:1,borderTopColor:'#366b5e',paddingTop:16}]}><Text style={{color:'#cbe7d9'}}>출발 전 예상</Text><Text style={{color:'white'}}>{(result.baseline_kg*1000).toFixed(1)} g</Text></View>
      <View style={S.between}><Text style={{color:'#cbe7d9'}}>실제 이동</Text><Text style={{color:'white'}}>{(result.actual_kg*1000).toFixed(1)} g</Text></View>
      {!!result.source&&<Text style={{color:'#cbe7d9',fontSize:12,lineHeight:18}}>{result.source}</Text>}
      {result.development_only&&<Text style={{color:'#cbe7d9',fontSize:11}}>로컬 테스트 보상 · 기준 출처를 확인해주세요.</Text>}
    </View>}
    <Card><View style={S.between}><View style={S.row}><Icon name="gift-outline"/><Text style={S.heading}>이번 여정 리워드</Text></View><Text style={S.pill}>{result?.status==='paid'?'적립 완료':'지급 기준 확인'}</Text></View>
      {result?.status==='paid'?<><Text style={[S.metric,{fontSize:32}]}>+{result.points} T</Text><Note>적게 배출한 탄소가 작은 보상이 됐어요.</Note><Button title="적립 보상 확인" onPress={()=>setCelebrate(true)}/></>:<Note>{error||result?.message||(result?.status==='no_reduction'?'이번 여정은 지급 가능한 절감 토큰이 없어요. 다음 실천도 응원할게요.':'지급 결과를 확인하고 있어요.')}</Note>}
      {!!error&&<Button title="다시 확인" quiet onPress={()=>void refresh()}/>}<Button title="토큰 내역 보기" quiet onPress={onWallet}/>
    </Card><Button title="이동 타임라인과 피드백" quiet onPress={onDetail}/>
    {celebrate&&<RewardCelebration amount={result.points} title="출퇴근 탄소 절감 보상" onClose={()=>setCelebrate(false)}/>}
  </>;
}
