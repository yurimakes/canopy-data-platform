import {describe,it,expect} from 'vitest';
import {bearing,journeyProgress,metersBetween} from './journeyGeometry';
import type {PlannedRoute} from './service';
const from={name:'집',latitude:37,longitude:127},to={name:'직장',latitude:37.01,longitude:127};
const route:PlannedRoute={id:'r',provider:'local-test',from,to,distance_m:1112,minutes:16,fare:null,legs:[],searchedAt:''};
describe('여정 진행 위치',()=>{
 it('출발과 도착, 중간 지점 표시',()=>{expect(journeyProgress(route,from)).toBe(0);expect(journeyProgress(route,to)).toBe(1);expect(journeyProgress(route,{...from,latitude:37.005})).toBeCloseTo(.5,3);});
 it('같은 곳을 돌아다닌 거리만으로 도착하지 않음',()=>{expect(journeyProgress(route,from)).toBe(0);expect(journeyProgress(route,{...from,latitude:36.99})).toBe(0);expect(journeyProgress(null,to)).toBe(0);});
 it('퇴근의 출발과 도착을 반대로 계산',()=>{const back={...route,from:to,to:from};expect(journeyProgress(back,to)).toBe(0);expect(journeyProgress(back,from)).toBe(1);});
 it('카메라 방향과 거리 단위',()=>{expect(bearing(from,to)).toBeCloseTo(0);expect(bearing(to,from)).toBeCloseTo(180);expect(metersBetween(from,to)).toBeCloseTo(1111.95,1);});
});
