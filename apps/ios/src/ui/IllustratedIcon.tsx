import React from 'react';
import {Image,View} from 'react-native';

// Individually commissioned Canopy assets; bundled locally, never fetched at runtime.
const art={
 office:require('../../assets/canopy-ui/premium/office.png'),
 home:require('../../assets/canopy-ui/premium/home.png'),
 bus:require('../../assets/canopy-ui/premium/bus.png'),
 mission:require('../../assets/canopy-ui/premium/mission.png'),
 wallet:require('../../assets/canopy-ui/premium/wallet.png'),
 walk:require('../../assets/canopy-ui/premium/walk.png'),
 trophy:require('../../assets/canopy-ui/premium/trophy.png'),
 leaf:require('../../assets/canopy-ui/premium/leaf.png'),
 profile:require('../../assets/canopy-ui/premium/profile.png'),
};
export type ArtName=keyof typeof art;
export function IllustratedIcon({name,size=56,label}:{name:ArtName;size?:number;label?:string}){
 return <View pointerEvents="none" style={{width:size,height:size,flexShrink:0}}><Image source={art[name]} resizeMode="contain" accessible={!!label} accessibilityLabel={label} style={{width:'100%',height:'100%'}}/></View>;
}
export function missionArt(title:string):ArtName{return /버스|대중|철도|지하철/.test(title)?'bus':/걷|걸|발|도보/.test(title)?'walk':/탄소|절감|친환경/.test(title)?'leaf':'mission';}
