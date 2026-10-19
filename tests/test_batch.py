import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('media', Path(__file__).parents[1] / 'scripts/media_metainfo.py')
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


class BatchTests(unittest.TestCase):
    def test_limit_and_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / 'ignore.txt').touch()
            (root / 'nested').mkdir()
            (root / 'nested/hidden.jpg').touch()
            for i in range(512):
                (root / f'{i:03d}.JPG').touch()
            self.assertEqual(len(media.expand_inputs([root])), 512)
            (root / 'extra.MP4').touch()
            with self.assertRaises(media.Refused):
                media.expand_inputs([root])

    def test_duplicates_and_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            with self.assertRaises(media.Refused):
                media.expand_inputs([root])
            file = root / 'space 图片.png'
            file.touch()
            self.assertEqual(media.expand_inputs([file]), [file])
            with self.assertRaises(media.Refused):
                media.expand_inputs([root, file])

    def test_config_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / 'media').mkdir()
            file = root / 'media/one.mp4'
            file.touch()
            config = root / 'config.json'
            config.write_text(json.dumps({'version': 1, 'inputs': ['./media'],
                                         'storage': 'sidecar', 'set': {'title': 'test'},
                                         'per_file': [{'path': './media/one.mp4', 'review': {}}]}))
            jobs = media.load_config(config)
            self.assertEqual(jobs[0]['source'], file)
            self.assertEqual(jobs[0]['dest'], root / 'output/one.mp4.metadata.json')


if __name__ == '__main__':
    unittest.main()
