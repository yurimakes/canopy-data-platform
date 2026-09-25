import {MapFace} from './MascotMedia';
import * as Location from 'expo-location';
import {bearing,metersBetween} from '../journeyGeometry';
import React,{useEffect,useRef,useState} from 'react';
import {View,Pressable,Platform} from 'react-native';
import MapView,{Marker,Polyline} from 'react-native-maps';
import {Icon,Note,C} from './theme';
import type {MapProps} from './JourneyMap';
export default function JourneyMap({walking=false,points,route,height=310,fill=false,places,selectedPlace=0,onSelectPlace}:MapProps) {
  const ref=useRef<MapView>(null),last=points.at(-1),first=points[0]??route?.from;
  const [follow,setFollow]=useState(true),[deviceHeading,setDeviceHeading]=useState<number|null>(null);
  useEffect(()=>{if(!last)return;let alive=true,sub:Location.LocationSubscription|undefined,lastUpdate=0;void Location.getForegroundPermissionsAsync().then(async permission=>{if(!permission.granted||!alive)return;const watch=await Location.watchHeadingAsync(h=>{const value=h.trueHeading>=0?h.trueHeading:h.magHeading;if(alive&&h.accuracy>=0&&Date.now()-lastUpdate>300){lastUpdate=Date.now();setDeviceHeading(value);}});if(alive)sub=watch;else watch.remove();}).catch(()=>{});return()=>{alive=false;sub?.remove();};},[!!last]);
  const heading=useRef(0);const anchor=useRef(points[0]);if(last&&!anchor.current)anchor.current=last;if(last&&anchor.current&&metersBetween(anchor.current,last)>2){heading.current=bearing(anchor.current,last);anchor.current=last;}
  useEffect(()=>{if(last&&follow)ref.current?.animateCamera({center:last,heading:deviceHeading??heading.current,pitch:0,zoom:17,altitude:750},{duration:300});},[last?.latitude,last?.longitude,follow,deviceHeading]);
  useEffect(()=>{if(places?.length)ref.current?.fitToCoordinates(places,{edgePadding:{top:35,right:35,bottom:35,left:35},animated:true});},[places]);
  useEffect(()=>{const p=places?.[selectedPlace];if(p)ref.current?.animateToRegion({...p,latitudeDelta:.008,longitudeDelta:.008},350);},[selectedPlace,places]);
  if(places?.length)return <MapView mapType={Platform.OS==='ios'?'mutedStandard':'standard'} showsBuildings={false} showsPointsOfInterests={false} pitchEnabled={false} ref={ref} style={{...(fill?{flex:1,minHeight:0}:{height}),width:'100%'}} initialRegion={{...places[0],latitudeDelta:.025,longitudeDelta:.025}} onMapReady={()=>ref.current?.fitToCoordinates(places,{edgePadding:{top:35,right:35,bottom:35,left:35},animated:false})}>{places.map((p,i)=><Marker key={`${p.id??p.name}-${i}`} coordinate={p} title={p.name} description={p.address} pinColor={selectedPlace===i?C.green:'#87958e'} onPress={()=>onSelectPlace?.(i)}/>)}</MapView>;
  if(!first)return <View style={{height:fill?'100%':height,backgroundColor:C.mint,alignItems:'center',justifyContent:'center',gap:16}}><Icon name="navigate-outline" size={40}/><Note>위치를 받으면 지도가 표시됩니다.</Note></View>;
  return <View style={fill?{flex:1,minHeight:0}:undefined}><MapView mapType={Platform.OS==='ios'?'mutedStandard':'standard'} showsBuildings={false} showsPointsOfInterests={false} pitchEnabled={false} ref={ref} onPanDrag={()=>setFollow(false)} style={{...(fill?{flex:1,minHeight:0}:{height}),width:'100%'}} initialRegion={{...first,latitudeDelta:.025,longitudeDelta:.025}}
    onMapReady={()=>{if(last&&follow)ref.current?.animateCamera({center:last,heading:deviceHeading??heading.current,pitch:0,zoom:17,altitude:750},{duration:0});else if(route)ref.current?.fitToCoordinates([route.from,route.to,...route.legs.flatMap(l=>l.points)],{edgePadding:{top:35,right:35,bottom:35,left:35},animated:false});}}>
    {route?.provider==='local-test'&&<Polyline coordinates={[route.from,route.to]} strokeWidth={3} strokeColor='#799b92' lineDashPattern={[6,6]}/>}
    {route?.legs.filter(l=>l.points.length>1).map((leg,i)=><Polyline key={i} coordinates={leg.points} strokeWidth={6} strokeColor={leg.mode==='WALK'?'#9AAE8B':leg.mode==='BUS'?'#69945C':'#8B8FC4'} lineDashPattern={leg.mode==='WALK'?[5,5]:undefined}/>)}
    {points.length>1&&<Polyline coordinates={points} strokeColor={C.green} strokeWidth={6}/>}
    <Marker coordinate={route?.from??first} title="출발" anchor={{x:.5,y:.5}}><View style={{padding:9,borderRadius:20,backgroundColor:C.white,borderWidth:3,borderColor:"#C9DDB2"}}><Icon name="home-outline" size={20}/></View></Marker>
    {route&&<Marker coordinate={route.to} title="도착" anchor={{x:.5,y:.5}}><View style={{padding:9,borderRadius:20,backgroundColor:C.white,borderWidth:3,borderColor:"#D9D4EE"}}><Icon name="flag-outline" size={20}/></View></Marker>}
    {last&&!follow&&<Marker coordinate={last} title="현재 위치" anchor={{x:.5,y:.5}}><MapFace moving={walking}/></Marker>}
  </MapView>{last&&follow&&<View pointerEvents="none" style={{position:'absolute',top:'50%',left:'50%',width:40,height:40,marginLeft:-20,marginTop:-20}}><MapFace moving={walking}/></View>}{route?.provider==='local-test'&&<View style={{position:'absolute',top:12,left:12,right:12,padding:8,borderRadius:12,backgroundColor:'#ffffffee'}}><Note>점선은 직선거리 비교 기준입니다. 실제 도로 길 안내가 아닙니다.</Note></View>}{last&&<Pressable accessibilityRole="button" accessibilityLabel="내 위치로 지도 이동" onPress={()=>{setFollow(true);ref.current?.animateCamera({center:last,heading:deviceHeading??heading.current,pitch:0,zoom:17,altitude:750},{duration:300});}} style={{position:'absolute',bottom:16,right:16,padding:14,borderRadius:30,backgroundColor:C.white,elevation:3}}><Icon name="locate-outline"/></Pressable>}</View>;
}
