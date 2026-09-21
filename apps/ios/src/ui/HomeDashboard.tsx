import Text from './AppText';
import React from 'react';
import {View} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {CanopyMascot} from './CanopyMascot';
import {C,Icon,Note,S,Fade} from './theme';
import {Touch,Eyebrow,SectionTitle,ProgressTrack} from './DesignPrimitives';
import type {ServiceProps} from './ServiceScreen';
export function HomeDashboard({p,busy,onRoute,onResult,onBaseline,onRewards,onMissions}:{p:ServiceProps;busy:boolean;onRoute(direction:'outbound'|'return'):void;onResult():void;onBaseline():void;onRewards():void;onMissions():void}){
 const baseline=p.baseline?.state==='ready'?p.baseline.data:null,balance=p.rewards?.state==='ready'?p.rewards.data.balance:null;
 const done=p.trips.filter(t=>t.status==='completed').length;
 return <View style={{padding:22,gap:24}}>
  <Fade><View style={{gap:6}}><Eyebrow>MOVE LIGHT. LIVE GREEN.</Eyebrow><Text style={S.title}>{p.profile.nickname}님,{'\n'}오늘은 어디로 갈까요?</Text></View></Fade>
  <Touch onPress={()=>onRoute('outbound')} label="출근 경로 찾기" style={{borderRadius:30,overflow:'hidden'}}>
   <LinearGradient colors={['#173F33','#0C2823']} start={{x:0,y:0}} end={{x:1,y:1}} style={{padding:24,minHeight:245}}>
    <View style={S.between}><Text style={{color:C.leaf,fontSize:12,fontWeight:'700'}}>나의 이동이 보상이 되는 곳</Text><Icon name="sparkles" size={18} color={C.leaf}/></View>
    <View style={{flexDirection:'row',alignItems:'center',flex:1}}><View style={{flex:1,gap:12,zIndex:1}}><Text style={{fontSize:29,lineHeight:39,fontWeight:'700',color:'white'}}>가벼운 발걸음,{'\n'}쌓이는 토큰.</Text><View style={{flexDirection:'row',alignItems:'center',gap:8,marginTop:8}}><Text style={{color:C.leaf,fontSize:14,fontWeight:'700'}}>지금 출발하기</Text><Icon name="arrow-forward-circle" color={C.leaf} size={25}/></View></View><View style={{width:'43%',marginRight:-10}}><CanopyMascot pose="run" height={185}/></View></View>
   </LinearGradient>
  </Touch>
  <View style={{flexDirection:'row',gap:12}}>{([['outbound','출근','business-outline'],['return','퇴근','home-outline']] as const).map(([direction,title,icon])=><Touch key={direction} onPress={()=>onRoute(direction)} style={{flex:1,backgroundColor:C.white,borderRadius:20,borderWidth:1,borderColor:C.line}}><View style={[S.between,{padding:18}]}><View style={{gap:10}}><Icon name={icon} size={24}/><Text style={S.label}>{busy?'이동 중':title}</Text></View><Icon name="arrow-up-right-box-outline" size={18}/></View></Touch>)}</View>
  <Touch onPress={onRewards} label="내 지갑 열기" style={{backgroundColor:C.leaf,borderRadius:24}}><View style={[S.between,{paddingHorizontal:22,paddingVertical:20}]}><View style={{gap:4}}><Text style={{color:C.deep,fontSize:12,fontWeight:'600'}}>차곡차곡, 내 토큰</Text><Text style={{fontSize:34,fontWeight:'700',letterSpacing:-1.5,color:C.deep}}>{balance==null?'—':balance.toLocaleString('ko-KR',{maximumFractionDigits:2})}<Text style={{fontSize:17}}> T</Text></Text></View><View style={{width:72}}><CanopyMascot pose="coin" height={72} animated/></View><Icon name="chevron-forward" size={18}/></View></Touch>
  <View style={{gap:14}}><SectionTitle title="나의 초록 발자국" action="보상 기준" onPress={onBaseline}/><View style={{flexDirection:'row',gap:12}}><View style={[S.card,{flex:1,padding:18}]}><Icon name="footsteps-outline"/><Text style={S.note}>완료한 여정</Text><Text style={S.metric}>{done}<Text style={{fontSize:13}}> 회</Text></Text></View><Touch onPress={onBaseline} style={[S.card,{flex:1,padding:18}]}><View style={{gap:12}}><Icon name="leaf-outline"/><Text style={S.note}>나의 보상 기준</Text><Text style={[S.label,{fontSize:17}]}>{baseline?.personalKg==null?'첫날부터 보상':`${baseline.personalKg.toFixed(1)} g/km`}</Text></View></Touch></View><Note>{baseline?.personalKg==null?'경로를 고르면 출발 전에 보상 기준을 알려드려요.':'기준보다 탄소를 줄이면 토큰이 쌓여요.'}</Note></View>
  {p.missions?.state==='ready'&&p.missions.data.items.filter(m=>m.status==='active').slice(0,1).map(m=><View key={m.id} style={[S.card,{backgroundColor:'#EFF3E7',borderWidth:0}]}><View style={S.between}><Eyebrow>YOUR NEXT CHALLENGE</Eyebrow><Icon name="flag-outline"/></View><Text style={S.heading}>{m.title}</Text><ProgressTrack value={m.progress} max={m.goal}/><View style={S.between}><Note>{m.progress} / {m.goal} {m.unit}</Note><Text style={S.link}>+{m.rewardPoints??0} T</Text></View><Touch onPress={onMissions} label="미션 자세히 보기"><View style={[S.between,{minHeight:44}]}><Text style={S.link}>미션 보기</Text><Icon name="arrow-forward" size={18}/></View></Touch></View>)}
  {p.serverTrip?.status==='ready'&&!busy&&<Touch onPress={onResult}><View style={[S.between,{paddingVertical:12}]}><Text style={S.link}>최근 여정 돌아보기</Text><Icon name="arrow-forward" size={18}/></View></Touch>}
 </View>;
}
