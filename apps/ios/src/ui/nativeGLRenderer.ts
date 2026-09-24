import * as T from 'three';

// Expo SDK 57의 WebGL2 객체는 WebGL1 클래스도 상속함.
// Three의 context 인자 검사는 이를 WebGL1로 오인하므로 canvas의 webgl2 경로로 전달.
export function createNativeRenderer(gl:WebGL2RenderingContext){
 if(typeof gl.texStorage2D!=='function'||typeof gl.createVertexArray!=='function'){
  throw new Error('WebGL2 기능을 사용할 수 없습니다. Expo Go 버전을 확인해주세요.');
 }
 const canvas={width:gl.drawingBufferWidth,height:gl.drawingBufferHeight,style:{},
  addEventListener(){},removeEventListener(){},
  getContext(name:string){return name==='webgl2'?gl:null;}};
 return new T.WebGLRenderer({canvas:canvas as unknown as HTMLCanvasElement,alpha:true,premultipliedAlpha:false});
}
