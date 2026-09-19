import React from 'react';
import {View} from 'react-native';
import ActorCanvas from './ActorCanvas';
export type MascotPose='walk'|'start'|'complete'|'run'|'coin'|'trophy';
export function CanopyMascot({pose='start',height=200,animated=true}:{pose?:MascotPose;height?:number;animated?:boolean}){
 return <View pointerEvents="none" accessible accessibilityLabel={pose==='coin'?'입체 캐노피 토큰':pose==='trophy'?'입체 랭킹 트로피':pose==='complete'?'폭죽을 터뜨리는 캐노피':pose==='run'?'달리는 캐노피':'손을 흔드는 캐노피'} style={{height,width:'100%'}}><ActorCanvas pose={pose} animated={animated}/></View>;
}
