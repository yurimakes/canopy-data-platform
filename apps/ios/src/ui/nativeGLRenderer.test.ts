import {afterEach,expect,it,vi} from 'vitest';
import * as T from 'three';
import {createNativeRenderer} from './nativeGLRenderer';
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
it('Expo의 WebGL2 상속 구조를 WebGL1로 오인하지 않고 드라이버에 전달',()=>{
 class WebGL1{}
 class WebGL2 extends WebGL1{
  drawingBufferWidth=200;drawingBufferHeight=200;
  getContextAttributes(){return {alpha:true};}
  getShaderPrecisionFormat(){return {precision:23};}
  texStorage2D(){}createVertexArray(){}getExtension(){return null;}
  getParameter(){throw new Error('DRIVER_REACHED');}
 }
 vi.stubGlobal('WebGLRenderingContext',WebGL1);vi.stubGlobal('WebGL2RenderingContext',WebGL2);
 vi.spyOn(console,'error').mockImplementation(()=>{});
 const gl=new WebGL2() as unknown as WebGL2RenderingContext;
 const canvas={addEventListener(){},removeEventListener(){}} as unknown as HTMLCanvasElement;
 expect(()=>new T.WebGLRenderer({canvas,context:gl})).toThrow('WebGL 1 is not supported');
 expect(()=>createNativeRenderer(gl)).toThrow('DRIVER_REACHED');
});
it('WebGL2 기능이 없는 컨텍스트는 명확히 거부',()=>{
 expect(()=>createNativeRenderer({} as WebGL2RenderingContext)).toThrow('WebGL2 기능');
});
