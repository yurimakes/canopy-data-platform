import {describe,expect,it} from 'vitest';
import * as T from 'three';
import {robotRig} from './robotRig';

describe('3D mascot poses',()=>{
  it('keeps both feet on opposite pedals over a complete cycle',()=>{
    const actor=robotRig('cycle');
    const ankles:T.Object3D[]=[],pedals:T.Object3D[]=[];
    actor.scene.traverse(o=>{if(o.name==='ankle')ankles.push(o);if(o.name==='pedal')pedals.push(o);});
    for(let i=0;i<120;i++){
      actor.update(i/120*1.5);actor.scene.updateMatrixWorld(true);
      for(let j=0;j<2;j++){
        const sole=ankles[j].localToWorld(new T.Vector3(0,-.08,0));
        const pedal=pedals[j].getWorldPosition(new T.Vector3());
        expect(sole.distanceTo(pedal)).toBeLessThan(.015);
      }
    }
    actor.dispose();
  });
  it('faces travel right and keeps elbows and wrists in the arm hierarchy',()=>{
    for(const pose of ['run','cycle','start','complete'] as const){
      const actor=robotRig(pose);actor.update(1.2);actor.scene.updateMatrixWorld(true);
      const head=actor.scene.getObjectByName('head')!;
      const forward=new T.Vector3(0,0,1).applyQuaternion(head.getWorldQuaternion(new T.Quaternion()));
      if(pose==='run'||pose==='cycle')expect(forward.x).toBeGreaterThan(.7);
      if(pose==='start'){
        expect(forward.x).toBeCloseTo(0,8);expect(forward.y).toBeCloseTo(0,8);expect(forward.z).toBeCloseTo(1,8);
        const wrist=actor.scene.getObjectByName('rightShoulder')!.getObjectByName('wrist')!;
        expect(wrist.getWorldPosition(new T.Vector3()).x).toBeGreaterThan(.6);
      }
      const shoulder=actor.scene.getObjectByName('rightShoulder')!;
      const elbow=shoulder.getObjectByName('elbow')!,wrist=elbow.getObjectByName('wrist')!;
      expect(elbow.parent).toBe(shoulder);expect(wrist.parent).toBe(elbow);
      actor.dispose();
    }
  });
  it('only launches confetti in the completion scene',()=>{
    for(const pose of ['start','cycle','run','complete'] as const){
      const actor=robotRig(pose);actor.update(1.5);
      const particles=actor.scene.children.filter(o=>o instanceof T.Mesh&&o.geometry instanceof T.PlaneGeometry);
      expect(particles.some(p=>p.visible)).toBe(pose==='complete');actor.dispose();
    }
  });
});
