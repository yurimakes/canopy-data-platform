import React from 'react';
import {Image,View} from 'react-native';
import {Icon} from './theme';
import type {SheetOptions,sheetMotions} from './sheetRig';
export type MascotPose=typeof sheetMotions[number]['id']|'start'|'coin'|'trophy'|'garden';
const photos={hello:require('../../assets/canopy-ui/sheet-rig/hello-clean.png'),walk:require('../../assets/canopy-ui/sheet-rig/walk-clean.png'),celebrate:require('../../assets/canopy-ui/sheet-rig/celebrate-clean.png')};
export function CanopyMascot({pose='start',height=200}:{pose?:MascotPose;height?:number;animated?:boolean}&SheetOptions){
 const celebration=['complete','celebrate','jump','happy'].includes(pose);
 const walking=['walk','run','cycle'].includes(pose);
 return <View pointerEvents="none" style={{height,width:'100%',alignItems:'center',justifyContent:'center'}}>
  {pose==='coin'||pose==='trophy'?<Icon name={pose==='coin'?'leaf':'trophy'} size={height*.65}/>:<Image accessibilityLabel={celebration?'기뻐하는 캐노피':walking?'이동하는 캐노피':'인사하는 캐노피'} source={celebration?photos.celebrate:walking?photos.walk:photos.hello} resizeMode="contain" style={{width:'100%',height:'100%'}}/>}
 </View>;
}
