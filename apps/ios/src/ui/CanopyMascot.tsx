import React,{useEffect,useState} from 'react';
import {AppState,Image,View} from 'react-native';
import {useReducedMotion} from './DesignPrimitives';
import ActorCanvas from './ActorCanvas';
import type {SheetOptions,sheetMotions} from './sheetRig';
export type MascotPose=typeof sheetMotions[number]['id']|'start'|'coin'|'trophy'|'garden';
const motion={wave:require('../../assets/canopy-ui/backpack/wave.gif'),walk:require('../../assets/canopy-ui/backpack/walk.gif'),celebrate:require('../../assets/canopy-ui/backpack/celebrate.gif')};
const posters={wave:require('../../assets/canopy-ui/backpack/wave-poster.png'),walk:require('../../assets/canopy-ui/backpack/walk-poster.png'),celebrate:require('../../assets/canopy-ui/backpack/celebrate-poster.png')};
export function CanopyMascot({pose='start',height=200,animated=true}:{pose?:MascotPose;height?:number;animated?:boolean}&SheetOptions){
 const reduced=useReducedMotion();
 const [foreground,setForeground]=useState(AppState.currentState==='active');
 useEffect(()=>{const sub=AppState.addEventListener('change',v=>setForeground(v==='active'));return()=>sub.remove();},[]);
 if(pose==='coin'||pose==='trophy')return <View accessibilityLabel={pose==='coin'?'캐노피 토큰':'트로피'} pointerEvents="none" style={{height,width:'100%'}}><ActorCanvas pose={pose} animated={animated&&!reduced&&foreground}/></View>;
 const action=['complete','celebrate','jump','happy'].includes(pose)?'celebrate':['walk','run','cycle'].includes(pose)?'walk':'wave';
 return <View pointerEvents="none" style={{height,width:'100%',alignItems:'center',justifyContent:'flex-end'}}>
  <Image accessibilityLabel={action==='celebrate'?'기뻐하며 뛰는 배낭 캐노피':action==='walk'?'걸어가는 배낭 캐노피':'손을 흔드는 배낭 캐노피'} source={reduced||!foreground||!animated?posters[action]:motion[action]} resizeMode="contain" style={{width:'100%',height:'100%'}}/>
 </View>;
}
