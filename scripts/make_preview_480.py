from pathlib import Path
from mebs.runtime_ui_480 import render
p=Path(__file__).parent/'preview';p.mkdir(exist_ok=True)
base={'cpu_temp_c':52,'ram_percent':33,'uptime_seconds':3932,'total_bytes':100}
steps=[('READY',0,0),('WAITING_SOURCE',0,0),('CONNECTED',0,0),('COPYING',12,0),('COPYING',36,0),('COPYING',61,0),('COPYING',86,0),('COPYING',100,0),('VERIFYING',100,21),('VERIFYING',100,65),('VERIFYING',100,100),('COMPLETE',100,100),('UNMOUNTING',100,100),('SAFE_TO_REMOVE',100,100)]
frames=[]
for i,(state,copied,verified) in enumerate(steps):
    frame=render(dict(base,state=state,copied_bytes=copied,verified_bytes=verified))
    frame.save(p/f'{i:02d}-{state.lower()}.png')
    frames.append(frame)
frames[0].save(p/'runtime-480x320-final.gif',save_all=True,append_images=frames[1:],duration=[700,700,600]+[300]*8+[900,600,1400],loop=0,optimize=True,disposal=2)
print('GIF size:',(p/'runtime-480x320-final.gif').stat().st_size)