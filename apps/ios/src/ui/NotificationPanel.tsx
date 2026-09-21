import React,{useState} from 'react';
import Text from './AppText';
import {Pressable,View} from 'react-native';
import {Button,Card,C,Icon,Note,S} from './theme';
import {Eyebrow} from './DesignPrimitives';
import {localAction} from '../communityClient';
import type {RemotePanel} from './CommunityPanels';
export type NotificationView={unread:number;items:{id:string;title:string;message:string;time:string;read:boolean;target:'history'|'missions'|'rewards'}[]};
export function NotificationPanel({value,onOpen,onRefresh}:{value?:RemotePanel<NotificationView>;onOpen(target:'history'|'missions'|'rewards'):void;onRefresh?():void}){
 const [error,setError]=useState(''),[opening,setOpening]=useState<string|null>(null);
 async function open(item:NotificationView['items'][number]){if(opening)return;setOpening(item.id);try{await localAction('/notifications/read',{id:item.id});onRefresh?.();onOpen(item.target);}catch{setError('알림을 열지 못했어요. 다시 시도해주세요.');}finally{setOpening(null);}}
 return <><Eyebrow>GOOD NEWS FOR YOU</Eyebrow><Text style={S.title}>반가운 소식이{'\n'}도착했어요.</Text>{!!error&&<Note error>{error}</Note>}{value?.state==='ready'?value.data.items.length?value.data.items.map(item=><Pressable key={item.id} accessibilityRole="button" accessibilityLabel={`${item.read?'':'새 알림. '}${item.title}`} disabled={!!opening} onPress={()=>void open(item)} style={[S.row,{alignItems:'flex-start',paddingVertical:20,borderBottomWidth:1,borderColor:C.line}]}><View style={{padding:12,borderRadius:16,backgroundColor:item.read?C.mint:C.leaf}}><Icon name={item.target==='rewards'?'wallet-outline':item.target==='missions'?'flag-outline':'footsteps-outline'}/></View><View style={{flex:1,gap:8}}><Text style={S.label}>{item.title}</Text><Note>{item.message}</Note><Text style={{fontSize:11,color:C.muted}}>{new Date(item.time).toLocaleString('ko-KR')}</Text></View><Icon name="chevron-forward" size={16}/></Pressable>):<Card><Icon name="notifications-outline" size={36}/><Text style={S.heading}>모두 확인했어요</Text><Note>보상과 미션 소식을 여기서 알려드릴게요.</Note></Card>:<Card><Note>{value?.state==='error'?'연결을 확인하고 다시 시도해주세요.':'알림을 불러오고 있어요.'}</Note><Button title="다시 불러오기" onPress={()=>onRefresh?.()}/></Card>}</>;
}
