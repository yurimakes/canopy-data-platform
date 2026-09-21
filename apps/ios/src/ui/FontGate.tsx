import React from 'react';
import {ActivityIndicator,View} from 'react-native';
import {useFonts} from 'expo-font';
const NotoSansKR_400Regular=require('@expo-google-fonts/noto-sans-kr/400Regular/NotoSansKR_400Regular.ttf');
const NotoSansKR_600SemiBold=require('@expo-google-fonts/noto-sans-kr/600SemiBold/NotoSansKR_600SemiBold.ttf');
const NotoSansKR_700Bold=require('@expo-google-fonts/noto-sans-kr/700Bold/NotoSansKR_700Bold.ttf');
const Nunito_800ExtraBold=require('@expo-google-fonts/nunito/800ExtraBold/Nunito_800ExtraBold.ttf');
export function FontGate({children}:{children:React.ReactNode}){const [loaded,error]=useFonts({Nunito_800ExtraBold,NotoSansKR_400Regular,NotoSansKR_600SemiBold,NotoSansKR_700Bold});return loaded||error?children:<View style={{flex:1,justifyContent:'center',backgroundColor:'#f4faf7'}}><ActivityIndicator color='#108454'/></View>;}
