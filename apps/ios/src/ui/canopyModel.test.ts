import {describe,expect,it} from 'vitest';
import * as T from 'three';
import {createCanopyHead} from './canopyModel';

describe('head surface seam',()=>{
  it('shares every perimeter vertex between the visor and helmet',()=>{
    const head=createCanopyHead();
    const face=head.group.getObjectByName('referenceFace') as T.Mesh;
    const helmet=head.group.getObjectByName('continuousHelmet') as T.Mesh;
    const front=face.geometry.getAttribute('position'),back=helmet.geometry.getAttribute('position');
    for(let j=0;j<=96;j++){
      const i=22*97+j;
      expect(front.getX(i)).toBeCloseTo(back.getX(j),7);
      expect(front.getY(i)).toBeCloseTo(back.getY(j),7);
      expect(front.getZ(i)).toBeCloseTo(back.getZ(j),7);
    }
    for(const expression of [0,1,2] as const){
      head.setExpression(expression);
      expect((face.material as T.MeshBasicMaterial).map!.offset.x).toBeGreaterThanOrEqual(0);
      expect(front.count).toBe(23*97);
    }
    face.geometry.dispose();helmet.geometry.dispose();head.dispose();
  });
});
