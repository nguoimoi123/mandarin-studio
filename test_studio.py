import copy
import io
import json
import threading
import tempfile
import wave
from pathlib import Path
from email.message import Message
import unittest
from unittest.mock import patch

from studio import ROOT, FFMPEG, Cancelled, check, generate_lesson, validate_lesson, speech, export_video, run, wav_duration


class LessonTests(unittest.TestCase):
    def setUp(self):
        self.lesson = json.loads((ROOT / 'sample_lesson.json').read_text(encoding='utf-8'))

    def test_generation_contract(self):
        response = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(self.lesson)}]}}]}
        def fake_urlopen(request, timeout):
            self.assertEqual(request.get_header('X-goog-api-key'), 'test-only')
            self.assertNotIn('test-only', request.full_url)
            body = json.loads(request.data)
            self.assertEqual(body['generationConfig']['responseMimeType'], 'application/json')
            return io.BytesIO(json.dumps(response).encode())
        with patch('urllib.request.urlopen', fake_urlopen):
            result = generate_lesson('First day', 'A1–A2', 3, 'test-only', 'test-model')
        self.assertEqual(result, self.lesson)

    def test_truncated_generation_is_not_rendered(self):
        response = {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{}'}]}}]}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaisesRegex(ValueError, 'MAX_TOKENS'):
                generate_lesson('First day', 'A1–A2', 3, 'test-only', 'test-model')

    def test_unknown_speaker_is_rejected(self):
        lesson = copy.deepcopy(self.lesson)
        lesson['lines'][0]['speaker'] = 'Nobody'
        with self.assertRaises(ValueError):
            validate_lesson(lesson)

    def test_cancel_before_work(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled):
            check(event)

    def test_elevenlabs_reads_hanzi_and_keeps_key_out_of_url(self):
        def fake_urlopen(request, timeout):
            self.assertEqual(request.get_header('Xi-api-key'), 'test-secret')
            self.assertNotIn('test-secret', request.full_url)
            body = json.loads(request.data)
            self.assertEqual(body['text'], self.lesson['lines'][0]['zh'])
            self.assertEqual(body['model_id'], 'eleven_multilingual_v2')
            self.assertNotIn('language_code', body)
            self.assertEqual(body['voice_settings']['speed'], 0.9)
            response = io.BytesIO(b'ID3' + b'a' * 1000)
            response.headers = Message()
            response.headers['Content-Type'] = 'audio/mpeg'
            return response
        with tempfile.TemporaryDirectory() as folder, patch('urllib.request.urlopen', fake_urlopen):
            target = Path(folder) / 'speech.mp3'
            speech(self.lesson['lines'][0]['zh'], 'testVoice', 0.9, target, None, 'test-secret')
            self.assertGreater(target.stat().st_size, 500)

    def test_missing_pinyin_rejected(self):
        del self.lesson['lines'][0]['pinyin']
        with self.assertRaisesRegex(ValueError, 'pinyin'):
            validate_lesson(self.lesson)

    def test_video_pipeline_with_fake_audio(self):
        # Silence is a test fixture, not an ElevenLabs speech sample.
        lesson = copy.deepcopy(self.lesson)
        lesson['lines'] = lesson['lines'][:2]
        def fake_speech(text, voice, speed, target, cancel, api_key, model):
            with wave.open(str(target), 'wb') as output:
                output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                output.writeframes(b'\x00\x00' * 24000)
        with tempfile.TemporaryDirectory() as folder, patch('studio.speech', fake_speech):
            out = Path(folder)
            video = export_video(lesson, out, {'resolution': '720p', 'voices': ['test1', 'test2'],
                                 'eleven_key': 'do-not-save', 'practice': True})
            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            # Each of the two turns plays once, with only the natural 0.45-second gap.
            self.assertAlmostEqual(manifest['duration_seconds'], 2.9, places=2)
            self.assertAlmostEqual(wav_duration(out / 'assets/full.wav'), 2.9, places=2)
            self.assertNotIn('do-not-save', (out / 'manifest.json').read_text())
            self.assertIn('Jīntiān', (out / 'hanzi_pinyin_vietnamese.srt').read_text(encoding='utf-8'))
            self.assertFalse((out / 'assets/practice_000.png').exists())
            self.assertEqual(manifest['passes'], 1)
            self.assertEqual(len((out / 'chinese.srt').read_text(encoding='utf-8').strip().split('\n\n')), 2)
            self.assertNotIn('Lin:', (out / 'chinese.srt').read_text(encoding='utf-8'))
            self.assertGreater(video.stat().st_size, 1000)
            run([FFMPEG, '-v', 'error', '-i', video, '-f', 'null', '-'])


if __name__ == '__main__':
    unittest.main()
