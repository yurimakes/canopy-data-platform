import React,{useEffect,useRef,useState} from 'react';
import {View,Pressable} from 'react-native';
import MapView,{Marker,Polyline} from 'react-native-maps';
import {Icon,Note,C} from './theme';
import type {MapProps} from './JourneyMap';
export default function JourneyMap({points,route,height=310,places,selectedPlace=0,onSelectPlace}:MapProps) {
  const ref=useRef<MapView>(null),last=points.at(-1),first=points[0]??route?.from;
  const [follow,setFollow]=useState(true);
  useEffect(()=>{if(last&&follow)ref.current?.animateToRegion({...last,latitudeDelta:.008,longitudeDelta:.008},400);},[last?.latitude,last?.longitude,follow]);
  useEffect(()=>{if(places?.length)ref.current?.fitToCoordinates(places,{edgePadding:{top:35,right:35,bottom:35,left:35},animated:true});},[places]);
  useEffect(()=>{const p=places?.[selectedPlace];if(p)ref.current?.animateToRegion({...p,latitudeDelta:.008,longitudeDelta:.008},350);},[selectedPlace,places]);
  if(places?.length)return <MapView ref={ref} style={{height,width:'100%'}} initialRegion={{...places[0],latitudeDelta:.025,longitudeDelta:.025}} onMapReady={()=>ref.current?.fitToCoordinates(places,{edgePadding:{top:35,right:35,bottom:35,left:35},animated:false})}>{places.map((p,i)=><Marker key={`${p.id??p.name}-${i}`} coordinate={p} title={p.name} description={p.address} pinColor={selectedPlace===i?C.green:'#87958e'} onPress={()=>onSelectPlace?.(i)}/>)}</MapView>;
  if(!first)return <View style={{height,backgroundColor:C.mint,alignItems:'center',justifyContent:'center',gap:16}}><Icon name="navigate-outline" size={40}/><Note>위치를 받으면 지도가 표시됩니다.</Note></View>;
  return <View><MapView ref={ref} onPanDrag={()=>setFollow(false)} style={{height,width:'100%'}} initialRegion={{...first,latitudeDelta:.025,longitudeDelta:.025}}
    onMapReady={()=>{if(route)ref.current?.fitToCoordinates([route.from,route.to,...route.legs.flatMap(l=>l.points)],{edgePadding:{top:35,right:35,bottom:35,left:35},animated:false});}}>
    {route?.legs.filter(l=>l.points.length>1).map((leg,i)=><Polyline key={i} coordinates={leg.points} strokeWidth={5} strokeColor={leg.mode==='WALK'?'#9baba5':'#5279d1'} lineDashPattern={leg.mode==='WALK'?[5,5]:undefined}/>)}
    {points.length>1&&<Polyline coordinates={points} strokeColor={C.green} strokeWidth={4}/>}
    <Marker coordinate={route?.from??first} title="출발" pinColor={C.green}/>
    {route&&<Marker coordinate={route.to} title="도착" pinColor="#5279d1"/>}
    {last&&<Marker coordinate={last} title="최근 GPS 위치" pinColor={C.deep}/>}
  </MapView>{last&&<Pressable accessibilityRole="button" accessibilityLabel="내 위치로 지도 이동" onPress={()=>{setFollow(true);ref.current?.animateToRegion({...last,latitudeDelta:.008,longitudeDelta:.008},400);}} style={{position:'absolute',bottom:16,right:16,padding:14,borderRadius:30,backgroundColor:C.white,elevation:3}}><Icon name="locate-outline"/></Pressable>}</View>;
}
