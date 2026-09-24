export type CharacterAction = 'start' | 'walk' | 'run' | 'complete' | 'cycle' | 'garden';
const TAU = Math.PI * 2;
const clamp = (v: number) => Math.max(0, Math.min(1, v));
export const ease = (v: number) => { const x = clamp(v); return x * x * (3 - 2 * x); };
const pulse = (t: number, start: number, end: number, edge: number) => ease((t - start) / edge) * (1 - ease((t - end + edge) / edge));

export function gardenMotion(seconds: number) {
  const t = Math.max(0, seconds) % 12;
  const hello = pulse(t, 4, 9.5, .9);
  const wave = pulse(t, 5, 8.7, .45) * Math.sin((t - 5) * TAU * 1.65);
  return { hello, wave, pour: 1 - hello, smile: pulse(t, 5.1, 8.5, .45) };
}

// The foot stays on the floor during stance; only the returning foot lifts.
export function footCycle(phase: number) {
  const p = ((phase % 1) + 1) % 1;
  if (p < .6) return { z: .17 - .34 * ease(p / .6), y: .085, contact: true };
  const u = (p - .6) / .4;
  return { z: -.17 + .34 * ease(u), y: .085 + .115 * Math.sin(Math.PI * u) ** 2, contact: false };
}

export function legAngles(y: number, z: number) {
  const upper = .245, lower = .245;
  const distance = Math.min(upper + lower - .0001, Math.hypot(y, z));
  const knee = Math.acos(Math.max(-1, Math.min(1, (distance * distance - upper * upper - lower * lower) / (2 * upper * lower))));
  const hip = Math.atan2(-z, -y) - Math.atan2(lower * Math.sin(knee), upper + lower * Math.cos(knee));
  return { hip, knee, ankle: -hip - knee };
}

export function characterMotion(action: CharacterAction, seconds: number) {
  const t = Math.max(0, seconds);
  const walking = action === 'walk' || action === 'run';
  const cycle = t / (action === 'run' ? .68 : .96);
  const step = Math.sin(cycle * TAU);
  const greeting = t % 6;
  const raise = pulse(greeting, .35, 4.25, .75);
  const wave = pulse(greeting, 1.15, 3.5, .3) * Math.sin((greeting - 1.15) * TAU * 2.15);
  const prepare = ease((t - .3) / .8);
  const settle = ease((t - 1.75) / .9);
  const recoil = pulse(t, 1.15, 1.65, .18);
  const blink = pulse(t % 5.7, 5.1, 5.32, .11);
  const wink = !walking ? pulse(action === 'complete' ? t : greeting, 2.15, 2.65, .18) : 0;
  return {
    walking, cycle, step,
    bounce: walking ? .012 * Math.cos(cycle * TAU * 2) : .006 * Math.sin(t * 2),
    yaw: walking ? 1.22 : -.12 + .025 * Math.sin(t * 1.2),
    headTilt: walking ? .025 * Math.sin(cycle * TAU) : -.055 * raise,
    armRaise: action === 'complete' ? 1.95 * prepare - 1.55 * settle + recoil * .12 : .15 + 1.95 * raise,
    elbow: action === 'complete' ? .30 * prepare - .20 * settle : -.12 + .67 * raise,
    wrist: action === 'complete' ? -.2 * prepare + .15 * settle : wave * .42,
    blink, wink,
    burstAge: action === 'complete' ? t - 1.2 : -1,
    recoil,
  };
}
