import * as T from 'three';
import { characterMotion, legAngles, footCycle, type CharacterAction } from './mascotMotion';

// Rigid shell pieces rotate around anatomical pivots, keeping the robot's shape.
export function robotRig(action: CharacterAction) {
  const scene = new T.Scene();
  const camera = new T.PerspectiveCamera(30, 1, .1, 30);
  camera.position.set(0, 1.35, 5.3);
  camera.lookAt(0, 1.24, 0);
  scene.add(new T.HemisphereLight(0xf3fcff, 0x748469, 2));
  for (const [color, intensity, x, y, z] of [[0xfff4df, 3.1, -3, 5, 4], [0xd8f5ff, 1.7, 3, 3, 2], [0xffffff, 3, 1, 4, -3]]) {
    const light = new T.DirectionalLight(color, intensity); light.position.set(x, y, z); scene.add(light);
  }
  const materials: T.Material[] = [];
  const mat = (color: string, roughness = .3, metalness = .08) => {
    const m = new T.MeshPhysicalMaterial({ color, roughness, metalness, clearcoat: .8, clearcoatRoughness: .18 });
    materials.push(m); return m;
  };
  const ivory = mat('#f4f2df', .24), face = mat('#fffbed', .34);
  const leafGreen = mat('#7eab40', .29), trim = mat('#aac876', .23), glove = mat('#3d7650', .36);
  const joint = mat('#263e32', .4), eyeBlack = mat('#091b12', .11), irisMat = mat('#347846', .18);
  const white = new T.MeshBasicMaterial({ color: '#ffffff' }); materials.push(white);
  const mint = new T.MeshStandardMaterial({ color: '#d5ffe0', emissive: '#83ffa5', emissiveIntensity: .65 }); materials.push(mint);
  const body = new T.Group(); scene.add(body);
  function mesh(parent: T.Object3D, geo: T.BufferGeometry, material: T.Material, x = 0, y = 0, z = 0) {
    const m = new T.Mesh(geo, material); m.position.set(x, y, z); parent.add(m); return m;
  }
  function orb(parent: T.Object3D, material: T.Material, x: number, y: number, z: number, sx: number, sy = sx, sz = sx, roundness = 1) {
    const g = new T.SphereGeometry(1, 40, 28);
    if (roundness !== 1) {
      const p = g.attributes.position;
      for (let i = 0; i < p.count; i++) {
        const f = (v: number) => Math.sign(v) * Math.pow(Math.abs(v), roundness);
        p.setXYZ(i, f(p.getX(i)), f(p.getY(i)), f(p.getZ(i)));
      }
      g.computeVertexNormals();
    }
    const m = mesh(parent, g, material, x, y, z); m.scale.set(sx, sy, sz); return m;
  }
  function pivot(parent: T.Object3D, name: string, x: number, y: number, z = 0) {
    const p = new T.Group(); p.name = name; p.position.set(x, y, z); parent.add(p); return p;
  }
  function line(parent: T.Object3D, points: number[][], radius: number, material: T.Material) {
    const curve = new T.CatmullRomCurve3(points.map(p => new T.Vector3(p[0], p[1], p[2])));
    return mesh(parent, new T.TubeGeometry(curve, 30, radius, 8, false), material);
  }
  function leaf(parent: T.Object3D, scale: number, tilt: number) {
    const group = pivot(parent, 'leaf', 0, 0); group.rotation.z = tilt; group.scale.setScalar(scale);
    const vertices: number[] = [], indices: number[] = [];
    const rows = 20, cols = 10;
    for (let i = 0; i <= rows; i++) {
      const t = i / rows, w = .24 * Math.sin(Math.PI * t) ** .85;
      for (let j = 0; j <= cols; j++) {
        const u = j / cols * 2 - 1;
        vertices.push(u * w, t * .68, .12 * Math.sin(Math.PI * t) * (1 - u * u) - .07 * t * t);
        if (i < rows && j < cols) { const n = i * (cols + 1) + j; indices.push(n, n + 1, n + cols + 1, n + 1, n + cols + 2, n + cols + 1); }
      }
    }
    const g = new T.BufferGeometry(); g.setAttribute('position', new T.Float32BufferAttribute(vertices, 3)); g.setIndex(indices); g.computeVertexNormals();
    const lm = leafGreen.clone(); lm.side = T.DoubleSide; materials.push(lm); mesh(group, g, lm);
    line(group, [[0, 0, .012], [0, .22, .108], [0, .44, .091], [0, .65, -.043]], .009, trim);
    for (const side of [-1, 1]) for (const t of [.28, .48, .65]) line(group, [[0, t * .68, .105], [side * .1, (t + .09) * .68, .07], [side * .17, (t + .13) * .68, .013]], .003, trim);
    return group;
  }
  orb(body, joint, 0, .79, -.02, .31, .37, .245);
  orb(body, ivory, 0, .86, .03, .32, .375, .27);
  for (const side of [-1, 1]) { const panel = orb(body, leafGreen, side * .265, .72, -.035, .065, .24, .20); panel.rotation.z = side * -.25; }
  orb(body, joint, 0, 1.18, 0, .14, .09, .135);
  const head = pivot(body, 'head', 0, 1.65);
  orb(head, leafGreen, 0, 0, 0, .61, .465, .37, .79);
  orb(head, ivory, 0, -.012, .045, .583, .443, .375, .8);
  orb(head, trim, 0, -.025, .266, .515, .351, .193, .78);
  orb(head, face, 0, -.025, .285, .493, .333, .183, .8);
  for (const s of [-1, 1]) {
    orb(head, joint, s * .584, -.015, -.035, .067, .238, .23);
    orb(head, ivory, s * .629, -.015, -.018, .065, .219, .215);
    orb(head, glove, s * .676, -.015, -.008, .036, .171, .174);
    const ring = mesh(head, new T.TorusGeometry(.136, .013, 10, 48), mint, s * .713, -.015, -.008); ring.rotation.y = Math.PI / 2;
    orb(head, trim, s * .716, -.015, -.008, .012, .086, .087);
  }
  const sprout = pivot(head, 'sprout', 0, .426, -.01);
  orb(sprout, leafGreen, 0, .004, 0, .15, .045, .12);
  line(sprout, [[0, 0, 0], [-.01, .1, 0], [-.045, .24, -.02]], .025, glove);
  const leafA = leaf(sprout, .78, .58); leafA.position.set(-.03, .14, 0); leafA.rotation.y = -.2;
  const leafB = leaf(sprout, .64, -.95); leafB.position.set(0, .105, .01); leafB.rotation.y = .2;
  const eyes = [-1, 1].map(side => {
    const group = pivot(head, 'eye', side * .215, .041, .443);
    orb(group, eyeBlack, 0, 0, 0, .112, .139, .061);
    orb(group, irisMat, 0, -.018, .048, .077, .099, .024);
    orb(group, eyeBlack, 0, .009, .068, .051, .076, .013);
    orb(group, white, -.034, .06, .076, .035, .043, .008);
    orb(group, white, .037, -.054, .075, .012, .016, .006);
    const lid = line(head, [[side * .215 - .095, .034, .481], [side * .215, .077, .494], [side * .215 + .095, .034, .481]], .021, eyeBlack); lid.visible = false;
    return { group, lid };
  });
  const mouthShape = new T.Shape(); mouthShape.moveTo(-.085, 0); mouthShape.quadraticCurveTo(0, -.021, .085, 0); mouthShape.quadraticCurveTo(.065, -.102, 0, -.102); mouthShape.quadraticCurveTo(-.067, -.102, -.085, 0);
  mesh(head, new T.ShapeGeometry(mouthShape, 24), joint, 0, -.12, .47);
  orb(head, mat('#bd7b6c', .4), 0, -.204, .476, .034, .012, .003);
  const cheek = mat('#e3bca0', .6);
  for (const x of [-.35, .35]) orb(head, cheek, x, -.117, .449, .044, .018, .006);
  orb(body, leafGreen, 0, .96, .287, .142, .142, .033);
  mesh(body, new T.TorusGeometry(.127, .01, 12, 48), mint, 0, .96, .317);
  const badge = leaf(body, .21, -.55); badge.position.set(-.035, .90, .32);
  badge.traverse(o => { if (o instanceof T.Mesh) o.material = mint; });
  function arm(side: number) {
    const shoulder = pivot(body, side < 0 ? 'leftShoulder' : 'rightShoulder', side * .33, 1.085);
    orb(shoulder, joint, 0, 0, 0, .105);
    orb(shoulder, ivory, side * .018, -.095, .012, .108, .156, .109);
    const elbow = pivot(shoulder, 'elbow', 0, -.23);
    orb(elbow, joint, 0, 0, 0, .075);
    orb(elbow, ivory, 0, -.09, .005, .083, .132, .085);
    const wrist = pivot(elbow, 'wrist', 0, -.215);
    orb(wrist, trim, 0, .008, 0, .084, .035, .083);
    orb(wrist, glove, 0, -.073, .005, .091, .103, .043);
    const fingers: T.Group[] = [];
    for (let i = 0; i < 4; i++) {
      const finger = pivot(wrist, 'finger', (i - 1.5) * .043, -.13, .007);
      finger.rotation.z = (i - 1.5) * .12;
      orb(finger, glove, 0, -.039, 0, .023, .062 - Math.abs(i - 1.5) * .006, .025);
      fingers.push(finger);
    }
    const thumb = pivot(wrist, 'thumb', -side * .087, -.068, .005); thumb.rotation.z = -side * .7;
    orb(thumb, glove, 0, -.026, 0, .033, .059, .031);
    return { shoulder, elbow, wrist, fingers, thumb };
  }
  const left = arm(-1), right = arm(1);
  function leg(side: number) {
    const hip = pivot(body, 'hip', side * .162, .515);
    orb(hip, joint, 0, 0, 0, .104);
    orb(hip, ivory, 0, -.11, .005, .114, .158, .112);
    const knee = pivot(hip, 'knee', 0, -.245);
    orb(knee, joint, 0, 0, 0, .08);
    orb(knee, ivory, 0, -.096, .012, .105, .145, .106);
    const ankle = pivot(knee, 'ankle', 0, -.245);
    orb(ankle, glove, 0, -.019, .062, .139, .067, .208, .86);
    orb(ankle, ivory, 0, .025, .018, .115, .079, .132);
    orb(ankle, joint, 0, -.065, .065, .14, .018, .207, .84);
    return { hip, knee, ankle };
  }
  const legs = [leg(-1), leg(1)];
  const popper = pivot(right.wrist, 'popper', 0, -.19, .035);
  popper.rotation.z = Math.PI;
  const paper = mat('#eac779', .27, .4);
  mesh(popper, new T.CylinderGeometry(.071, .04, .21, 32), paper, 0, .015);
  mesh(popper, new T.TorusGeometry(.069, .008, 8, 32), glove, 0, .12).rotation.x = Math.PI / 2;
  const muzzle = pivot(popper, 'muzzle', 0, .125);
  popper.visible = action === 'complete';
  const burstOrigin = new T.Vector3();
  const confettiMaterials = ['#80b960', '#edcc79', '#b7ded4', '#f0ad9a'].map(c => mat(c, .4));
  const confetti = Array.from({ length: 38 }, (_, i) => mesh(scene, new T.PlaneGeometry(.025 + (i % 3) * .008, .048), confettiMaterials[i % 4]));
  confettiMaterials.forEach(m => { m.side = T.DoubleSide; });
  // Several translucent rings give a soft floor contact without a shadow map.
  const shadows = Array.from({ length: 12 }, (_, i) => {
    const sm = new T.MeshBasicMaterial({ color: '#35563e', transparent: true, opacity: .012 }); materials.push(sm);
    const m = mesh(scene, new T.CircleGeometry(.24 + i * .021, 48), sm, 0, .001 + i * .0001, 0);
    m.rotation.x = -Math.PI / 2; m.scale.y = .66; return m;
  });
  function applyBody(t: number) {
    const m = characterMotion(action, t);
    body.position.y = m.bounce; body.rotation.y = m.yaw;
    body.rotation.z = m.walking ? .015 * m.step : -.015 * m.recoil;
    head.rotation.set(m.walking ? .012 * Math.cos(m.cycle * Math.PI * 4) : 0, .025 * Math.sin(t * 1.2), m.headTilt);
    sprout.rotation.z = .025 * Math.sin(t * 2.4); sprout.rotation.x = m.walking ? .035 * m.step : 0;
    left.shoulder.rotation.set(m.walking ? footCycle(m.cycle).z * 2.1 : -.1, 0, -.20);
    right.shoulder.rotation.set(m.walking ? footCycle(m.cycle + .5).z * 2.1 : .035, 0, m.walking ? .20 : m.armRaise);
    left.elbow.rotation.set(-.14, 0, -.08);
    right.elbow.rotation.set(m.walking ? -.14 : 0, 0, m.walking ? .08 : m.elbow);
    right.wrist.rotation.set(0, m.walking ? 0 : -.2, m.wrist);
    for (const f of right.fingers) f.rotation.x = action === 'complete' ? -1.1 : 0;
    for (let i = 0; i < legs.length; i++) {
      const foot = m.walking ? footCycle(m.cycle + i * .5) : { y: .085, z: .02 };
      const angles = legAngles(foot.y - .515 - m.bounce, foot.z);
      legs[i].hip.rotation.x = angles.hip; legs[i].knee.rotation.x = angles.knee; legs[i].ankle.rotation.x = angles.ankle;
    }
    eyes.forEach((eye, i) => {
      const close = Math.max(m.blink, i === 1 ? m.wink : 0);
      eye.group.scale.y = Math.max(.04, 1 - close);
      eye.group.visible = close < .92; eye.lid.visible = close >= .92;
    });
    return m;
  }
  applyBody(1.2); scene.updateMatrixWorld(true); muzzle.getWorldPosition(burstOrigin);
  function update(t: number) {
    const m = applyBody(t);
    confetti.forEach((piece, i) => {
      const age = m.burstAge - (i % 4) * .016;
      piece.visible = age >= 0 && age < 2.8;
      if (!piece.visible) return;
      const a = i * 2.39996, speed = .38 + (i % 7) * .08;
      piece.position.set(burstOrigin.x + Math.cos(a) * speed * age, burstOrigin.y + (1.6 + (i % 4) * .15) * age - 1.3 * age * age, burstOrigin.z + Math.sin(a) * .38 * age);
      piece.rotation.set(age * (2 + i % 3), a + age * 3, age * 2);
      piece.scale.setScalar(Math.min(1, Math.max(0, (2.8 - age) * 3)));
    });
    shadows.forEach(s => { s.scale.x = 1 - m.bounce; });
  }
  function dispose() { scene.traverse(o => { if (o instanceof T.Mesh) o.geometry.dispose(); }); materials.forEach(m => m.dispose()); }
  update(0);
  return { scene, camera, update, dispose };
}
