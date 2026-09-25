import React from 'react';
import {Image,View} from 'react-native';
import Text from './AppText';
import {C,S,Icon,Note} from './theme';
const faces={idle:require('../../assets/mascot/face-neutral.png'),moving:require('../../assets/mascot/face-moving.png')};
const gifs={complete:require('../../assets/mascot/complete.gif'),processing:require('../../assets/mascot/processing.gif')};
export function MapFace({moving=false}:{moving?:boolean}){return <Image source={moving?faces.moving:faces.idle} accessibilityLabel={moving?'웃는 캐노피 얼굴':'무표정 캐노피 얼굴'} resizeMode="contain" style={{width:40,height:40}}/>;}
export function MascotMedia({kind,size=220}:{kind:keyof typeof gifs;size?:number}){return <Image source={gifs[kind]} accessibilityLabel={kind==='complete'?'여정 완료를 축하하는 캐노피':'여정을 분석하는 캐노피'} resizeMode="contain" style={{width:size,height:size,alignSelf:'center'}}/>;}
export function ProcessingStatus({stage}:{stage:{step:number;title:string;detail:string;failed?:boolean}}){return <View style={{gap:16}}>{stage.failed?<Icon name="alert-circle-outline" size={40}/>:<MascotMedia kind="processing"/>}<Text style={[S.heading,{textAlign:'center'}]}>{stage.title}</Text><Note>{stage.detail}</Note><View style={{gap:12}}>{['위치 기록 보내기','이동 분석하기','결과 준비하기'].map((label,i)=><View key={label} style={[S.row,{padding:12,borderRadius:16,backgroundColor:i===stage.step?C.mint:C.paper}]}><Icon name={i<stage.step?'checkmark-circle':i===stage.step?'radio-button-on':'ellipse-outline'} color={i<=stage.step?C.green:C.muted}/><Text style={S.label}>{label}</Text></View>)}</View></View>;}
