import * as T from 'three';
import type {MascotPose} from './CanopyMascot';
export function mascotScene(pose:MascotPose){
 const scene=new T.Scene(),camera=new T.PerspectiveCamera(32,1,.1,40);
 camera.position.set(0,1.15,5.9);camera.lookAt(0,.95,0);
 scene.add(new T.HemisphereLight(0xffffff,0x557561,2.6));
 const key=new T.DirectionalLight(0xfff5de,4);key.position.set(-3,5,5);scene.add(key);
 const rim=new T.DirectionalLight(0xc4faff,2);rim.position.set(3,3,-2);scene.add(rim);
 const root=new T.Group();scene.add(root);const mats=new Map<string,T.MeshStandardMaterial>();
 function material(color:string,metalness=0){const id=color+metalness;if(!mats.has(id))mats.set(id,new T.MeshStandardMaterial({color,roughness:metalness?.27:.48,metalness}));return mats.get(id)!;}
 function ball(parent:T.Object3D,color:string,x:number,y:number,z:number,sx:number,sy=sx,sz=sx){const m=new T.Mesh(new T.SphereGeometry(1,28,20),material(color));m.position.set(x,y,z);m.scale.set(sx,sy,sz);parent.add(m);return m;}
 const green='#a5d638',dark='#69a52a',ink='#173e2b';
 ball(root,green,0,.34,0,.43,.51,.32);
 // Backpack and shoulder straps belong to the original Canopy tree character.
 ball(root,'#337d64',0,.48,-.29,.40,.40,.16);
 for(const x of [-.32,.32]){const strap=ball(root,'#d99a43',x,.58,.25,.048,.28,.06);strap.rotation.z=x>0?.12:-.12;}
 const head=new T.Group();head.position.y=1.30;root.add(head);
 ball(head,green,0,-.03,.03,.65,.47,.42);
 for(const [x,y,r] of [[-.50,.12,.27],[-.37,.42,.30],[0,.57,.31],[.35,.43,.30],[.53,.12,.26],[-.52,-.15,.22],[.51,-.15,.22]])ball(head,green,x,y,-.07,r,r,r*.87);
 const eyes=[ball(head,ink,-.20,-.04,.438,.036,.060,.023),ball(head,ink,.20,-.04,.438,.036,.060,.023)];
 ball(head,'#ffffff',-.210,-.023,.458,.010);ball(head,'#ffffff',.190,-.023,.458,.010);
 ball(head,'#f0ae55',-.34,-.14,.408,.079,.052,.026);ball(head,'#f0ae55',.34,-.14,.408,.079,.052,.026);
 const smile=new T.Mesh(new T.TorusGeometry(.084,.018,12,30,Math.PI),material(ink));smile.rotation.z=Math.PI;smile.position.set(0,-.15,.451);head.add(smile);
 function emblem(parent:T.Object3D,scale:number,x:number,y:number,z:number,color:string){
   const shape=new T.Shape();shape.moveTo(-.24,-.32);shape.bezierCurveTo(-.48,.12,-.18,.40,.34,.42);shape.bezierCurveTo(.43,-.08,.16,-.43,-.24,-.32);
   const group=new T.Group();group.position.set(x,y,z);group.scale.setScalar(scale);parent.add(group);
   group.add(new T.Mesh(new T.ExtrudeGeometry(shape,{depth:.025,bevelEnabled:true,bevelThickness:.018,bevelSize:.015,bevelSegments:3,steps:1,curveSegments:24}),material(color,.15)));
   const vein=new T.CatmullRomCurve3([new T.Vector3(-.28,-.40,.05),new T.Vector3(-.08,-.12,.06),new T.Vector3(.24,.30,.055)]);
   group.add(new T.Mesh(new T.TubeGeometry(vein,24,.014,8,false),material('#e6f5ba')));return group;
 }
 emblem(root,.30,.015,.35,.325,'#d9ed82');
 function limb(x:number,y:number,leg=false){const joint=new T.Group();joint.position.set(x,y,0);root.add(joint);ball(joint,green,0,-.13,0,leg?.14:.11,.20,.12);ball(joint,green,0,-.28,leg?.09:0,leg?.19:.135,.12,.16);return joint;}
 const left=limb(-.43,.55),right=limb(.43,.55),ll=limb(-.21,-.02,true),rl=limb(.21,-.02,true);
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
   else{right.rotation.z=2.15+Math.sin(t*3.4)*.22;right.rotation.x=Math.sin(t*3)*.12;left.rotation.z=-.12;head.rotation.z=Math.sin(t*1.8)*.055;}
   eyes.forEach(e=>e.scale.y=.060*(t%4.6>4.42?.12:1));
   confetti.forEach((c,i)=>{const age=(t+i*.023)%2.8,a=i*2.399,speed=.55+(i%5)*.14;c.position.set(.55+Math.cos(a)*age*speed,1.3+age*1.7-age*age*.8,Math.sin(a)*age*.6);c.rotation.set(age*3,a,age*2);c.visible=pose==='complete'&&age<2.4;});
   artifact.rotation.y=Math.sin(t*.9)*.4;artifact.rotation.z=Math.sin(t*.7)*.07;
 }
 function dispose(){scene.traverse(o=>{if(o instanceof T.Mesh)o.geometry.dispose();});mats.forEach(m=>m.dispose());(shadow.material as T.Material).dispose();}
 update(0);return {scene,camera,update,dispose};
}
