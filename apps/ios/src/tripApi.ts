import type { Identity, Trip, TransportMode } from './types';
import type { Storage } from './storage';

export type ServerTrip = {
  trip_id:string; user_id:string; device_id:string; started_at:string; ended_at:string|null;
  status:'collecting'|'processing'|'ready'|'failed'; model_version:string|null; is_mock:boolean;
  failed_step:string|null; error_message:string|null;
  segments:Array<{segment_id:string;mode:TransportMode;start_time:string;end_time:string;distance_m:number;confidence:number}>;
};
export type TripConfig = {url:string;token:string;functionKey?:string;allowLocalHttp?:boolean};
type StartIntent = {request_id:string;device_id:string;api_url:string};
type Sync = {result?:ServerTrip;error?:string;retry_at?:number;attempts?:number;retry_request_id?:string};

export class TripApi {
  private busy=false;
  error='';
  constructor(private db:Storage,private config:()=>TripConfig|null,private uuid:()=>string,
    private request:typeof fetch=fetch,private now:()=>number=Date.now) {}

  private configuration(url?:string) {
    const config=this.config();
    if(!config?.url || !config.token) throw new Error('Trip API 주소와 사용자 인증 설정이 필요합니다.');
    const parsed=new URL(config.url);
    if(parsed.protocol!=='https:' && !(config.allowLocalHttp && parsed.protocol==='http:')) throw new Error('Trip API는 HTTPS 주소를 사용하세요.');
    if(parsed.username || parsed.password || parsed.search || parsed.hash || !/\/api\/?$/.test(parsed.pathname)) throw new Error('Trip API 주소는 /api로 끝나야 합니다.');
    const base=config.url.replace(/\/$/,'');
    if(url && url!==base) throw new Error('이 Trip을 시작한 서버 주소와 현재 설정이 다릅니다.');
    return {...config,url:base};
  }
  private async call(path:string,method:string,body?:unknown,url?:string):Promise<ServerTrip> {
    const config=this.configuration(url), abort=new AbortController();
    const timeout=setTimeout(()=>abort.abort(),10000);
    try {
      const response=await this.request(config.url+path,{method,signal:abort.signal,redirect:'error',
        headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json',
          ...(config.functionKey?{'x-functions-key':config.functionKey}:{})},
        ...(body===undefined?{}:{body:JSON.stringify(body)})});
      const result=await response.json();
      if(!response.ok) throw new Error(`Trip API ${response.status}: ${result.message??result.status??'요청 실패'}`);
      if(typeof result.trip_id!=='string' || typeof result.user_id!=='string' || !Number.isFinite(Date.parse(result.started_at)) ||
         !['collecting','processing','ready','failed'].includes(result.status) || !Array.isArray(result.segments)) throw new Error('Trip API 응답 형식이 다릅니다.');
      return result;
    } finally {clearTimeout(timeout);}
  }
  async start(identity:Identity):Promise<Pick<Trip,'trip_id'|'user_id'|'started_at'|'server'>> {
    const config=this.configuration();
    let intent=await this.db.syncValue<StartIntent>('start');
    if(!intent) {
      intent={request_id:this.uuid(),device_id:identity.device_id,api_url:config.url};
      await this.db.saveSync('start',intent); // Persist BEFORE HTTP; reuse after a timeout/restart.
    }
    if(intent.device_id!==identity.device_id) throw new Error('대기 중인 시작 요청의 기기가 다릅니다.');
    const result=await this.call('/trips/start','POST',{request_id:intent.request_id,device_id:intent.device_id},intent.api_url);
    if(result.device_id!==intent.device_id) throw new Error('시작 응답의 기기 ID가 일치하지 않습니다.');
    if(result.status!=='collecting') throw new Error('이 시작 요청의 Trip은 이미 종료됐습니다. 저장된 Trip 상태를 확인하세요.');
    // Storage clears this start intent atomically when the local Trip is saved.
    return {trip_id:result.trip_id,user_id:result.user_id,started_at:result.started_at,
      server:{api_url:intent.api_url,request_id:intent.request_id}};
  }
  result(id:string) {return this.db.syncValue<Sync>('trip:'+id);}
  async retry(id:string) {
    const state=await this.result(id);
    if(state?.result?.status==='failed') await this.db.saveSync('trip:'+id,{...state,retry_at:0,retry_request_id:state.retry_request_id??this.uuid()});
    await this.tick(true);
  }
  async tick(wake=false) {
    if(this.busy)return;this.busy=true;this.error='';
    try {
      for(const trip of await this.db.list()) {
        if(!trip.server || trip.status==='recording')continue;
        const state=await this.result(trip.trip_id) ?? {};
        if(state.result?.status==='ready' || (state.result?.status==='failed' && !state.retry_request_id))continue;
        if(!wake && (state.retry_at??0)>this.now())continue;
        try {
          if((await this.db.deliveryStatus(trip.trip_id)).pending>0)continue;
          let result=state.result;
          if(!result || result.status==='collecting' || state.retry_request_id) {
            const ended_at=trip.ended_at ?? trip.last_event_time ?? trip.recovered_at ?? trip.started_at;
            result=await this.call(`/trips/${trip.trip_id}/stop`,'POST',{
              ended_at, expected_last_sequence:trip.gps_count,
              ...(state.retry_request_id?{retry:true,retry_request_id:state.retry_request_id}:{})},trip.server.api_url);
          } else {
            result=await this.call(`/trips/${trip.trip_id}`,'GET',undefined,trip.server.api_url);
          }
          if(result.trip_id!==trip.trip_id || result.user_id!==trip.user_id) throw new Error('서버 Trip ID 또는 사용자 ID가 일치하지 않습니다.');
          await this.db.saveSync('trip:'+trip.trip_id,{result,retry_at:this.now()+3000});
        } catch(e) {
          const attempts=(state.attempts??0)+1;
          const error=String(e);this.error=error;
          await this.db.saveSync('trip:'+trip.trip_id,{...state,error,attempts,retry_at:this.now()+Math.min(60000,1000*2**Math.min(attempts,6))});
        }
      }
    } finally {this.busy=false;}
  }
}
