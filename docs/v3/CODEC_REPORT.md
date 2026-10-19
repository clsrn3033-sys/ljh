# V3 영상·RAW 지원과 검증 범위

Sony FX3는 [공식 사양](https://www.sony.com/electronics/support/camcorders-and-video-cameras-interchangeable-lens-camcorders/ilme-fx3/specifications)에 XAVC S(H.264), XAVC HS(H.265), XAVC S-I(All-Intra H.264), 4:2:2 10비트 녹화 모드가 명시된다. Pi4B [공식 데이터시트](https://pip-assets.raspberrypi.com/categories/545-raspberry-pi-4-model-b/documents/RP-008341-DS-1-raspberry-pi-4-datasheet.pdf?disposition=inline)는 H.264 1080p60 및 HEVC 4Kp60 하드웨어 디코더를 나열한다. 이 사양만으로 현재 Buildroot 커널·FFmpeg·DRM 경로에서 특정 FX3 4:2:2 10비트 파일이 하드웨어 재생된다고 판단할 수 없다.

V3는 [FFprobe 공식 문서](https://ffmpeg.org/ffprobe.html)의 JSON 스트림 정보에서 코덱, 프로필, 해상도, 픽셀 형식, 비트 심도, 프레임레이트, 비트레이트를 읽는다. XAVC 상품명이나 All-Intra 여부는 코덱 이름만으로 확정하지 않는다. MP4/MOV 영상은 FFmpeg로 첫 프레임 썸네일을 시도한다. RAW/ARW도 FFmpeg가 해독할 수 있을 때에만 썸네일을 표시하고, 실패 시 이름·크기·날짜를 표시한다. 기존 파일을 변경하지 않는다.

| 파일 특성 | V3 표시·재생 정책 | 현재 증거 |
|---|---|---|
| JPG/PNG 등 일반 이미지 | Pillow 축소 미리보기 | 호스트 시험 PASS, 최종 ARM64 QEMU JPG PASS. Buildroot JPEG+Pillow 재빌드 포함 |
| Sony RAW/ARW | 한 프레임 해독 시도, 실패하면 정보 표시 | 손상 가상 RAW의 실패 처리 PASS; 실제 Sony RAW NOT TESTED |
| MP4/MOV, H.264 8비트 4:2:0 ≤1080p | 정보·썸네일, 30초 무음 SW 미리보기 | 호스트 생성 H.264 클립 재생 PASS, ARM64 QEMU 생성 MPEG4 클립 분석·썸네일 PASS; Pi4 재생 HARDWARE NOT TESTED |
| H.264 4K/4:2:2 10비트 및 XAVC S-I | 정보·가능하면 썸네일, 재생 제한 | 4K 4:2:2 10비트 FFprobe JSON 모의 입력 PASS; 실제 FX3 파일 NOT TESTED |
| H.265/HEVC XAVC HS | 정보·가능하면 썸네일, 재생 제한 | 코덱 분류 모의 입력 PASS; Pi4 가속 HARDWARE NOT TESTED |

하드웨어 가속은 이미지에 포함되었다고 주장하지 않는다. Pi4에서 실제 4K·10비트 촬영 파일로 디코더/DRM 경로와 발열·전력·메모리를 측정하기 전까지 제한을 해제하지 않는다. Buildroot에서는 FFmpeg CLI와 FFprobe만 추가하고 FFplay/SDL/X11은 비활성화한다.
