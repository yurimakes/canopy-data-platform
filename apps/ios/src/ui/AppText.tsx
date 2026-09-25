import React from 'react';
import {Text as NativeText,type TextProps} from 'react-native';
// Keep Korean, Latin and numbers in the same rounded family throughout the app.
export default function Text(props:TextProps){return <NativeText {...props} style={[{letterSpacing:-.15},props.style,{fontFamily:'Jua',fontWeight:'normal'}]}/>;}
