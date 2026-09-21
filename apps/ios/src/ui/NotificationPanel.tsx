import React,{useState} from 'react';
import Text from './AppText';
import {Button,Card,Icon,Note,S} from './theme';
import {localAction} from '../communityClient';
import type {RemotePanel} from './CommunityPanels';
export type NotificationView={unread:number;items:{id:string;title:string;message:string;time:string;read:boolean;target:'history'|'missions'|'rewards'}[]};
export function NotificationPanel({value,onOpen,onRefresh}:{value?:RemotePanel<NotificationView>;onOpen(target:'history'|'missions'|'rewards'):void;onRefresh?():void}){
  const [error,setError]=useState('');
  async function open(item:NotificationView['items'][number]){try{await localAction('/notifications/read',{id:item.id});onRefresh?.();onOpen(item.target);}catch(e){setError(e instanceof Error?e.message:'알림을 열지 못했어요.');}}
  return <>{!!error&&<Note error>{error}</Note>}{value?.state==='ready'?value.data.items.length?value.data.items.map(item=><Card key={item.id}><Text style={S.pill}>{item.read?'확인한 알림':'새 알림'}</Text><Text style={S.heading}>{item.title}</Text><Note>{item.message}</Note><Note>{new Date(item.time).toLocaleString('ko-KR')}</Note><Button title="내용 확인" quiet onPress={()=>void open(item)}/></Card>):<Card><Icon name="notifications-outline" size={32}/><Text style={S.heading}>새로운 알림이 없어요</Text><Note>여정 분석 완료, 미션 달성, 보상 적립 소식이 여기에 쌓여요.</Note></Card>:<Card><Note>{value?.state==='error'?value.message:'알림을 불러오는 중이에요.'}</Note><Button title="다시 불러오기" onPress={()=>onRefresh?.()}/></Card>}</>;
}
