import {useEffect,useState,useCallback,useRef} from 'react';
import Constants from 'expo-constants';
import {loadSession} from './accountSession';
import {accountConfig} from './accountConfig';
import type {BaselineView,MissionView,RankingView,RewardView,RemotePanel} from './ui/CommunityPanels';
import type {NotificationView} from './ui/NotificationPanel';
type Panels={weeklyStatus?:{state:string;message:string};notifications?:RemotePanel<NotificationView>;baseline:RemotePanel<BaselineView>;missions:RemotePanel<MissionView>;ranking:RemotePanel<RankingView>;rewards:RemotePanel<RewardView>};
const empty:Panels={notifications:{state:'unavailable'},baseline:{state:'unavailable'},missions:{state:'unavailable'},ranking:{state:'unavailable'},rewards:{state:'unavailable'}};
export function useCommunity(userId?:string){
  const [panels,setPanels]=useState<Panels>(empty);
  const currentUser=useRef(userId);currentUser.current=userId;
  const refresh=useCallback(async()=>{
    if(!userId){setPanels(empty);return;}
    try{
      const s=await loadSession(),config=accountConfig();
      if(!s||s.profile.id!==userId||s.api_url!==config.url.replace(/\/+$/,'')){setPanels(empty);return;}
      const next=await localAction('/community');if(currentUser.current===userId)setPanels(next);
    }catch(e){if(currentUser.current!==userId)return;const value={state:'error' as const,message:e instanceof Error?e.message:'조회 실패'};setPanels({notifications:value,baseline:value,missions:value,ranking:value,rewards:value});}
  },[userId]);
  useEffect(()=>{setPanels(empty);void refresh();const timer=setInterval(()=>void refresh(),15000);return()=>clearInterval(timer);},[refresh]);
  return {...panels,onRefreshCommunity:()=>void refresh()};
}

export async function localAction(path:string,body?:unknown){
  const s=await loadSession();if(!s)throw Error('다시 로그인해주세요.');
  const config=accountConfig();if(s.api_url!==config.url.replace(/\/+$/,''))throw Error('서버가 변경됐어요. 다시 로그인해주세요.');
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),path==='/local/reward-demo'?120000:20000);
  try{const r=await fetch(config.url.replace(/\/+$/,'')+path,{signal:controller.signal,method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+s.access_token,'Content-Type':'application/json',...(config.functionKey?{'x-functions-key':config.functionKey}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
    const result=await r.json();if(!r.ok)throw Error(result.message??'요청 실패');return result;
  }catch(e){if(e instanceof TypeError||(e as Error).name==='AbortError')throw Error('서버 연결을 확인하고 다시 시도해주세요.');throw e;}finally{clearTimeout(timer);}
}
export async function prepareJourney(quoteId?:string,direction:'outbound'|'return'='outbound'){
  await localAction('/journey/prepare',{quote_id:quoteId??null,direction});
}
