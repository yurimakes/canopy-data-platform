import Text from './AppText';
import React,{useState} from 'react';
import {Modal,Pressable,ScrollView,View} from 'react-native';
import {SafeAreaView,SafeAreaProvider} from 'react-native-safe-area-context';
import type {PlannedRoute} from '../service';
import {routeCarbon} from '../routeCarbon';
import type {BaselineView,RemotePanel} from './CommunityPanels';
import {C,S,Note,Icon,Button} from './theme';
export function PopulationPreview({route,baseline,compact=false}:{route:PlannedRoute;baseline?:RemotePanel<BaselineView>;compact?:boolean}){
 const [open,setOpen]=useState(false);
 const data=routeCarbon(route,baseline?.state==='ready'?baseline.data.personalKg:null);
 const amount=(n:number|null)=>n==null?'확인 중':`${(n*1000).toFixed(0)} g`;
 const percent=data.percent==null?'비교 준비 중':`${Math.abs(data.percent)}% ${data.percent>=0?'덜':'더'} 배출 예상`;
 const max=Math.max(data.baseline??0,data.estimate??0,.001);
 const graph=<View style={{gap:12}}>{[{label:'비교 기준',value:data.baseline,color:'#CCD6BE'},{label:'이 경로 예상 배출량',value:data.estimate,color:'#87AF65'}].map(row=><View key={row.label} style={{gap:5}}><View style={S.between}><Text style={{fontSize:12,color:C.muted}}>{row.label}</Text><Text style={{fontSize:15,fontFamily:'Jua',color:C.deep}}>{amount(row.value)}</Text></View><View style={{height:9,borderRadius:8,backgroundColor:'#E5ECD9'}}><View style={{height:9,borderRadius:8,width:`${(row.value??0)/max*100}%`,backgroundColor:row.color}}/></View></View>)}</View>;
 return <><Pressable accessibilityRole="button" accessibilityLabel="경로 탄소 비교 기준 자세히 보기" onPress={event=>{event.stopPropagation();setOpen(true);}} style={{backgroundColor:'#EFF4E4',borderRadius:20,padding:compact?12:15,gap:12}}>
 <View style={S.between}><View style={{flex:1,gap:4}}><Text style={{fontSize:12,color:C.muted}}>이 경로의 예상 탄소 · CO₂e</Text><View style={{flexDirection:'row',alignItems:'baseline',gap:8,flexWrap:'wrap'}}><Text style={{fontFamily:'Jua',fontSize:compact?22:25,color:C.deep}}>{amount(data.estimate)}</Text><Text style={{fontSize:13,color:data.percent!=null&&data.percent<0?'#96603F':C.green}}>{percent}</Text></View></View><Icon name="leaf-outline" size={25}/></View>
 {graph}<Text style={{fontSize:12,color:C.muted}}>비교 기준 알아보기 ›</Text>
 </Pressable><Modal transparent visible={open} animationType="slide" onRequestClose={()=>setOpen(false)}><SafeAreaProvider><View style={{flex:1,backgroundColor:'#183A3266',justifyContent:'flex-end'}}><SafeAreaView edges={['bottom']} style={{backgroundColor:C.paper,borderTopLeftRadius:28,borderTopRightRadius:28,maxHeight:'75%'}}><ScrollView contentContainerStyle={{padding:24,gap:18}}><Text style={S.title}>이 길은 얼마나 가벼울까요?</Text>{graph}<Text style={S.heading}>{percent}</Text><Note>{data.source==='내 평소 이동 기준'?'평소 나의 이동 기록을 바탕으로 비교해요.':'아직 내 기록이 부족해 교통 통계로 비교 기준을 정했어요.'}</Note><Note>예상 배출량은 이 경로의 이동수단과 거리로 계산해요. 걷는 구간은 탄소 배출 0으로 계산해요.</Note>{data.estimate==null&&<Note>이 경로는 이동 구간 정보가 없어 예상 탄소를 계산할 수 없어요.</Note>}<Note>출발 전 예상값이며 실제 GPS 기록과 다를 수 있어요. 보상은 실제 여정 분석과 지급 조건 확인 후 확정됩니다.</Note><Button title="확인했어요" onPress={()=>setOpen(false)}/></ScrollView></SafeAreaView></View></SafeAreaProvider></Modal></>;
}
