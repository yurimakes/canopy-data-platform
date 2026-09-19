import { describe, expect, it } from 'vitest';
import { characterMotion, footCycle, legAngles, gardenMotion } from './mascotMotion';

describe('continuous character motion', () => {
  it('waters, pauses to smile and wave, then returns seamlessly to watering', () => {
    expect(gardenMotion(0).pour).toBe(1);
    expect(gardenMotion(6).pour).toBe(0);
    expect(gardenMotion(6).hello).toBe(1);
    expect(gardenMotion(6).smile).toBe(1);
    expect(gardenMotion(10).pour).toBe(1);
    expect(gardenMotion(12)).toEqual(gardenMotion(0));
    expect(gardenMotion(6).wave).not.toBeCloseTo(gardenMotion(6.2).wave);
  });
  it('keeps both feet alternating and the stance foot on the ground', () => {
    for (let i = 0; i < 120; i++) {
      const a = footCycle(i / 120), b = footCycle(i / 120 + .5);
      expect(a.contact || b.contact).toBe(true);
      if (a.contact) expect(a.y).toBe(.085);
      expect(a.y).toBeGreaterThanOrEqual(.085);
      const angles = legAngles(a.y - .515, a.z);
      const y = -.245 * Math.cos(angles.hip) - .245 * Math.cos(angles.hip + angles.knee);
      const z = -.245 * Math.sin(angles.hip) - .245 * Math.sin(angles.hip + angles.knee);
      expect(y).toBeCloseTo(a.y - .515, 5);
      expect(z).toBeCloseTo(a.z, 5);
      expect(angles.hip + angles.knee + angles.ankle).toBeCloseTo(0, 8);
    }
  });
  it('closes the walk cycle without a position jump', () => {
    for (const boundary of [0, .6, 1]) {
      const a = footCycle(boundary - .00001), b = footCycle(boundary + .00001);
      expect(Math.abs(a.z - b.z)).toBeLessThan(.0001);
      expect(Math.abs(a.y - b.y)).toBeLessThan(.0001);
    }
  });
  it('has a waving wrist, brief wink, and an open-eyed rest', () => {
    expect(characterMotion('start', 0).wink).toBe(0);
    expect(characterMotion('start', 2.4).wink).toBe(1);
    expect(characterMotion('start', 3).wink).toBe(0);
    expect(characterMotion('start', 1.8).wrist).not.toBeCloseTo(characterMotion('start', 2).wrist);
    expect(characterMotion('start', 0).armRaise).toBeCloseTo(characterMotion('start', 6).armRaise);
    expect(characterMotion('walk', 2.4).wink).toBe(0);
  });
  it('fires the popper once and settles rather than repeating the burst', () => {
    expect(characterMotion('complete', 0).burstAge).toBeLessThan(0);
    expect(characterMotion('complete', 1.2).burstAge).toBe(0);
    expect(characterMotion('complete', 10).burstAge).toBeGreaterThan(2.8);
    expect(characterMotion('complete', 5).armRaise).toBeCloseTo(.4);
  });
});
