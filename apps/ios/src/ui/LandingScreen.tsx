import Text from './AppText';
import React,{useEffect,useRef,useState} from 'react';
import {Animated,Image,ImageBackground,Platform,Pressable,ScrollView,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {LinearGradient} from 'expo-linear-gradient';
import {CanopyMascot} from './CanopyMascot';
import {Button,C,Note,S} from './theme';
import {useReducedMotion} from './DesignPrimitives';
let introSeen=false;
export function LandingScreen({onLogin,onSignup,onContinue,nickname,ready,error}:{onLogin():void;onSignup():void;onContinue?:()=>void;nickname?:string;ready:boolean;error?:string}){
 const reduced=useReducedMotion(),[intro,setIntro]=useState(!introSeen),fade=useRef(new Animated.Value(1)).current;
 function finish(){introSeen=true;Animated.timing(fade,{toValue:0,duration:reduced?0:550,useNativeDriver:Platform.OS!=='web'}).start(({finished})=>{if(finished)setIntro(false);});}
 useEffect(()=>{if(!intro)return;const timer=setTimeout(finish,3200);return()=>{clearTimeout(timer);fade.stopAnimation();};},[intro,reduced]);
 return <View style={[S.root,{backgroundColor:'#E9F4EF'}]}>
  <ImageBackground source={require('../../assets/canopy-ui/premium/slogan-garden.png')} resizeMode="cover" style={{flex:1}}>
   <LinearGradient colors={['#F4FBFFAA','#FFFFFF00','#E8F4EEF5']} locations={[0,.52,1]} style={{flex:1}}>
    <SafeAreaView style={{flex:1}}><ScrollView contentContainerStyle={{flexGrow:1,padding:28,gap:22,justifyContent:'space-between'}}>
     <View style={{alignItems:'center',paddingTop:26,gap:12}}><Image source={require('../../assets/canopy-ui/canopy-wordmark-v2.png')} resizeMode="contain" style={{width:200,height:54}} accessibilityLabel="CANOPY"/><Text style={{fontSize:12,color:'#396856',letterSpacing:1,textAlign:'center'}}>A Greener Tomorrow Together</Text></View>
     <View style={{alignItems:'center',gap:8}}><CanopyMascot pose="start" height={245}/><View style={{backgroundColor:'#FFFFFFE8',borderRadius:22,paddingHorizontal:22,paddingVertical:16,borderWidth:1,borderColor:'white',boxShadow:'0 8px 26px #15382F14'}}><Text style={{color:C.deep,fontSize:20,lineHeight:29,fontWeight:'700',textAlign:'center'}}>작은 이동이 만드는,{'\n'}더 큰 변화.</Text></View></View>
     <View style={{gap:12}}>{!!error&&<Note error>{error}</Note>}{nickname&&onContinue?<Button title={`${nickname}님으로 계속`} disabled={!ready} onPress={onContinue}/>:<Button title="로그인" onPress={onLogin}/>}<Button title="처음이에요 · 시작하기" quiet onPress={onSignup}/></View>
    </ScrollView></SafeAreaView>
   </LinearGradient>
  </ImageBackground>
  {intro&&<Animated.View style={{position:'absolute',top:0,left:0,right:0,bottom:0,opacity:fade,zIndex:20}}><ImageBackground source={require('../../assets/canopy-ui/premium/slogan-garden.png')} resizeMode="cover" style={{flex:1}}><LinearGradient colors={['#EDF8FF22','#17433300','#103E33ED']} locations={[0,.6,1]} style={{flex:1}}><SafeAreaView style={{flex:1,padding:28,justifyContent:'space-between'}}><View><Pressable accessibilityRole="button" accessibilityLabel="소개 건너뛰기" onPress={finish} style={{alignSelf:'flex-end',padding:12}}><Text style={{fontSize:12,color:C.deep}}>건너뛰기</Text></Pressable><Text style={{fontSize:35,lineHeight:46,fontWeight:'600',fontStyle:'italic',letterSpacing:-1,color:'#235446',textAlign:'center',marginTop:22}}>A Greener{'\n'}Tomorrow{'\n'}Together</Text></View><View style={{gap:14,paddingBottom:34}}><Text style={{fontSize:27,lineHeight:39,color:'white',fontWeight:'700'}}>작은 이동이 만드는{'\n'}더 큰 변화</Text><Text style={{color:'#D4EADD',fontSize:14}}>지금, 캐노피와 함께해요.</Text><Pressable accessibilityRole="button" onPress={finish} style={{minHeight:48,justifyContent:'center'}}><Text style={{fontSize:14,color:'white',fontWeight:'700'}}>시작하기 →</Text></Pressable></View></SafeAreaView></LinearGradient></ImageBackground></Animated.View>}
 </View>;
}
