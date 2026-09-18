import type {Profile} from './service';

export type AccountConfig={url:string;functionKey?:string;allowLocalHttp?:boolean};
export type AccountSession={access_token:string;expires_at:number;profile:Profile;api_url:string};
export class AccountError extends Error {constructor(public status:number,message:string){super(message);}}
export function accountUrl(config:AccountConfig):string {
  const url=new URL(config.url);
  if((url.protocol!=='https:'&&!(config.allowLocalHttp&&url.protocol==='http:'))||url.username||url.password||url.search||url.hash||!/^\/api\/?$/.test(url.pathname))throw Error('로그인 서버 주소를 확인해주세요.');
  return config.url.replace(/\/+$/,'');
}
export async function accountRequest(config:AccountConfig,path:string,method:string,body?:unknown,token?:string,request:typeof fetch=fetch):Promise<any>{
  const url=accountUrl(config),controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try {
    const response=await request(url+'/auth/'+path,{method,redirect:'error',signal:controller.signal,
      headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...(config.functionKey?{'x-functions-key':config.functionKey}:{})},
      ...(body===undefined?{}:{body:JSON.stringify(body)})});
    let result:any;try{result=await response.json();}catch{throw Error('로그인 서버 응답을 확인할 수 없습니다.');}
    if(!response.ok)throw new AccountError(response.status,typeof result.message==='string'&&/[가-힣]/.test(result.message)?result.message:'계정 요청을 처리하지 못했습니다. 다시 시도해주세요.');
    return result;
  } finally {clearTimeout(timer);}
}
export function checkedProfile(value:any):Profile {
  if(!value||typeof value.id!=='string'||!value.id||typeof value.email!=='string'||typeof value.nickname!=='string'||!['user','developer'].includes(value.role)||typeof value.campaignCode!=='string'||typeof value.campaign_id!=='string')throw Error('사용자 정보를 확인할 수 없습니다.');
  return value;
}
export function checkedSession(value:any,config:AccountConfig):AccountSession {
  if(!value||typeof value.access_token!=='string'||!value.access_token.startsWith('canopy1.')||!Number.isFinite(value.expires_at)||value.expires_at*1000<=Date.now())throw Error('로그인 응답을 확인할 수 없습니다.');
  return {access_token:value.access_token,expires_at:value.expires_at,profile:checkedProfile(value.profile),api_url:accountUrl(config)};
}
