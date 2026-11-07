#!/bin/bash
# Generates full-HD abstract B-roll into assets/broll/<category>/ with ffmpeg (no downloads, no licensing).
# Run from the pipeline root:  bash scripts/generate-broll.sh
cd "/Users/ashu/Desktop/Desktop - Ashutosh's MacBook Air/Desktop - Ashutosh’s MacBook Air/UI_UX_Projects/video-pipeline"
enc=(-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30 -movflags +faststart)
g(){ echo ">> $2"; ffmpeg -hide_banner -loglevel error -y -f lavfi -i "$1" -t "${3:-7}" "${enc[@]}" "$2"; }
# gradients (animated multi-colour sweeps)
g "gradients=s=1920x1080:d=7:speed=0.012:c0=0x0a2a6c:c1=0xb21f1f:c2=0xfdbb2d:x0=0:y0=0:x1=1920:y1=1080" assets/broll/gradient/gradient-warm.mp4
g "gradients=s=1920x1080:d=7:speed=0.012:c0=0x0f2027:c1=0x203a43:c2=0x2c5364" assets/broll/gradient/gradient-cool.mp4
g "gradients=s=1920x1080:d=7:speed=0.010:c0=0x111113:c1=0x1d1d20:c2=0x3a3a3e" assets/broll/gradient/gradient-mono.mp4
# fractal (slow mandelbrot zoom)
g "mandelbrot=s=1920x1080:rate=30:maxiter=400" assets/broll/fractal/mandelbrot-zoom.mp4 8
# particles (game-of-life fields, tinted)
g "life=s=1920x1080:rate=30:ratio=0.08:life_color=0x3b82f6:death_color=0x0a0a0b:mold=12" assets/broll/particles/cells-blue.mp4
g "life=s=1920x1080:rate=30:ratio=0.08:life_color=0xe00219:death_color=0x0a0a0b:mold=12" assets/broll/particles/cells-red.mp4
# abstract (soft moving noise -> clouds/bokeh texture)
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "nullsrc=s=1920x1080:r=30" -vf "format=gray,noise=alls=40:allf=t,gblur=sigma=22,eq=contrast=1.6:brightness=-0.1,colorbalance=rs=0.2:bs=0.3,format=yuv420p" -t 7 "${enc[@]}" assets/broll/abstract/soft-bokeh.mp4
echo "=== generated ===" ; find assets/broll -name "*.mp4" -exec sh -c 'printf "%s  " "$1"; ffprobe -v error -show_entries stream=width,height -of csv=p=0 "$1"' _ {} \;
