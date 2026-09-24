import {readFileSync} from 'node:fs';
import factors from './routeCarbonFactors.json';
import {describe,it,expect} from 'vitest';
import {routeCarbon} from './routeCarbon';
import type {PlannedRoute} from './service';
const route={id:'r',provider:'tmap',distance_m:1000,baselineRateG:139.5,legs:[{mode:'BUS',distance_m:1000}]} as PlannedRoute;
describe('route carbon comparison',()=>{
 it('compares distinct route modes against the same baseline',()=>{const bus=routeCarbon(route);const rail=routeCarbon({...route,legs:[{...route.legs[0],mode:'SUBWAY'}]});expect(bus.baseline).toBe(.1395);expect(bus.estimate).toBe(.12552);expect(rail.estimate).toBe(.01549);expect(rail.percent).toBeGreaterThan(bus.percent!);});
 it('keeps missing routes unknown and zero emission walks valid',()=>{expect(routeCarbon({...route,legs:[]}).estimate).toBeNull();expect(routeCarbon({...route,legs:[{...route.legs[0],mode:'UNKNOWN'}]}).estimate).toBeNull();expect(routeCarbon({...route,legs:[{...route.legs[0],mode:'WALK'}]}).percent).toBe(100);});
 it('adds emissions per leg and scales the reference by route distance',()=>{
  const mixed=routeCarbon({...route,distance_m:3200,legs:[{...route.legs[0],mode:'WALK',distance_m:500},{...route.legs[0],mode:'SUBWAY',distance_m:2700}]});
  expect(mixed.estimate).toBeCloseTo(.041823);expect(mixed.baseline).toBeCloseTo(.4464);
 });
 it('matches the existing server carbon policy',()=>{
  const policy=readFileSync(new URL('../../../cloud/azure/functions/func_canopy_dev/carbon_policy.yaml',import.meta.url),'utf8');
  expect(policy).toContain('factor_version: "'+factors.version+'"');
  for(const [mode,factor] of Object.entries(factors.kgPerKm)){
   const match=policy.match(new RegExp('  '+mode+':\\s*\\n    value: ([0-9.]+)'));
   expect(Number(match?.[1])).toBe(factor);
  }
 });
 it('uses the personal rate when available without dividing by zero',()=>{expect(routeCarbon(route,100).percent).toBe(-26);expect(routeCarbon(route,0).percent).toBeNull();});
});
