import * as T from 'three';
import {createCanopyHead, createReferenceLeaves, shellGeometry} from './canopyModel';
import { characterMotion, legAngles, footCycle, gardenMotion, type CharacterAction } from './mascotMotion';

// Rigid shell pieces rotate around anatomical pivots, keeping the robot's shape.
export function robotRig(action: CharacterAction) {
  const scene = new T.Scene();
  const camera = new T.PerspectiveCamera(30, 1, .1, 30);
  camera.position.set(0, 1.35, 6.0);
  camera.lookAt(0, 1.24, 0);
  scene.add(new T.HemisphereLight(0xffffff, 0xb0bca4, 1.15));
  for (const [color, intensity, x, y, z] of [[0xffffff, .65, -3, 5, 4], [0xffffff, .18, 3, 3, 2]]) {
    const light = new T.DirectionalLight(color, intensity); light.position.set(x, y, z); scene.add(light);
  }
  const materials: T.Material[] = [];
  let flatCharacter = true;
  const mat = (color: string, roughness = .3, metalness = .08) => {
    const m = flatCharacter
      ? new T.MeshBasicMaterial({ color, toneMapped: false })
      : new T.MeshPhysicalMaterial({ color, roughness, metalness, clearcoat: .8, clearcoatRoughness: .18 });
    materials.push(m); return m;
  };
  const ivory = mat('#e9e7dd', .24), face = mat('#f3f0e7', .34);
  const leafGreen = mat('#82a35a', .29), trim = mat('#b1c987', .23), glove = mat('#4c703e', .36);
  const joint = mat('#263e32', .4), eyeBlack = mat('#091b12', .11), irisMat = mat('#347846', .18);
  const white = new T.MeshBasicMaterial({ color: '#ffffff', toneMapped: false }); materials.push(white);
  const mint = new T.MeshBasicMaterial({ color: '#d5ffe0', toneMapped: false }); materials.push(mint);
  const ink = new T.MeshBasicMaterial({color:'#283626',side:T.BackSide,toneMapped:false});materials.push(ink);
  const body = new T.Group(); scene.add(body);
  function mesh(parent: T.Object3D, geo: T.BufferGeometry, material: T.Material, x = 0, y = 0, z = 0) {
    const m = new T.Mesh(geo, material); m.position.set(x, y, z); parent.add(m);
    if(flatCharacter && (material===ivory || material===glove || material===leafGreen)){
      const edge=geo.clone(),position=edge.getAttribute('position'),normal=edge.getAttribute('normal');
      if(normal){for(let i=0;i<position.count;i++)position.setXYZ(i,position.getX(i)+normal.getX(i)*.014,position.getY(i)+normal.getY(i)*.014,position.getZ(i)+normal.getZ(i)*.014);}
      const outline=new T.Mesh(edge,ink);outline.name='characterOutline';m.add(outline);
    }
    return m;
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
    const m = mesh(parent, g, material, x, y, z); m.scale.set(sx, sy, sz);
    return m;
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
  function emblem(parent:T.Object3D, scale:number) {
    const g=pivot(parent,'leaf emblem',0,0);g.scale.setScalar(scale);
    const shape=new T.Shape();shape.moveTo(-.40,-.28);shape.bezierCurveTo(-.49,.20,-.15,.44,.48,.35);shape.bezierCurveTo(.28,-.25,-.02,-.40,-.40,-.28);
    mesh(g,new T.ShapeGeometry(shape,28),mint);
    line(g,[[-.48,-.43,.009],[-.19,-.15,.009],[.28,.20,.009]],.027,leafGreen);
    return g;
  }
  orb(body, joint, 0, .79, -.02, .31, .37, .245);
  mesh(body, shellGeometry([[.46,.06,.09,.02],[.51,.23,.18,.025],[.64,.285,.24,.025],[.84,.35,.285,.035],[1.04,.33,.25,.025],[1.16,.24,.18,0],[1.21,.10,.08,0]]), ivory);
  for (const side of [-1, 1]) { const panel = orb(body, leafGreen, side * .265, .72, -.035, .065, .24, .20); panel.rotation.z = side * -.25; }
  orb(body, joint, 0, 1.18, 0, .14, .09, .135);
  const head = pivot(body, 'head', 0, 1.65);
  const authoredHead=createCanopyHead();head.add(authoredHead.group);
  for (const s of [-1, 1]) {
    orb(head, joint, s * .619, -.085, -.035, .067, .238, .23);
    orb(head, ivory, s * .659, -.085, -.018, .065, .219, .215);
    orb(head, glove, s * .706, -.085, -.008, .036, .171, .174);
    const ring = mesh(head, new T.TorusGeometry(.136, .013, 10, 48), mint, s * .743, -.085, -.008); ring.rotation.y = Math.PI / 2;
    const earLeaf = emblem(head, .20); earLeaf.position.set(s * .751, -.085, -.008); earLeaf.rotation.y=s*Math.PI/2;
  }
  const sprout = pivot(head, 'sprout', 0, .426, -.01);
  const crown=orb(sprout,leafGreen,0,-.035,.225,.235,.055,.235); crown.rotation.x=.32;
  line(sprout, [[0, 0, 0], [-.01, .1, 0], [-.045, .24, -.02]], .025, glove);
  const referenceLeaves=createReferenceLeaves();referenceLeaves.group.position.set(0,.08,0);sprout.add(referenceLeaves.group);
  orb(body, leafGreen, 0, .965, .298, .164, .164, .028);
  mesh(body, new T.TorusGeometry(.155, .010, 12, 48), mint, 0, .965, .326);
  const badge=emblem(body,.24); badge.position.set(0,.965,.336);
  function arm(side: number) {
    const shoulder = pivot(body, side < 0 ? 'leftShoulder' : 'rightShoulder', side * .33, 1.085);
    orb(shoulder, joint, 0, 0, 0, .105);
    mesh(shoulder,shellGeometry([[-.26,.055,.056,0],[-.22,.078,.078,0],[-.10,.098,.09,.012],[-.015,.082,.082,0],[.025,.025,.025,0]]),glove);
    const elbow = pivot(shoulder, 'elbow', 0, -.23);
    orb(elbow, joint, 0, 0, 0, .075);
    mesh(elbow,shellGeometry([[-.23,.078,.076,.008],[-.20,.101,.096,.009],[-.09,.116,.106,.006],[.012,.077,.076,0],[.032,.04,.04,0]]),ivory);
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
    mesh(hip,shellGeometry([[-.27,.074,.072,0],[-.22,.093,.092,0],[-.10,.125,.12,.006],[.012,.12,.11,0],[.037,.065,.065,0]]),ivory);
    const knee = pivot(hip, 'knee', 0, -.245);
    orb(knee, joint, 0, 0, 0, .08);
    mesh(knee,shellGeometry([[-.27,.10,.112,.016],[-.21,.126,.126,.016],[-.08,.12,.105,.008],[.018,.082,.076,0],[.034,.04,.04,0]]),ivory);
    const ankle = pivot(knee, 'ankle', 0, -.245);
    orb(ankle, glove, 0, -.019, .062, .139, .067, .208, .86);
    orb(ankle, glove, 0, .025, .018, .129, .084, .158);
    orb(ankle, joint, 0, -.065, .065, .14, .018, .207, .84);
    return { hip, knee, ankle };
  }
  const legs = [leg(-1), leg(1)];
  flatCharacter = false;
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
  const bicycle = new T.Group(); scene.add(bicycle); bicycle.visible = action === 'cycle';
  bicycle.rotation.y = 1.02;
  const wheels: T.Group[] = [];
  const frameMaterial = mat('#649c78', .25, .45), chrome = mat('#dbe5cc', .23, .6);
  const spokeMaterial = mat('#9cafa0', .35, .4);
  if (action === 'cycle') {
    camera.position.set(0, 1.5, 6.7); camera.lookAt(0, 1.32, 0);
    for (const z of [-.52, .53]) {
      const wheel = pivot(bicycle, 'wheel', 0, .29, z); wheels.push(wheel);
      mesh(wheel, new T.TorusGeometry(.265, .029, 12, 48), joint).rotation.y = Math.PI / 2;
      mesh(wheel, new T.TorusGeometry(.234, .009, 8, 48), chrome).rotation.y = Math.PI / 2;
      orb(wheel, chrome, 0, 0, 0, .05, .031, .031);
      for (let i = 0; i < 12; i++) { const a = i * Math.PI / 6; line(wheel, [[0, 0, 0], [0, Math.sin(a) * .23, Math.cos(a) * .23]], .004, spokeMaterial); }
    }
    for (const points of [
      [[0,.29,-.52],[0,.72,-.17],[0,.38,0],[0,.29,-.52]],
      [[0,.72,-.17],[0,.79,.36],[0,.38,0]],
      [[0,.79,.36],[0,.29,.53]], [[0,.72,-.17],[0,.80,-.19]],
      [[0,.79,.36],[0,1.10,.40]], [[-.34,1.10,.40],[0,1.10,.40],[.34,1.10,.40]],
    ]) line(bicycle, points, .023, frameMaterial);
    orb(bicycle, glove, 0, .805, -.19, .14, .034, .115);
    for (const x of [-.33,.33]) orb(bicycle, joint, x, 1.10, .4, .055,.035,.038);
    mesh(bicycle, new T.TorusGeometry(.115,.012,8,40), chrome, .06,.38,0).rotation.y=Math.PI/2;
    line(bicycle, [[.06,.38,.10],[.06,.32,-.52],[.06,.25,-.52],[.06,.38,-.1]], .008, joint);
  }
  const pedals = [-1,1].map(side => {
    const pedal = pivot(bicycle, 'pedal', side*.162,.38);
    mesh(pedal,new T.BoxGeometry(.12,.026,.065),joint);
    return pedal;
  });
  const cranks = [-1,1].map(side => {
    const crank=pivot(bicycle,'crank',side*.162,.38);
    line(crank,[[0,0,0],[0,0,.13]],.012,chrome);
    return crank;
  });
  const can = pivot(right.wrist, 'wateringCan', 0,-.15,.035); can.visible=action==='garden';
  const nozzle = pivot(can,'nozzle',.36,.14,.015);
  const drops: T.Mesh[] = [];
  if(action==='garden') {
    camera.position.set(0,1.5,6.25); camera.lookAt(0,1.10,0);
    shadows.forEach(shadow=>{shadow.visible=false;});
    mesh(can,new T.CylinderGeometry(.115,.09,.19,32),mat('#e7c370',.32,.2));
    const handle=mesh(can,new T.TorusGeometry(.105,.015,10,32),chrome,-.09,.04,0);handle.scale.x=.7;
    line(can,[[.075,-.035,0],[.18,.03,0],[.32,.14,.015]],.025,chrome);
    orb(can,chrome,.35,.14,.015,.045,.038,.045);
    const water=new T.MeshPhysicalMaterial({color:'#85d1df',transparent:true,opacity:.78,roughness:.15});materials.push(water);
    for(let i=0;i<18;i++)drops.push(orb(scene,water,0,0,0,.009,.022,.009));
  }
  function applyBody(t: number) {
    const m = characterMotion(action, t);
    body.position.y = m.bounce; body.rotation.y = m.yaw;
    const joy=action==='complete'?Math.sin(Math.PI*Math.min(1,Math.max(0,(t-.75)/1.3))):0;
    body.position.y+=joy*.065;
    body.rotation.z = m.walking ? .015 * m.step : -.035 * m.recoil;
    authoredHead.setExpression(Math.max(m.blink,action==='complete'&&joy>.8?1:0)>.75?1:m.wink>.75?2:0);
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
    if(action==='start') {
      body.rotation.set(0,0,0);head.rotation.set(0,0,0);
      const wave=Math.sin(t*Math.PI*2*1.25)*.18;
      right.shoulder.rotation.set(-.18,0,1.10);
      right.elbow.rotation.set(0,0,1.60);
      right.wrist.rotation.set(0,0,wave);
      authoredHead.setExpression(m.blink>.75?1:0);
    }
    if(action==='cycle') {
      body.rotation.set(0,1.02,0); body.position.set(-.08*Math.sin(1.02),.235,-.08*Math.cos(1.02));
      const angle=t*Math.PI*2/1.5;
      for(let i=0;i<2;i++) {
        const a=angle+i*Math.PI, y=.38+Math.sin(a)*.13, z=Math.cos(a)*.13;
        pedals[i].position.set((i===0?-1:1)*.162,y,z);
        cranks[i].rotation.x=-a;
        const angles=legAngles(y+.08-.75,z+.08);
        legs[i].hip.rotation.x=angles.hip;legs[i].knee.rotation.x=angles.knee;legs[i].ankle.rotation.x=angles.ankle;
      }
      wheels.forEach(w=>{w.rotation.x=angle*1.8;});
      for(const arm of [left,right]){arm.shoulder.rotation.set(-1.12,0,0);arm.elbow.rotation.set(.15,0,0);arm.wrist.rotation.set(.1,0,0);arm.fingers.forEach(f=>{f.rotation.x=-1.0;});}
      head.rotation.set(-.035,.06*Math.sin(t*.8),.025*Math.sin(t*2));
    }
    if(action==='complete') {
      head.rotation.y=.16*joy;
      head.rotation.z=-.07*joy;
      left.shoulder.rotation.z=-.20-.30*joy;
      left.elbow.rotation.z=-.08-.16*joy;
    }
    if(action==='garden') {
      const g=gardenMotion(t);
      body.position.set(-.12,-.21,0);body.rotation.set(.065*g.pour,.55,0);
      head.rotation.set(.15*g.pour,-.55*g.hello+.12*g.pour,-.08*g.hello);
      right.shoulder.rotation.set(-.05,0,.80-.14*g.hello);right.elbow.rotation.set(0,0,.38);right.wrist.rotation.set(0,0,0);
      right.fingers.forEach(f=>{f.rotation.x=-.85;});
      can.rotation.z=-right.shoulder.rotation.z-right.elbow.rotation.z-.42*g.pour;
      left.shoulder.rotation.set(-.15,0,-.3-1.55*g.hello);
      left.elbow.rotation.set(0,0,-.35*g.hello);left.wrist.rotation.z=g.wave*.42;
      for(let i=0;i<2;i++) {const angles=legAngles(.085-.305,.34);legs[i].hip.rotation.x=angles.hip;legs[i].knee.rotation.x=angles.knee;legs[i].ankle.rotation.x=angles.ankle;}
      authoredHead.setExpression(Math.max(m.blink,g.smile)>.75?1:0);
      scene.updateMatrixWorld(true);const origin=nozzle.getWorldPosition(new T.Vector3());
      drops.forEach((drop,i)=>{const u=(t*1.8+i/18)%1;drop.visible=g.pour>.65;drop.position.set(T.MathUtils.lerp(origin.x,.78,u)+(i%3-1)*.008,T.MathUtils.lerp(origin.y,.02,u*u),T.MathUtils.lerp(origin.z,.18,u));drop.scale.set(.009*g.pour,.022*g.pour,.009*g.pour);});
    }
    return m;
  }
  applyBody(1.2); scene.updateMatrixWorld(true); muzzle.getWorldPosition(burstOrigin);
  function update(t: number) {
    const m = applyBody(t);
    confetti.forEach((piece, i) => {
      const age = m.burstAge - (i % 4) * .016;
      piece.visible = action==='complete' && age >= 0 && age < 2.8;
      if (!piece.visible) return;
      const a = i * 2.39996, speed = .38 + (i % 7) * .08;
      piece.position.set(burstOrigin.x + Math.cos(a) * speed * age, burstOrigin.y + (1.6 + (i % 4) * .15) * age - 1.3 * age * age, burstOrigin.z + Math.sin(a) * .38 * age);
      piece.rotation.set(age * (2 + i % 3), a + age * 3, age * 2);
      piece.scale.setScalar(Math.min(1, Math.max(0, (2.8 - age) * 3)));
    });
    shadows.forEach(s => { s.scale.x = 1 - m.bounce; });
  }
  function dispose() { authoredHead.dispose(); referenceLeaves.dispose(); scene.traverse(o => { if (o instanceof T.Mesh) o.geometry.dispose(); }); materials.forEach(m => m.dispose()); }
  update(0);
  return { scene, camera, update, dispose };
}
