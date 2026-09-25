import {describe,it,expect} from 'vitest';
import {displaySegments} from './displaySegments';
import type {FinalSegment} from './tripApi';
const row=(mode:FinalSegment['mode'],start:number,end:number):FinalSegment=>({segment_id:String(start),mode,start_time:new Date(start*1000).toISOString(),end_time:new Date(end*1000).toISOString(),distance_m:10,confidence:.8,carbon_kg:.01});
describe('display segments',()=>{
  it('preserves server segments and reports missing time without merging',()=>{
    const rows=[row('walk',0,60),row('walk',80,120)];const before=JSON.stringify(rows);
    const groups=displaySegments(rows);
    expect(groups).toHaveLength(2);expect(groups[1]).toMatchObject({recordedSeconds:40,gapSeconds:20,distance_m:10,carbon_kg:.01});
    expect(JSON.stringify(rows)).toBe(before);
  });
  it('keeps intervening modes and uses confirmed modes',()=>{
    expect(displaySegments([row('walk',0,60),row('car',60,120),row('walk',120,180)])).toHaveLength(3);
    expect(displaySegments([row('walk',0,60),{...row('car',60,120),confirmed_mode:'walk'}])).toHaveLength(2);
  });
  it('does not merge overlapping or out-of-order segments',()=>{
    expect(displaySegments([row('walk',0,60),row('walk',30,120)])).toHaveLength(2);
  });
});
