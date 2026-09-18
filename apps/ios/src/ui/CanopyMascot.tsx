import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,Animated,AppState,Easing,Platform,View} from 'react-native';

// PoC의 입체 캐릭터 이미지 사용. 프레임 교체 없이 네이티브 연속 보간으로 움직임 처리
export function CanopyMascot({pose='walk',height=200,animated=true}:{pose?:'walk'|'start'|'complete';height?:number;animated?:boolean}){
  const motion=useRef(new Animated.Value(0)).current;
  const [reduced,setReduced]=useState(true),[active,setActive]=useState(AppState.currentState==='active');
  useEffect(()=>{let alive=true;void AccessibilityInfo.isReduceMotionEnabled().then(v=>{if(alive)setReduced(v);}).catch(()=>{});
    const a=AccessibilityInfo.addEventListener('reduceMotionChanged',setReduced),b=AppState.addEventListener('change',v=>setActive(v==='active'));
    return()=>{alive=false;a.remove();b.remove();};},[]);
  useEffect(()=>{motion.setValue(0);if(!animated||reduced||!active)return;
    const timing=(toValue:number)=>Animated.timing(motion,{toValue,duration:2400,easing:Easing.inOut(Easing.sin),useNativeDriver:Platform.OS!=='web'});
    const loop=Animated.loop(Animated.sequence([timing(1),timing(0)]));loop.start();return()=>loop.stop();
  },[animated,reduced,active]);
  const complete=pose==='complete';
  return <View pointerEvents="none" accessible accessibilityLabel="캐노피 캐릭터" style={{height,width:'100%',alignItems:'center',justifyContent:'center'}}>
    <Animated.Image source={complete?require('../../assets/canopy-ui/journey-complete-frame-4.png'):require('../../assets/canopy-ui/landing-mascot-point.png')} resizeMode="contain"
      style={{width:'100%',height:'100%',transform:[{perspective:900},{translateY:motion.interpolate({inputRange:[0,1],outputRange:[0,-7]})},{rotateY:motion.interpolate({inputRange:[0,1],outputRange:['-3deg','3deg']})},{rotateZ:motion.interpolate({inputRange:[0,1],outputRange:['-1deg','1deg']})},{scale:motion.interpolate({inputRange:[0,1],outputRange:complete?[1.55,1.58]:[1,1.018]})}]}}/>
  </View>;
}
