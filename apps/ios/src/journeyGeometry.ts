import type {Place,PlannedRoute} from './service';
export function metersBetween(a:Place,b:Place){const r=Math.PI/180,dlat=(b.latitude-a.latitude)*r,dlon=(b.longitude-a.longitude)*r;return 6371000*2*Math.atan2(Math.sqrt(Math.sin(dlat/2)**2+Math.cos(a.latitude*r)*Math.cos(b.latitude*r)*Math.sin(dlon/2)**2),Math.sqrt(Math.max(0,1-(Math.sin(dlat/2)**2+Math.cos(a.latitude*r)*Math.cos(b.latitude*r)*Math.sin(dlon/2)**2))));}
export function bearing(a:Place,b:Place){const r=Math.PI/180,dl=(b.longitude-a.longitude)*r;return (Math.atan2(Math.sin(dl)*Math.cos(b.latitude*r),Math.cos(a.latitude*r)*Math.sin(b.latitude*r)-Math.sin(a.latitude*r)*Math.cos(b.latitude*r)*Math.cos(dl))*180/Math.PI+360)%360;}
// 경로가 없는 자유 여정에 가상의 도착률을 표시하지 않음
export function journeyProgress(route:PlannedRoute|null,last?:Place){if(!route||!last)return 0;const total=metersBetween(route.from,route.to);return total<1?0:Math.min(1,Math.max(0,1-metersBetween(last,route.to)/total));}
