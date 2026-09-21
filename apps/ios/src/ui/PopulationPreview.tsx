import Text from './AppText';
import React from 'react';
import {View} from 'react-native';
import type {PlannedRoute} from '../service';
import {routeBaselineRate} from '../routeQuote';
import type {BaselineView,RemotePanel} from './CommunityPanels';
import {C,S,Note,Icon} from './theme';
import {Disclosure,Eyebrow} from './DesignPrimitives';
const labels:Record<string,string>={walk:'걷기',bike:'자전거',bicycle:'자전거',car:'자동차',bus:'버스',rail:'철도',subway:'지하철'};
export function PopulationPreview({route,baseline}:{route:PlannedRoute;baseline?:RemotePanel<BaselineView>}){
 const rows=Object.entries(route.modeProbabilities??{}).sort((a,b)=>b[1]-a[1]);
 const personal=baseline?.state==='ready'?baseline.data.personalKg:null;
 const rate=personal??routeBaselineRate(route);
 return <View style={{backgroundColor:'#EAF3DE',borderRadius:22,padding:20,gap:12}}>
 <View style={S.between}><Eyebrow>출발 전 보상 기준</Eyebrow><Icon name="leaf-outline" size={21}/></View>
 <Text style={S.heading}>탄소를 줄이고, 토큰을 모아요.</Text>
 <View style={{flexDirection:'row',alignItems:'baseline',gap:6}}><Text style={{fontSize:34,fontWeight:'700',letterSpacing:-1.3,color:C.deep}}>{rate===undefined?'확인 중':rate.toFixed(1)}</Text><Text style={S.note}>g / km</Text></View>
 <Note>1km마다 이 기준보다 적게 배출하면 보상 대상이에요.</Note>
 <Disclosure title="어떻게 계산하나요?">
 <Note>{personal!=null?'이번 주 나의 이동 기록으로 정한 기준이에요.':'기록이 없는 첫날에는 교통 통계로 기준을 정해요.'}</Note>
 {rate!==undefined&&<Note>선택한 경로 {(route.distance_m/1000).toFixed(1)}km의 예상 기준은 {(rate*route.distance_m/1000).toFixed(1)}g이에요.</Note>}
 <Note>실제 이동거리로 최종 계산해요. 절감량이 적으면 토큰이 없을 수 있어요.</Note>
 {personal==null&&<><Note>출처: 국가교통DB(KTDB) 이동 예측. 아래 비율은 실제 이용 통계가 아닌 모델 예상값이에요.</Note>{rows.map(([mode,n])=><View key={mode} style={S.between}><Text style={S.note}>{labels[mode]??mode}</Text><Text style={S.label}>{(n*100).toFixed(1)}%</Text></View>)}</>}
 </Disclosure></View>;
}
