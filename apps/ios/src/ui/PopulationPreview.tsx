import Text from './AppText';
import React from 'react';
import {View} from 'react-native';
import type {PlannedRoute} from '../service';
import {routeBaselineRate} from '../routeQuote';
import type {BaselineView,RemotePanel} from './CommunityPanels';
import {C,S,Note} from './theme';
const labels:Record<string,string>={walk:'도보',bike:'자전거',bicycle:'자전거',car:'승용차',bus:'버스',rail:'철도',subway:'지하철'};
export function PopulationPreview({route,baseline}:{route:PlannedRoute;baseline?:RemotePanel<BaselineView>}){
 const rows=Object.entries(route.modeProbabilities??{}).sort((a,b)=>b[1]-a[1]);
 const personal=baseline?.state==='ready'?baseline.data.personalKg:null;
 const global=baseline?.state==='ready'?baseline.data.globalKg:null;
 const rate=personal??routeBaselineRate(route);
 return <View style={{backgroundColor:'#edf3e5',borderRadius:24,padding:20,gap:12}}>
  <Text style={S.pill}>출발 전 · {personal!=null?'Personal':'KTDB'} 비교 기준</Text>
  <Text style={S.heading}>이 값보다 적게 배출하면 절감 보상 대상이에요</Text>
  <Text style={[S.metric,{fontSize:30}]}>{rate===undefined?'확인 필요':rate.toFixed(2)} <Text style={{fontSize:14}}>gCO₂e/km</Text></Text>
  {rate!==undefined&&<Text style={S.label}>선택 경로 {(route.distance_m/1000).toFixed(2)} km 기준 약 {(rate*route.distance_m/1000).toFixed(2)} gCO₂e</Text>}
  <Note>최종 비교량은 위 거리당 기준 × 실제 확정 이동거리입니다. 절감량이 최소 지급 단위보다 작으면 보상은 0점일 수 있어요.</Note>
  {personal!=null?<><Note>이번 주 고정 개인 기준을 적용합니다.</Note>{global!=null&&<Note>개선 보상에 해당하지 않으면 Global {global.toFixed(2)} gCO₂e/km 이하인지 비교합니다. 기준과 같으면 차액 보상은 0점입니다.</Note>}</>:<Note>개인 기준이 준비되지 않았을 때 적용하는 KTDB 경로 기준입니다. 지정한 출발·도착지와 다르게 이동하면 실제 위치로 다시 계산합니다.</Note>}
  {baseline?.state!=='ready'&&<Note>주간 개인 기준의 준비 여부는 출발 시 서버에서 최종 확인합니다.</Note>}
  <Text style={S.label}>KTDB 예상 이동수단 비율</Text>
  <Note>모델 예측이며 실제 이용자 집계는 아닙니다.</Note>
  {rows.map(([mode,p])=><View key={mode} style={S.between}><Text style={S.note}>{labels[mode]??mode}</Text><Text style={S.label}>{(p*100).toFixed(1)}%</Text></View>)}
 </View>;
}
