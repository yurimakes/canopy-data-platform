import Ionicons from '@expo/vector-icons/Ionicons';
import React from 'react';
import {SvgXml} from 'react-native-svg';
import {previewIcons} from './previewIcons';
export function PreviewIcon({name,size=24,color='#547952'}:{name:keyof typeof previewIcons|'car'|'buildings';size?:number;color?:string}){
 if(name==='car'||name==='buildings')return <Ionicons name={name==='car'?'car-outline':'business-outline'} size={size} color={color}/>;
 return <SvgXml xml={previewIcons[name]} width={size} height={size} color={color}/>;
}
