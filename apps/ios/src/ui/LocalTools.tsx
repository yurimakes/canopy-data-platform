import {JourneyReplay} from './JourneyReplay';
import {randomUUID} from 'expo-crypto';
import {TripResult} from './TripResult';
import {BaselinePanel,RankingPanel,RewardPanel} from './CommunityPanels';
import {localAction} from '../communityClient';
import React,{useEffect,useState} from 'react';
import Constants from 'expo-constants';
import {session} from '../accountSession';
import {accountConfig} from '../accountConfig';
import {Text,Modal,ScrollView} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {JourneyComplete} from './RewardExperience';
import type {ServerTrip} from '../tripApi';
import {Card,Note,Button,S} from './theme';
import {MODES} from '../types';

async function localRequest(path:string,method='GET'){
  const saved=session();if(!saved)throw Error('다시 로그인해주세요.');
  const response=await fetch(accountConfig().url.replace(/\/$/,'')+path,{method,headers:{Authorization:'Bearer '+saved.access_token}});
  const body=await response.json();if(!response.ok)throw Error(body.message??'로컬 요청 실패');return body;
}
export function LivePrediction({tripId}:{tripId?:string}){
  const [value,setValue]=useState<{mode?:string;confidence?:number;point_count?:number;error?:string}>({});
  useEffect(()=>{let alive=true;setValue({});if(!tripId||!Constants.expoConfig?.extra?.localOnly)return;
    const refresh=()=>localRequest('/predictions/'+tripId).then(v=>{if(alive)setValue(v);}).catch(e=>{if(alive)setValue({error:String(e)});});
    void refresh();const timer=setInterval(refresh,2000);return()=>{alive=false;clearInterval(timer);};},[tripId]);
  if(!tripId||!Constants.expoConfig?.extra?.localOnly)return null;
  return <Card><Text style={S.heading}>{value.mode?`예측 이동수단: ${MODES.find(m=>m.value===value.mode)?.title??value.mode}`:'이동수단 분석 준비 중'}</Text>
    <Note>{value.error??(value.mode?`GPS ${value.point_count}개 반영 · 신뢰도 ${Math.round((value.confidence??0)*100)}%`:'GPS가 쌓이면 실제 모델 예측을 표시합니다.')}</Note></Card>;
}
export function LocalWeekly(){
  const [demoDetail,setDemoDetail]=useState(false),[replay,setReplay]=useState(false);
  const [message,setMessage]=useState(''),[busy,setBusy]=useState(false),[demo,setDemo]=useState<ServerTrip|null>(null),[expanded,setExpanded]=useState(false),[scenario,setScenario]=useState<any>(null),[panel,setPanel]=useState<'baseline'|'ranking'|'rewards'>('baseline');
  const run=async()=>{setBusy(true);try{const r=await localRequest('/local/weekly','POST');setMessage(r.message);}catch(e){setMessage(String(e));}finally{setBusy(false);}};
  useEffect(()=>{if(!Constants.expoConfig?.extra?.localOnly)return;const timer=setInterval(()=>{void localRequest('/local/weekly').then(r=>{if(r.status==='running')setMessage('PC에서 주간 집계 실행 중');else if(r.exit_code!==undefined)setMessage(r.exit_code===0?'주간 집계 완료 · 미션/랭킹 화면에서 확인':'주간 집계 실패 · .local-data/weekly.log 확인');}).catch(()=>{});},5000);return()=>clearInterval(timer);},[]);
  if(!Constants.expoConfig?.extra?.localOnly)return null;
  return <><Button title={expanded?"개발자 테스트 접기":"개발자 테스트 열기"} quiet onPress={()=>setExpanded(!expanded)}/>{expanded&&<Card><Text style={S.heading}>로컬 통합 테스트</Text><Note>이 PC의 저장된 여정으로 주간 집계 실행. 지급 포인트는 테스트 값입니다.</Note><Button title="주간 집계 실행" busy={busy} onPress={()=>void run()}/><Button title="검증된 개인 기준 연결" quiet disabled={busy} onPress={()=>{setBusy(true);void localAction('/local/baseline-test',{}).then(()=>setMessage('테스트 기준 연결 완료 · 나의 이동 기준에서 확인해주세요.')).catch(e=>setMessage(String(e))).finally(()=>setBusy(false));}}/><Button title="GPS 재생으로 보상 테스트" quiet disabled={busy} onPress={()=>{setBusy(true);setMessage('합성 GPS를 실제 모델로 분석 중이에요.');void localAction('/local/reward-demo',{}).then(r=>{setReplay(false);setDemoDetail(false);setDemo(r);setMessage('여정 테스트 완료 · 미션에서 달성 내역 확인');}).catch(e=>setMessage(String(e))).finally(()=>setBusy(false));}}/><Button title="6명 주간 통합 결과 보기" quiet disabled={busy} onPress={()=>{setBusy(true);void localAction('/local/scenario').then(setScenario).catch(e=>setMessage(String(e))).finally(()=>setBusy(false));}}/><Note>재생 테스트는 2km 합성 여정을 내 계정에 추가합니다. 실제 이동 기록과 구분해 표시합니다.</Note>{!!message&&<Note>{message}</Note>}</Card>}
    <Modal visible={!!scenario} animationType="slide" onRequestClose={()=>setScenario(null)}><SafeAreaView style={S.root}><ScrollView contentContainerStyle={S.scroll}><Button title="주간 예제 닫기" quiet onPress={()=>setScenario(null)}/><Text style={S.heading}>실제 계산된 통합 시나리오</Text><Note>6명 · {scenario?.inputTrips}개 합성 여정 / {scenario?.user} 기준. 내 계정의 실제 기록과 지갑에는 합산되지 않습니다.</Note><Button title="개인·전체 기준" quiet onPress={()=>setPanel('baseline')}/><Button title="캠페인 랭킹" quiet onPress={()=>setPanel('ranking')}/><Button title="주간·랭킹 보상" quiet onPress={()=>setPanel('rewards')}/>{scenario&&(panel==='baseline'?<BaselinePanel value={scenario.baseline}/>:panel==='ranking'?<RankingPanel value={scenario.ranking}/>:<RewardPanel value={scenario.rewards}/>)}</ScrollView></SafeAreaView></Modal>
    <Modal visible={!!demo} animationType="slide" onRequestClose={()=>setDemo(null)}><SafeAreaView style={S.root}>{replay&&demo?<JourneyReplay trip={demo} onClose={()=>setReplay(false)}/>:<ScrollView contentContainerStyle={S.scroll}><Button title="기록으로 이동 화면 재생" quiet onPress={()=>setReplay(true)}/><Button title="테스트 결과 닫기" quiet onPress={()=>setDemo(null)}/>{demo&&(demoDetail?<><Button title="여정 결과로 돌아가기" quiet onPress={()=>setDemoDetail(false)}/><TripResult trip={demo} onFeedback={async input=>{const next=await localAction(`/trips/${demo.trip_id}/feedback`,{request_id:randomUUID(),...input});setDemo(next);}}/></>:<JourneyComplete trip={demo} onDetail={()=>setDemoDetail(true)} onWallet={()=>setDemo(null)}/>)}</ScrollView>}</SafeAreaView></Modal></>;
}
