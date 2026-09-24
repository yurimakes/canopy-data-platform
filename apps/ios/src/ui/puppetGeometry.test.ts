import {describe, expect, it} from 'vitest';
import {jointEnd, spriteFrame} from './puppetGeometry';

describe('puppet atlas joints', () => {
  it('keeps the crop shoulder and elbow on their world pivots throughout a full turn', () => {
    const rect = [116,441,150,250], anchor: [number,number] = [232,466];
    const end: [number,number] = [156,679];
    const scale = 27 / Math.hypot(end[0]-anchor[0],end[1]-anchor[1]);
    const base = Math.atan2(-(end[0]-anchor[0]),end[1]-anchor[1]);
    for(let i=0;i<120;i++) {
      const angle=i/120*Math.PI*2, rotation=angle-base;
      const f=spriteFrame(rect,anchor,scale,[131,178],rotation);
      const world=(p:[number,number]) => {
        const x=(p[0]-rect[0])*scale-f.width/2;
        const y=(p[1]-rect[1])*scale-f.height/2;
        return [f.left+f.width/2+x*Math.cos(rotation)-y*Math.sin(rotation),
          f.top+f.height/2+x*Math.sin(rotation)+y*Math.cos(rotation)];
      };
      expect(f.width).toBeGreaterThan(0);
      expect(f.height).toBeGreaterThan(0);
      world(anchor).forEach((v,j)=>expect(v).toBeCloseTo([131,178][j],8));
      world(end).forEach((v,j)=>expect(v).toBeCloseTo(jointEnd(131,178,angle,27)[j],8));
    }
  });
});
