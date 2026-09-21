import {describe,it,expect} from 'vitest';
import {liveSpeedKmh} from './liveMotion';
import type {GpsEvent} from './types';

const now=Date.parse('2026-09-21T12:00:00Z');
const fix=(changes:Partial<GpsEvent>={}):GpsEvent=>({event_time:new Date(now).toISOString(),accuracy:5,speed:1.5,...changes} as GpsEvent);
describe('live GPS speed',()=>{
  it('converts device m/s to km/h and keeps a valid stationary fix',()=>{
    expect(liveSpeedKmh([fix()],now)).toBeCloseTo(5.4);
    expect(liveSpeedKmh([fix({speed:0})],now)).toBe(0);
  });
  it('does not show missing or invalid speed as zero',()=>{
    for(const speed of [null,-1,NaN,Infinity])expect(liveSpeedKmh([fix({speed})],now)).toBeNull();
    expect(liveSpeedKmh([],now)).toBeNull();
  });
  it('expires an old fix even when no new GPS arrives',()=>{
    expect(liveSpeedKmh([fix()],now+15001)).toBeNull();
    expect(liveSpeedKmh([fix({event_time:'invalid'})],now)).toBeNull();
    expect(liveSpeedKmh([fix()],now-6000)).toBeNull();
  });
  it('uses the latest fix and rejects poor accuracy instead of reusing an old speed',()=>{
    expect(liveSpeedKmh([fix({speed:20}),fix({speed:1})],now)).toBeCloseTo(3.6);
    expect(liveSpeedKmh([fix(),fix({accuracy:100})],now)).toBeNull();
  });
});
