import React from 'react';
import {Text,View} from 'react-native';
import type {PlannedRoute} from '../service';
import {C,S,Note} from './theme';
const labels:Record<string,string>={walk:'도보',bike:'자전거',bicycle:'자전거',car:'승용차',bus:'버스',rail:'철도',subway:'지하철'};
export function PopulationPreview({route}:{route:PlannedRoute}){
 const rows=Object.entries(route.modeProbabilities??{}).sort((a,b)=>b[1]-a[1]);
 return <View style={{backgroundColor:'#edf3e5',borderRadius:24,padding:20,gap:13}}>
  <Text style={{fontSize:11,letterSpacing:1.5,color:'#60764b',fontWeight:'700'}}>BEFORE YOUR JOURNEY</Text>
  <Text style={S.heading}>이 길, 보통 어떻게 이동할까요?</Text>
  <Note>KTDB 모델이 예상한 이동수단 비율이에요. 실제 이용자 집계와는 달라요.</Note>
  {rows.map(([mode,p])=><View key={mode} style={{gap:6}}><View style={S.between}><Text style={S.label}>{labels[mode]??mode}</Text><Text style={S.label}>{(p*100).toFixed(1)}%</Text></View><View style={{height:6,backgroundColor:'#dce6d0',borderRadius:6,overflow:'hidden'}}><View style={{width:`${Math.max(0,Math.min(100,p*100))}%`,height:6,backgroundColor:C.green,borderRadius:6}}/></View></View>)}
  {!rows.length&&<Note>이 경로의 이동수단별 예측 비율은 제공되지 않았어요. 경로를 다시 검색해주세요.</Note>}
  <View style={{borderTopWidth:1,borderColor:'#d5e2ca',paddingTop:14,gap:5}}><Text style={S.note}>이 여정의 예상 탄소 배출량</Text><Text style={[S.metric,{fontSize:30}]}>{route.expectedKg===undefined?'—':(route.expectedKg*1000).toFixed(0)} <Text style={{fontSize:14}}>gCO₂e</Text></Text><Note>지정한 경로를 완료하고 이보다 적게 배출하면 여정 보상 대상이 돼요.</Note></View>
 </View>;
}
