import React,{useEffect,useRef,useState} from 'react';
import {Animated,AppState,Easing,View} from 'react-native';
import Svg,{Circle,Ellipse,Path} from 'react-native-svg';
import {useReducedMotion} from './DesignPrimitives';

// Decorative vectors sit around the original GIF, keeping its animation intact.
export function LoginGarden(){
 const reduced=useReducedMotion(),[active,setActive]=useState(AppState.currentState==='active');
 const wind=useRef(new Animated.Value(0)).current,cloud=useRef(new Animated.Value(0)).current;
 useEffect(()=>{const sub=AppState.addEventListener('change',s=>setActive(s==='active'));return()=>sub.remove();},[]);
 useEffect(()=>{
  if(reduced||!active)return;
  const sway=Animated.loop(Animated.sequence([Animated.timing(wind,{toValue:1,duration:2300,easing:Easing.inOut(Easing.sin),useNativeDriver:true,isInteraction:false}),Animated.timing(wind,{toValue:0,duration:2300,easing:Easing.inOut(Easing.sin),useNativeDriver:true,isInteraction:false})]));
  const drift=Animated.loop(Animated.sequence([Animated.timing(cloud,{toValue:1,duration:11000,easing:Easing.inOut(Easing.sin),useNativeDriver:true,isInteraction:false}),Animated.timing(cloud,{toValue:0,duration:11000,easing:Easing.inOut(Easing.sin),useNativeDriver:true,isInteraction:false})]));
  sway.start();drift.start();return()=>{sway.stop();drift.stop();};
 },[active,reduced,wind,cloud]);
 return <View pointerEvents="none" accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{position:'absolute',inset:0}}>
  <View style={{position:'absolute',right:'12%',top:'0%',width:68,height:68}}><Svg width="100%" height="100%" viewBox="0 0 80 80"><Circle cx="40" cy="40" r="36" fill="#FFF8DB"/><Circle cx="40" cy="40" r="25" fill="#F8DB7F"/><Circle cx="33" cy="39" r="1.8" fill="#A58B48"/><Circle cx="47" cy="39" r="1.8" fill="#A58B48"/><Path d="M36 46 Q40 50 44 46" stroke="#A58B48" strokeWidth="2" fill="none" strokeLinecap="round"/></Svg></View>
  {[{left:'5%' as const,top:'9%' as const,width:98},{left:'65%' as const,top:'23%' as const,width:76}].map((p,i)=><Animated.View key={i} style={{position:'absolute',...p,height:48,opacity:.85,transform:[{translateX:cloud.interpolate({inputRange:[0,1],outputRange:i?[7,-7]:[-9,9]})}]}}><Svg width="100%" height="100%" viewBox="0 0 100 50"><Path d="M17 43 C-2 43 0 20 18 20 C20 0 48 0 55 18 C70 9 84 18 84 28 C103 26 105 43 85 43 Z" fill="#E7F2EE"/></Svg></Animated.View>)}
  <View style={{position:'absolute',left:0,right:0,bottom:'0%',height:'13%'}}><Svg width="100%" height="100%" viewBox="0 0 380 55" preserveAspectRatio="none"><Ellipse cx="190" cy="26" rx="177" ry="22" fill="#EFF6DE"/><Ellipse cx="192" cy="24" rx="71" ry="7" fill="#D8E6B8" opacity=".6"/></Svg></View>
  {[5,15,26,72,83,92].map((left,i)=><Animated.View key={left} style={{position:'absolute',left:`${left}%`,bottom:i%2?'4%':'7%',width:22,height:30,transform:[{rotate:wind.interpolate({inputRange:[0,1],outputRange:i%2?['-5deg','9deg']:['-8deg','6deg']})}]}}><Svg width="22" height="30" viewBox="0 0 22 30"><Path d="M11 29 Q0 18 2 10 Q11 16 11 29 M11 29 Q8 10 14 1 Q18 15 11 29 M11 29 Q15 15 22 14 Q21 25 11 29" fill={i%2?'#A5C77A':'#BED795'}/></Svg></Animated.View>)}
 </View>;
}
