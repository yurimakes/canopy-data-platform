import {afterEach,expect,it,vi} from 'vitest';
import {currentOrigin} from './currentOrigin';
afterEach(()=>vi.useRealTimers());
const now=100000;
const fix={timestamp:now,coords:{latitude:37.5,longitude:127,accuracy:10}};
it('uses the actual fresh GPS fix as origin',async()=>{expect(await currentOrigin({permission:async()=>true,position:async()=>fix},100,()=>now)).toEqual({name:'현재 위치',latitude:37.5,longitude:127});});
it('does not substitute home or a default point when permission is denied',async()=>{const position=vi.fn();await expect(currentOrigin({permission:async()=>false,position})).rejects.toThrow('허용');expect(position).not.toHaveBeenCalled();});
it('rejects stale or inaccurate coordinates',async()=>{for(const f of [{...fix,timestamp:1},{...fix,coords:{...fix.coords,accuracy:200}},{...fix,coords:{...fix.coords,latitude:NaN}}])await expect(currentOrigin({permission:async()=>true,position:async()=>f},100,()=>now)).rejects.toThrow('정확한');});
it('times out instead of waiting forever for a fix',async()=>{vi.useFakeTimers();const result=currentOrigin({permission:async()=>true,position:()=>new Promise(()=>{})},100);const assertion=expect(result).rejects.toThrow('찾지 못했어요');await vi.advanceTimersByTimeAsync(101);await assertion;});
