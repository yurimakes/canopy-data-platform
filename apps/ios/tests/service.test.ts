import {describe,it,expect,vi} from 'vitest';
import {parseRoutes,searchRoutes,gpsDistance,validPlace} from '../src/service';
const from={name:'서울역',latitude:37.55,longitude:126.97},to={name:'강남역',latitude:37.5,longitude:127.02};
describe('서비스 화면 연결 계약',()=>{
  it('TMAP의 초와 미터, 경도/위도 순서를 화면 계약으로 변환',()=>{
    const routes=parseRoutes({metaData:{plan:{itineraries:[{totalTime:601,totalDistance:2000,fare:{regular:{totalFare:1500}},legs:[{mode:'BUS',route:'간선:401',sectionTime:601,distance:2000,passShape:{linestring:'126.97,37.55 127.02,37.5'}}]}]}}},from,to);
    expect(routes[0]).toMatchObject({minutes:11,distance_m:2000,fare:1500});
    expect(routes[0].legs[0].points[0]).toMatchObject({longitude:126.97,latitude:37.55});
  });
  it('공급자가 선을 주지 않으면 임의 경로 생성 제외',()=>{
    expect(parseRoutes({metaData:{plan:{itineraries:[{totalTime:60,totalDistance:50,legs:[{mode:'WALK'}]}]}}},from,to)[0].legs[0].points).toEqual([]);
  });
  it('주소 미설정과 잘못된 좌표에서 네트워크 호출 제외',async()=>{
    const request=vi.fn();await expect(searchRoutes('',{},from,to,request)).rejects.toThrow('연결');
    expect(validPlace({...from,latitude:NaN})).toBe(false);expect(request).not.toHaveBeenCalled();
  });
  it('서버가 실패하면 가짜 경로로 대체하지 않음',async()=>{
    await expect(searchRoutes('https://example.test/api/routes/transit',{},from,to,vi.fn().mockResolvedValue({ok:false,status:429}))).rejects.toThrow('한도');
  });
  it('기록이 없으면 실제 이동거리 0',()=>{expect(gpsDistance([])).toBe(0);});
});
