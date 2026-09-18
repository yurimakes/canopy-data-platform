import type {TripConfig} from './tripApi';

export type RegisteredUser={user_id:string;campaign_id:string;created_at:string;campaign_joined_at:string};

export async function registerServerUser(config:TripConfig|null,nickname:string,campaignCode:string,request:typeof fetch=fetch):Promise<RegisteredUser> {
  if(!config?.url||!config.token)throw Error('사용자 저장 서버의 인증 설정이 필요합니다.');
  const url=new URL(config.url);
  if(url.protocol!=='https:'&&!(config.allowLocalHttp&&url.protocol==='http:'))throw Error('사용자 저장에는 HTTPS 서버가 필요합니다.');
  if(url.username||url.password||url.search||url.hash)throw Error('서버 주소 설정을 확인해주세요.');
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try {
    const response=await request(config.url.replace(/\/+$/,'')+'/users/register',{
      method:'POST',redirect:'error',signal:controller.signal,
      headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json',...(config.functionKey?{'x-functions-key':config.functionKey}:{})},
      body:JSON.stringify({nickname,campaign_code:campaignCode}),
    });
    const result=await response.json();
    if(!response.ok)throw Error(response.status===409?'서버의 기존 캠페인 등록 정보를 확인해주세요.':'사용자 정보를 저장하지 못했습니다. 인증과 연결 상태를 확인하고 다시 시도해주세요.');
    if(typeof result.user_id!=='string'||typeof result.campaign_id!=='string'||!Number.isFinite(Date.parse(result.created_at))||!Number.isFinite(Date.parse(result.campaign_joined_at)))throw Error('사용자 저장 응답을 확인할 수 없습니다.');
    return result;
  } finally {clearTimeout(timer);}
}
