import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from premium import audit_lesson, publishing_kit, scene, short_ranges
from studio import ROOT, FFMPEG, export_video, run


class PremiumTests(unittest.TestCase):
    def setUp(self):
        self.lesson = json.loads((ROOT/'sample_lesson.json').read_text(encoding='utf-8'))

    def test_short_selection_preserves_turns_and_never_overlaps(self):
        lesson = copy.deepcopy(self.lesson)
        lesson['lines'] *= 10
        durations = [5.5] * len(lesson['lines'])
        clips = short_ranges(lesson, durations)
        self.assertEqual(len(clips), 3)
        used = set()
        for clip in clips:
            indexes = set(range(clip['start'], clip['stop']))
            self.assertFalse(indexes & used)
            used |= indexes
            self.assertLessEqual(clip['duration'], 58)
            self.assertAlmostEqual(sum(durations[clip['start']:clip['stop']]), clip['duration'])
        self.assertEqual(short_ranges(self.lesson, [90]*4), [])

    def test_checks_flag_duplicate_and_non_chinese_lines(self):
        self.lesson['lines'][1] = copy.deepcopy(self.lesson['lines'][0])
        self.lesson['lines'][2]['zh'] = 'Hello'
        report = audit_lesson(self.lesson)
        self.assertTrue(any('trùng' in text for text in report['warnings']))
        self.assertTrue(any('chưa có chữ Hán' in text for text in report['warnings']))

    def test_publishing_kit_is_local_and_does_not_store_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            options = {'eleven_key': 'secret-do-not-publish', 'brand': 'Test channel'}
            with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
                publishing_kit(self.lesson, folder, options)
            for path in Path(folder).glob('*.json'):
                self.assertNotIn('secret-do-not-publish', path.read_text(encoding='utf-8'))
            self.assertEqual(len(list(Path(folder).glob('thumbnail_*.jpg'))), 3)
            self.assertTrue((Path(folder)/'content_plan.csv').exists())
            self.assertEqual(scene(self.lesson, 0, options, portrait=True).size, (1080, 1920))

    def test_full_export_and_reexport_reuse_audio_without_tts(self):
        self.lesson['lines'] = self.lesson['lines'][:2]
        def fake_speech(text, voice, speed, target, cancel, api_key, model, **kwargs):
            with wave.open(str(target), 'wb') as wav:
                wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\0\0' * 12000)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            options = {'premium': True, 'shorts': True, 'resolution': '720p',
                       'voices': ['voice1', 'voice2'], 'eleven_key': 'test-secret',
                       'audio_cache': base/'cache'}
            with patch('studio.speech', side_effect=fake_speech) as tts:
                export_video(self.lesson, base/'first', options)
                self.assertEqual(tts.call_count, 2)
            with patch('studio.speech', side_effect=AssertionError('TTS must be reused')):
                export_video(self.lesson, base/'second', options)
            out = base/'second'
            manifest = json.loads((out/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['edition'], 'premium-mvp')
            self.assertEqual(len(manifest['shorts']), 1)
            for path in [out/'video.mp4', out/'shorts/short_01.mp4']:
                self.assertGreater(path.stat().st_size, 1000)
                run([FFMPEG, '-v', 'error', '-i', path, '-f', 'null', '-'])
            probe = run([FFMPEG, '-i', out/'shorts/short_01.mp4', '-frames:v', '1', '-f', 'image2pipe', '-c:v', 'png', '-'])
            from PIL import Image
            import io
            self.assertEqual(Image.open(io.BytesIO(probe)).size, (1080, 1920))

    def test_video_only_export_does_not_create_local_thumbnail_or_publishing_copy(self):
        from PIL import Image
        lesson = copy.deepcopy(self.lesson)
        lesson['lines'] = lesson['lines'][:1]
        def speech(text, voice, speed, target, *args, **kwargs):
            with wave.open(str(target), 'wb') as wav:
                wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\0\0' * 12000)
        def render(images, durations, audio, target, *args):
            target.write_bytes(b'fake video; rendering verified by other pipeline tests')
        with tempfile.TemporaryDirectory() as folder, \
                patch('studio.speech', side_effect=speech), \
                patch('premium.scene', return_value=Image.new('RGB', (64, 36))), \
                patch('premium.render_frames', side_effect=render), \
                patch('premium.publishing_kit') as kit, patch('premium.thumbnail') as thumb:
            out = Path(folder)
            export_video(lesson, out, {'premium': True, 'shorts': False, 'local_publishing': False,
                'voices': ['voice1', 'voice2'], 'eleven_key': 'test', 'audio_cache': out/'cache'})
            kit.assert_not_called()
            thumb.assert_not_called()
            self.assertTrue((out/'video.mp4').exists())
            self.assertFalse((out/'description.txt').exists())
            self.assertEqual(list(out.glob('thumbnail*')), [])


if __name__ == '__main__':
    unittest.main()
