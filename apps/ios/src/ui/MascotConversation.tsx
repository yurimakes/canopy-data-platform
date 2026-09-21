import React,{useEffect,useState} from 'react';
import {Pressable,View} from 'react-native';
import Text from './AppText';
import {CanopyMascot} from './CanopyMascot';
import {useReducedMotion} from './DesignPrimitives';
import {C} from './theme';

export function MascotConversation({message,compact=false}:{message:string;compact?:boolean}){
 const reduced=useReducedMotion(),[count,setCount]=useState(0);
 const letters=Array.from(message);
 useEffect(()=>{setCount(0);if(reduced){setCount(letters.length);return;}const timer=setInterval(()=>setCount(n=>{if(n>=letters.length){clearInterval(timer);return n;}return n+1;}),42);return()=>clearInterval(timer);},[message,reduced]);
 return <View style={{flexDirection:'row',alignItems:'center',gap:2}}>
  <View style={{width:compact?75:106,marginLeft:-9,marginRight:-6,zIndex:1}}><CanopyMascot pose="start" height={compact?98:139}/></View>
  <Pressable accessibilityRole="button" accessibilityLabel={message+' 전체 보기'} onPress={()=>setCount(letters.length)} style={{flex:1,backgroundColor:'#FFFFFFEE',borderWidth:1,borderColor:'white',borderRadius:24,borderBottomLeftRadius:5,padding:compact?14:18,boxShadow:'0 8px 24px #154C3A0D'}}>
   <Text style={{fontSize:10,color:C.green,fontWeight:'700',letterSpacing:1,marginBottom:6}}>CANOPY SAYS</Text>
   <View><Text accessible={false} style={{fontSize:compact?13:14,lineHeight:23,fontWeight:'600',color:'transparent'}}>{message}</Text><Text accessible={false} style={{position:'absolute',top:0,left:0,right:0,fontSize:compact?13:14,lineHeight:23,fontWeight:'600',color:C.deep}}>{letters.slice(0,count).join('')}</Text></View>
  </Pressable>
 </View>;
}
