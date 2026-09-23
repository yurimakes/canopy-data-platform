"""Build cyclic 120-frame motion atlases from the character keyframes."""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'apps/ios/assets/canopy-ui'
COUNT=120

def build(name,size):
    sheet=Image.open(ASSETS/f'mascot-{name}-atlas.png').convert('RGBA')
    w,h=sheet.size
    keys=[]
    for i in range(8):
        box=(round(i%4*w/4),round(i//4*h/2),round((i%4+1)*w/4),round((i//4+1)*h/2))
        keys.append(np.asarray(sheet.crop(box).resize((size,size),Image.Resampling.LANCZOS),dtype=np.float32)/255)
    # Flow sees an opaque neutral composite; output retains premultiplied alpha.
    gray=[cv2.cvtColor(np.uint8((a[:,:,:3]*a[:,:,3:]+(1-a[:,:,3:])*.94)*255),cv2.COLOR_RGB2GRAY) for a in keys]
    optical=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    optical.setUseSpatialPropagation(True)
    forward=[optical.calc(gray[i],gray[(i+1)%8],None) for i in range(8)]
    backward=[optical.calc(gray[(i+1)%8],gray[i],None) for i in range(8)]
    grid=np.stack(np.meshgrid(np.arange(size,dtype=np.float32),np.arange(size,dtype=np.float32)),axis=-1)
    premul=[np.concatenate([a[:,:,:3]*a[:,:,3:],a[:,:,3:]],axis=2) for a in keys]
    frames=[]
    positions={'wave':[0,15,30,45,52,59,80,100,120],'celebrate':[0,16,32,48,64,80,88,96,120]}.get(name,list(range(0,121,15)))
    for n in range(COUNT):
        i=min(7,int(np.searchsorted(positions,n,side='right')-1))
        t=(n-positions[i])/(positions[i+1]-positions[i]);t=t*t*(3-2*t)
        # Cyclic source adjacency also interpolates the last pose back to the first.
        wa=cv2.remap(premul[i],grid-t*forward[i],None,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        wb=cv2.remap(premul[(i+1)%8],grid-(1-t)*backward[i],None,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        rgba=(1-t)*wa+t*wb
        alpha=rgba[:,:,3:];rgb=np.divide(rgba[:,:,:3],alpha,out=np.zeros_like(rgba[:,:,:3]),where=alpha>1e-5)
        frames.append(Image.fromarray(np.uint8(np.clip(np.concatenate([rgb,alpha],axis=2),0,1)*255)))
    atlas=Image.new('RGBA',(10*size,12*size))
    for n,frame in enumerate(frames):atlas.paste(frame,((n%10)*size,(n//10)*size))
    path=ASSETS/f'mascot-{name}-120.png';atlas.save(path,optimize=True)
    output=ROOT/'.local-data/motion-preview';output.mkdir(exist_ok=True)
    frames[0].save(output/f'{name}.png',save_all=True,append_images=frames[1:],duration=1000/(60 if name=='walk' else 30),loop=0,disposal=0,blend=0)
    composite=[np.asarray(f,dtype=float)[:,:,:3]*(np.asarray(f,dtype=float)[:,:,3:]/255)+240*(1-np.asarray(f,dtype=float)[:,:,3:]/255) for f in frames]
    diffs=[float(np.abs(composite[(n+1)%COUNT]-composite[n]).mean()) for n in range(COUNT)]
    report={'frames':COUNT,'unique_frames':len({f.tobytes() for f in frames}),'fps':60 if name=='walk' else 30,'seconds':2 if name=='walk' else 4,'cell_size':size,'seam_difference':diffs[-1],'median_difference':float(np.median(diffs)),'maximum_difference':max(diffs),'bytes':path.stat().st_size}
    print(name,json.dumps(report));return report

if __name__=='__main__':
    reports={name:build(name,size) for name,size in [('wave',256),('walk',160),('celebrate',256)]}
    (ROOT/'.local-data/motion-preview/checks.json').write_text(json.dumps(reports,indent=2))
