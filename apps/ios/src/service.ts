import type { GpsEvent } from './types';

export type Place = { name:string; latitude:number; longitude:number };
export type Profile = { id:string; nickname:string; email:string; role:'user'|'developer'; campaignCode:'TEST'; home:Place|null; work:Place|null };
export type RouteLeg = { mode:string; name:string; minutes:number; distance_m:number; points:Place[] };
export type PlannedRoute = { id:string; provider:'tmap'; searchedAt:string; minutes:number; distance_m:number; fare:number|null; legs:RouteLeg[]; from:Place; to:Place };
export const developerProfile:Profile={id:'local-developer',nickname:'개발자',email:'canopydev',role:'developer',campaignCode:'TEST',home:null,work:null};
export function validPlace(p:Place|null):p is Place {return !!p && !!p.name.trim() && Number.isFinite(p.latitude) && Math.abs(p.latitude)<=90 && Number.isFinite(p.longitude) && Math.abs(p.longitude)<=180;}
export const km=(m:number)=>`${(m/1000).toFixed(2)} km`;
export function gpsDistance(events:GpsEvent[]):number {
  let total=0;
  for(let i=1;i<events.length;i++) {
    const a=events[i-1],b=events[i];
    if(a.trip_id!==b.trip_id || a.accuracy==null || b.accuracy==null || a.accuracy>100 || b.accuracy>100)continue;
    const dt=(Date.parse(b.event_time)-Date.parse(a.event_time))/1000;
    if(dt<=0 || dt>60)continue;
    const rad=Math.PI/180, dlat=(b.lat-a.lat)*rad,dlon=(b.lon-a.lon)*rad;
    const h=Math.sin(dlat/2)**2+Math.cos(a.lat*rad)*Math.cos(b.lat*rad)*Math.sin(dlon/2)**2;
    const d=6371000*2*Math.asin(Math.sqrt(Math.min(1,h)));
    if(Number.isFinite(d) && d/dt<70)total+=d;
  }
  return total;
}

// TMAP 원본 응답 변환. 실제 폴리라인이 없으면 직선 경로 생성 제외
export function parseRoutes(raw:any,from:Place,to:Place):PlannedRoute[] {
  const itineraries=raw?.metaData?.plan?.itineraries;
  if(!Array.isArray(itineraries))throw Error('길찾기 응답을 확인할 수 없습니다. 잠시 후 다시 검색해주세요.');
  const amount=(v:unknown)=>typeof v==='number' && Number.isFinite(v) && v>=0;
  return itineraries.filter((r:any)=>amount(r.totalTime)&&amount(r.totalDistance)&&Array.isArray(r.legs)).map((r:any,i:number)=>({
    id:`tmap-${i}`,provider:'tmap',searchedAt:new Date().toISOString(),minutes:Math.ceil(r.totalTime/60),distance_m:r.totalDistance,
    fare:amount(r.fare?.regular?.totalFare)?r.fare.regular.totalFare:null,from,to,
    legs:r.legs.map((leg:any)=>({mode:String(leg.mode??'UNKNOWN'),name:leg.route??(leg.mode==='WALK'?'도보':'이동'),minutes:Math.ceil((leg.sectionTime??0)/60),distance_m:leg.distance??0,
      points:(leg.passShape?.linestring?[leg.passShape.linestring]:(leg.steps??[]).map((s:any)=>s.linestring)).flatMap((line:any)=>typeof line==='string'?line.split(' ').filter(Boolean).map((pair:string)=>{
        const [longitude,latitude]=pair.split(',').map(Number);return {name:'경로',latitude,longitude};
      }).filter(validPlace):[])})),
  }));
}

export async function searchRoutes(url:string,headers:Record<string,string>,from:Place,to:Place,request:typeof fetch=fetch):Promise<PlannedRoute[]> {
  if(!validPlace(from)||!validPlace(to))throw Error('출발지와 도착지의 위치를 확인해주세요.');
  if(from.latitude===to.latitude&&from.longitude===to.longitude)throw Error('출발지와 도착지를 다르게 선택해주세요.');
  if(!url)throw Error('길찾기 서버 연결을 준비하고 있습니다. 경로 없이 여정 기록은 시작할 수 있어요.');
  if(new URL(url).protocol!=='https:')throw Error('길찾기 서버는 HTTPS 주소가 필요합니다.');
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
  try {
    const response=await request(url,{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({from,to}),signal:abort.signal,redirect:'error'});
    if(!response.ok)throw Error(response.status===429?'길찾기 이용 한도에 도달했습니다. 잠시 후 다시 시도해주세요.':'길찾기 서버에 연결하지 못했습니다. 다시 시도해주세요.');
    return parseRoutes(await response.json(),from,to);
  }catch(e){if(e instanceof Error && e.name==='AbortError')throw Error('길찾기 응답이 늦어지고 있습니다. 다시 시도해주세요.');throw e;}
  finally{clearTimeout(timer);}
}
