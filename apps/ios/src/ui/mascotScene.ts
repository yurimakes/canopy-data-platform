import * as T from 'three';
import type {MascotPose} from './CanopyMascot';
import {robotRig} from './robotRig';
export function mascotScene(pose:MascotPose){
 if(pose!=='coin'&&pose!=='trophy')return robotRig(pose==='walk'||pose==='run'||pose==='complete'||pose==='cycle'||pose==='garden'?pose:'start');
 const scene=new T.Scene(),camera=new T.PerspectiveCamera(32,1,.1,40);
 camera.position.set(0,.85,3.5);camera.lookAt(0,.85,0);
 scene.add(new T.HemisphereLight(0xffffff,0x557561,1.9));
 const key=new T.DirectionalLight(0xfff5de,3);key.position.set(-3,5,5);scene.add(key);
 const rim=new T.DirectionalLight(0xc4faff,2);rim.position.set(3,3,-2);scene.add(rim);
 const mats=new Map<string,T.MeshStandardMaterial>();
 function material(color:string,metalness=0){const id=color+metalness;if(!mats.has(id))mats.set(id,new T.MeshStandardMaterial({color,roughness:metalness?.27:.48,metalness}));return mats.get(id)!;}
 function ball(parent:T.Object3D,color:string,x:number,y:number,z:number,sx:number,sy=sx,sz=sx){const m=new T.Mesh(new T.SphereGeometry(1,28,20),material(color));m.position.set(x,y,z);m.scale.set(sx,sy,sz);parent.add(m);return m;}
 function emblem(parent:T.Object3D,scale:number,x:number,y:number,z:number,color:string){
   const shape=new T.Shape();shape.moveTo(-.24,-.32);shape.bezierCurveTo(-.48,.12,-.18,.40,.34,.42);shape.bezierCurveTo(.43,-.08,.16,-.43,-.24,-.32);
   const group=new T.Group();group.position.set(x,y,z);group.scale.setScalar(scale);parent.add(group);
   group.add(new T.Mesh(new T.ExtrudeGeometry(shape,{depth:.025,bevelEnabled:true,bevelThickness:.018,bevelSize:.015,bevelSegments:3,steps:1,curveSegments:24}),material(color,.15)));
   const vein=new T.CatmullRomCurve3([new T.Vector3(-.28,-.40,.05),new T.Vector3(-.08,-.12,.06),new T.Vector3(.24,.30,.055)]);
   group.add(new T.Mesh(new T.TubeGeometry(vein,24,.014,8,false),material('#e6f5ba')));return group;
 }
 const artifact=new T.Group();scene.add(artifact);
 if(pose==='coin'||pose==='trophy'){
   const gold=material('#e7b957',.65);
   if(pose==='coin'){
     const disc=new T.Mesh(new T.CylinderGeometry(.75,.75,.20,64),gold);disc.rotation.x=Math.PI/2;artifact.add(disc);
     const ring=new T.Mesh(new T.TorusGeometry(.61,.035,12,64),material('#fff0af',.45));ring.position.z=.115;artifact.add(ring);
     const inset=new T.Mesh(new T.CylinderGeometry(.57,.57,.025,64),material('#207e55',.32));inset.rotation.x=Math.PI/2;inset.position.z=.12;artifact.add(inset);emblem(artifact,1,0,0,.15,'#b7dd75');
     const reverse=new T.Group();reverse.rotation.y=Math.PI;artifact.add(reverse);const reverseRing=ring.clone();reverseRing.geometry=ring.geometry.clone();reverse.add(reverseRing);const reverseInset=inset.clone();reverseInset.geometry=inset.geometry.clone();reverse.add(reverseInset);emblem(reverse,1,0,0,.15,'#b7dd75');
     for(let i=0;i<48;i++){const a=i*Math.PI/24;ball(artifact,'#f9d880',Math.cos(a)*.69,Math.sin(a)*.69,.105,.016,.016,.012);}
   }else{
     const cup=new T.Mesh(new T.CylinderGeometry(.58,.23,.64,48),gold);cup.position.y=.25;artifact.add(cup);
     const stem=new T.Mesh(new T.CylinderGeometry(.075,.10,.48,24),gold);stem.position.y=-.28;artifact.add(stem);
     const base=new T.Mesh(new T.CylinderGeometry(.38,.40,.13,48),gold);base.position.y=-.58;artifact.add(base);
     for(const x of [-.57,.57]){const h=new T.Mesh(new T.TorusGeometry(.22,.055,12,32),gold);h.position.set(x,.26,0);artifact.add(h);}
   }artifact.position.y=.85;
 }
 const shadow=new T.Mesh(new T.CircleGeometry(.6,48),new T.MeshBasicMaterial({color:0x265340,transparent:true,opacity:.09}));shadow.rotation.x=-Math.PI/2;shadow.position.y=-.48;shadow.scale.y=.7;scene.add(shadow);
 function update(t:number){artifact.rotation.y=pose==='coin'?t*.9:Math.sin(t*.9)*.4;artifact.rotation.z=Math.sin(t*.7)*.07;}
 function dispose(){scene.traverse(o=>{if(o instanceof T.Mesh)o.geometry.dispose();});mats.forEach(m=>m.dispose());(shadow.material as T.Material).dispose();}
 update(0);return {scene,camera,update,dispose};
}
