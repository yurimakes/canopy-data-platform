import React from 'react';
import {Text as NativeText,StyleSheet,type TextProps} from 'react-native';
export default function Text(props:TextProps){const weight=StyleSheet.flatten(props.style)?.fontWeight;const bold=weight==='bold'||Number(weight)>=700;const medium=Number(weight)>=500;return <NativeText {...props} style={[{fontFamily:bold?'NotoSansKR_700Bold':medium?'NotoSansKR_600SemiBold':'NotoSansKR_400Regular',letterSpacing:-.25},props.style,{fontWeight:'normal'}]}/>;}
