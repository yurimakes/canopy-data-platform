import type { GpsEvent } from './types';

export type Place = { name:string; latitude:number; longitude:number; address?:string; id?:string };
export type Profile = { id:string; nickname:string; email:string; role:'user'|'developer'; campaignCode:string; campaign_id?:string; department_id?:string|null; department_name?:string; home:Place|null; work:Place|null };
export type RouteLeg = { mode:string; name:string; minutes:number; distance_m:number; points:Place[]; startName?:string; endName?:string };
export type PlannedRoute = { id:string; provider:'tmap'|'local-test';quoteId?:string;expectedKg?:number;baselineRateG?:number;baselineSource?:string;modeProbabilities?:Record<string,number>; searchedAt:string; minutes:number; distance_m:number; fare:number|null; legs:RouteLeg[]; from:Place; to:Place };
export const developerProfile:Profile={id:'local-developer',nickname:'개발자',email:'canopydev',role:'developer',campaignCode:'TEST',home:null,work:null};
export function validPlace(p:Place|null):p is Place {return !!p && !!p.name.trim() && Number.isFinite(p.latitude) && Math.abs(p.latitude)<=90 && Number.isFinite(p.longitude) && Math.abs(p.longitude)<=180;}
export const km=(m:number)=>`${(m/1000).toFixed(2)} km`;
// 기존 설치본에도 있는 Trip API 설정을 사용. 호스트와 인증정보 하드코딩 제외
export function routeApiUrl(config:{routeApiUrl?:unknown;tripApiUrl?:unknown}):string {
  if(typeof config.routeApiUrl==='string'&&config.routeApiUrl.trim())return config.routeApiUrl.trim();
  if(typeof config.tripApiUrl==='string'&&config.tripApiUrl.trim())return config.tripApiUrl.trim().replace(/\/+$/,'')+'/routes/transit';
  return '';
}
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
    legs:r.legs.filter((leg:any)=>leg&&typeof leg==='object').map((leg:any)=>({mode:String(leg.mode??'UNKNOWN'),name:leg.route??(leg.mode==='WALK'?'도보':'이동'),minutes:amount(leg.sectionTime)?Math.ceil(leg.sectionTime/60):0,distance_m:amount(leg.distance)?leg.distance:0,startName:leg.start?.name,endName:leg.end?.name,
      points:(leg.passShape?.linestring?[leg.passShape.linestring]:(leg.steps??[]).map((s:any)=>s.linestring)).flatMap((line:any)=>typeof line==='string'?line.split(' ').filter(Boolean).map((pair:string)=>{
        const [longitude,latitude]=pair.split(',').map(Number);return {name:'경로',latitude,longitude};
      }).filter(validPlace):[])})),
  }));
}

// 화면 표시 전용 상태. 완료율이나 ML 진행률을 추정하지 않고 실제 응답만 사용
export function journeyStage(pending:number|undefined,status:string|undefined,failedMessage?:string|null) {
  if(status==='failed')return {step:1,title:'결과 처리를 마치지 못했어요',detail:failedMessage||'잠시 후 다시 시도해주세요.',failed:true};
  if(status==='ready')return {step:2,title:'여정 분석 완료',detail:'서버에서 확정한 이동 결과입니다.',failed:false};
  if(pending==null)return {step:0,title:'저장된 기록을 확인하고 있어요',detail:'휴대폰의 전송 상태를 확인하고 있습니다.',failed:false};
  if(pending>0)return {step:0,title:'이동 기록을 전송 중이에요',detail:`남은 위치 ${pending}개를 전송하고 있습니다. 연결이 끊겨도 기록은 휴대폰에 남습니다.`,failed:false};
  return {step:1,title:'서버에서 여정을 분석 중이에요',detail:'완료되면 결과가 자동으로 표시됩니다. 다른 화면으로 이동해도 괜찮아요.',failed:false};
}

export async function searchRoutes(url:string,headers:Record<string,string>,from:Place,to:Place,request:typeof fetch=fetch):Promise<PlannedRoute[]> {
  if(!validPlace(from)||!validPlace(to))throw Error('출발지와 도착지의 위치를 확인해주세요.');
  if(from.latitude===to.latitude&&from.longitude===to.longitude)throw Error('출발지와 도착지를 다르게 선택해주세요.');
  if(!url)throw Error('앱에 서버 주소가 반영되지 않았어요. Expo Go에서 현재 프로젝트를 닫고 PC의 새 QR 코드로 다시 열어주세요.');
  if(new URL(url).protocol!=='https:')throw Error('길찾기 서버는 HTTPS 주소가 필요합니다.');
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),30000);
  try {
    const response=await request(url,{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({from,to}),signal:abort.signal,redirect:'error'});
    if(!response.ok)throw await routeError(response);
    return parseRoutes(await response.json(),from,to);
  }catch(e){if(e instanceof Error && e.name==='AbortError')throw Error('길찾기 응답이 늦어지고 있습니다. 다시 시도해주세요.');throw e;}
  finally{clearTimeout(timer);}
}

export async function routeError(response:Response):Promise<Error> {
  let body:any;try{body=await response.json();}catch{}
  if(response.status===401||response.status===403)return Error('서버 인증이 만료됐습니다. 앱을 새로 열어도 같으면 관리자에게 알려주세요.');
  if(response.status===404)return Error('검색 서비스를 찾지 못했습니다. 앱을 새로 열어 다시 시도해주세요.');
  if(typeof body?.message==='string'&&body.message.length<400&&/[가-힣]/.test(body.message))return Error(body.message);
  return Error(response.status===429?'검색 이용 한도에 도달했습니다. 잠시 후 다시 시도해주세요.':'검색 서버 응답에 문제가 있습니다. 잠시 후 다시 시도해주세요.');
}
export async function searchPlaces(url:string,headers:Record<string,string>,query:string,request:typeof fetch=fetch):Promise<Place[]> {
  if(query.trim().length<2)throw Error('장소 이름이나 주소를 두 글자 이상 입력해주세요.');
  if(!url)throw Error('앱에 검색 서버 주소가 반영되지 않았습니다. 새 QR 코드로 다시 열어주세요.');
  const endpoint=new URL(url);if(endpoint.protocol!=='https:')throw Error('검색 서버는 HTTPS 주소가 필요합니다.');
  endpoint.pathname=endpoint.pathname.replace(/\/routes\/transit\/?$/, '/routes/places');
  if(!endpoint.pathname.endsWith('/routes/places'))throw Error('장소 검색 서버 주소를 확인해주세요.');
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
  try {
    const response=await request(endpoint.toString(),{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({query:query.trim()}),signal:abort.signal});
    if(!response.ok)throw await routeError(response);
    const data=await response.json();if(!Array.isArray(data.places))throw Error('장소 검색 응답을 확인할 수 없습니다.');
    return data.places.filter((p:any)=>p&&typeof p.name==='string'&&validPlace(p));
  }catch(e){if(e instanceof Error&&e.name==='AbortError')throw Error('장소 검색 응답이 늦어지고 있습니다. 다시 시도해주세요.');throw e;}
  finally{clearTimeout(timer);}
}
