import React from 'react';
import {LoginIntro} from './LoginIntro';
import {Button,Note} from './theme';
export function LandingScreen({onLogin,onSignup,onContinue,nickname,ready,error}:{onLogin():void;onSignup():void;onContinue?:()=>void;nickname?:string;ready:boolean;error?:string}){
 return <LoginIntro>
  {!!error&&<Note error>{error}</Note>}
  {nickname&&onContinue&&<Button title={`${nickname}님으로 계속하기`} disabled={!ready} onPress={onContinue}/>}
  <Button title="로그인" onPress={onLogin}/>
  <Button title="회원가입" quiet onPress={onSignup}/>
 </LoginIntro>;
}
