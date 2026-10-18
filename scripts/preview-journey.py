#!/usr/bin/env python3
"""Offline playback from real renderers and touch controls, all events simulated.

No device discovery, mounts, backup files, clock changes or shutdown. Preview
frame durations are editorial playback durations, not measured boot timing.
"""
from datetime import datetime
import argparse
import base64
import json
from pathlib import Path
import tempfile
from PIL import Image, ImageDraw
from mebs import boot_animation
from mebs.controls import Controls
from mebs.display import font
from mebs.sensors import Reading
from mebs.settings import SettingsStore
from mebs.ui800 import render


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('artifacts/boot-menu-preview'))
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    timeline=[];animation=[];durations=[];keyframes=[]
    def mark(image):
        image=image.copy()
        d=ImageDraw.Draw(image)
        d.rectangle((0,462,799,479),fill='black')
        d.text((400,464),'PREVIEW · 모의 데이터 / 실제 부팅 시간 아님',font=font(11),fill='#7294af',anchor='mt')
        return image
    def boot_frame(pct,opacity=1,state='boot',caption='Initializing system...'):
        source=boot_animation.render(pct,opacity=opacity,state=state,caption=caption)
        image=Image.new('RGB',(800,480),'black')
        image.paste(source.resize((800,450),Image.Resampling.LANCZOS),(0,15))
        return mark(image)
    def add(name,title,image,duration=1400,key=True,animate=True):
        assert image.size==(800,480) and image.mode=='RGB'
        filename=name+'.png';image.save(out/filename)
        timeline.append({'name':name,'title':title,'file':filename,'duration_ms':duration})
        if animate:
            animation.append(image);durations.append(duration)
        if key:keyframes.append((image,title))
    # Uses upstream stage/frame logic with deliberately simulated ready checks.
    boot_samples=list(boot_animation.frames([True]*5,steps=4))
    for i,(pct,opacity,state,caption) in enumerate(boot_samples):
        image=boot_frame(pct,opacity,state,caption)
        animation.append(image);durations.append(120)
    add('01-boot','01 부팅 · 원본 로고와 진행 게이지',boot_frame(78),600,animate=False)
    add('02-boot-ready','02 준비 완료 · 메인 화면으로 전환',boot_frame(100,state='ready'),1000)
    with tempfile.TemporaryDirectory() as temp:
        c=Controls(SettingsStore(Path(temp)/'settings.json'))
        c.reading=Reading(cpu_c=46,voltage=7.6,current_a=.8,percent=65)
        now=datetime(2026,10,18,9,0)
        def screen():return mark(render(c,now=now))
        def state(phase,**values):
            c.update(dict(state=phase,demo=True,**values))
        state('READY')
        add('03-main','03 메인 · 외장 저장장치 먼저 연결',screen())
        state('WAITING_SOURCE',target_connected=True)
        add('04-storage','04 STORAGE READY · 원본 SD 연결 대기',screen())
        connected=dict(source_connected=True,target_connected=True,total_files=120,total_bytes=1024**3,free_bytes=64*1024**3)
        state('SCANNING',**connected)
        add('05-scan','05 SD READY · 원본 파일 확인',screen(),900)
        c.begin_job()
        progress=dict(connected,copied_bytes=640*1024**2,verified_files=70,current_file='DCIM/100MEDIA/CLIP_0042.MOV')
        state('COPYING',**progress)
        add('06-copy','06 자동 백업 · 구조 보존 및 복사',screen())
        assert c.gesture((400,5),(400,150),.4)=='open'
        add('07-settings','07 상단 스와이프 · 백업 중 빠른 설정',screen(),1800)
        assert c.worker_active
        c.gesture((400,130),(400,130),.1)
        c.tick()
        add('08-brightness','08 수동 밝기 조절 · 백업 계속',screen(),1100,key=False)
        c.gesture((750,30),(750,30),.1)
        assert c.confirm_power
        add('09-power','09 전원 선택 · 완료 후 종료 확인',screen(),1800)
        c.gesture((550,290),(550,290),.1)
        assert c.shutdown_pending and not c.shutdown_ready()
        c.gesture((400,360),(400,150),.4)
        add('10-queued','10 종료 예약 · 복사와 검증 계속',screen(),1500)
        state('VERIFYING',**progress)
        add('11-verify','11 SHA-256 검증',screen(),1100,key=False)
        state('FINAL_CHECK',**dict(progress,copied_bytes=1024**3,verified_files=120))
        add('12-final','12 독립 최종 검증',screen(),1000,key=False)
        c.finish_job(dict(state='SAFE_TO_REMOVE',demo=True,safe_to_remove=True,**dict(progress,copied_bytes=1024**3,verified_files=120,current_file='')))
        assert c.shutdown_ready()
        add('13-complete','13 검증·분리 완료 · 예약된 안전 종료 직전',screen(),2200)
    animation[0].save(out/'boot-to-menu.gif',save_all=True,append_images=animation[1:],duration=durations,loop=0,optimize=True)
    # Compact storyboard with essential transitions.
    chosen=[keyframes[i] for i in (0,2,3,4,5,6,7,9)]
    w,h=600,360
    board=Image.new('RGB',(1200,4*408+54),'#080d14');d=ImageDraw.Draw(board)
    d.text((20,14),'MEBS · 부팅 → 메인 → 설정 → 종료 예약 / 모의 프리뷰',font=font(22),fill='#8edfff')
    for i,(image,title) in enumerate(chosen):
        x=i%2*w;y=54+i//2*408
        d.text((x+12,y+8),title,font=font(17),fill='#e9f0f9')
        board.paste(image.resize((w,h),Image.Resampling.LANCZOS),(x,y+40))
    board.save(out/'storyboard.jpg')
    # Self-contained offline player, no web service or external dependency.
    slides=[]
    for entry in timeline:
        raw=(out/entry['file']).read_bytes()
        slides.append(dict(entry,image='data:image/png;base64,'+base64.b64encode(raw).decode()))
    html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>MEBS 부팅·메뉴 프리뷰</title>
