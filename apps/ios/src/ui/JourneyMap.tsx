import React from 'react';
import {View} from 'react-native';
import {Icon,Note,C} from './theme';
import type {Place,PlannedRoute} from '../service';
export type MapProps={walking?:boolean;points:Place[];route?:PlannedRoute|null;height?:number;fill?:boolean;places?:Place[];selectedPlace?:number;onSelectPlace?:(index:number)=>void};
export default function JourneyMap(_p:MapProps){return <View style={{height:_p.fill?'100%':_p.height??280,backgroundColor:C.mint,alignItems:'center',justifyContent:'center',gap:16,padding:24}}><Icon name="map-outline" size={42}/><Note>실제 지도와 GPS 이동 경로는 iPhone에서 확인할 수 있어요.</Note></View>;}
