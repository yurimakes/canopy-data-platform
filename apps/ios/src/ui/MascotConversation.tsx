import React,{useEffect,useState} from 'react';
import {Pressable,View,useWindowDimensions} from 'react-native';
import Text from './AppText';
import {CanopyMascot} from './CanopyMascot';
import {useReducedMotion} from './DesignPrimitives';
import {C} from './theme';

export function MascotConversation({message,compact=false,greeting=false}:{message:string;compact?:boolean;greeting?:boolean}){
 const narrow=useWindowDimensions().width<360;
 const reduced=useReducedMotion(),[count,setCount]=useState(0);
 const letters=Array.from(message);
 useEffect(()=>{setCount(0);if(reduced){setCount(letters.length);return;}const timer=setInterval(()=>setCount(n=>{if(n>=letters.length){clearInterval(timer);return n;}return n+1;}),42);return()=>clearInterval(timer);},[message,reduced]);
 return <View style={{flexDirection:'row',alignItems:greeting?'flex-end':'center',gap:2}}>
  <View style={{width:compact?75:greeting?(narrow?100:116):106,marginLeft:-9,marginRight:-6,zIndex:1}}><CanopyMascot pose="start" height={compact?98:greeting?(narrow?100:116):139}/></View>
  <Pressable accessibilityRole="button" accessibilityLabel={message+' 전체 보기'} onPress={()=>setCount(letters.length)} style={{flex:1,marginBottom:greeting?66:0,backgroundColor:'#FFFFF5F5',borderWidth:2,borderColor:'white',borderRadius:32,borderTopLeftRadius:greeting?40:32,borderBottomLeftRadius:greeting?6:10,padding:compact?14:greeting&&narrow?11:16,boxShadow:'0 8px 24px #154C3A0D'}}>

   <View><Text accessible={false} style={{fontSize:compact?13:14,lineHeight:23,fontWeight:'600',color:'transparent'}}>{message}</Text><Text accessible={false} style={{position:'absolute',top:0,left:0,right:0,fontSize:compact?13:14,lineHeight:23,fontWeight:'600',color:C.deep}}>{letters.slice(0,count).join('')}</Text></View>
  </Pressable>
 </View>;
}
