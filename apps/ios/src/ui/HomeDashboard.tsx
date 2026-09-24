import Text from './AppText';
import React,{useState} from 'react';
import {View,Image} from 'react-native';
import {IllustratedIcon} from './IllustratedIcon';
import {MascotConversation} from './MascotConversation';
import {LinearGradient} from 'expo-linear-gradient';
import {CanopyMascot} from './CanopyMascot';
import {C,Icon,Note,S,Fade} from './theme';
import {Touch,Eyebrow,SectionTitle,ProgressTrack} from './DesignPrimitives';
import type {ServiceProps} from './ServiceScreen';
export function HomeDashboard({p,busy,onRoute,onResult,onBaseline,onRewards,onMissions}:{p:ServiceProps;busy:boolean;onRoute(direction:'outbound'|'return'):void;onResult():void;onBaseline():void;onRewards():void;onMissions():void}){
 const [heroWidth,setHeroWidth]=useState(346);
 const baseline=p.baseline?.state==='ready'?p.baseline.data:null,balance=p.rewards?.state==='ready'?p.rewards.data.balance:null;
 const done=p.trips.filter(t=>t.status==='completed').length;
 return <View style={{padding:22,paddingTop:6,gap:20}}>
  <View onLayout={e=>setHeroWidth(e.nativeEvent.layout.width)} style={{borderRadius:34,overflow:'hidden',minHeight:300,backgroundColor:'#EDF7E6',justifyContent:'flex-end',padding:18,paddingBottom:12}}>
   <Image source={require('../../assets/canopy-ui/home-park.png')} resizeMode="cover" style={{position:'absolute',bottom:0,left:0,width:'100%',height:Math.max(300,heroWidth*1672/940)}}/>
   <MascotConversation greeting message={busy?'안전하게 도착해요!':`안녕하세요 ${p.profile.nickname}님,\n오늘도 가볍게 시작해볼까요?`}/>
  </View>
  <Touch onPress={()=>onRoute('outbound')} label="나의 이동 시작하기" style={{borderRadius:24,backgroundColor:'#DDF1CB',marginTop:-7}}><View style={{borderRadius:24,backgroundColor:'#DDF1CB',borderWidth:1,borderColor:'#F4FFE9',minHeight:72,paddingVertical:13,paddingHorizontal:19,flexDirection:'row',alignItems:'center',justifyContent:'center',gap:14}}><Text style={{flexShrink:1,fontSize:17,fontWeight:'700',color:'#24513D'}}>{busy?'진행 중인 여정':'나의 이동 시작하기'}</Text></View></Touch>
  <Touch onPress={onRewards} label="내 지갑 열기" style={{backgroundColor:'#E6F0D9',borderRadius:24,borderWidth:1,borderColor:'white'}}><View style={[S.between,{paddingHorizontal:22,paddingVertical:20}]}><View style={{gap:4}}><Text style={{color:C.deep,fontSize:12,fontWeight:'600'}}>차곡차곡, 내 토큰</Text><Text style={{fontFamily:'Nunito_800ExtraBold',fontSize:37,letterSpacing:-.5,color:C.deep}}>{balance==null?'—':balance.toLocaleString('ko-KR',{maximumFractionDigits:2})}<Text style={{fontSize:17}}> T</Text></Text></View><View style={{width:72}}><CanopyMascot pose="coin" height={72} animated/></View><Icon name="chevron-forward" size={18}/></View></Touch>
  <View style={{gap:14}}><SectionTitle title="나의 초록 발자국" action="보상 기준" onPress={onBaseline}/><View style={{flexDirection:'row',gap:12}}><View style={[S.card,{flex:1,padding:18}]}><IllustratedIcon name="walk" size={46}/><Text style={S.note}>완료한 여정</Text><Text style={S.metric}>{done}<Text style={{fontSize:13}}> 회</Text></Text></View><Touch onPress={onBaseline} style={[S.card,{flex:1,padding:18}]}><View style={{gap:12}}><IllustratedIcon name="leaf" size={46}/><Text style={S.note}>나의 보상 기준</Text><Text style={[S.label,{fontSize:17}]}>{baseline?.personalKg==null?'첫날부터 보상':`${baseline.personalKg.toFixed(1)} g/km`}</Text></View></Touch></View><Note>{baseline?.personalKg==null?'경로를 고르면 출발 전에 보상 기준을 알려드려요.':'기준보다 탄소를 줄이면 토큰이 쌓여요.'}</Note></View>
  {p.missions?.state==='ready'&&p.missions.data.items.filter(m=>m.status==='active').slice(0,1).map(m=><View key={m.id} style={[S.card,{backgroundColor:'#E6F0D9',borderWidth:0}]}><View style={S.between}><Eyebrow>YOUR NEXT CHALLENGE</Eyebrow><IllustratedIcon name="mission" size={48}/></View><Text style={S.heading}>{m.title}</Text><ProgressTrack value={m.progress} max={m.goal}/><View style={S.between}><Note>{m.progress} / {m.goal} {m.unit}</Note><Text style={S.link}>+{m.rewardPoints??0} T</Text></View><Touch onPress={onMissions} label="미션 자세히 보기"><View style={[S.between,{minHeight:44}]}><Text style={S.link}>미션 보기</Text><Icon name="arrow-forward" size={18}/></View></Touch></View>)}
  {p.serverTrip?.status==='ready'&&!busy&&<Touch onPress={onResult}><View style={[S.between,{paddingVertical:12}]}><Text style={S.link}>최근 여정 돌아보기</Text><Icon name="arrow-forward" size={18}/></View></Touch>}
 </View>;
}
