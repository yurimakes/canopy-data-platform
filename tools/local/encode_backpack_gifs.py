"""Encode 36 chronological generated poses per action as seamless local GIFs.

Each source is a 6x6 transparent sheet. Intermediates smooth the 36 original
poses; they do not replace the requirement for 30+ distinct source poses.
"""
from pathlib import Path
import hashlib
import json
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'apps/ios/assets/canopy-ui/backpack'

def encode(name):
    sheet = Image.open(ASSETS / f'{name}-poses.png').convert('RGBA')
    size = 224
    keys = []
    for i in range(36):
        x, y = i % 6, i // 6
        cell = sheet.crop((round(x*sheet.width/6), round(y*sheet.height/6),
                           round((x+1)*sheet.width/6), round((y+1)*sheet.height/6)))
        # Equal-cell crop and equal scale preserve the anchored camera.
        keys.append(np.asarray(cell.resize((size,size),Image.Resampling.LANCZOS),dtype=np.float32)/255)
    assert len({a.tobytes() for a in keys}) == 36
    gray = [cv2.cvtColor(np.uint8((a[:,:,:3]*a[:,:,3:]+(1-a[:,:,3:])*.94)*255),cv2.COLOR_RGB2GRAY) for a in keys]
    optical = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    grid = np.stack(np.meshgrid(np.arange(size,dtype=np.float32),np.arange(size,dtype=np.float32)),axis=-1)
    premul = [np.concatenate([a[:,:,:3]*a[:,:,3:],a[:,:,3:]],axis=2) for a in keys]
    frames = []
    for i in range(36):
        j = (i+1)%36
        forward = optical.calc(gray[i],gray[j],None)
        backward = optical.calc(gray[j],gray[i],None)
        for step in range(3):
            t = step/3
            a = cv2.remap(premul[i],grid-t*forward,None,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            b = cv2.remap(premul[j],grid-(1-t)*backward,None,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            rgba = (1-t)*a+t*b
            alpha = rgba[:,:,3:]
            rgb = np.divide(rgba[:,:,:3],alpha,out=np.zeros_like(rgba[:,:,:3]),where=alpha>1e-5)
            frames.append(Image.fromarray(np.uint8(np.clip(np.concatenate([rgb,alpha],axis=2),0,1)*255)))
    # One palette avoids color flicker. Index 255 is reserved for transparency.
    sample = Image.new('RGB',(size*6,size*6),'#EAF2E7')
    for i,frame in enumerate(frames[::3]):sample.paste(frame,(i%6*size,i//6*size),frame)
    palette = sample.quantize(colors=255,method=Image.Quantize.MEDIANCUT)
    encoded=[]
    for frame in frames:
        rgb=Image.new('RGB',frame.size,'#EAF2E7');rgb.paste(frame,mask=frame.getchannel('A'))
        indexed=rgb.quantize(palette=palette,dither=Image.Dither.NONE)
        indexed.paste(255,mask=frame.getchannel('A').point(lambda a:255 if a<110 else 0))
        encoded.append(indexed)
    frames[0].save(ASSETS/f'{name}-poster.png')
    out=ASSETS/f'{name}.gif'
    encoded[0].save(out,save_all=True,append_images=encoded[1:],duration=[30,30,40]*36,
                    loop=0,transparency=255,disposal=2,optimize=False)
    with Image.open(out) as check:
        hashes=[]
        for n in range(check.n_frames):
            check.seek(n);hashes.append(hashlib.sha256(check.convert('RGBA').tobytes()).hexdigest())
        report={'source_poses':36,'encoded_frames':check.n_frames,'unique_frames':len(set(hashes)),
                'seconds':3.6,'bytes':out.stat().st_size,'loop':check.info.get('loop')}
    assert report['encoded_frames']==108 and report['unique_frames']>=36
    return report

if __name__=='__main__':
    reports={name:encode(name) for name in ['wave','walk','celebrate']}
    (ASSETS/'manifest.json').write_text(json.dumps(reports,indent=2)+'\n')
    print(json.dumps(reports,indent=2))
