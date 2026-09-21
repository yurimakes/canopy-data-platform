import Text from './AppText';
import React from 'react';
import {ScrollView,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {LinearGradient} from 'expo-linear-gradient';
import {CanopyMascot} from './CanopyMascot';
import {Button,C,Fade,Icon,Note,S} from './theme';
import {Eyebrow} from './DesignPrimitives';
export function LandingScreen({onLogin,onSignup,onContinue,nickname,ready,error}:{onLogin():void;onSignup():void;onContinue?:()=>void;nickname?:string;ready:boolean;error?:string}){
 return <SafeAreaView style={[S.root,{backgroundColor:C.deep}]}><ScrollView contentContainerStyle={{flexGrow:1,padding:26,gap:24,justifyContent:'space-between'}}>
 <View style={[S.between,{paddingTop:10}]}><View style={S.row}><Icon name="leaf" color={C.leaf}/><Text style={{fontSize:24,color:'white',fontWeight:'700',letterSpacing:-1}}>canopy</Text></View><Eyebrow light>EVERY MOVE MATTERS</Eyebrow></View>
 <Fade><Text style={{fontSize:40,lineHeight:53,fontWeight:'700',letterSpacing:-2,color:'white'}}>매일의 이동을,{'\n'}더 가치 있게.</Text><Text style={{fontSize:15,color:'#C3D6C9',lineHeight:24}}>걷고, 달리고, 함께 타고.{'\n'}탄소를 줄인 만큼 토큰이 쌓여요.</Text></Fade>
 <LinearGradient colors={['#D9F899','#B6D7B6']} style={{borderRadius:36,padding:16,alignItems:'center'}}><CanopyMascot pose="walk" animated height={230}/><View style={{backgroundColor:C.white,borderRadius:18,paddingHorizontal:18,paddingVertical:10,marginTop:-14}}><Text style={S.link}>오늘의 작은 이동, 내일의 큰 변화</Text></View></LinearGradient>
 <View style={{gap:12}}>{!!error&&<Note error>{error}</Note>}{nickname&&onContinue?<Button title={`${nickname}님으로 계속`} disabled={!ready} onPress={onContinue}/>:<Button title="캐노피 시작하기" quiet onPress={onSignup}/>}<Button title={nickname?'다른 계정으로 로그인':'이미 계정이 있어요'} quiet onPress={onLogin}/></View>
 </ScrollView></SafeAreaView>;
}
