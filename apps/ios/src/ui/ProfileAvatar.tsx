import React,{useState} from 'react';
import {Image,View} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import {manipulateAsync,SaveFormat} from 'expo-image-manipulator';
import Text from './AppText';
import {C} from './theme';
export function ProfileAvatar({name,uri,size=48}:{name:string;uri?:string|null;size?:number}){
 const [failed,setFailed]=useState<string|null>(null);
 return <View style={{width:size,height:size,borderRadius:size/2,backgroundColor:C.mint,alignItems:'center',justifyContent:'center',overflow:'hidden',borderWidth:2,borderColor:'white'}}>{uri&&failed!==uri?<Image source={{uri}} style={{width:size,height:size}} onError={()=>setFailed(uri)} accessibilityLabel={`${name} 프로필 사진`}/>:<Text style={{fontSize:size*.35,fontWeight:'700',color:C.green}}>{Array.from(name.trim())[0]??'C'}</Text>}</View>;
}
export async function chooseProfilePhoto(){
 const result=await ImagePicker.launchImageLibraryAsync({mediaTypes:['images'],allowsEditing:true,aspect:[1,1],quality:1,exif:false});
 if(result.canceled)return undefined;
 const asset=result.assets[0],side=Math.min(asset.width,asset.height);
 const photo=await manipulateAsync(asset.uri,[{crop:{originX:(asset.width-side)/2,originY:(asset.height-side)/2,width:side,height:side}},{resize:{width:128,height:128}}],{compress:.65,format:SaveFormat.JPEG,base64:true});
 if(!photo.base64||photo.base64.length>59977)throw Error('더 작은 사진을 선택해주세요.');
 return 'data:image/jpeg;base64,'+photo.base64;
}
