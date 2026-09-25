import {describe,it,expect} from 'vitest';
import {gpsDistance} from './service';
import type {GpsEvent} from './types';
const point=(seconds:number,lat=37,accuracy:number|null=5,trip_id='a')=>({trip_id,event_time:new Date(Date.UTC(2026,0,1)+seconds*1000).toISOString(),lat,lon:127,accuracy} as GpsEvent);
describe('GPS distance contract shared with pipeline',()=>{
 it('skips millisecond duplicate displacement',()=>expect(gpsDistance([point(0),point(.001,37.00003),point(1,37.00001)])).toBeCloseTo(1.11195,3));
 it('never connects across invalid accuracy or an outage',()=>expect(gpsDistance([point(0),point(1,37.01,200),point(2,37.02),point(30,37.03)])).toBe(0));
 it('never connects distinct trips',()=>expect(gpsDistance([point(0),point(1,37.01,5,'b')])).toBe(0));
});
