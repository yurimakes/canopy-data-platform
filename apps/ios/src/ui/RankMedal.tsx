import React from 'react';
import {View} from 'react-native';
import {PreviewIcon} from './PreviewIcon';
export function RankMedal({rank,size=32}:{rank:number;size?:number}){return <View accessible accessibilityLabel={`${rank}위`}><PreviewIcon name="medal" size={size} color={rank===1?'#9A7D34':rank===2?'#708396':'#B77E4D'}/></View>;}
