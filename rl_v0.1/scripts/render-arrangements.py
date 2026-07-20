import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent.parent
OUTPUT=ROOT/'outputs'/'best-arrangements'
REPORT=json.loads((OUTPUT/'evaluation.json').read_text())
SCALE=2
WIDTH,HEIGHT=1600*SCALE,1100*SCALE
PANEL=390*SCALE
MARGIN=80*SCALE
COLORS={'room':'#d8dfd6','corridor':'#e4cf87','core':'#c9816d'}

def font(size,bold=False):
    candidates=[
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/System/Library/Fonts/SFNS.ttf'
    ]
    for candidate in candidates:
        if Path(candidate).exists(): return ImageFont.truetype(candidate,size*SCALE)
    return ImageFont.load_default()

def bounds(points):
    xs=[p['x'] for p in points];ys=[p['y'] for p in points]
    return min(xs),min(ys),max(xs),max(ys)

def render(plan,index):
    image=Image.new('RGB',(WIDTH,HEIGHT),'#f3f1eb')
    draw=ImageDraw.Draw(image)
    outer=plan['site']['outer']
    min_x,min_y,max_x,max_y=bounds(outer)
    plot_w=WIDTH-PANEL-2*MARGIN;plot_h=HEIGHT-2*MARGIN
    world_w=max_x-min_x;world_h=max_y-min_y
    scale=min(plot_w/world_w,plot_h/world_h)
    offset_x=MARGIN+(plot_w-world_w*scale)/2-min_x*scale
    offset_y=MARGIN+(plot_h-world_h*scale)/2-min_y*scale
    def point(p): return (round(offset_x+p['x']*scale),round(offset_y+p['y']*scale))
    def polygon(poly): return [point(p) for p in poly]

    grid_step=max(12*SCALE,round(scale*2))
    for x in range(0,WIDTH-PANEL,grid_step): draw.line((x,0,x,HEIGHT),fill='#e6e4dd',width=1)
    for y in range(0,HEIGHT,grid_step): draw.line((0,y,WIDTH-PANEL,y),fill='#e6e4dd',width=1)

    outer_px=polygon(outer)
    draw.polygon(outer_px,fill='#faf9f5')
    for hole in plan['site']['holes']:
        hp=polygon(hole);draw.polygon(hp,fill='#b8d3d8')
        bx0,by0,bx1,by1=(*bounds(hole)[:2],*bounds(hole)[2:])
        x0,y0=point({'x':bx0,'y':by0});x1,y1=point({'x':bx1,'y':by1})
        for x in range(x0-(y1-y0),x1,12*SCALE): draw.line((x,y0,x+(y1-y0),y1),fill='#8eb9c1',width=1*SCALE)

    for placement in plan['placements']:
        poly=polygon(placement['poly']);category=placement['module']['category'];family=placement['module']['family']
        draw.polygon(poly,fill=COLORS[category],outline='#343930',width=1*SCALE)
        if family=='sheared': draw.polygon(poly,fill='#c5d3c5' if category=='room' else '#d5bb63',outline='#343930',width=1*SCALE)
        center=point(placement['center'])
        label=placement['module']['id']
        box=draw.textbbox((0,0),label,font=font(7,bold=True));tw=box[2]-box[0];th=box[3]-box[1]
        draw.text((center[0]-tw/2,center[1]-th/2),label,font=font(7,bold=True),fill='#252a22')
        if category=='corridor':
            angle=math.radians(placement['rotation']);length=math.sqrt(placement['module']['area'])*scale*.6
            a=(center[0]-math.cos(angle)*length,center[1]-math.sin(angle)*length)
            b=(center[0]+math.cos(angle)*length,center[1]+math.sin(angle)*length)
            segments=8
            for segment in range(0,segments,2):
                t0=segment/segments;t1=(segment+1)/segments
                draw.line((a[0]+(b[0]-a[0])*t0,a[1]+(b[1]-a[1])*t0,a[0]+(b[0]-a[0])*t1,a[1]+(b[1]-a[1])*t1),fill='#675822',width=1*SCALE)

    draw.line(outer_px+[outer_px[0]],fill='#171a16',width=3*SCALE,joint='curve')
    for hole in plan['site']['holes']:
        hp=polygon(hole);draw.line(hp+[hp[0]],fill='#4b747b',width=2*SCALE)

    panel_x=WIDTH-PANEL
    draw.rectangle((panel_x,0,WIDTH,HEIGHT),fill='#faf9f5')
    draw.line((panel_x,0,panel_x,HEIGHT),fill='#9fa198',width=1*SCALE)
    x=panel_x+34*SCALE;y=42*SCALE
    draw.text((x,y),f"ARRANGEMENT {index:02d}",font=font(11,bold=True),fill='#171a16');y+=30*SCALE
    draw.text((x,y),f"{plan['score']:.1f}",font=font(42,bold=True),fill='#171a16');
    draw.text((x+128*SCALE,y+35*SCALE),'/ 100',font=font(11),fill='#6e7169');y+=78*SCALE
    draw.text((x,y),f"SEED {plan['seed']}  ·  EPISODE {plan['episode']}",font=font(9),fill='#6e7169');y+=42*SCALE
    metrics=plan['metrics']
    rows=[
        ('NET FILL',metrics['fillRatio']),('CIRCULATION',metrics['circulationQuality']),
        ('ORIENTATION',metrics['orientationQuality']),('NOVELTY',metrics['spatialNovelty']),
        ('REGULARITY',metrics['regularity']),('DAYLIGHT',metrics['daylight']),
        ('ATRIUM USE',metrics['atriumUse']),('REUSE',metrics['reuse'])
    ]
    for label,value in rows:
        draw.text((x,y),label,font=font(8,bold=True),fill='#555a52')
        draw.text((x+275*SCALE,y),f"{value*100:.0f}%",font=font(8,bold=True),fill='#171a16')
        y+=18*SCALE
        draw.rectangle((x,y,x+310*SCALE,y+4*SCALE),fill='#deddd6')
        draw.rectangle((x,y,x+310*SCALE*max(0,min(1,value)),y+4*SCALE),fill='#718531')
        y+=24*SCALE
    y+=14*SCALE
    facts=[('MODULES',str(metrics['moduleCount'])),('DICTIONARY',str(metrics['dictionaryUsed'])),('REFLEX VERTICES',str(plan['site']['reflexVertices'])),('CONVEXITY',f"{plan['site']['convexityRatio']:.2f}"),('BASIS',f"{plan['orientationBasis']}°")]
    for label,value in facts:
        draw.text((x,y),label,font=font(8),fill='#6e7169');draw.text((x+220*SCALE,y),value,font=font(9,bold=True),fill='#171a16');y+=26*SCALE

    bar_y=HEIGHT-60*SCALE;bar_x=MARGIN
    metres=10;bar_w=metres*scale
    for segment in range(5):
        xa=bar_x+bar_w*segment/5;xb=bar_x+bar_w*(segment+1)/5
        draw.rectangle((xa,bar_y,xb,bar_y+7*SCALE),fill='#171a16' if segment%2==0 else '#faf9f5',outline='#171a16',width=1*SCALE)
    draw.text((bar_x,bar_y+12*SCALE),'0',font=font(7),fill='#171a16')
    draw.text((bar_x+bar_w-22*SCALE,bar_y+12*SCALE),'10 m',font=font(7),fill='#171a16')

    image.resize((WIDTH//SCALE,HEIGHT//SCALE),Image.Resampling.LANCZOS).save(OUTPUT/f'arrangement-{index:02d}.png')

for index,plan in enumerate(REPORT['selected'],1): render(plan,index)
shutil.copyfile(OUTPUT/'arrangement-02.png',OUTPUT/'selected-nicest.png')
print(f"rendered {len(REPORT['selected'])} arrangements to {OUTPUT}")
