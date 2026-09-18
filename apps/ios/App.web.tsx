import React,{useState} from 'react';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import {logoutProfile,updateProfile} from './src/profileStore';
import {AuthScreen} from './src/ui/AuthScreen';
import {ServiceScreen} from './src/ui/ServiceScreen';
import type {Profile,PlannedRoute} from './src/service';
// 웹은 동일 화면의 검토용. GPS 수집과 실제 서버 요청은 iPhone에서 실행
export default function App(){
  const [profile,setProfile]=useState<Profile|null>(null),[route,setRoute]=useState<PlannedRoute|null>(null),[mode,setMode]=useState<'user'|'developer'>('user');
  const noop=()=>{};
  return <SafeAreaProvider style={{width:'100%',maxWidth:430,alignSelf:'center'}}>{!profile?<AuthScreen onEnter={p=>{setProfile(p);setMode(p.role==='developer'?'developer':'user');}}/>:<ServiceScreen profile={profile} onProfile={async p=>setProfile(await updateProfile(p))} route={route} onRoute={setRoute} trips={[]} events={[]} onSelect={noop} preview collectionMode={mode} onCollectionMode={setMode}
    onBack={()=>{void logoutProfile().then(()=>setProfile(null));}} mode={null} phase="idle" ready={false} count={0} duration="00:00" accuracy={null} error="" onMode={noop} onStart={noop} onStop={noop} onExport={noop} canExport={false} sharing={false} onFeedback={async()=>{}}/>}</SafeAreaProvider>;
}
