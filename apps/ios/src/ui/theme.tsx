import {PreviewIcon} from './PreviewIcon';
import {IllustratedIcon,type ArtName} from './IllustratedIcon';
import Text from './AppText';
import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,Animated,ActivityIndicator,Platform,Pressable,StyleSheet,TextInput,View,type TextInputProps} from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
export const C={green:'#547952',deep:'#254B38',ink:'#263E34',muted:'#74816B',mint:'#ECF1D8',paper:'#F8F9F1',line:'#E7E9DE',white:'#FFFFFF',surface:'#FFFFFF',leaf:'#D8EC9A',red:'#B34040',gold:'#947528'};
export function Icon({name,size=24,color=C.green}:{name:React.ComponentProps<typeof Ionicons>['name'];size?:number;color?:string}){
 const mapping:Record<string,string>={'home-outline':'house','leaf':'leaf','leaf-outline':'leaf','footsteps-outline':'sneaker-move','walk-outline':'sneaker-move','flag-outline':'flag-checkered','gift-outline':'gift','wallet-outline':'wallet','trophy-outline':'medal','podium-outline':'ranking','bus-outline':'bus','train-outline':'train','bicycle-outline':'bicycle','car-outline':'car','notifications-outline':'bell','settings-outline':'gear','person-outline':'user-circle','arrow-forward':'arrow-right','arrow-back':'arrow-left','chevron-forward':'caret-right','chevron-down':'caret-down','chevron-up':'caret-up','time-outline':'timer','location-outline':'map-pin','checkmark-circle':'check-circle'};
 const mapped=mapping[name];return mapped?<PreviewIcon name={mapped as React.ComponentProps<typeof PreviewIcon>['name']} size={size} color={color}/>:<Ionicons name={name} size={size} color={color}/>;
}
export function Button({title,onPress,disabled=false,quiet=false,danger=false,busy=false}:{title:string;onPress:()=>void;disabled?:boolean;quiet?:boolean;danger?:boolean;busy?:boolean}){
 const scale=useRef(new Animated.Value(1)).current,reduced=useRef(true);
 useEffect(()=>{let alive=true;void AccessibilityInfo.isReduceMotionEnabled().then(v=>{if(alive)reduced.current=v;});const sub=AccessibilityInfo.addEventListener('reduceMotionChanged',v=>{reduced.current=v;});return()=>{alive=false;sub.remove();};},[]);
 const motion=(toValue:number)=>{if(!reduced.current)Animated.spring(scale,{toValue,speed:32,bounciness:3,useNativeDriver:Platform.OS!=='web'}).start();};
 return <Animated.View style={{transform:[{scale}],minWidth:0}}><Pressable accessibilityRole="button" accessibilityState={{disabled:disabled||busy,busy}} disabled={disabled||busy} onPressIn={()=>motion(.975)} onPressOut={()=>motion(1)} onPress={onPress} style={[S.button,quiet&&S.quiet,danger&&{backgroundColor:C.red},(disabled||busy)&&{opacity:.45}]}>{busy&&<ActivityIndicator color={danger?'white':C.deep}/>}<Text style={[S.buttonText,danger&&{color:C.white}]}>{title}</Text>{!busy&&!quiet&&<Icon name="arrow-forward" size={18} color={danger?C.white:C.deep}/>}</Pressable></Animated.View>;
}
export function Field({label,...props}:TextInputProps&{label:string}){return <View style={{gap:8}}><Text style={S.label}>{label}</Text><TextInput {...props} accessibilityLabel={label} placeholderTextColor="#8a9790" style={[S.input,props.style]}/></View>;}
export function Card({children}:{children:React.ReactNode}){return <View style={S.card}>{children}</View>;}
export function Note({children,error=false}:{children:React.ReactNode;error?:boolean}){return <Text accessibilityRole={error?'alert':undefined} style={[S.note,error&&{color:C.red}]}>{children}</Text>;}
export function Stat({label,value}:{label:string;value:string}){return <View style={{flex:1,minWidth:0,gap:8}}><Text style={S.note}>{label}</Text><Text adjustsFontSizeToFit numberOfLines={1} minimumFontScale={.7} style={S.metric}>{value}</Text></View>;}
export function Fade({children,delay=0}:{children:React.ReactNode;delay?:number}) {
  const progress=useRef(new Animated.Value(0)).current;
  useEffect(()=>{let alive=true;let animation:Animated.CompositeAnimation|undefined;
    void AccessibilityInfo.isReduceMotionEnabled().then(reduce=>{if(!alive)return;if(reduce)progress.setValue(1);else{animation=Animated.timing(progress,{toValue:1,duration:220,delay,useNativeDriver:Platform.OS!=='web'});animation.start();}}).catch(()=>progress.setValue(1));
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
  root:{flex:1,width:'100%',maxWidth:Platform.OS==='web'?480:undefined,alignSelf:'center',backgroundColor:C.paper},scroll:{padding:20,paddingBottom:24,gap:20,width:'100%',maxWidth:640,alignSelf:'center'},
  row:{flexDirection:'row',alignItems:'center',gap:12},between:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:12},
  title:{fontSize:28,lineHeight:37,fontFamily:'Jua',fontWeight:'800',letterSpacing:-1.3,color:C.deep},heading:{fontSize:18,lineHeight:25,fontWeight:'700',color:C.ink},
  label:{fontSize:14,fontWeight:'600',color:C.ink},note:{fontSize:13,lineHeight:21,color:C.muted},metric:{fontSize:26,fontFamily:'Jua',fontWeight:'700',color:C.deep},
  card:{backgroundColor:C.surface,borderRadius:24,padding:20,gap:16,borderWidth:1,borderColor:C.line},
  input:{fontFamily:'Jua',borderWidth:1,borderColor:C.line,borderRadius:14,padding:16,fontSize:16,color:C.ink,backgroundColor:C.white,minHeight:54},
  button:{minHeight:56,borderRadius:18,backgroundColor:C.leaf,alignItems:'center',justifyContent:'center',padding:13,flexDirection:'row',gap:10},
  buttonText:{flexShrink:1,textAlign:'center',fontSize:16,fontWeight:'700',color:C.deep},quiet:{backgroundColor:C.leaf},
  pill:{color:C.green,backgroundColor:C.mint,alignSelf:'flex-start',paddingHorizontal:10,paddingVertical:5,borderRadius:8,fontSize:12,fontWeight:'600'},
  divider:{height:1,backgroundColor:C.line},link:{fontSize:14,color:C.green,fontWeight:'600'},
});
