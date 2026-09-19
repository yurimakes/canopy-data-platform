import {useEffect,useState,useCallback,useRef} from 'react';
import Constants from 'expo-constants';
import {loadSession} from './accountSession';
import {accountConfig} from './accountConfig';
import type {BaselineView,MissionView,RankingView,RewardView,RemotePanel} from './ui/CommunityPanels';
type Panels={baseline:RemotePanel<BaselineView>;missions:RemotePanel<MissionView>;ranking:RemotePanel<RankingView>;rewards:RemotePanel<RewardView>};
const empty:Panels={baseline:{state:'unavailable'},missions:{state:'unavailable'},ranking:{state:'unavailable'},rewards:{state:'unavailable'}};
export function useCommunity(userId?:string){
  const [panels,setPanels]=useState<Panels>(empty);
  const currentUser=useRef(userId);currentUser.current=userId;
  const refresh=useCallback(async()=>{
    if(!userId||Constants.expoConfig?.extra?.localOnly!==true){setPanels(empty);return;}
    try{
      const s=await loadSession(),config=accountConfig();
      if(!s||s.profile.id!==userId||s.api_url!==config.url.replace(/\/+$/,'')){setPanels(empty);return;}
      const response=await fetch(config.url.replace(/\/+$/,'')+'/community',{headers:{Authorization:'Bearer '+s.access_token}});
      if(!response.ok)throw Error('주간 결과를 불러오지 못했습니다.');
      const next=await response.json();if(currentUser.current===userId)setPanels(next);
    }catch(e){if(currentUser.current!==userId)return;const value={state:'error' as const,message:e instanceof Error?e.message:'조회 실패'};setPanels({baseline:value,missions:value,ranking:value,rewards:value});}
  },[userId]);
  useEffect(()=>{setPanels(empty);void refresh();const timer=setInterval(()=>void refresh(),15000);return()=>clearInterval(timer);},[refresh]);
  return {...panels,onRefreshCommunity:()=>void refresh()};
}

export async function localAction(path:string,body?:unknown){
  if(Constants.expoConfig?.extra?.localOnly!==true)throw Error('연결이 준비되지 않았습니다.');
  const s=await loadSession();if(!s)throw Error('다시 로그인해주세요.');
  const r=await fetch(accountConfig().url.replace(/\/+$/,'')+path,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+s.access_token,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const result=await r.json();if(!r.ok)throw Error(result.message??'요청 실패');return result;
}
export async function prepareJourney(quoteId?:string){
  if(Constants.expoConfig?.extra?.localOnly===true)await localAction('/journey/prepare',{quote_id:quoteId??null});
}
