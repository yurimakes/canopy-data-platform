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
 const green='#a8d747',dark='#668e2e',skin='#f5efc9',ink='#183d35';
 ball(root,green,0,.40,0,.43,.52,.32);ball(root,skin,0,.45,.28,.29,.33,.09);
 const head=new T.Group();head.position.y=1.30;root.add(head);ball(head,dark,0,0,0,.66,.62,.4);ball(head,skin,0,0,.13,.59,.53,.36);
 for(let i=0;i<7;i++){const a=i*Math.PI/6;ball(head,green,Math.cos(a)*.56,Math.sin(a)*.52,-.12,.24,.23,.23);}
 const eyes=[ball(head,ink,-.22,.04,.475,.048,.078,.027),ball(head,ink,.22,.04,.475,.048,.078,.027)];
 ball(head,'#ffffff',-.232,.067,.498,.014);ball(head,'#ffffff',.208,.067,.498,.014);
 ball(head,'#ef9e85',-.36,-.13,.441,.089,.045,.02);ball(head,'#ef9e85',.36,-.13,.441,.089,.045,.02);
 const smile=new T.Mesh(new T.TorusGeometry(.095,.013,8,24,Math.PI),material(ink));smile.rotation.z=Math.PI;smile.position.set(0,-.08,.482);head.add(smile);
 const sprout=new T.Group();sprout.position.set(0,.49,0);head.add(sprout);
 const stem=new T.Mesh(new T.CylinderGeometry(.025,.035,.39,12),material(dark));stem.position.y=.18;stem.rotation.z=-.2;sprout.add(stem);
 const leaf=ball(sprout,green,.17,.38,0,.23,.09,.10);leaf.rotation.z=.45;
 const leaf2=ball(sprout,'#6ca848',-.15,.29,0,.19,.08,.09);leaf2.rotation.z=-.45;
 function limb(x:number,y:number,leg=false){const joint=new T.Group();joint.position.set(x,y,0);root.add(joint);ball(joint,green,0,-.16,0,leg?.135:.105,.23,.12);ball(joint,leg?dark:skin,0,-.34,leg?.075:0,leg?.17:.13,.115,.15);return joint;}
 const left=limb(-.43,.63),right=limb(.43,.63),ll=limb(-.21,.03,true),rl=limb(.21,.03,true);
 const popper=new T.Group();right.add(popper);popper.position.set(0,-.43,0);
 const cone=new T.Mesh(new T.ConeGeometry(.12,.32,24),material('#eab96a',.35));cone.rotation.z=Math.PI;popper.add(cone);popper.visible=pose==='complete';
 const confetti=Array.from({length:26},(_,i)=>{const m=new T.Mesh(new T.BoxGeometry(.045,.09,.018),material(['#f4bc65','#82bc7a','#83c8d7','#e5a0a3'][i%4]));scene.add(m);return m;});
 const artifact=new T.Group();scene.add(artifact);
 if(pose==='coin'||pose==='trophy'){
   root.visible=false;const gold=material('#e7b957',.65);
   if(pose==='coin'){
     const disc=new T.Mesh(new T.CylinderGeometry(.75,.75,.20,64),gold);disc.rotation.x=Math.PI/2;artifact.add(disc);
     const ring=new T.Mesh(new T.TorusGeometry(.61,.035,12,64),material('#fff0af',.45));ring.position.z=.115;artifact.add(ring);
     ball(artifact,'#648642',0,0,.15,.18,.36,.05).rotation.z=-.55;
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
   else{right.rotation.z=2.35+Math.sin(t*6)*.28;right.rotation.x=Math.sin(t*3)*.12;left.rotation.z=-.12;head.rotation.z=Math.sin(t*1.8)*.055;}
   sprout.rotation.z=Math.sin(t*2.5)*.10;eyes.forEach(e=>e.scale.y=.078*(t%4.6>4.42?.12:1));
   confetti.forEach((c,i)=>{const age=(t+i*.023)%2.8,a=i*2.399,speed=.55+(i%5)*.14;c.position.set(.55+Math.cos(a)*age*speed,1.3+age*1.7-age*age*.8,Math.sin(a)*age*.6);c.rotation.set(age*3,a,age*2);c.visible=pose==='complete'&&age<2.4;});
   artifact.rotation.y=Math.sin(t*.9)*.4;artifact.rotation.z=Math.sin(t*.7)*.07;
 }
 function dispose(){scene.traverse(o=>{if(o instanceof T.Mesh)o.geometry.dispose();});mats.forEach(m=>m.dispose());(shadow.material as T.Material).dispose();}
 update(0);return {scene,camera,update,dispose};
}
