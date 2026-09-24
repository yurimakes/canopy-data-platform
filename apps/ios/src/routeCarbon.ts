import type {PlannedRoute} from './service';
import {routeBaselineRate} from './routeQuote';
import factors from './routeCarbonFactors.json';
export function routeCarbon(route:PlannedRoute,personalRate?:number|null){
 const rate=personalRate??routeBaselineRate(route);
 const baseline=rate!=null&&Number.isFinite(rate)&&rate>=0&&Number.isFinite(route.distance_m)&&route.distance_m>0?rate*route.distance_m/1000000:null;
 const aliases:Record<string,keyof typeof factors.kgPerKm>={WALK:'walk',BIKE:'bike',BICYCLE:'bike',CAR:'car',BUS:'bus',SUBWAY:'rail',TRAIN:'rail',RAIL:'rail'};
 let estimate:number|null=route.legs.length&&route.provider==='tmap'?0:null;
 for(const leg of route.legs){const mode=aliases[leg.mode.toUpperCase()];if(!mode||!Number.isFinite(leg.distance_m)||leg.distance_m<0){estimate=null;break;}if(estimate!==null)estimate+=leg.distance_m/1000*factors.kgPerKm[mode];}
 return {baseline,estimate,rate,source:personalRate!=null?'내 평소 이동 기준':'교통 통계 기준',percent:baseline!=null&&baseline>0&&estimate!=null?Math.round((baseline-estimate)/baseline*100):null};
}
