import React,{useId} from 'react';
import Svg,{Circle,Defs,LinearGradient,Stop,Path} from 'react-native-svg';

export function RankMedal({rank,size=48}:{rank:number;size?:number}){
 const gradientId='medal'+useId().replace(/[^a-zA-Z0-9]/g,'');
 const colors=rank===1?['#FFF0A1','#DCAC37','#A96815']:rank===2?['#F4F9FF','#B7C5D4','#708396']:['#FFD9AB','#CE9367','#905337'];
 return <Svg width={size} height={size*58/48} viewBox="0 0 48 58" accessibilityLabel={rank===1?'금메달':rank===2?'은메달':'동메달'}>
  <Defs><LinearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor={colors[0]}/><Stop offset=".55" stopColor={colors[1]}/><Stop offset="1" stopColor={colors[2]}/></LinearGradient></Defs>
  <Path d="M12 32 L6 56 L18 51 L24 57 L27 33 M26 33 L30 57 L37 51 L45 54 L36 31" fill="#5C9678"/>
  <Circle cx={24} cy={23} r={21} fill={`url(#${gradientId})`} stroke={colors[2]} strokeWidth={1}/>
  <Circle cx={24} cy={23} r={16} fill="none" stroke={colors[0]} strokeWidth={1.5}/>
  <Path d="M15 30 C12 18 24 12 33 14 C34 26 24 32 17 29 M17 30 L29 19" fill={colors[2]} stroke={colors[0]} strokeWidth={1.2} strokeLinecap="round"/>
 </Svg>;
}
