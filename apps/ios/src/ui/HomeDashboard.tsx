import {SoftSpeechBubble} from './SoftSpeechBubble';
import Text from './AppText';
import React,{useState,useEffect} from 'react';
import {View,Image,AppState} from 'react-native';
import {IllustratedIcon} from './IllustratedIcon';
import {MissionCard} from './MissionCard';
import {CanopyMascot} from './CanopyMascot';
import {C,Icon,Note,S,Fade} from './theme';
import {Touch,Eyebrow,SectionTitle,ProgressTrack,useReducedMotion} from './DesignPrimitives';
import type {ServiceProps} from './ServiceScreen';
export function HomeDashboard({p,busy,onRoute,onResult,onBaseline,onRewards,onMissions}:{p:ServiceProps;busy:boolean;onRoute(direction:'outbound'|'return'):void;onResult():void;onBaseline():void;onRewards():void;onMissions():void}){
 const message=`안녕하세요 ${p.profile.nickname}님,\n${busy?'안전하게 도착해요!':'오늘도 가볍게\n시작해볼까요?'}`;
 const reduced=useReducedMotion(),[typed,setTyped]=useState(0);
 useEffect(()=>{setTyped(0);if(reduced){setTyped(Array.from(message).length);return;}const timer=setInterval(()=>setTyped(n=>{if(n>=Array.from(message).length)clearInterval(timer);return n+1;}),65);return()=>clearInterval(timer);},[message,reduced]);
 const [foreground,setForeground]=useState(AppState.currentState==='active');
 useEffect(()=>{const sub=AppState.addEventListener('change',state=>setForeground(state==='active'));return()=>sub.remove();},[]);
 const [heroWidth,setHeroWidth]=useState(350);
 const baseline=p.baseline?.state==='ready'?p.baseline.data:null,balance=p.rewards?.state==='ready'?p.rewards.data.balance:null;
 const done=p.trips.filter(t=>t.status==='completed').length;
 return <View style={{padding:20,paddingTop:6,gap:20}}>
  <View onLayout={event=>setHeroWidth(event.nativeEvent.layout.width)} style={{height:259,borderRadius:28,borderBottomRightRadius:46,overflow:'hidden',backgroundColor:'#E9F1CE'}}>
   <Image source={require('../../assets/design-preview/park.png')} resizeMode="cover" style={{position:'absolute',bottom:0,width:'100%',height:heroWidth*1672/940}}/>
   <Text style={{position:'absolute',left:18,top:16,color:'#3F6545',fontSize:10,fontWeight:'800',letterSpacing:1.3}}>A LITTLE GREENER, EVERY DAY</Text>
   <View style={{position:'absolute',left:-17,bottom:-7,width:210}}><Image source={reduced||!foreground?require('../../assets/mascot/home-idle-still.png'):require('../../assets/mascot/home-idle.gif')} resizeMode="contain" style={{width:210,height:218}} accessibilityLabel="인사하고 따봉하는 캐노피"/></View>
   <View style={{position:'absolute',top:48,right:10,width:'55%'}}><SoftSpeechBubble><View accessibilityLabel={message}><Text accessible={false} style={{fontSize:16,lineHeight:25,color:'transparent'}}>{message}</Text><Text accessible={false} style={{position:'absolute',top:0,left:0,right:0,bottom:0,fontSize:16,lineHeight:25,color:C.deep}}>{Array.from(message).slice(0,typed).join('')}</Text></View></SoftSpeechBubble></View>
  </View>
  <Touch onPress={()=>onRoute('outbound')} label="나의 이동 시작하기" style={{borderRadius:19,backgroundColor:'#D8EC9A',marginTop:-6}}><View style={{borderRadius:24,backgroundColor:'#D8EC9A',borderWidth:1,borderColor:'#F4FFE9',minHeight:55,paddingVertical:13,paddingHorizontal:19,flexDirection:'row',alignItems:'center',justifyContent:'center',gap:14}}><Text style={{flexShrink:1,fontSize:17,fontWeight:'700',color:'#24513D'}}>{busy?'진행 중인 여정':'나의 이동 시작하기'}</Text></View></Touch>
  <Touch onPress={onRewards} label="내 지갑 열기" style={{backgroundColor:'#ECF1D8',borderRadius:24,borderWidth:1,borderColor:'white'}}><View style={[S.between,{paddingHorizontal:18,paddingVertical:19}]}><View style={{gap:4}}><Text style={{color:C.deep,fontSize:12,fontWeight:'600'}}>차곡차곡, 내 토큰</Text><Text style={{fontFamily:'Jua',fontSize:32,letterSpacing:-.5,color:C.deep}}>{balance==null?'—':balance.toLocaleString('ko-KR',{maximumFractionDigits:2})}<Text style={{fontSize:17}}> T</Text></Text></View><View style={{width:52}}><CanopyMascot pose="coin" height={52} animated/></View><Icon name="chevron-forward" size={18}/></View></Touch>
  <View style={{gap:14}}><SectionTitle title="나의 초록 발자국" action="보상 기준" onPress={onBaseline}/><View style={{flexDirection:'row',gap:12}}><View style={[S.card,{flex:1,padding:16,gap:7,backgroundColor:'white'}]}><IllustratedIcon name="walk" size={26}/><Text style={S.note}>완료한 여정</Text><Text style={S.metric}>{done}<Text style={{fontSize:13}}> 회</Text></Text></View><Touch onPress={onBaseline} style={[S.card,{flex:1,padding:16,gap:7,backgroundColor:'#F2EDE3'}]}><View style={{gap:7}}><IllustratedIcon name="leaf" size={26}/><Text style={S.note}>탄소 비교 기준</Text><Text style={[S.label,{fontSize:17}]}>{!baseline?'기준 확인 필요':baseline.personalKg==null?'경로별로 확인':`${baseline.personalKg.toFixed(1)} g/km`}</Text></View></Touch></View>{(!baseline||baseline.personalKg!=null)&&<Note>{!baseline?'카드를 눌러 비교 기준을 확인해주세요.':'1km당 탄소 배출량을 비교하는 나의 기준이에요. 실제 절감량과 보상 조건에 따라 토큰이 정해져요.'}</Note>}</View>
  {p.missions?.state==='ready'&&p.missions.data.items.filter(m=>m.status==='active').slice(0,1).map(m=><View key={m.id} style={{gap:14}}><SectionTitle title="이번 주, 작은 도전" action="모두 보기" onPress={onMissions}/><MissionCard mission={m} week={p.missions?.state==='ready'?p.missions.data.week:''} busy={false} onClaim={onMissions}/></View>)}
  {p.serverTrip?.status==='ready'&&!busy&&<Touch onPress={onResult}><View style={[S.between,{paddingVertical:12}]}><Text style={S.link}>최근 여정 돌아보기</Text><Icon name="arrow-forward" size={18}/></View></Touch>}
 </View>;
}
