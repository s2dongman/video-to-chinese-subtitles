#!/usr/bin/env python3
"""Compile reviewed cues, render previews/full video, and check media integrity."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unicodedata


def run(args, **kw):
    return subprocess.run(args, check=True, **kw)


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Expected a finite number')
    return value


def stamp(seconds, ass=False):
    scale = 100 if ass else 1000
    ticks = round(seconds * scale)
    hours, ticks = divmod(ticks, 3600 * scale)
    minutes, ticks = divmod(ticks, 60 * scale)
    sec, frac = divmod(ticks, scale)
    return (f'{hours}:{minutes:02}:{sec:02}.{frac:02}' if ass else
            f'{hours:02}:{minutes:02}:{sec:02},{frac:03}')


def clean(text):
    return text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\r', '')


def intersects(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def prepare(data):
    w, h = data['width'], data['height']
    padding = data.get('bottom_padding', round(h * 144 / 1080 / 2) * 2)
    for v in (w, h, padding):
        if type(v) is not int or v < 0:
            raise ValueError('Dimensions/padding must be nonnegative integers')
    if not w or not h or w % 2 or (h + padding) % 2:
        raise ValueError('Require positive, even output dimensions')
    scale = h / 1080
    font = data.get('font', 'Noto Sans CJK SC')
    if not font or any(c in font for c in ',\r\n'):
        raise ValueError('Invalid font family')
    rows, ids = [], set()
    for src in data['cues']:
        c = dict(src)
        if not isinstance(c['id'], str) or not c['id'] or c['id'] in ids:
            raise ValueError('Cue IDs must be unique nonempty strings')
        ids.add(c['id'])
        if c['kind'] not in ('voice', 'screen'):
            raise ValueError(f"{c['id']}: invalid kind")
        start, end = number(c['start']), number(c['end'])
        if start < 0 or end <= start or round(end * 100) <= round(start * 100):
            raise ValueError(f"{c['id']}: invalid or sub-centisecond duration")
        if not isinstance(c['zh'], str) or not c['zh'].strip():
            raise ValueError(f"{c['id']}: empty translation")
        c['zh'] = clean(c['zh']).strip()
        size = number(c.get('font_size', data.get(c['kind'] + '_size', 45 if c['kind'] == 'voice' else 46) * scale))
        if size <= 0:
            raise ValueError('Font size must be positive')
        box = c.get('original_box')
        if box is not None:
            if len(box) != 4:
                raise ValueError('Invalid original_box')
            x0,y0,x1,y1 = map(number, box)
            if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
                raise ValueError(f"{c['id']}: original_box outside source")
        if c['kind'] == 'screen' and box is None and not ('x' in c and 'y' in c):
            raise ValueError(f"{c['id']}: screen cue needs original_box or x,y")
        x = number(c.get('x', (box[0] + box[2])/2 if box else w/2))
        y = number(c.get('y', box[1] - 26*scale if c['kind'] == 'screen' and box else h*1048/1080))
        lines = c['zh'].split('\n')
        def units(s):
            return sum(0 if unicodedata.combining(ch) else 1 if unicodedata.east_asian_width(ch) in 'WF' else .6 for ch in s)
        tw = max(map(units, lines))*size + 16*scale
        th = len(lines)*size*1.15 + 16*scale
        bounds = [x-tw/2, y-th if c['kind']=='screen' else y-th/2, x+tw/2,
                  y if c['kind']=='screen' else y+th/2]
        if bounds[0]<0 or bounds[1]<0 or bounds[2]>w or bounds[3]>h+padding:
            raise ValueError(f"{c['id']}: estimated text outside output; wrap/reposition")
        c.update(size=size, x=x, y=y, bounds=bounds)
        rows.append(c)
    rows.sort(key=lambda c:(c['start'], c['end']))
    for i,c in enumerate(rows):
        for d in rows[i+1:]:
            if d['start'] >= c['end']:
                break
            if c['kind']==d['kind']=='voice':
                raise ValueError(f"Overlapping voice times: {c['id']}, {d['id']}")
            if intersects(c['bounds'], d['bounds']):
                raise ValueError(f"Estimated translated boxes overlap: {c['id']}, {d['id']}")
        for d in rows:
            if c['start'] < d['end'] and d['start'] < c['end'] and d.get('original_box') and intersects(c['bounds'],d['original_box']):
                raise ValueError(f"{c['id']}: estimated translation overlaps original {d['id']}")
    if not rows:
        raise ValueError('No cues; do not silently produce an untranslated video')
    return w,h,padding,font,scale,rows


def build(args):
    data = json.loads(Path(args.cues).read_text(encoding='utf-8'))
    w,h,pad,font,scale,rows = prepare(data)
    out = Path(args.out);out.mkdir(parents=True, exist_ok=True)
    header = f'[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h+pad}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n'
    header += 'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
    for name,align,color in [('Voice',5,'&H00000000'),('Screen',2,'&H0000D7FF')]:
        for box in (True,False):
            style = name+'Box' if box else name
            primary = '&HFF000000' if box else '&H00FFFFFF'
            outline = '&H18000000' if box else color
            header += f'Style: {style},{font},45,{primary},&H00FFFFFF,{outline},&H18000000,0,0,0,0,100,100,0,0,{3 if box else 1},{(8 if box else 1.6)*scale:g},0,{align},0,0,0,1\n'
    header += '\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    events=[]
    for c in rows:
        style=c['kind'].title()
        text='{\\pos(%g,%g)\\fs%g}'%(c['x'],c['y'],c['size'])+c['zh'].replace('\n','\\N')
        for layer,suffix in [(0,'Box'),(1,'')]:
            events.append(f"Dialogue: {layer},{stamp(c['start'],True)},{stamp(c['end'],True)},{style}{suffix},,0,0,0,,{text}")
    (out/'subtitles.ass').write_text(header+'\n'.join(events)+'\n',encoding='utf-8')
    for kind in ('voice','screen'):
        subset=[c for c in rows if c['kind']==kind]
        (out/f'{kind}.zh-CN.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['zh']}" for i,c in enumerate(subset))+'\n',encoding='utf-8')
    manifest={'width':w,'source_height':h,'height':h+pad,'bottom_padding':pad,'font':font,'count':len(rows),'max_end':max(c['end'] for c in rows),'cues':rows,'geometry_check':'estimated; actual rendered inspection required'}
    (out/'layout.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'count':len(rows),'output':str(out)},ensure_ascii=False))


def render(args):
    src=Path(args.source).resolve();bundle=Path(args.bundle).resolve();output=Path(args.output).resolve()
    if output==src:
        raise ValueError('Refusing to overwrite source')
    if output.exists():
        raise ValueError('Output exists; choose a new filename')
    m=json.loads((bundle/'layout.json').read_text(encoding='utf-8'))
    p=probe(src);v=next(s for s in p['streams'] if s['codec_type']=='video')
    if (v['width'],v['height'])!=(m['width'],m['source_height']):
        raise ValueError('Source dimensions differ; normalize rotation/display dimensions first')
    if any(s.get('rotation',0) for s in v.get('side_data_list',[])) or int(v.get('tags',{}).get('rotate',0)):
        raise ValueError('Normalize rotation before rendering')
    if m['max_end']>float(p['format']['duration'])+.05:
        raise ValueError('Cues exceed source duration')
    start=number(args.start)
    if start<0 or start>=float(p['format']['duration']):
        raise ValueError('Invalid preview start')
    if args.duration is not None and args.duration<=0:
        raise ValueError('Duration must be positive')
    output.parent.mkdir(parents=True,exist_ok=True)
    # Copy to a simple temporary name: user paths never enter FFmpeg filter syntax.
    with tempfile.TemporaryDirectory(prefix='subtitle-render-') as temp:
        shutil.copyfile(bundle/'subtitles.ass',Path(temp)/'captions.ass')
        vf=f'settb=AVTB,setpts=PTS+{start}/TB,pad={m["width"]}:{m["height"]}:0:0:color=0x101114,subtitles=captions.ass,setpts=PTS-STARTPTS'
        cmd=['ffmpeg','-hide_banner','-v','error','-n','-ss',str(start),'-i',str(src),'-map','0:v:0']
        if args.frame:
            cmd += ['-vf',vf,'-frames:v','1','-update','1',str(output)]
        else:
            cmd += ['-map','0:a:0?','-vf',vf,'-c:v','libx264','-crf',str(args.crf),'-preset','fast','-pix_fmt','yuv420p','-fps_mode','passthrough','-c:a',args.audio]
            if args.audio=='aac': cmd += ['-b:a','192k']
            if args.duration is not None:cmd += ['-t',str(args.duration)]
            cmd += ['-movflags','+faststart',str(output)]
        run(cmd,cwd=temp)
    print(output)


def audio_hash(path):
    return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-']).decode().strip()


def verify(args):
    src=probe(args.source);out=probe(args.output)
    v=next(s for s in out['streams'] if s['codec_type']=='video')
    sv=next(s for s in src['streams'] if s['codec_type']=='video')
    sa=[s for s in src['streams'] if s['codec_type']=='audio'];oa=[s for s in out['streams'] if s['codec_type']=='audio']
    if abs(float(src['format']['duration'])-float(out['format']['duration']))>args.tolerance:
        raise ValueError('Source/output duration mismatch')
    if bool(sa)!=bool(oa):raise ValueError('Audio missing or unexpectedly added')
    frames='unavailable'
    if sv.get('nb_frames') and v.get('nb_frames'):
        if sv['nb_frames']!=v['nb_frames']:raise ValueError('Frame count mismatch')
        frames='equal'
    if oa:
        if abs(float(oa[0].get('start_time',0))-float(v.get('start_time',0)))>args.tolerance:
            raise ValueError('Output audio/video start offset')
        if oa[0].get('duration') and v.get('duration') and abs(float(oa[0]['duration'])-float(v['duration']))>args.tolerance:
            raise ValueError('Output audio/video duration mismatch')
    if args.audio_copied and sa and audio_hash(args.source)!=audio_hash(args.output):
        raise ValueError('Copied audio hash differs')
    run(['ffmpeg','-v','error','-xerror','-i',args.output,'-f','null','-'])
    report={'duration':out['format']['duration'],'resolution':[v['width'],v['height']],'frames':frames,'full_decode':'passed','audio_hash_equal':bool(args.audio_copied and sa),'translation_and_visual_review':'not checked by this command'}
    if args.report:Path(args.report).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(required=True)
    b=sub.add_parser('build');b.add_argument('cues');b.add_argument('--out',required=True);b.set_defaults(func=build)
    r=sub.add_parser('render');r.add_argument('source');r.add_argument('bundle');r.add_argument('output');r.add_argument('--start',type=float,default=0);r.add_argument('--duration',type=float);r.add_argument('--frame',action='store_true');r.add_argument('--audio',choices=['copy','aac'],default='copy');r.add_argument('--crf',type=int,default=19);r.set_defaults(func=render)
    v=sub.add_parser('verify');v.add_argument('source');v.add_argument('output');v.add_argument('--audio-copied',action='store_true');v.add_argument('--tolerance',type=float,default=.15);v.add_argument('--report');v.set_defaults(func=verify)
    args=p.parse_args();args.func(args)

if __name__=='__main__':
    main()
