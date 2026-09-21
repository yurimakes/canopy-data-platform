import React from 'react';
import {Image,View} from 'react-native';
import {Icon} from './theme';
import ActorCanvas from './ActorCanvas';
import type {SheetOptions,sheetMotions} from './sheetRig';
export type MascotPose=typeof sheetMotions[number]['id']|'start'|'coin'|'trophy'|'garden';
const photos={hello:require('../../assets/canopy-ui/sheet-rig/hello-clean.png'),walk:require('../../assets/canopy-ui/sheet-rig/walk-clean.png'),celebrate:require('../../assets/canopy-ui/sheet-rig/celebrate-clean.png')};
export function CanopyMascot({pose='start',height=200,animated=false}:{pose?:MascotPose;height?:number;animated?:boolean}&SheetOptions){
 if(pose==='coin'||pose==='trophy'||(animated&&['walk','run','cycle','complete'].includes(pose)))return <View accessibilityLabel={pose==='coin'?'캐노피 토큰':pose==='trophy'?'트로피':'움직이는 캐노피'} pointerEvents="none" style={{height,width:'100%'}}><ActorCanvas pose={pose} animated={animated}/></View>;
 const celebration=['complete','celebrate','jump','happy'].includes(pose);
 const walking=['walk','run','cycle'].includes(pose);
 return <View pointerEvents="none" style={{height,width:'100%',alignItems:'center',justifyContent:'center'}}>
  {<Image accessibilityLabel={celebration?'기뻐하는 캐노피':walking?'이동하는 캐노피':'인사하는 캐노피'} source={celebration?photos.celebrate:walking?photos.walk:photos.hello} resizeMode="contain" style={{width:'100%',height:'100%'}}/>}
 </View>;
}
