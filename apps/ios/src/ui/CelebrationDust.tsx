import React,{useEffect,useRef,useState} from 'react';
import {Animated,AppState,Easing,View} from 'react-native';
import {useReducedMotion} from './DesignPrimitives';

const particles=Array.from({length:48},(_,i)=>({
 side:i%2?1:-1,spread:18+(i*19)%61,rise:95+(i*23)%85,
 size:3+i%4,color:['#B8D982','#E5C86E','#8DBFA1','#EADB9A'][i%4],
 delay:(i%24)*35,round:i%3!==0,
}));
export function CelebrationDust({children}:{children:React.ReactNode}){
 const reduced=useReducedMotion(),[active,setActive]=useState(AppState.currentState==='active');
 const values=useRef(particles.map(()=>new Animated.Value(0))).current;
 useEffect(()=>{const sub=AppState.addEventListener('change',s=>setActive(s==='active'));return()=>sub.remove();},[]);
 useEffect(()=>{
  if(reduced||!active){values.forEach(v=>v.setValue(0));return;}
  const animations=values.map((v,i)=>Animated.loop(Animated.sequence([
   Animated.delay(particles[i].delay),
   Animated.timing(v,{toValue:1,duration:2400,easing:Easing.out(Easing.quad),useNativeDriver:true,isInteraction:false}),
   Animated.delay(900-particles[i].delay),
   Animated.timing(v,{toValue:0,duration:0,useNativeDriver:true,isInteraction:false}),
  ])));
  animations.forEach(a=>a.start());return()=>animations.forEach(a=>a.stop());
 },[reduced,active,values]);
 return <View style={{width:'100%',height:195,alignItems:'center',justifyContent:'flex-end'}}>
  <View pointerEvents="none" accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{position:'absolute',inset:0,overflow:'hidden'}}>
   {!reduced&&particles.map((p,i)=><Animated.View key={i} style={{position:'absolute',left:'50%',top:160,width:p.size,height:p.round?p.size:p.size*1.7,borderRadius:p.round?p.size:1,backgroundColor:p.color,
    opacity:values[i].interpolate({inputRange:[0,.08,.55,1],outputRange:[0,.8,.65,0]}),
    transform:[{translateX:values[i].interpolate({inputRange:[0,.5,1],outputRange:[p.side*65,p.side*(65+p.spread),p.side*(72+p.spread)]})},{translateY:values[i].interpolate({inputRange:[0,1],outputRange:[0,-p.rise]})},{rotate:values[i].interpolate({inputRange:[0,1],outputRange:['0deg',`${p.side*160}deg`]})},{scale:values[i].interpolate({inputRange:[0,.2,1],outputRange:[.5,1,.4]})}],
   }}/>) }
  </View>
  {children}
 </View>;
}
