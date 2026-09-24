import React from 'react';
import {View} from 'react-native';
import {PreviewIcon} from './PreviewIcon';
const art={office:'buildings',home:'house',bus:'bus',mission:'flag-checkered',wallet:'wallet',walk:'sneaker-move',trophy:'ranking',leaf:'leaf',profile:'user-circle'} as const;
export type ArtName=keyof typeof art;
export function IllustratedIcon({name,size=24,label}:{name:ArtName;size?:number;label?:string}){return <View accessible={!!label} accessibilityLabel={label} style={{width:size,height:size,alignItems:'center',justifyContent:'center'}}><PreviewIcon name={art[name]} size={size}/></View>;}
export function missionArt(title:string):ArtName{return /버스|대중|철도|지하철/.test(title)?'bus':/걷|걸|발|도보/.test(title)?'walk':/탄소|절감|친환경/.test(title)?'leaf':'mission';}
