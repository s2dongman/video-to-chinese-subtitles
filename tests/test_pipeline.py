import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/subtitle_pipeline.py'
spec=importlib.util.spec_from_file_location('pipeline',SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
FONT=os.environ.get('SUBTITLE_TEST_FONT','Heiti SC' if sys.platform=='darwin' else 'Noto Sans CJK SC')


def data():
    return {'width':640,'height':360,'bottom_padding':48,'font':FONT,'cues':[
        {'id':'s','kind':'screen','start':.2,'end':1.8,'zh':'美好的一天','original_box':[100,310,540,335]},
        {'id':'v','kind':'voice','start':.3,'end':1.7,'zh':'这里真美。'}]}


class PipelineTests(unittest.TestCase):
    def test_invalid_geometry_and_time(self):
        for field,value in [('start',float('nan')),('end',0),('zh','')]:
            d=data();d['cues'][0][field]=value
            with self.assertRaises(ValueError):m.prepare(d)
        d=data();d['cues'][1]['y']=320
        with self.assertRaises(ValueError):m.prepare(d)
        d=data();d['cues'][1]['zh']='很长的字幕'*50
        with self.assertRaises(ValueError):m.prepare(d)
        d=data();d['cues'].append(dict(d['cues'][1],id='v2'))
        with self.assertRaises(ValueError):m.prepare(d)

    def test_portrait_multiline_and_text_controls(self):
        d={'width':720,'height':1280,'bottom_padding':170,'cues':[
            {'id':'v','kind':'voice','start':0,'end':2,'zh':'第一行\n第二行','y':1350}]}
        self.assertEqual(len(m.prepare(d)[-1]),1)
        self.assertNotIn('\\',m.clean('{\\pos(0,0)}'))

    def test_media_roundtrip_and_seek(self):
        with tempfile.TemporaryDirectory(prefix="字幕 test ' ") as t:
            p=Path(t);src=p/'source.mp4';bundle=p/'bundle'
            (p/'cues.json').write_text(json.dumps(data()),encoding='utf-8')
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=640x360:r=25:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-c:a','aac','-shortest',str(src)],check=True)
            def cli(*args):subprocess.run([sys.executable,str(SCRIPT),*map(str,args)],check=True,stdout=subprocess.DEVNULL)
            cli('build',p/'cues.json','--out',bundle)
            cli('render',src,bundle,p/'final.mp4')
            cli('verify',src,p/'final.mp4','--audio-copied')
            cli('render',src,bundle,p/'frame.png','--start',1,'--frame')
            cli('render',src,bundle,p/'clip.mp4','--start',1,'--duration',.5,'--audio','aac')
            def pixels(file,seek=0):
                return subprocess.check_output(['ffmpeg','-v','error','-ss',str(seek),'-i',str(file),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
            # Nonzero seek must show the same timed captions as the full render.
            still=pixels(p/'frame.png');full=pixels(p/'final.mp4',1);clip=pixels(p/'clip.mp4',0)
            def whites(raw):return sum(min(raw[i:i+3])>180 for i in range(0,len(raw),3))
            self.assertGreater(whites(still),50)
            self.assertLess(abs(whites(still)-whites(full)),whites(still)*.3)
            self.assertLess(abs(whites(still)-whites(clip)),whites(still)*.3)
            self.assertEqual(m.probe(p/'clip.mp4')['streams'][0]['width'],640)
            self.assertIn('这里真美',(bundle/'voice.zh-CN.srt').read_text())

if __name__=='__main__':unittest.main()
