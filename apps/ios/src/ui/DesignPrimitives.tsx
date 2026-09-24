import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,Animated,Platform,Pressable,View,type StyleProp,type ViewStyle} from 'react-native';
import Text from './AppText';
import {C,Icon,S} from './theme';

export function useReducedMotion(){
 const [reduced,setReduced]=useState(true);
 useEffect(()=>{let alive=true;void AccessibilityInfo.isReduceMotionEnabled().then(v=>{if(alive)setReduced(v);}).catch(()=>{});const sub=AccessibilityInfo.addEventListener('reduceMotionChanged',setReduced);return()=>{alive=false;sub.remove();};},[]);
 return reduced;
}
export function Touch({children,onPress,style,label,disabled=false}:{children:React.ReactNode;onPress():void;style?:StyleProp<ViewStyle>;label?:string;disabled?:boolean}){
 const scale=useRef(new Animated.Value(1)).current,reduced=useReducedMotion();
 const change=(toValue:number)=>{if(!reduced)Animated.spring(scale,{toValue,speed:35,bounciness:2,useNativeDriver:Platform.OS!=='web'}).start();};
 return <Animated.View style={[style,{transform:[{scale}]}]}><Pressable accessibilityRole="button" accessibilityLabel={label} disabled={disabled} onPress={onPress} onPressIn={()=>change(.975)} onPressOut={()=>change(1)} style={{flexGrow:1}}>{children}</Pressable></Animated.View>;
}
export function Eyebrow({children,light=false}:{children:React.ReactNode;light?:boolean}){return <Text style={{fontSize:10,fontWeight:'700',letterSpacing:2,color:light?'#C1D8C9':C.green}}>{children}</Text>;}
export function SectionTitle({title,action,onPress}:{title:string;action?:string;onPress?:()=>void}){return <View style={S.between}><Text style={S.heading}>{title}</Text>{action&&onPress&&<Pressable accessibilityRole="button" onPress={onPress} style={{minHeight:44,justifyContent:'center'}}><Text style={S.link}>{action} ↗</Text></Pressable>}</View>;}
export function Disclosure({title,children}:{title:string;children:React.ReactNode}){const [open,setOpen]=useState(false);return <View><Pressable accessibilityRole="button" accessibilityState={{expanded:open}} onPress={()=>setOpen(!open)} style={[S.between,{minHeight:44}]}><Text style={[S.note,{fontWeight:'600',color:C.green}]}>{title}</Text><Icon name={open?'chevron-up':'chevron-down'} size={16}/></Pressable>{open&&<View style={{gap:10,paddingVertical:10}}>{children}</View>}</View>;}
export function Segmented({items,value,onChange}:{items:readonly {id:string;label:string}[];value:string;onChange(id:string):void}){return <View style={{flexDirection:'row',padding:4,borderRadius:16,backgroundColor:'#E9EEE6',gap:4}}>{items.map(item=><Pressable key={item.id} accessibilityRole="tab" accessibilityState={{selected:value===item.id}} onPress={()=>onChange(item.id)} style={{flex:1,minHeight:44,alignItems:'center',justifyContent:'center',borderRadius:12,backgroundColor:value===item.id?C.white:'transparent',boxShadow:value===item.id?'0 2px 5px #102F2910':undefined}}><Text style={{fontSize:13,fontWeight:'600',color:value===item.id?C.deep:C.muted}}>{item.label}</Text></Pressable>)}</View>;}
export function ProgressTrack({value,max=1}:{value:number;max?:number}){const motion=useRef(new Animated.Value(0)).current,reduced=useReducedMotion();const fraction=max>0?Math.min(1,Math.max(0,value/max)):0;useEffect(()=>{const a=Animated.timing(motion,{toValue:fraction,duration:reduced?0:650,useNativeDriver:false});a.start();return()=>a.stop();},[fraction,reduced]);return <View accessibilityRole="progressbar" accessibilityValue={{min:0,max,now:Math.min(max,value)}} style={{height:7,borderRadius:7,backgroundColor:'#EAF0E5',overflow:'hidden'}}><Animated.View style={{height:7,borderRadius:7,backgroundColor:'#8EB864',width:motion.interpolate({inputRange:[0,1],outputRange:['0%','100%']})}}/></View>;}
