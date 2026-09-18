import Constants from 'expo-constants';
import type {RemotePanel,RankingView} from './ui/CommunityPanels';

type RankingRow={id:string;name:string;rank:number;points:number;is_me?:boolean};
type RankingResponse={
  status:'ready'|'empty'|'error';
  week?:string;
  updated_at?:string;
  score_unit?:string;
  personal?:RankingRow[];
  department?:RankingRow[];
};

function rankingConfig(){
  const extra=Constants.expoConfig?.extra;
  const base=typeof extra?.rankingApiUrl==='string'?extra.rankingApiUrl.trim().replace(/\/+$/,''):'';
  const functionKey=typeof extra?.rankingFunctionKey==='string'?extra.rankingFunctionKey:'';
  const campaignId=typeof extra?.rankingCampaignId==='string'?extra.rankingCampaignId.trim():'';
  const week=typeof extra?.rankingWeek==='string'?extra.rankingWeek.trim():'';
  return {base,functionKey,campaignId,week};
}

export async function loadRanking(userId:string,request:typeof fetch=fetch):Promise<RemotePanel<RankingView>>{
  const config=rankingConfig();
  if(!config.base||!config.functionKey)return {state:'unavailable'};

  const url=new URL(config.base);
  if(config.campaignId)url.searchParams.set('campaign_id',config.campaignId);
  if(config.week)url.searchParams.set('week',config.week);

  const response=await request(url.toString(),{
    method:'GET',
    headers:{
      'x-functions-key':config.functionKey,
      'x-canopy-user-id':userId,
    },
  });

  let body:RankingResponse;
  try{body=await response.json();}catch{return {state:'error',message:'랭킹 응답 형식을 확인할 수 없습니다.'};}

  if(response.status===401||response.status===403)return {state:'forbidden'};
  if(!response.ok)return {state:'error',message:'랭킹을 불러오지 못했습니다.'};
  if(body.status==='empty')return {state:'empty'};
  if(body.status!=='ready'||body.score_unit!=='points'||typeof body.week!=='string'||typeof body.updated_at!=='string'){
    return {state:'error',message:'랭킹 응답 계약이 현재 앱과 다릅니다.'};
  }

  const convert=(rows:RankingRow[]|undefined,personal:boolean)=>Array.isArray(rows)?rows
    .filter(row=>row&&typeof row.id==='string'&&typeof row.name==='string'&&Number.isFinite(row.rank)&&Number.isFinite(row.points))
    .map(row=>({
      id:row.id,
      name:row.name,
      rank:row.rank,
      points:row.points,
      ...(personal?{isMe:row.is_me===true}:{}),
    })):[];
  const personal=convert(body.personal,true);
  const department=convert(body.department,false).map(({isMe,...row})=>row);

  return {state:'ready',data:{week:body.week,updatedAt:body.updated_at,personal,department}};
}
