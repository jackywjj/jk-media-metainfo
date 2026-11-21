import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('media', Path(__file__).parents[1] / 'scripts/media_metainfo.py')
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


class MP3DiscoveryTests(unittest.TestCase):
    def test_mixed_directory_includes_mp3(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            for name in ('one.JPG', 'two.MP4', 'three.MP3', 'ignore.wav'):
                (root / name).touch()
            files = media.expand_inputs([root])
            self.assertEqual(len(files), 3)
            self.assertEqual(media.media_type(root / 'three.MP3'), 'audio')


@unittest.skipUnless(importlib.util.find_spec('mutagen') and shutil.which('ffmpeg') and shutil.which('exiftool'),
                     'MP3 integration needs mutagen, ffmpeg (fixture only), exiftool')
class MP3IntegrationTests(unittest.TestCase):
    def setUp(self):
        from mutagen.id3 import APIC, ID3, TALB, TXXX, TIT2, COMM
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.src = self.root / '中文 sample.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=0.2', '-id3v2_version', '4', str(self.src)], check=True)
        tags = ID3(self.src)
        tags.add(TIT2(encoding=3, text=['旧标题']))
        tags.add(TALB(encoding=3, text=['保留专辑']))
        tags.add(TXXX(encoding=3, desc='replaygain_track_gain', text=['-1.0 dB']))
        tags.add(COMM(encoding=3, lang='zho', desc='备注', text=['保留中文评论']))
        tags.add(APIC(encoding=3, mime='image/png', type=3, desc='cover', data=b'original-cover-bytes'))
        tags.save(self.src, v1=0, v2_version=4)
        self.args = argparse.Namespace(exiftool=None)

    def job(self, src=None, dest='out.mp3', changes=None, remove=None, storage='embedded'):
        src = src or self.src
        return {'source': src, 'dest': self.root / dest, 'storage': storage,
                'set': changes or {'title': '新标题', 'creator': ['Jacky', '另一位作者'],
                                   'description': '测试说明', 'rights': '测试版权',
                                   'keywords': ['音频', '中文'], 'project': '项目'},
                'remove': remove or [], 'review': {'kind': 'audio', 'people_scope': 'none',
                    'basis': 'user', 'evidence': '本地合成测试音频', 'input_sha256': media.sha(src)}}

    def apply(self, job):
        plan = media.plan_job(job, self.args)
        self.assertTrue(plan['ready'], plan['issues'])
        return media.apply_job(job, plan, self.args)

    def test_write_read_remove_preserves_audio_and_other_tags(self):
        from mutagen.id3 import ID3
        original_hash = media.sha(self.src)
        job = self.job()
        self.assertEqual(self.apply(job)['status'], 'embedded_verified')
        metadata = media.inspect(job['dest'], self.args)['metadata']
        self.assertEqual(metadata, job['set'])
        tags = ID3(job['dest'])
        self.assertEqual(tags['TALB'].text, ['保留专辑'])
        self.assertEqual(tags['APIC:cover'].data, b'original-cover-bytes')
        self.assertEqual(tags['COMM:备注:zho'].text, ['保留中文评论'])
        self.assertEqual(media.sha(self.src), original_hash)
        second = self.job(src=job['dest'], dest='second.mp3', changes={'title': '二次标题'},
                          remove=['creator', 'keywords'])
        self.apply(second)
        metadata = media.inspect(second['dest'], self.args)['metadata']
        self.assertNotIn('creator', metadata)
        self.assertNotIn('keywords', metadata)
        self.assertEqual(metadata['project'], '项目')
        self.assertEqual(metadata['description'], '测试说明')

    def test_old_id3_and_id3v1_require_sidecar(self):
        from mutagen.id3 import ID3
        ID3(self.src).save(self.src, v1=0, v2_version=3)
        job = self.job()
        self.assertFalse(media.plan_job(job, self.args)['ready'])
        job = self.job(dest='old.mp3.metadata.json', storage='sidecar')
        self.assertEqual(self.apply(job)['status'], 'sidecar_saved')
        self.assertFalse(json.loads(job['dest'].read_text())['embedded'])
        ID3(self.src, translate=False).save(self.src, v1=0, v2_version=4)
        with self.src.open('ab') as handle:
            handle.write(b'TAG' + b'\0' * 125)
        self.assertFalse(media.plan_job(self.job(), self.args)['ready'])

    def test_signatures_detect_payload_cover_and_unrelated_tag_changes(self):
        from mutagen.id3 import ID3, TALB
        before = media.mp3_content(self.src, {'title': 'changed'}, [])
        tags = ID3(self.src)
        tags['APIC:cover'].data = b'changed-cover'
        tags.save(self.src, v1=0, v2_version=4)
        self.assertNotEqual(before, media.mp3_content(self.src, {'title': 'changed'}, []))
        before = media.mp3_content(self.src, {'title': 'changed'}, [])
        tags = ID3(self.src)
        tags.add(TALB(encoding=3, text=['changed album']))
        tags.save(self.src, v1=0, v2_version=4)
        self.assertNotEqual(before, media.mp3_content(self.src, {'title': 'changed'}, []))
        before = media.mp3_content(self.src, {'title': 'changed'}, [])
        with self.src.open('ab') as handle:
            handle.write(b'unexpected-payload')
        self.assertNotEqual(before, media.mp3_content(self.src, {'title': 'changed'}, []))

    def test_untagged_mp3_and_cli(self):
        import sys
        from mutagen.id3 import delete
        delete(self.src, delete_v1=True, delete_v2=True)
        self.assertEqual(self.apply(self.job())['status'], 'embedded_verified')
        script = Path(__file__).parents[1] / 'scripts/media_metainfo.py'
        config = self.root / 'config.json'
        job = self.job(dest='cli.mp3')
        config.write_text(json.dumps({'version': 1, 'inputs': [str(self.src)],
                                     'output_dir': str(self.root / 'cli'), 'set': job['set'],
                                     'review': job['review']}), encoding='utf-8')
        for command, arg in [('precheck', self.src), ('plan', config), ('apply', config)]:
            result = subprocess.run([sys.executable, str(script), command, str(arg)],
                                    capture_output=True, text=True, check=True)
            report = json.loads(result.stdout)
            if command == 'precheck':
                self.assertFalse(report['visual_review_required'])
            elif command == 'apply':
                self.assertEqual(report['results'][0]['status'], 'embedded_verified')
                self.assertTrue(report['runtime']['capabilities']['mp3_embedded'])

    def test_audio_review_and_depicted_people_blocked(self):
        job = self.job(changes={'depicted_real_people': ['someone']})
        self.assertFalse(media.plan_job(job, self.args)['ready'])
        job = self.job()
        job['review']['kind'] = 'photo'
        job['review']['people_scope'] = 'real'
        self.assertFalse(media.plan_job(job, self.args)['ready'])


if __name__ == '__main__':
    unittest.main()
