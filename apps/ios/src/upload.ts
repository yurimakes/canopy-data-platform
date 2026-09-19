import type { Storage } from './storage';
import type { GpsEvent } from './types';

export type ApiConfig = { url: string; functionKey: string; allowLocalHttp?:boolean };
export function validateApi(config: ApiConfig): ApiConfig {
  const url = new URL(config.url);
  const local=config.allowLocalHttp===true&&url.protocol==='http:'&&/^(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(url.hostname);
  if ((!local&&url.protocol!=='https:') || url.username || url.password || url.search || url.hash || !url.pathname.endsWith('/api/gps'))
    throw new Error('GPS API는 인증정보 없는 HTTPS /api/gps 주소여야 합니다.');
  if (!config.functionKey.trim()) throw new Error('GPS 함수 키가 설정되지 않았습니다.');
  return config;
}
export class Uploader {
  private busy = false;
  error = '';
  constructor(private db: Storage, private config: () => ApiConfig | null,
    private uuid: () => string, private now = Date.now, private request: typeof fetch = fetch) {}
  async tick(limit=20) {
    if (this.busy) return;
    this.busy=true;
    try {
      const candidate=this.config(); if(!candidate) {this.error='서버 설정 없음 · GPS는 휴대폰에 보관됩니다.';return;}
      const config=validateApi(candidate), deadline=this.now()+12000;
      for(let i=0;i<limit && this.now()<deadline;i++) {
        const job=await this.db.claimDelivery(config.url,this.now(),this.uuid()); if(!job) break;
        const event: GpsEvent=JSON.parse(job.payload);
        const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),5000);
        let blocked=false;
        try {
          const response=await this.request(config.url,{method:'POST',redirect:'error',signal:controller.signal,
            headers:{'Content-Type':'application/json','x-functions-key':config.functionKey},body:job.payload});
          if(response.status!==202) {
            blocked=response.status!==408 && response.status!==429 && response.status<500;
            throw new Error('GPS API HTTP '+response.status);
          }
          let ack: {status?:string;event_id?:string;trip_id?:string};
          try { ack=await response.json(); } catch {blocked=true;throw new Error('GPS API 확인 응답이 JSON이 아닙니다.');}
          // Team Bronze endpoint acknowledges the request without echoing IDs.
          // Older deployments echo IDs; reject an explicit mismatch in those responses.
          if(!ack || ack.status!=='accepted' ||
            (ack.event_id!==undefined && ack.event_id!==event.event_id) ||
            (ack.trip_id!==undefined && ack.trip_id!==event.trip_id)) {
            blocked=true;throw new Error('GPS API 확인 응답 ID 불일치');
          }
          await this.db.deliverySuccess(job,new Date(this.now()).toISOString());this.error='';
        } catch(e) {
          this.error=e instanceof Error ? e.message : 'GPS 전송 실패';
          await this.db.deliveryFailure(job,this.now()+Math.min(60000,1000*2**Math.min(job.retry_count,6)),this.error,blocked);
          break;
        } finally {clearTimeout(timer);}
      }
    } catch(e) {this.error=e instanceof Error?e.message:'전송 대기열 오류';}
    finally {this.busy=false;}
  }
}
