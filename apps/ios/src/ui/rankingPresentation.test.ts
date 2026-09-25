import {describe,it,expect} from 'vitest';
import {rankingPresentation} from './rankingPresentation';
describe('release ranking presentation',()=>{
 it('replaces server test employees for weekly and cumulative display without mutating rewards',()=>{
  const source=Array.from({length:75},(_,i)=>({id:String(i).padStart(3,'0'),name:i===74?'민철':`테스트 직원 ${i}`,rank:i<7?1:8,points:230,carbonKg:0,isMe:i===74}));
  const snapshot=JSON.stringify(source);
  const shown=rankingPresentation(source,true);
  expect(shown.slice(0,6).map(r=>r.name)).toEqual(['신민철','김창연','박준용','김이레','최유리','양유진']);
  expect(shown[0].id).toBe('074');
  expect(shown[0].isMe).toBe(true);
  expect(new Set(shown.map(r=>r.points)).size).toBe(75);
  expect(shown.map(r=>r.rank)).toEqual(Array.from({length:75},(_,i)=>i+1));
  expect(JSON.stringify(source)).toBe(snapshot);
  expect(rankingPresentation([...source].reverse(),true)).toEqual(shown);
 });
 it('preserves real names and points and department names, assigning stable display positions',()=>{
  const source=[{id:'b',name:'실제 회원',rank:1,points:230,carbonKg:0},{id:'a',name:'다른 회원',rank:1,points:230,carbonKg:0}];
  expect(rankingPresentation(source,true).map(r=>[r.name,r.points,r.rank])).toEqual([['다른 회원',230,1],['실제 회원',230,2]]);
  expect(rankingPresentation([{...source[0],name:'테스트 직원 팀'}],false)[0].name).toBe('테스트 직원 팀');
  expect(rankingPresentation([],true)).toEqual([]);
 });
});
