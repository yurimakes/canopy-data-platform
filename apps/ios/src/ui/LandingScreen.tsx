import React from 'react';
import {ScrollView,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import Text from './AppText';
import {CanopyMascot} from './CanopyMascot';
import {Button,C,Note,S} from './theme';
export function LandingScreen({onLogin,onSignup,onContinue,nickname,ready,error}:{onLogin():void;onSignup():void;onContinue?:()=>void;nickname?:string;ready:boolean;error?:string}){return <SafeAreaView style={S.root}><ScrollView contentContainerStyle={{flexGrow:1,padding:28,paddingTop:55,justifyContent:'center',gap:24}}><Text style={{fontFamily:'Jua',fontSize:44,color:C.deep,textAlign:'center'}}>canopy</Text><Text style={{fontSize:9,letterSpacing:1.5,textAlign:'center',color:C.muted}}>A GREENER TOMORROW TOGETHER</Text><CanopyMascot height={245}/><Text style={[S.title,{textAlign:'center'}]}>작은 이동이 만드는,{'\n'}더 큰 변화.</Text>{!!error&&<Note error>{error}</Note>}{nickname&&onContinue&&<Button title={`${nickname}님으로 계속하기`} disabled={!ready} onPress={onContinue}/>}<Button title="로그인" onPress={onLogin}/><Button title="회원가입" quiet onPress={onSignup}/><Note>나의 계정으로 여정과 캠페인을 이어가세요.</Note></ScrollView></SafeAreaView>;}
