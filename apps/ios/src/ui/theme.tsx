import Text from './AppText';
import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,Animated,ActivityIndicator,Platform,Pressable,StyleSheet,TextInput,View,type TextInputProps} from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
export const C={green:'#24764f',deep:'#193f32',ink:'#263f33',muted:'#617561',mint:'#e7f0d9',paper:'#f1f5e9',line:'#dae5ce',white:'#fff',surface:'#fbfcf5',leaf:'#d5ed9c',red:'#b13c3c'};
export function Icon({name,size=22,color=C.green}:{name:React.ComponentProps<typeof Ionicons>['name'];size?:number;color?:string}){return <Ionicons name={name} size={size} color={color}/>;}
export function Button({title,onPress,disabled=false,quiet=false,danger=false,busy=false}:{title:string;onPress:()=>void;disabled?:boolean;quiet?:boolean;danger?:boolean;busy?:boolean}){return <Pressable accessibilityRole="button" accessibilityState={{disabled:disabled||busy,busy}} disabled={disabled||busy} onPress={onPress} style={({pressed})=>[S.button,quiet&&S.quiet,danger&&{backgroundColor:C.red},(pressed||disabled||busy)&&{opacity:.5}]}>{busy&&<ActivityIndicator color={quiet?C.green:'white'}/>}<Text style={[S.buttonText,quiet&&{color:C.green}]}>{title}</Text></Pressable>;}
export function Field({label,...props}:TextInputProps&{label:string}){return <View style={{gap:8}}><Text style={S.label}>{label}</Text><TextInput {...props} accessibilityLabel={label} placeholderTextColor="#8a9790" style={[S.input,props.style]}/></View>;}
export function Card({children}:{children:React.ReactNode}){return <View style={S.card}>{children}</View>;}
export function Note({children,error=false}:{children:React.ReactNode;error?:boolean}){return <Text accessibilityRole={error?'alert':undefined} style={[S.note,error&&{color:C.red}]}>{children}</Text>;}
export function Stat({label,value}:{label:string;value:string}){return <View style={{flex:1,minWidth:0,gap:8}}><Text style={S.note}>{label}</Text><Text adjustsFontSizeToFit numberOfLines={1} minimumFontScale={.7} style={S.metric}>{value}</Text></View>;}
export function Fade({children,delay=0}:{children:React.ReactNode;delay?:number}) {
  const progress=useRef(new Animated.Value(0)).current;
  useEffect(()=>{let alive=true;let animation:Animated.CompositeAnimation|undefined;
    void AccessibilityInfo.isReduceMotionEnabled().then(reduce=>{if(!alive)return;if(reduce)progress.setValue(1);else{animation=Animated.timing(progress,{toValue:1,duration:420,delay,useNativeDriver:Platform.OS!=='web'});animation.start();}}).catch(()=>progress.setValue(1));
    return()=>{alive=false;animation?.stop();};},[]);
  return <Animated.View style={{opacity:progress,transform:[{translateY:progress.interpolate({inputRange:[0,1],outputRange:[12,0]})}],gap:18}}>{children}</Animated.View>;
}
export function Floating({children}:{children:React.ReactNode}) {
  const y=useRef(new Animated.Value(0)).current;
  useEffect(()=>{let alive=true;let loop:Animated.CompositeAnimation|undefined;
    void AccessibilityInfo.isReduceMotionEnabled().then(reduce=>{if(!alive||reduce)return;
      loop=Animated.loop(Animated.sequence([Animated.timing(y,{toValue:-7,duration:1700,useNativeDriver:Platform.OS!=='web'}),Animated.timing(y,{toValue:0,duration:1700,useNativeDriver:Platform.OS!=='web'})]));loop.start();
    }).catch(()=>{});return()=>{alive=false;loop?.stop();};},[]);
  return <Animated.View style={{transform:[{translateY:y}]}}>{children}</Animated.View>;
}
export const S=StyleSheet.create({
  root:{flex:1,width:'100%',maxWidth:Platform.OS==='web'?480:undefined,alignSelf:'center',backgroundColor:C.paper},scroll:{padding:20,paddingBottom:28,gap:16,width:'100%',maxWidth:640,alignSelf:'center'},
  row:{flexDirection:'row',alignItems:'center',gap:12},between:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:12},
  title:{fontSize:26,lineHeight:35,fontWeight:'800',letterSpacing:-1,color:C.deep},heading:{fontSize:18,lineHeight:25,fontWeight:'700',color:C.ink},
  label:{fontSize:14,fontWeight:'600',color:C.ink},note:{fontSize:13,lineHeight:21,color:C.muted},metric:{fontSize:22,fontWeight:'700',color:C.deep},
  card:{backgroundColor:C.surface,borderRadius:26,padding:20,gap:16,borderWidth:1,borderColor:C.line,boxShadow:'0 6px 24px #173c4206'},
  input:{borderWidth:1,borderColor:C.line,borderRadius:14,padding:16,fontSize:16,color:C.ink,backgroundColor:C.white,minHeight:54},
  button:{minHeight:48,borderRadius:28,backgroundColor:C.green,alignItems:'center',justifyContent:'center',padding:13,flexDirection:'row',gap:10},
  buttonText:{fontSize:15,fontWeight:'700',color:C.white},quiet:{backgroundColor:C.mint},
  pill:{color:C.green,backgroundColor:C.mint,paddingHorizontal:12,paddingVertical:6,borderRadius:12,fontSize:12,fontWeight:'600'},
  divider:{height:1,backgroundColor:C.line},link:{fontSize:14,color:C.green,fontWeight:'600'},
});
