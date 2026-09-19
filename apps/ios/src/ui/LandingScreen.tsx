import Text from './AppText';
import React from 'react';
import {Image,KeyboardAvoidingView,Platform,ScrollView,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {CanopyMascot} from './CanopyMascot';
import {Button,Fade,Note,S} from './theme';
export function LandingScreen({onLogin,onSignup,onContinue,nickname,ready,error,loginForm}:{onLogin():void;onSignup():void;onContinue?:()=>void;nickname?:string;ready:boolean;error?:string;loginForm?:React.ReactNode}){
 return <SafeAreaView style={[S.root,{backgroundColor:'#eef5f4'}]}>
  <Image source={require('../../assets/canopy-ui/landing-city-v2.png')} resizeMode="cover" style={{position:'absolute',width:'100%',height:'100%'}}/>
  <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':undefined}>
   <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{flexGrow:1,paddingHorizontal:24,paddingTop:28,paddingBottom:24,justifyContent:'space-between',gap:12}}>
    <Fade><View style={{alignItems:'center'}}><Image accessibilityLabel="CANOPY" source={require('../../assets/canopy-ui/canopy-wordmark-v2.png')} resizeMode="contain" style={{width:'100%',height:106}}/><Text style={{fontSize:8,letterSpacing:1.7,color:'#496961',textAlign:'center',marginTop:-12}}>SMART MOBILITY FOR A GREENER TOMORROW</Text></View>
     <View style={{flexDirection:'row',alignItems:'center',height:225}}><View style={{flex:1,gap:12}}><Text style={[S.title,{fontSize:24,lineHeight:34}]}>작은 이동이{'\n'}만드는{'\n'}더 푸른 내일.</Text><Text style={[S.note,{color:'#385b51'}]}>나의 일상 속{'\n'}초록빛 여정, 캐노피.</Text></View><View style={{width:'59%',height:225}}><CanopyMascot height={225}/></View></View>
    </Fade>
    <View style={{backgroundColor:'#ffffffed',borderColor:'#ffffff',borderWidth:1,borderRadius:28,padding:20,gap:12,boxShadow:'0 10px 40px #17453816'}}>
     <Text style={S.heading}>오늘의 여정을 시작해요</Text>
     {!!error&&<Note error>{error}</Note>}
     {nickname&&onContinue&&<Button title={`${nickname}님으로 계속하기`} disabled={!ready} onPress={onContinue}/>}
     {loginForm??<Button title="로그인" onPress={onLogin}/>}
     <Button title="처음이에요 · 회원가입" quiet onPress={onSignup}/>
    </View>
   </ScrollView>
  </KeyboardAvoidingView>
 </SafeAreaView>;
}
