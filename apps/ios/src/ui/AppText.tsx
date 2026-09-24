import React from 'react';
import {Text as NativeText,StyleSheet,type TextProps} from 'react-native';
export default function Text(props:TextProps){const style=StyleSheet.flatten(props.style);return <NativeText {...props} style={[{fontFamily:'Pretendard',letterSpacing:-.25},props.style,style?.fontFamily==='Jua'?{fontWeight:'normal'}:{}]}/>;}
