import * as T from 'three';
import type {MascotPose} from './CanopyMascot';
export function mascotScene(pose:MascotPose){
 const scene=new T.Scene(),camera=new T.PerspectiveCamera(32,1,.1,40);
 camera.position.set(0,1.22,6.35);camera.lookAt(0,1.05,0);
 scene.add(new T.HemisphereLight(0xffffff,0x557561,1.9));
 const key=new T.DirectionalLight(0xfff5de,3);key.position.set(-3,5,5);scene.add(key);
 const rim=new T.DirectionalLight(0xc4faff,2);rim.position.set(3,3,-2);scene.add(rim);
 const root=new T.Group();scene.add(root);const mats=new Map<string,T.MeshStandardMaterial>();
 function material(color:string,metalness=0){const id=color+metalness;if(!mats.has(id))mats.set(id,new T.MeshStandardMaterial({color,roughness:metalness?.27:.48,metalness}));return mats.get(id)!;}
 function ball(parent:T.Object3D,color:string,x:number,y:number,z:number,sx:number,sy=sx,sz=sx){const m=new T.Mesh(new T.SphereGeometry(1,28,20),material(color));m.position.set(x,y,z);m.scale.set(sx,sy,sz);parent.add(m);return m;}
 const green='#719e4e',dark='#285b43',ink='#10291e',shell='#f1f2e8';
 ball(root,shell,0,.36,0,.40,.48,.30);
 ball(root,dark,0,.36,-.19,.33,.36,.20);
 ball(root,shell,0,.37,.06,.37,.45,.29);
 ball(root,dark,0,.79,0,.20,.10,.19);
 const head=new T.Group();head.position.y=1.31;root.add(head);
 ball(head,green,0,0,0,.65,.55,.39);
 ball(head,shell,0,-.015,.06,.62,.51,.40);
 ball(head,'#a6c57c',0,-.02,.278,.564,.424,.22);
 ball(head,'#f5f5eb',0,-.02,.302,.548,.410,.22);
 function tube(parent:T.Object3D,points:number[][],radius:number,color:string){const curve=new T.CatmullRomCurve3(points.map(p=>new T.Vector3(...p as [number,number,number])));const mesh=new T.Mesh(new T.TubeGeometry(curve,32,radius,10,false),material(color));parent.add(mesh);return mesh;}
 for(const x of [-.64,.64]){
   ball(head,dark,x,0,0,.10,.29,.27);ball(head,green,x*1.075,0,.015,.085,.245,.24);
   const ring=new T.Mesh(new T.TorusGeometry(.18,.024,12,48),material('#e6f5dd',.25));ring.rotation.y=Math.PI/2;ring.position.set(x*1.19,0,.015);head.add(ring);
   ball(head,'#9dc184',x*1.20,0,.015,.018,.115,.112);
 }
 const eyes=[ball(head,ink,-.22,.065,.509,.116,.149,.055),ball(head,ink,.22,.065,.509,.116,.149,.055)];
 const irises=[ball(head,'#38795b',-.22,.04,.556,.077,.096,.024),ball(head,'#38795b',.22,.04,.556,.077,.096,.024)];
 const pupils=[ball(head,'#061f17',-.22,.062,.574,.052,.075,.014),ball(head,'#061f17',.22,.062,.574,.052,.075,.014)];
 const shines=[ball(head,'#ffffff',-.250,.12,.575,.032,.039,.012),ball(head,'#ffffff',.190,.12,.575,.032,.039,.012)];
 ball(head,'#ffffff',-.188,.018,.573,.013);ball(head,'#ffffff',.252,.018,.573,.013);
 const wink=tube(head,[[.115,.035,.53],[.20,.09,.55],[.28,.085,.54],[.335,.02,.515]],.029,ink);wink.visible=false;
 const mouth=new T.Shape();mouth.moveTo(-.095,-.13);mouth.quadraticCurveTo(0,-.16,.095,-.13);mouth.quadraticCurveTo(.078,-.245,0,-.245);mouth.quadraticCurveTo(-.078,-.245,-.095,-.13);
 const smile=new T.Mesh(new T.ShapeGeometry(mouth,24),material(ink));smile.position.z=.529;head.add(smile);
 ball(head,'#bd7d75',0,-.222,.535,.04,.014,.006);
 const sprout=new T.Group();sprout.position.set(0,.48,0);head.add(sprout);
 ball(sprout,green,0,0,0,.19,.042,.15);
 tube(sprout,[[0,0,0],[.015,.15,0],[-.025,.31,0]],.026,dark);
 function leafBlade(x:number,y:number,z:number,angle:number,size:number){const shape=new T.Shape();shape.moveTo(0,0);shape.bezierCurveTo(-.27,.20,-.22,.53,0,.75);shape.bezierCurveTo(.29,.47,.26,.15,0,0);const g=new T.Group();g.position.set(x,y,z);g.rotation.z=angle;g.scale.setScalar(size);sprout.add(g);g.add(new T.Mesh(new T.ExtrudeGeometry(shape,{depth:.025,bevelEnabled:true,bevelThickness:.035,bevelSize:.025,bevelSegments:3,curveSegments:24}),material(green)));tube(g,[[0,.02,.05],[0,.31,.065],[0,.68,.05]],.008,'#c3d597');}
 leafBlade(-.025,.23,0,.53,.77);leafBlade(.01,.15,.03,-.93,.65);
 function emblem(parent:T.Object3D,scale:number,x:number,y:number,z:number,color:string){
   const shape=new T.Shape();shape.moveTo(-.24,-.32);shape.bezierCurveTo(-.48,.12,-.18,.40,.34,.42);shape.bezierCurveTo(.43,-.08,.16,-.43,-.24,-.32);
   const group=new T.Group();group.position.set(x,y,z);group.scale.setScalar(scale);parent.add(group);
   group.add(new T.Mesh(new T.ExtrudeGeometry(shape,{depth:.025,bevelEnabled:true,bevelThickness:.018,bevelSize:.015,bevelSegments:3,steps:1,curveSegments:24}),material(color,.15)));
   const vein=new T.CatmullRomCurve3([new T.Vector3(-.28,-.40,.05),new T.Vector3(-.08,-.12,.06),new T.Vector3(.24,.30,.055)]);
   group.add(new T.Mesh(new T.TubeGeometry(vein,24,.014,8,false),material('#e6f5ba')));return group;
 }
 ball(root,green,0,.48,.366,.164,.164,.038);
 const badge=new T.Mesh(new T.TorusGeometry(.152,.011,10,48),material('#e5ffe9'));badge.position.set(0,.48,.407);root.add(badge);
 emblem(root,.29,0,.475,.419,'#efffe8');
 function limb(x:number,y:number,leg=false){const joint=new T.Group();joint.position.set(x,y,0);root.add(joint);
   ball(joint,dark,0,-.025,0,leg?.135:.12,.13,.12);
   ball(joint,shell,0,-.16,0,leg?.145:.11,.20,.12);
   const hand=new T.Group();hand.position.set(0,-.32,leg?.075:0);joint.add(hand);
   ball(hand,green,0,0,0,leg?.18:.106,leg?.11:.12,leg?.23:.08);
   if(leg){ball(hand,dark,0,-.074,.04,.184,.043,.224);ball(hand,shell,0,.035,.055,.153,.073,.16);}
   else{for(let i=0;i<3;i++)ball(hand,green,(i-1)*.066,-.088,0,.038,.082,.045);ball(hand,green,-Math.sign(x)*.11,-.01,.005,.06,.045,.047);}
   return joint;}
 const left=limb(-.40,.68),right=limb(.40,.68),ll=limb(-.19,.02,true),rl=limb(.19,.02,true);
 const popper=new T.Group();right.add(popper);popper.position.set(0,-.43,0);
 const cone=new T.Mesh(new T.ConeGeometry(.12,.32,24),material('#eab96a',.35));cone.rotation.z=Math.PI;popper.add(cone);popper.visible=pose==='complete';
 const confetti=Array.from({length:26},(_,i)=>{const m=new T.Mesh(new T.BoxGeometry(.045,.09,.018),material(['#f4bc65','#82bc7a','#83c8d7','#e5a0a3'][i%4]));scene.add(m);return m;});
 const artifact=new T.Group();scene.add(artifact);
 if(pose==='coin'||pose==='trophy'){
   root.visible=false;const gold=material('#e7b957',.65);
   if(pose==='coin'){
     const disc=new T.Mesh(new T.CylinderGeometry(.75,.75,.20,64),gold);disc.rotation.x=Math.PI/2;artifact.add(disc);
     const ring=new T.Mesh(new T.TorusGeometry(.61,.035,12,64),material('#fff0af',.45));ring.position.z=.115;artifact.add(ring);
     const inset=new T.Mesh(new T.CylinderGeometry(.57,.57,.025,64),material('#207e55',.32));inset.rotation.x=Math.PI/2;inset.position.z=.12;artifact.add(inset);emblem(artifact,1,0,0,.15,'#b7dd75');
     for(let i=0;i<48;i++){const a=i*Math.PI/24;ball(artifact,'#f9d880',Math.cos(a)*.69,Math.sin(a)*.69,.105,.016,.016,.012);}
   }else{
     const cup=new T.Mesh(new T.CylinderGeometry(.58,.23,.64,48),gold);cup.position.y=.25;artifact.add(cup);
     const stem=new T.Mesh(new T.CylinderGeometry(.075,.10,.48,24),gold);stem.position.y=-.28;artifact.add(stem);
     const base=new T.Mesh(new T.CylinderGeometry(.38,.40,.13,48),gold);base.position.y=-.58;artifact.add(base);
     for(const x of [-.57,.57]){const h=new T.Mesh(new T.TorusGeometry(.22,.055,12,32),gold);h.position.set(x,.26,0);artifact.add(h);}
   }artifact.position.y=.85;
 }
 const shadow=new T.Mesh(new T.CircleGeometry(.6,48),new T.MeshBasicMaterial({color:0x265340,transparent:true,opacity:.09}));shadow.rotation.x=-Math.PI/2;shadow.position.y=-.48;shadow.scale.y=.7;scene.add(shadow);
 function update(t:number){
   if(pose==='run'||pose==='walk'){const stride=Math.sin(t*9);ll.rotation.x=stride*.8;rl.rotation.x=-stride*.8;left.rotation.x=-stride*.8;right.rotation.x=stride*.8;root.position.y=Math.abs(Math.sin(t*9))*.045;root.rotation.y=.30;}
   else if(pose==='complete'){right.rotation.z=2.3+Math.sin(t*3)*.2;left.rotation.z=-1.4+Math.sin(t*3)*.15;head.rotation.z=Math.sin(t*2)*.05;popper.rotation.z=.35;}
   else{right.rotation.z=2.15+Math.sin(t*3.4)*.22;right.rotation.x=Math.sin(t*3)*.12;left.rotation.z=-.42;root.rotation.y=-.12;head.rotation.z=Math.sin(t*1.8)*.055;}
   const blink=t%5.2>5.06;const winking=pose!=='run'&&pose!=='walk'&&t%7>5.8;eyes.forEach((e,i)=>{e.scale.y=.149*(blink?.1:1);e.visible=!(i===1&&winking);irises[i].visible=e.visible&&!blink;pupils[i].visible=e.visible&&!blink;shines[i].visible=e.visible&&!blink;});wink.visible=winking;sprout.rotation.z=Math.sin(t*1.7)*.035;
   confetti.forEach((c,i)=>{const age=(t+i*.023)%2.8,a=i*2.399,speed=.55+(i%5)*.14;c.position.set(.55+Math.cos(a)*age*speed,1.3+age*1.7-age*age*.8,Math.sin(a)*age*.6);c.rotation.set(age*3,a,age*2);c.visible=pose==='complete'&&age<2.4;});
   artifact.rotation.y=Math.sin(t*.9)*.4;artifact.rotation.z=Math.sin(t*.7)*.07;
 }
 function dispose(){scene.traverse(o=>{if(o instanceof T.Mesh)o.geometry.dispose();});mats.forEach(m=>m.dispose());(shadow.material as T.Material).dispose();}
 update(0);return {scene,camera,update,dispose};
}