<style>body{margin:0;background:#05090f;color:#eaf3fc;font:16px system-ui;text-align:center}main{max-width:880px;margin:auto;padding:20px}img{width:100%;max-width:800px;border:1px solid #233548;border-radius:12px}button{background:#102235;color:#a9eaff;border:1px solid #35536d;border-radius:8px;padding:12px;margin:4px;cursor:pointer}button[aria-pressed=true]{background:#164a61}p{color:#8da8bf}nav{margin:12px}small{display:block;color:#8da8bf}</style>
<main><h2>MEBS 부팅 → 메인 메뉴</h2><p>실제 UI 렌더러 · 모의 데이터 · 부팅·하드웨어 검증 영상 아님</p><img id="screen" alt="MEBS 프리뷰"><h3 id="label"></h3><nav><button id="prev">이전</button><button id="play">자동 재생</button><button id="next">다음</button></nav><section id="events"></section><p>설정창은 상단 스와이프, 전원은 완료 후 종료 예약 흐름입니다.</p><small>여기의 버튼은 프리뷰 장면만 바꿉니다. 디스크 접근·복사·전원 종료를 실행하지 않습니다.</small></main><script>
const slides=__SLIDES__;let index=0,timer=null;const screen=document.getElementById('screen'),label=document.getElementById('label');
function show(n){index=(n+slides.length)%slides.length;screen.src=slides[index].image;label.textContent=slides[index].title;document.querySelectorAll('#events button').forEach((b,i)=>b.setAttribute('aria-pressed',i===index?'true':'false'));}
slides.forEach((s,i)=>{const b=document.createElement('button');b.textContent=s.title;b.onclick=()=>show(i);document.getElementById('events').appendChild(b)});
document.getElementById('prev').onclick=()=>show(index-1);document.getElementById('next').onclick=()=>show(index+1);
document.getElementById('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;document.getElementById('play').textContent='자동 재생'}else{timer=setInterval(()=>show(index+1),1600);document.getElementById('play').textContent='일시 정지'}};
document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')show(index-1);if(e.key==='ArrowRight')show(index+1)});show(0);
</script></html>'''.replace('__SLIDES__',json.dumps(slides,ensure_ascii=False))
    (out/'preview.html').write_text(html)
    report={'simulation':True,'renderer':'existing boot_animation + ui800 + Controls gestures','logo_source':boot_animation.logo_asset().source,'actual_boot_time_measured':False,'hardware_tested':False,'image_size':[800,480],'animation_frames':len(animation),'timeline':timeline,'scope':'UI playback only; no OS image build or physical poweroff'}
    (out/'preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Preview:',out,'frames:',len(animation),'key scenes:',len(timeline))


if __name__=='__main__':main()
