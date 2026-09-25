import React from 'react';
import {View} from 'react-native';
import Svg,{Path} from 'react-native-svg';

export function SoftSpeechBubble({children}:{children:React.ReactNode}){
 return <View style={{paddingBottom:13}}>
  <View style={{backgroundColor:'#F0F6E4',borderColor:'#D1E1BA',borderWidth:1.5,borderRadius:24,paddingHorizontal:15,paddingVertical:17}}>
   {children}
  </View>
  <Svg pointerEvents="none" width={32} height={20} viewBox="0 0 32 20" style={{position:'absolute',left:12,bottom:0}}>
   <Path d="M 6 0 L 30 0 Q 17 17 2 18 Q 12 8 6 0" fill="#F0F6E4"/>
   <Path d="M 30 0 Q 17 17 2 18 Q 12 8 6 0" fill="none" stroke="#D1E1BA" strokeWidth={1.5}/>
  </Svg>
 </View>;
}
