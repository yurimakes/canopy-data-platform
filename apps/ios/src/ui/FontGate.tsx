import React from 'react';
import {ActivityIndicator,View} from 'react-native';
import {useFonts} from 'expo-font';
export function FontGate({children}:{children:React.ReactNode}){
 const [loaded,error]=useFonts({Jua:require('../../assets/design-preview/Jua.ttf')});
 return loaded||error?children:<View style={{flex:1,justifyContent:'center',backgroundColor:'#F8F9F0'}}><ActivityIndicator color="#176B50"/></View>;
}
