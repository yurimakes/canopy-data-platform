import type { Identity, Trip, TransportMode } from './types';
import type { Storage } from './storage';

export type FinalSegment = {
  segment_id:string; mode:TransportMode; start_time:string; end_time:string; distance_m:number; confidence:number;
  model_prediction?:TransportMode; confirmed_mode?:TransportMode|null; carbon_kg?:number;
};
export type ConfirmedTrip = {
  schema_version:'canopy.confirmed-trip.v1';trip_id:string;user_id:string;campaign_id:string;
  started_at:string;ended_at:string;confirmed_at:string;revision:number;confirmation_status:'confirmed';
  total_distance_m:number;total_carbon_kg:number;walk_distance_m:number;bike_distance_m:number;
  car_distance_m:number;bus_distance_m:number;rail_distance_m:number;
  carbon_unit:'kgCO2e';carbon_policy_version:string;factor_version:string;mode_source:'confirmed_mode'|'model_prediction';
  confirmation_source?:'system'|'user';
  is_mock:boolean;model_version:string;
};
export type Confirmation = {segment_id:string;confirmed_mode:TransportMode};
type ConfirmIntent = {request_id:string;expected_revision:number;segments:Confirmation[];api_url:string};
export type ServerTrip = {
  trip_id:string; user_id:string; device_id:string; started_at:string; ended_at:string|null;
  status:'collecting'|'processing'|'ready'|'failed'; model_version:string|null; is_mock:boolean;
  failed_step:string|null; error_message:string|null;
  segments:FinalSegment[];original_segments?:FinalSegment[];confirmed_segments?:FinalSegment[];
  confirmation_status?:'pending'|'confirmed';revision?:number;confirmed_at?:string;confirmed_trip?:ConfirmedTrip;
};
export type TripConfig = {url:string;token:string;functionKey?:string;allowLocalHttp?:boolean};
type StartIntent = {request_id:string;device_id:string;api_url:string};
type Sync = {result?:ServerTrip;error?:string;retry_at?:number;attempts?:number;retry_request_id?:string;confirmation?:ConfirmIntent};
class TripHttpError extends Error {
  constructor(public status:number,public code:string,message:string){super(`Trip API ${status}: ${message}`);}
}

export class TripApi {
  private busy=false;
  private confirming=new Set<string>();
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
      if(!response.ok) throw new TripHttpError(response.status,result.status,result.message??result.status??'요청 실패');
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
  async refresh(id:string):Promise<ServerTrip> {
    const trip=(await this.db.list()).find(t=>t.trip_id===id);
    if(!trip?.server)throw Error('저장된 서버 Trip이 없습니다.');
    if(this.confirming.has(id))throw Error('확인 결과를 저장하고 있습니다.');
    this.confirming.add(id);
    try {
      const state=await this.result(id)??{};
      const result=await this.call(`/trips/${id}`,'GET',undefined,trip.server.api_url);
      if(result.trip_id!==id || result.user_id!==trip.user_id)throw Error('서버 Trip ID 또는 사용자 ID가 일치하지 않습니다.');
      const refreshed={...state,result};delete refreshed.error;
      await this.db.saveSync('trip:'+id,refreshed);
      return result;
    } finally {this.confirming.delete(id);}
  }
  async confirm(id:string,segments?:Confirmation[]):Promise<ServerTrip> {
    if(this.confirming.has(id))throw Error('확인 결과를 저장하고 있습니다.');
    this.confirming.add(id);
    let state:Sync={};
    try {
      const trip=(await this.db.list()).find(t=>t.trip_id===id);
      state=await this.result(id)??{};
      if(!trip?.server || state.result?.status!=='ready')throw Error('Trip 처리 완료 후 확인할 수 있습니다.');
      let intent=state.confirmation;
      if(intent && segments && JSON.stringify(intent.segments)!==JSON.stringify(segments))throw Error('대기 중인 확인 요청을 먼저 재전송하세요.');
      if(!intent) {
        if(!segments)throw Error('확인할 이동수단을 선택하세요.');
        intent={request_id:this.uuid(),expected_revision:state.result.revision??0,segments,api_url:trip.server.api_url};
        state={...state,confirmation:intent};delete state.error;
        await this.db.saveSync('trip:'+id,state);
      }
      let result=await this.call(`/trips/${id}/confirm`,'POST',{
        request_id:intent.request_id,expected_revision:intent.expected_revision,segments:intent.segments},intent.api_url);
      if(result.trip_id!==id || result.user_id!==trip.user_id || result.confirmation_status!=='confirmed')throw Error('확인 응답의 Trip 또는 사용자 정보가 일치하지 않습니다.');
      // Clear the durable intent only after the server acknowledges it.
      state={result};await this.db.saveSync('trip:'+id,state);
      result=await this.call(`/trips/${id}`,'GET',undefined,intent.api_url);
      if(result.trip_id!==id || result.user_id!==trip.user_id)throw Error('결과 조회의 Trip 또는 사용자 정보가 일치하지 않습니다.');
      await this.db.saveSync('trip:'+id,{result});
      return result;
    } catch(e) {
      if(e instanceof TripHttpError && e.code==='revision_conflict') {
        // A different editor won. Never overwrite that revision automatically.
        state={...state};delete state.confirmation;
        const latest=await this.call(`/trips/${id}`,'GET',undefined,state.result? (await this.db.list()).find(t=>t.trip_id===id)?.server?.api_url:undefined);
        if(latest.trip_id===id && latest.user_id===state.result?.user_id)state.result=latest;
      }
      const attempts=(state.attempts??0)+1;
      await this.db.saveSync('trip:'+id,{...state,error:String(e),attempts,retry_at:this.now()+Math.min(60000,1000*2**Math.min(attempts,6))});
      throw e;
    } finally {this.confirming.delete(id);}
  }
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
        if(this.confirming.has(trip.trip_id))continue;
        if(state.confirmation) {
          if(wake || (state.retry_at??0)<=this.now()) {
            try {await this.confirm(trip.trip_id);}catch(e){this.error=String(e);}
          }
          continue;
        }
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
