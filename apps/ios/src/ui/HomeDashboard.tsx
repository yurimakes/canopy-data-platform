import React from 'react';
import {Pressable,Text,View} from 'react-native';
import {CanopyMascot} from './CanopyMascot';
import {Button,C,Icon,Note,S} from './theme';
import type {ServiceProps} from './ServiceScreen';
export function HomeDashboard({p,busy,onRoute,onResult,onBaseline,onRewards}:{p:ServiceProps;busy:boolean;onRoute(direction:'outbound'|'return'):void;onResult():void;onBaseline():void;onRewards():void}){
 const baseline=p.baseline?.state==='ready'?p.baseline.data:null,balance=p.rewards?.state==='ready'?p.rewards.data.balance:null;
 return <View style={{padding:20,gap:18}}>
  <View style={{backgroundColor:'#e8efdc',borderRadius:32,padding:24,paddingBottom:12,overflow:'hidden'}}>
   <Text style={{color:'#67824e',letterSpacing:1.8,fontSize:10,fontWeight:'800'}}>MAKE YOUR WAY GREENER</Text>
   <Text style={[S.title,{fontSize:30,lineHeight:40,marginTop:14}]}>{p.profile.nickname}님,{ '\n'}오늘의 이동도{ '\n'}가볍게 시작해요.</Text>
   <View style={{marginTop:-42,marginLeft:80,height:200}}><CanopyMascot height={200}/></View>
   <Text style={[S.note,{marginTop:-12,marginBottom:12}]}>더 나은 선택을, 캐노피와 함께.</Text>
  </View>
  <View style={{flexDirection:'row',gap:12}}>{([['outbound','출근하기','직장으로','business-outline'],['return','퇴근하기','집으로','home-outline']] as const).map(([direction,title,sub,icon])=><Pressable key={direction} accessibilityRole="button" onPress={()=>onRoute(direction)} style={{flex:1,backgroundColor:direction==='outbound'?C.deep:C.white,borderRadius:26,padding:20,gap:16,borderWidth:1,borderColor:C.line}}><View style={{width:42,height:42,alignItems:'center',justifyContent:'center',borderRadius:14,backgroundColor:direction==='outbound'?'#ffffff18':C.mint}}><Icon name={icon} color={direction==='outbound'?'#c9e6a3':C.green}/></View><View style={{gap:5}}><Text style={{color:direction==='outbound'?'#b8d6c7':C.muted,fontSize:12}}>{sub}</Text><Text style={{color:direction==='outbound'?'white':C.deep,fontSize:19,fontWeight:'800'}}>{busy?'여정 계속하기':title}</Text></View></Pressable>)}</View>
  {p.serverTrip?.status==='ready'&&!busy&&<Button title="최근 여정 결과 다시 보기" quiet onPress={onResult}/>}
  <Pressable accessibilityRole="button" onPress={onBaseline} style={[S.card,{gap:12}]}><View style={S.between}><Text style={S.heading}>이번 주, 나의 탄소 기준</Text><Icon name="chevron-forward" size={17}/></View><Text style={[S.metric,{fontSize:30}]}>{baseline?.personalKg==null?'기록을 쌓는 중':baseline.personalKg.toFixed(2)}{baseline?.personalKg!=null&&<Text style={{fontSize:13}}> {baseline.unit??'gCO₂e/km'}</Text>}</Text><Note>{baseline?.personalKg==null?'개인 기준이 준비되기 전에는 출발 전 KTDB 경로 기준을 확인해보세요.':'개인 기준보다 낮게 배출하면 개선 보상에 도전할 수 있어요.'}</Note></Pressable>
  <Pressable accessibilityRole="button" onPress={onRewards} style={{flexDirection:'row',alignItems:'center',backgroundColor:'#f5efdf',borderRadius:26,padding:16,gap:10}}><View style={{width:84}}><CanopyMascot pose="coin" height={100}/></View><View style={{flex:1,gap:6}}><Text style={S.note}>나의 실천이 모인 지갑</Text><Text style={[S.metric,{fontSize:28}]}>{balance==null?'—':balance.toLocaleString('ko-KR',{maximumFractionDigits:2})} T</Text></View><Icon name="chevron-forward" size={17}/></Pressable>
 </View>;
}
