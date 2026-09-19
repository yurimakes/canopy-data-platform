import React,{useEffect,useState} from 'react';
import Constants from 'expo-constants';
import {session} from '../accountSession';
import {accountConfig} from '../accountConfig';
import {Text} from 'react-native';
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
  const [message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  const run=async()=>{setBusy(true);try{const r=await localRequest('/local/weekly','POST');setMessage(r.message);}catch(e){setMessage(String(e));}finally{setBusy(false);}};
  useEffect(()=>{if(!Constants.expoConfig?.extra?.localOnly)return;const timer=setInterval(()=>{void localRequest('/local/weekly').then(r=>{if(r.status==='running')setMessage('PC에서 주간 집계 실행 중');else if(r.exit_code!==undefined)setMessage(r.exit_code===0?'주간 집계 완료 · 미션/랭킹 화면에서 확인':'주간 집계 실패 · .local-data/weekly.log 확인');}).catch(()=>{});},5000);return()=>clearInterval(timer);},[]);
  if(!Constants.expoConfig?.extra?.localOnly)return null;
  return <Card><Text style={S.heading}>로컬 통합 테스트</Text><Note>이 PC의 저장된 여정으로 주간 집계 실행. 지급 포인트는 테스트 값입니다.</Note><Button title="주간 집계 실행" busy={busy} onPress={()=>void run()}/>{!!message&&<Note>{message}</Note>}</Card>;
}
