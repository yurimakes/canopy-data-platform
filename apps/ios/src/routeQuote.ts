import type {PlannedRoute} from './service';
export function attachRouteQuote(route:PlannedRoute,quote:PlannedRoute):PlannedRoute {
 if(!quote.quoteId||!Number.isFinite(quote.expectedKg)||quote.expectedKg!<0||!Number.isFinite(quote.distance_m)||quote.distance_m<=0)throw Error('보상 비교 기준을 가져오지 못했어요. 다시 검색해주세요.');
 const baselineRateG=quote.expectedKg!*1000000/quote.distance_m;
 return {...route,quoteId:quote.quoteId,baselineRateG,expectedKg:baselineRateG*route.distance_m/1000000,baselineSource:quote.baselineSource,modeProbabilities:quote.modeProbabilities};
}
export function routeBaselineRate(route:PlannedRoute):number|undefined {
 const rate=route.baselineRateG??(route.expectedKg===undefined||route.distance_m<=0?undefined:route.expectedKg*1000000/route.distance_m);
 return rate!==undefined&&Number.isFinite(rate)&&rate>=0?rate:undefined;
}
