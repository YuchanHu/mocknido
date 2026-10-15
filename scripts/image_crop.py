import numpy as np


def manual_crop(image, rectangle, aspect):
    if not isinstance(rectangle,dict):raise ValueError('请先选择并确认裁切区域')
    x,y,w,h=[float(rectangle[k]) for k in ('x','y','w','h')]
    if not np.all(np.isfinite([x,y,w,h])) or min(x,y)<-1e-7 or min(w,h)<=0 or x+w>1.000001 or y+h>1.000001:
        raise ValueError('裁切区域超出图片边界')
    iw,ih=image.size
    if abs((w*iw)/(h*ih)/aspect-1)>.004:
        raise ValueError('裁切比例已改变，请重新选择区域')
    return image.crop((x*iw,y*ih,(x+w)*iw,(y+h)*ih))
