import {describe,it,expect} from 'vitest';
import {sheetParts,sheetPose,sheetMotions,sheetExpressions,type SheetLayer} from './sheetRig';
function project(l:SheetLayer,p:[number,number]){const o=sheetParts[l.part].pivot,a=l.angle*Math.PI/180,x=(p[0]-o[0])*l.scale*(l.flip?-1:1)*(l.widthScale??1),y=(p[1]-o[1])*l.scale;return [l.x+x*Math.cos(a)-y*Math.sin(a),l.y+x*Math.sin(a)+y*Math.cos(a)];}
describe('source sheet animation attachments',()=>{
 it('walk plants the foot front-to-back and lifts it on the forward return',()=>{
  const foot=(phase:number,direction:'left'|'right')=>sheetPose('walk',phase*1.18,{direction}).layers.find(l=>l.part==='footSide')!;
  for(const direction of ['left','right'] as const){
   const facing=direction==='right'?1:-1,a=foot(.125,direction),b=foot(.375,direction),c=foot(.625,direction),d=foot(.875,direction);
   expect(a.y).toBeCloseTo(334);expect(b.y).toBeCloseTo(334);
   expect((b.x-a.x)*facing).toBeLessThan(0);
   expect(c.y).toBeLessThan(334);expect(d.y).toBeLessThan(334);
   expect((d.x-c.x)*facing).toBeGreaterThan(0);
  }
 });
 for(const motion of sheetMotions)it(`${motion.id}: joints stay connected through 240 samples`,()=>{
  for(let n=0;n<240;n++)for(const direction of ['left','right'] as const){
   const f=sheetPose(motion.id,n/30,{direction});
   for(let i=0;i<f.layers.length;i++){
    const l=f.layers[i];expect([l.x,l.y,l.angle,l.scale].every(Number.isFinite)).toBe(true);
    const end=l.part==='arm'||l.part==='foreArm'?[416,509]:l.part==='upperArm'?[402,480]:l.part==='thighL'?[61,638]:l.part==='legShaft'?[54,670]:null;
    if(end){const q=project(l,end as [number,number]),next=f.layers[i+1];expect(Math.hypot(q[0]-next.x,q[1]-next.y)).toBeLessThan(.001);}
   }
  }
 });
 it('uses profile heads and shoes for all travel motions even with a frontal expression requested',()=>{
  for(const pose of ['walk','run','cycle']){const f=sheetPose(pose,.4,{expression:'happy'});expect(f.layers.some(l=>l.part==='sideHead')).toBe(true);expect(f.layers.filter(l=>l.part==='footSide')).toHaveLength(2);expect(f.layers.some(l=>l.part==='frontBody')).toBe(false);}
 });
 it('exposes all twelve original expression heads',()=>{expect(sheetExpressions).toHaveLength(12);for(const e of sheetExpressions)expect(sheetPose('idle',0,{expression:e.id}).layers.some(l=>l.part===e.part)).toBe(true);});
 it('reflection keeps debug bones aligned with the visual rig',()=>{const a=sheetPose('cycle',.4),b=sheetPose('cycle',.4,{direction:'left'});a.bones.forEach((bone,i)=>{expect(b.bones[i].from).toEqual([-bone.from[0],bone.from[1]]);expect(b.bones[i].to).toEqual([-bone.to[0],bone.to[1]]);});});
});
