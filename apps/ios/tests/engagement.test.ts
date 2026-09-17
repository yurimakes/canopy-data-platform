import {describe,expect,it,vi} from 'vitest';
import {HttpEngagementApi,parseMissionBundle,parseRanking,parseReward} from '../src/engagementApi';
import {engagementReadyFixture,MockEngagementApi} from '../src/engagementMock';

describe('weekly mission and ranking contract',()=>{
  it('keeps all four server assignments and never asks the user to select one',()=>{
    const fixture=engagementReadyFixture();
    const parsed=parseMissionBundle({status:'assigned',bundle:fixture.missions});
    expect(parsed.missions).toHaveLength(4);
    expect(new Set(parsed.missions.map(item=>item.category_id))).toEqual(new Set(['challenge','habit','easy_win','explore']));
  });
  it('rejects duplicate assignments instead of rendering ambiguous progress',()=>{
    const fixture=engagementReadyFixture();
    const bundle=structuredClone(fixture.missions)!;bundle.missions[1].assignment_id=bundle.missions[0].assignment_id;
    expect(()=>parseMissionBundle({status:'assigned',bundle})).toThrow('중복된 미션');
  });
  it('parses reward ledger and finalized ranking snapshot separately',()=>{
    const fixture=engagementReadyFixture();
    expect(parseReward(fixture.reward).total_points).toBe(320);
    const ranking=parseRanking(fixture.rankings.individual,'individual');
    expect(ranking.snapshot_status).toBe('finalized');expect(ranking.entries.find(item=>item.is_me)?.rank).toBe(3);
  });
  it('rejects unsupported reward states instead of displaying untrusted ledger data',()=>{
    const fixture=engagementReadyFixture();
    const reward=structuredClone(fixture.reward)!;reward.entries[0].status='unknown' as 'paid';
    expect(()=>parseReward(reward)).toThrow('보상 상태');
  });
  it('loads mission, reward, personal ranking and department ranking through API only',async()=>{
    const fixture=engagementReadyFixture();const request=vi.fn(async(url:string|URL|Request)=>{
      const value=String(url);let body:unknown;
      if(value.includes('/missions'))body={status:'assigned',bundle:fixture.missions};
      else if(value.includes('/rewards'))body=fixture.reward;
      else body=value.includes('scope=department')?fixture.rankings.department:fixture.rankings.individual;
      return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
    });
    const api=new HttpEngagementApi({url:'https://example.test/api',token:'test'},request as unknown as typeof fetch);
    const result=await api.loadDashboard('2026-09-14');
    expect(result.missions?.bundle_id).toBe('bundle_demo_20260914');expect(request).toHaveBeenCalledTimes(4);
    expect(request.mock.calls.every(([url])=>String(url).startsWith('https://example.test/api/'))).toBe(true);
  });
  it('keeps healthy sections visible when one backend projection fails',async()=>{
    const fixture=engagementReadyFixture();const request=vi.fn(async(url:string|URL|Request)=>{
      const value=String(url);
      if(value.includes('/rewards'))return new Response(JSON.stringify({code:'service_unavailable',message:'보상 조회 지연'}),{status:503});
      const body=value.includes('/missions')?{status:'assigned',bundle:fixture.missions}:value.includes('scope=department')?fixture.rankings.department:fixture.rankings.individual;
      return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
    });
    const result=await new HttpEngagementApi({url:'https://example.test/api'},request as unknown as typeof fetch).loadDashboard();
    expect(result.missions?.missions).toHaveLength(4);expect(result.reward).toBeNull();expect(result.errors.reward).toBe('보상 조회 지연');
    expect(result.rankings.individual?.snapshot_status).toBe('finalized');
  });
});
