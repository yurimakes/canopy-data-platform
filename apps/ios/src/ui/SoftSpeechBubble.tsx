import React,{useState} from 'react';
import {View} from 'react-native';
import Svg,{Path} from 'react-native-svg';

export function SoftSpeechBubble({children}:{children:React.ReactNode}){
 const [size,setSize]=useState({width:180,height:130});
 const w=size.width,h=size.height-18;
 // Rounded bubble with a curved tail pointing toward the mascot.
 const outline=`M26 2 H${w-26} Q${w-2} 2 ${w-2} 26 V${h-24} Q${w-2} ${h} ${w-26} ${h} H43 Q28 ${h+13} 12 ${h+12} Q22 ${h+5} 23 ${h-1} Q2 ${h-3} 2 ${h-24} V26 Q2 2 26 2 Z`;
 return <View onLayout={e=>setSize(e.nativeEvent.layout)} style={{paddingHorizontal:18,paddingTop:17,paddingBottom:35}}>
  <Svg pointerEvents="none" width="100%" height="100%" style={{position:'absolute',inset:0}}><Path d={outline} fill="#F0F6E4" stroke="#D1E1BA" strokeWidth={1.5} strokeLinejoin="round"/></Svg>
  {children}
 </View>;
}
