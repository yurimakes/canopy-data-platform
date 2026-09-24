import {describe,it,expect} from 'vitest';
import {attachRouteQuote,routeBaselineRate} from './routeQuote';
import type {PlannedRoute} from './service';
const route={id:'tmap-route',provider:'tmap',distance_m:1500,minutes:20,legs:[{mode:'WALK',name:'도보',minutes:20,distance_m:1500,points:[]}],from:{name:'A',latitude:37,longitude:127},to:{name:'B',latitude:37.01,longitude:127},searchedAt:'2026-09-20',fare:null} as PlannedRoute;
const quote={...route,id:'quote',provider:'local-test',quoteId:'quote',distance_m:1000,expectedKg:.024,baselineSource:'KTDB'} as PlannedRoute;
describe('route reward reference',()=>{
 it('keeps TMAP route and snapshot, scales estimate with same rate',()=>{const r=attachRouteQuote(route,quote);expect(r.id).toBe('tmap-route');expect(r.legs).toEqual(route.legs);expect(r.quoteId).toBe('quote');expect(r.expectedKg).toBeCloseTo(.036);expect(routeBaselineRate(r)).toBe(24);});
 it('rejects missing or invalid reference',()=>{for(const change of [{quoteId:undefined},{expectedKg:NaN},{expectedKg:-1},{distance_m:0}])expect(()=>attachRouteQuote(route,{...quote,...change})).toThrow();});
 it('keeps precision for short routes',()=>{expect(routeBaselineRate({...quote,distance_m:20,expectedKg:.00048})).toBeCloseTo(24);});
});
