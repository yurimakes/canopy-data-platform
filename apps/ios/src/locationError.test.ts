import {describe,it,expect} from 'vitest';
import {locationError} from './locationError';
describe('location error recovery guidance',()=>{
  it('explains browser errors without serializing the object',()=>{
    expect(locationError({code:1})).toContain('권한');
    expect(locationError({code:2})).toContain('현재 위치');
    expect(locationError({code:3})).toContain('시간');
    expect(locationError({code:99})).not.toContain('[object');
  });
});
