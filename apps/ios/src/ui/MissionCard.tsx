import React,{useEffect,useRef,useState} from 'react';
import {Animated,AppState,Easing,Platform,Pressable,View} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import * as Haptics from 'expo-haptics';
import Text from './AppText';
import {C,Icon,Note,S,Button} from './theme';
import {Disclosure,ProgressTrack,useReducedMotion} from './DesignPrimitives';
import {IllustratedIcon,missionArt} from './IllustratedIcon';
import type {MissionView} from './CommunityPanels';

const stamped=new Set<string>();
type Item=MissionView['items'][number];
export function MissionCard({mission:m,week,busy,onClaim,leaving=false}:{mission:Item;week:string;busy:boolean;onClaim():void;leaving?:boolean}){
 const reduced=useReducedMotion(),stamp=useRef(new Animated.Value(0)).current,shine=useRef(new Animated.Value(0)).current,exit=useRef(new Animated.Value(0)).current;
 const [showStamp,setShowStamp]=useState(false),[foreground,setForeground]=useState(AppState.currentState==='active');
 const achieved=m.status==='claimable'||m.status==='completed';
 useEffect(()=>{const s=AppState.addEventListener('change',v=>setForeground(v==='active'));return()=>s.remove();},[]);
 useEffect(()=>{
  const key=week+':'+m.id;
  setShowStamp(achieved);
  if(!achieved){stamp.setValue(0);return;}
  if(stamped.has(key)||reduced||m.status==='completed'){stamp.setValue(1);return;}
  stamped.add(key);stamp.setValue(0);
  const a=Animated.timing(stamp,{toValue:1,duration:420,easing:Easing.out(Easing.back(1.7)),useNativeDriver:Platform.OS!=='web'});
  a.start();void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(()=>{});
  return()=>a.stop();
 },[achieved,m.id,m.status,week,reduced]);
 useEffect(()=>{if(m.status!=='claimable'||reduced||!foreground)return;shine.setValue(0);const a=Animated.loop(Animated.sequence([Animated.timing(shine,{toValue:1,duration:1500,easing:Easing.inOut(Easing.quad),useNativeDriver:Platform.OS!=='web'}),Animated.delay(1600),Animated.timing(shine,{toValue:0,duration:0,useNativeDriver:Platform.OS!=='web'})]));a.start();return()=>a.stop();},[m.status,reduced,foreground]);
 useEffect(()=>{const a=Animated.timing(exit,{toValue:leaving?1:0,duration:reduced?0:400,useNativeDriver:Platform.OS!=='web'});a.start();return()=>a.stop();},[leaving,reduced]);
 return <Animated.View style={{opacity:exit.interpolate({inputRange:[0,1],outputRange:[m.status==='completed'?.65:1,0]}),transform:[{translateX:exit.interpolate({inputRange:[0,1],outputRange:[0,100]})},{scale:exit.interpolate({inputRange:[0,1],outputRange:[1,.93]})}]}}>
  <View style={{backgroundColor:achieved?'#EDF0E6':'#FFFDF5',borderRadius:23,borderTopLeftRadius:10,borderWidth:1.5,borderColor:'#DCE4C8',padding:18,gap:14,boxShadow:'0 4px 0 #E0E8CD',overflow:'hidden'}}>
   <View style={[S.row,{gap:14}]}><IllustratedIcon name={missionArt(m.title)} size={32}/><View style={{flex:1,gap:5}}><Text style={{fontSize:10,fontWeight:'700',letterSpacing:1,color:C.green}}>도전과제</Text><Text style={[S.heading,{fontSize:17,lineHeight:25}]}>{m.title}</Text></View></View>
   {m.week&&m.week!==week&&<Note>{m.week} 주에 달성했어요</Note>}
   <View style={S.between}><Text style={{fontSize:23,fontWeight:'700',color:C.deep}}>{m.progress.toLocaleString()}<Text style={{fontSize:14,color:C.muted}}> / {m.goal.toLocaleString()} {m.unit}</Text></Text><Text style={{fontSize:17,fontWeight:'700',color:'#518B52'}}>+{m.rewardPoints??0} T</Text></View>
   <ProgressTrack value={m.progress} max={m.goal}/>
   {achieved&&<View style={[S.row,{gap:7}]}><Icon name="checkmark-circle" color="#4F9D6C" size={20}/><Text style={{fontSize:12,fontWeight:'700',color:C.green}}>{m.status==='completed'?'보상까지 받았어요':'목표 달성! 보상을 받아요'}</Text></View>}
   <Disclosure title="달성 방법"><Note>{m.description}</Note></Disclosure>

   {showStamp&&<View pointerEvents="none" style={{alignSelf:'flex-end',marginVertical:8,marginRight:4,alignItems:'center',justifyContent:'center'}}><Animated.View style={{borderWidth:3,borderColor:'#3A8558',backgroundColor:'#F5FFF2F0',borderRadius:20,paddingHorizontal:12,paddingVertical:8,opacity:stamp.interpolate({inputRange:[0,.2,1],outputRange:[0,1,1]}),transform:[{scale:stamp.interpolate({inputRange:[0,1],outputRange:[2.1,1]})},{rotate:'-13deg'}]}}><Text style={{color:'#287447',fontSize:20,fontWeight:'700',letterSpacing:3}}>미션 완료</Text><Text style={{textAlign:'center',color:'#287447',fontSize:8,letterSpacing:2}}>WELL DONE!</Text></Animated.View></View>}
   {m.status==='claimable'&&<Pressable accessibilityRole="button" accessibilityLabel="보상 받기" accessibilityState={{disabled:busy,busy}} disabled={busy} onPress={onClaim} style={{borderRadius:18,overflow:'hidden'}}><LinearGradient colors={['#39855A','#13503F']} style={{minHeight:56,alignItems:'center',justifyContent:'center',flexDirection:'row',gap:8,borderRadius:18,borderTopWidth:1,borderColor:'#8EC5A0'}}><Text style={{fontSize:16,color:'white',fontWeight:'700'}}>{busy?'보상 확인 중':'보상 받기'}</Text><Icon name="arrow-forward" color="#DDF5C9" size={18}/><Animated.View pointerEvents="none" style={{position:'absolute',top:-20,bottom:-20,width:45,opacity:.5,transform:[{translateX:shine.interpolate({inputRange:[0,1],outputRange:[-240,240]})},{rotate:'22deg'}]}}><LinearGradient colors={['#FFFFFF00','#FFFFFF99','#FFFFFF00']} style={{flex:1}}/></Animated.View></LinearGradient></Pressable>}
  </View>
 </Animated.View>;
}
