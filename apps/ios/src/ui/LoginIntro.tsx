import React,{useEffect,useRef,useState} from 'react';
import {Animated,Image,ScrollView,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import Text from './AppText';
import {useReducedMotion} from './DesignPrimitives';
import {C} from './theme';
import {LoginGarden} from './LoginGarden';
export function LoginIntro({children}:{children:React.ReactNode}){
 const reduced=useReducedMotion(),[loaded,setLoaded]=useState(false),[logo,setLogo]=useState(false),[controls,setControls]=useState(false);
 const values=useRef('canopy'.split('').map(()=>new Animated.Value(0))).current;
 const reveal=useRef(new Animated.Value(0)).current;
 useEffect(()=>{if(!loaded)return;const timer=setTimeout(()=>setLogo(true),reduced?0:5450);return()=>clearTimeout(timer);},[loaded,reduced]);
 useEffect(()=>{if(!logo)return;const animation=Animated.stagger(reduced?0:110,values.map(value=>Animated.spring(value,{toValue:1,friction:5,tension:130,useNativeDriver:true})));animation.start();const timer=setTimeout(()=>setControls(true),reduced?0:1600);return()=>{animation.stop();clearTimeout(timer);};},[logo,reduced,values]);
 useEffect(()=>{if(!controls)return;const animation=Animated.timing(reveal,{toValue:1,duration:reduced?0:350,useNativeDriver:true});animation.start();return()=>animation.stop();},[controls,reduced,reveal]);
 return <SafeAreaView style={{flex:1,backgroundColor:C.paper}}><ScrollView contentContainerStyle={{flexGrow:1,justifyContent:'center',alignItems:'center',paddingHorizontal:24,paddingVertical:24}}>
  <View style={{width:'100%',maxWidth:382,aspectRatio:1,backgroundColor:C.paper,isolation:'isolate'}}>
   <View style={{width:'100%',height:'100%',mixBlendMode:'multiply'}}><Image source={reduced?require('../../assets/mascot/face-neutral.png'):require('../../assets/mascot/login.gif')} onLoad={()=>setLoaded(true)} onError={()=>{setLoaded(true);setLogo(true);}} resizeMode="contain" style={{width:'100%',height:'100%'}} accessibilityLabel="인사하는 캐노피"/></View>
   <LoginGarden/>
  </View>
  <View style={{height:80,justifyContent:'center',alignItems:'center'}}>
   {logo&&<View accessibilityLabel="canopy" style={{flexDirection:'row'}}>{'canopy'.split('').map((letter,i)=><Animated.View key={i} style={{opacity:values[i],transform:[{translateY:values[i].interpolate({inputRange:[0,1],outputRange:[18,0]})},{scale:values[i].interpolate({inputRange:[0,1],outputRange:[.5,1]})}]}}><Text style={{fontSize:52,color:C.deep}}>{letter}</Text></Animated.View>)}</View>}
  </View>
  <Animated.View pointerEvents={controls?'auto':'none'} accessibilityElementsHidden={!controls} importantForAccessibility={controls?'auto':'no-hide-descendants'} aria-hidden={!controls} style={{width:'100%',maxWidth:382,minHeight:160,gap:16,paddingTop:18,opacity:reveal}}>{controls?children:null}</Animated.View>
 </ScrollView></SafeAreaView>;
}
