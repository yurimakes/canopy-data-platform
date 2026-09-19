import * as T from 'three';
import {gunzipSync} from 'fflate';
import {textureBytes,textureWidth,textureHeight} from './canopyTextureData';

let pixels:Uint8Array|undefined;
function atlasTexture(){
  if(!pixels){
    const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    const bytes:number[]=[];let bits=0,value=0;
    for(const c of textureBytes){const n=alphabet.indexOf(c);if(n<0)continue;value=(value<<6)|n;bits+=6;if(bits>=8){bits-=8;bytes.push((value>>bits)&255);}}
    pixels=gunzipSync(new Uint8Array(bytes));
  }
  const texture=new T.DataTexture(pixels,textureWidth,textureHeight,T.RGBAFormat);
  texture.colorSpace=T.SRGBColorSpace;texture.magFilter=T.LinearFilter;texture.minFilter=T.LinearFilter;
  texture.needsUpdate=true;return texture;
}

// A closed, authored cross-section loft. Each row is y, half-width, half-depth,
// centre-z; it defines the actual shell silhouette rather than scaling a sphere.
export function shellGeometry(rows:number[][]){
  const curve=new T.CatmullRomCurve3(rows.map(r=>new T.Vector3(r[1],r[2],r[3]??0)));
  const n=48,m=40,positions:number[]=[],indices:number[]=[];
  for(let i=0;i<=m;i++){
    const t=i/m,q=t*(rows.length-1),k=Math.min(rows.length-2,Math.floor(q)),u=q-k;
    const profile=curve.getPoint(t),y=T.MathUtils.lerp(rows[k][0],rows[k+1][0],u);
    for(let j=0;j<=n;j++){const a=j/n*Math.PI*2;positions.push(Math.cos(a)*Math.max(.001,profile.x),y,Math.sin(a)*Math.max(.001,profile.y)+profile.z);
      if(i<m&&j<n){const p=i*(n+1)+j;indices.push(p,p+n+1,p+1,p+1,p+n+1,p+n+2);}}
  }
  const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(positions,3));g.setIndex(indices);g.computeVertexNormals();return g;
}

// Front contour measured in the original atlas. UVs preserve its eyes, mouth,
// cheek outline and asymmetry, while depth is supplied by a curved face mesh.
const faceContour=[[121,195],[160,197],[201,210],[254,211],[289,229],[308,264],[321,312],[301,350],[263,378],[221,390],[163,386],[115,369],[79,343],[61,303],[72,254],[91,218]];
export function createCanopyHead(){
  const group=new T.Group();group.name='authoredHeadShell';
  const texture=atlasTexture();
  const faceMaterial=new T.MeshBasicMaterial({map:texture,side:T.DoubleSide,toneMapped:false});
  const green=new T.MeshBasicMaterial({color:'#829e58',toneMapped:false});
  const outline=new T.CatmullRomCurve3(faceContour.map(p=>new T.Vector3(p[0],p[1],0)),true,'catmullrom',.3);
  const positions:number[]=[],uv:number[]=[],indices:number[]=[],rings=22,sides=96;
  for(let r=0;r<=rings;r++)for(let j=0;j<=sides;j++){
    const t=r/rings,p=outline.getPoint(j/sides),px=188+(p.x-188)*t,py=292+(p.y-292)*t;
    positions.push((px-188)*.0046,(292-py)*.0046,.30+.145*(1-t*t));
    uv.push(px/textureWidth,py/textureHeight);
    if(r<rings&&j<sides){const k=r*(sides+1)+j;indices.push(k,k+1,k+sides+1,k+1,k+sides+2,k+sides+1);}
  }
  const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(positions,3));g.setAttribute('uv',new T.Float32BufferAttribute(uv,2));g.setIndex(indices);g.computeVertexNormals();
  const face=new T.Mesh(g,faceMaterial);face.name='referenceFace';group.add(face);
  // The visor and helmet share the same perimeter, rather than intersecting
  // independently modelled surfaces. The first shell ring is the visor edge.
  const shellPositions:number[]=[],shellIndices:number[]=[];
  const sections=[[1,.30],[1.045,.29],[1.10,.12],[1.055,-.12],[.82,-.32],[.38,-.43],[.001,-.45]];
  const shellProfile=new T.CatmullRomCurve3(sections.map(p=>new T.Vector3(p[0],p[1],0)),false,'centripetal');
  const shellRings=36;
  for(let r=0;r<=shellRings;r++)for(let j=0;j<=sides;j++){
    const p=outline.getPoint(j/sides),profile=shellProfile.getPoint(r/shellRings),scale=Math.max(.001,profile.x),z=profile.y;
    shellPositions.push((p.x-188)*.0046*scale,(292-p.y)*.0046*scale,z);
    if(r<shellRings&&j<sides){const k=r*(sides+1)+j;shellIndices.push(k,k+1,k+sides+1,k+1,k+sides+2,k+sides+1);}
  }
  const shellGeometry=new T.BufferGeometry();shellGeometry.setAttribute('position',new T.Float32BufferAttribute(shellPositions,3));shellGeometry.setIndex(shellIndices);shellGeometry.computeVertexNormals();
  const shell=new T.Mesh(shellGeometry,green);shell.name='continuousHelmet';group.add(shell);

  return {group,setExpression(expression:0|1|2){texture.offset.x=[0,350/textureWidth,702/textureWidth][expression];},dispose(){texture.dispose();faceMaterial.dispose();green.dispose();}};
}

export function createReferenceLeaves(){
  const group=new T.Group();group.name='referenceLeaves';
  const texture=atlasTexture();
  const material=new T.MeshBasicMaterial({map:texture,side:T.DoubleSide,toneMapped:false,alphaTest:.1});
  const contours=[
    [[212,177],[166,164],[127,135],[103,95],[98,40],[139,47],[176,73],[207,112],[224,153]],
    [[214,179],[238,140],[278,111],[318,99],[348,104],[325,145],[282,169],[240,180]],
  ];
  for(const points of contours){
    const curve=new T.CatmullRomCurve3(points.map(p=>new T.Vector3(p[0],p[1],0)),true,'catmullrom',.25);
    const center=points.reduce((v,p)=>v.add(new T.Vector2(p[0],p[1])),new T.Vector2()).multiplyScalar(1/points.length);
    const positions:number[]=[],uv:number[]=[],indices:number[]=[],n=64,rings=12;
    for(let r=0;r<=rings;r++)for(let j=0;j<=n;j++){
      const t=r/rings,p=curve.getPoint(j/n),x=center.x+(p.x-center.x)*t,y=center.y+(p.y-center.y)*t;
      positions.push((x-213)*.0048,(181-y)*.0048,.05*(1-t*t));uv.push(x/textureWidth,y/textureHeight);
      if(r<rings&&j<n){const k=r*(n+1)+j;indices.push(k,k+1,k+n+1,k+1,k+n+2,k+n+1);}
    }
    const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(positions,3));g.setAttribute('uv',new T.Float32BufferAttribute(uv,2));g.setIndex(indices);g.computeVertexNormals();
    const leaf=new T.Mesh(g,material);leaf.rotation.y=group.children.length===0?-.28:.4;group.add(leaf);
  }
  return {group,dispose(){texture.dispose();material.dispose();}};
}
