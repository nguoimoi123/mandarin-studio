import copy
import io
import hashlib
import json
import threading
import tempfile
import wave
from pathlib import Path
from PIL import Image
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
            result = generate_lesson('First day', 'A1–A2', 3, 'test-only', 'test-model', speakers=self.lesson['speakers'])
        self.assertEqual(result, self.lesson)

    def test_truncated_generation_is_not_rendered(self):
        response = {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{}'}]}}]}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaisesRegex(ValueError, 'MAX_TOKENS'):
                generate_lesson('First day', 'A1–A2', 3, 'test-only', 'test-model', speakers=self.lesson['speakers'])

    def test_one_to_ten_speakers_and_single_turn_are_supported(self):
        for count in (1, 2, 3, 10):
            with self.subTest(speakers=count):
                lesson = copy.deepcopy(self.lesson)
                lesson['speakers'] = [f'Person {n}' for n in range(count)]
                lesson['lines'] = [dict(lesson['lines'][0], speaker=name) for name in lesson['speakers']]
                self.assertEqual(validate_lesson(lesson), lesson)
        for speakers in ([], ['Same', 'Same'], [''] , [f'Person {n}' for n in range(11)]):
            lesson = copy.deepcopy(self.lesson)
            lesson['speakers'] = speakers
            with self.subTest(invalid=speakers), self.assertRaises(ValueError):
                validate_lesson(lesson)

    def test_generation_uses_requested_cast_and_rejects_unexpected_cast(self):
        lesson = copy.deepcopy(self.lesson)
        lesson['speakers'] = ['Lan']
        lesson['lines'] = [dict(lesson['lines'][0], speaker='Lan')]
        response = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(lesson)}]}}]}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            self.assertEqual(generate_lesson('A late bus', 'HSK 1–2', 3, 'test', 'test', speakers=['Lan']), lesson)
        response['candidates'][0]['content']['parts'][0]['text'] = json.dumps(self.lesson)
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaises(ValueError):
                generate_lesson('A late bus', 'HSK 1–2', 3, 'test', 'test', speakers=['Lan'])

    def test_generation_requires_every_requested_speaker_to_speak(self):
        lesson = copy.deepcopy(self.lesson)
        lesson['speakers'] = ['Lan', 'Minh', 'Bác tài']
        lesson['lines'] = [dict(lesson['lines'][0], speaker='Lan')]
        response = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(lesson)}]}}]}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaises(ValueError):
                generate_lesson('A late bus', 'HSK 1–2', 3, 'test', 'test', speakers=lesson['speakers'])

    def test_lesson_voice_mapping_rejects_unknown_names_and_invalid_ids(self):
        speaker = self.lesson['speakers'][0]
        for assigned in ([], {'Nobody': 'validVoice'}, {speaker: ''},
                         {speaker: 'https://example.com/voice'}, {speaker: None}):
            with self.subTest(assigned=assigned):
                lesson = dict(self.lesson, speaker_voices=assigned)
                with self.assertRaises(ValueError):
                    validate_lesson(lesson)
        validate_lesson(dict(self.lesson, speaker_voices={speaker: 'validVoice'}))

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

    def test_elevenlabs_receives_context_and_adjustable_stability(self):
        def fake_urlopen(request, timeout):
            body = json.loads(request.data)
            self.assertEqual(body['text'], '等等，我忘了拿钥匙。')
            self.assertEqual(body['previous_text'], '我们走吧。')
            self.assertEqual(body['next_text'], '钥匙在桌上。')
            self.assertEqual(body['voice_settings']['stability'], 0.25)
            self.assertEqual(body['language_code'], 'zh')
            response = io.BytesIO(b'ID3' + b'a' * 1000)
            response.headers = Message()
            response.headers['Content-Type'] = 'audio/mpeg'
            return response
        with tempfile.TemporaryDirectory() as folder, patch('urllib.request.urlopen', fake_urlopen):
            speech('等等，我忘了拿钥匙。', 'testVoice', 1.0, Path(folder) / 'speech.mp3', None, 'test',
                   'eleven_flash_v2_5', previous_text='我们走吧。', next_text='钥匙在桌上。', stability=0.25)

    def test_export_requires_only_used_speakers_and_fails_before_tts(self):
        lesson = copy.deepcopy(self.lesson)
        lesson['lines'] = [dict(lesson['lines'][0], speaker=lesson['speakers'][0])]
        with tempfile.TemporaryDirectory() as folder, patch('studio.speech') as tts:
            with self.assertRaises(ValueError):
                export_video(lesson, folder, {'eleven_key': 'test', 'speaker_voices': {}})
            tts.assert_not_called()

    def test_missing_pinyin_rejected(self):
        del self.lesson['lines'][0]['pinyin']
        with self.assertRaisesRegex(ValueError, 'pinyin'):
            validate_lesson(self.lesson)

    def test_video_pipeline_with_fake_audio(self):
        # Silence is a test fixture, not an ElevenLabs speech sample.
        lesson = copy.deepcopy(self.lesson)
        lesson['lines'] = lesson['lines'][:2]
        def fake_speech(text, voice, speed, target, cancel, api_key, model, **kwargs):
            with wave.open(str(target), 'wb') as output:
                output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                output.writeframes(b'\x00\x00' * 24000)
        with tempfile.TemporaryDirectory() as folder, patch('studio.speech', fake_speech):
            out = Path(folder)
            video = export_video(lesson, out, {'resolution': '720p', 'voices': ['test1', 'test2'],
                                 'eleven_key': 'do-not-save', 'practice': True, 'audio_cache': out/'cache'})
            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            # Each turn plays once, with a 0.2-second gap only between turns.
            self.assertAlmostEqual(manifest['duration_seconds'], 2.2, places=2)
            self.assertAlmostEqual(wav_duration(out / 'assets/full.wav'), 2.2, places=2)
            self.assertNotIn('do-not-save', (out / 'manifest.json').read_text())
            self.assertIn('Jīntiān', (out / 'hanzi_pinyin_vietnamese.srt').read_text(encoding='utf-8'))
            self.assertFalse((out / 'assets/practice_000.png').exists())
            self.assertEqual(manifest['passes'], 1)
            self.assertEqual(len((out / 'chinese.srt').read_text(encoding='utf-8').strip().split('\n\n')), 2)
            self.assertNotIn('Lin:', (out / 'chinese.srt').read_text(encoding='utf-8'))
            self.assertGreater(video.stat().st_size, 1000)
            run([FFMPEG, '-v', 'error', '-i', video, '-f', 'null', '-'])


class VoiceRoutingAndCacheTests(unittest.TestCase):
    def setUp(self):
        self.lesson = json.loads((ROOT / 'sample_lesson.json').read_text(encoding='utf-8'))
        self.lesson['speakers'] = ['Lan', 'Minh', 'Bác tài']
        self.lesson['lines'] = [dict(line, speaker=speaker) for line, speaker in
                                zip(self.lesson['lines'][:3], self.lesson['speakers'])]

    @staticmethod
    def fake_speech(text, voice, speed, target, cancel, api_key, model, **kwargs):
        with wave.open(str(target), 'wb') as output:
            output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\x00\x00' * 12000)

    @staticmethod
    def audio_only_run(args, cancel=None):
        if '-af' in args:
            return run(args, cancel)
        Path(args[-1]).write_bytes(b'fake video; audio pipeline is real')
        return b''

    def test_named_voice_mapping_context_cache_and_gap_reuse(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch('studio.run', side_effect=self.audio_only_run), \
                patch('studio.card', return_value=Image.new('RGB', (64, 36))):
            base = Path(folder)
            options = {'speaker_voices': {'Bác tài': 'driverVoice', 'Lan': 'lanVoice', 'Minh': 'minhVoice'},
                       'eleven_key': 'do-not-publish', 'audio_cache': base / 'cache'}
            with patch('studio.speech', side_effect=self.fake_speech) as tts:
                export_video(self.lesson, base / 'first', options)
                self.assertEqual([call.args[1] for call in tts.call_args_list], ['lanVoice', 'minhVoice', 'driverVoice'])
                self.assertEqual(tts.call_args_list[0].kwargs['next_text'], self.lesson['lines'][1]['zh'])
                self.assertEqual(tts.call_args_list[1].kwargs['previous_text'], self.lesson['lines'][0]['zh'])
                self.assertEqual(tts.call_args_list[2].kwargs['next_text'], '')
            manifest = json.loads((base / 'first' / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['speaker_voices'], options['speaker_voices'])
            self.assertNotIn('do-not-publish', json.dumps(manifest))
            self.assertAlmostEqual(wav_duration(base / 'first' / 'assets' / 'full.wav'), 1.9, places=2)
            with patch('studio.speech', side_effect=AssertionError('cached speech must be reused')):
                export_video(self.lesson, base / 'same', options)
                export_video(self.lesson, base / 'longer_pause', dict(options, turn_gap=0.4))
            self.assertAlmostEqual(wav_duration(base / 'longer_pause' / 'assets' / 'full.wav'), 2.3, places=2)
            with patch('studio.speech', side_effect=self.fake_speech) as tts:
                export_video(self.lesson, base / 'expression', dict(options, stability=0.5))
                self.assertEqual(tts.call_count, 3)
            changed = copy.deepcopy(self.lesson)
            changed['lines'][1]['zh'] += '。'
            with patch('studio.speech', side_effect=self.fake_speech) as tts:
                export_video(changed, base / 'context_changed', options)
                self.assertEqual(tts.call_count, 3)

    def test_legacy_episode_reuses_exact_old_assets_and_keeps_final_pause(self):
        self.lesson['lines'] = self.lesson['lines'][:2]
        voices = {'Lan': 'lanVoice', 'Minh': 'minhVoice'}
        with tempfile.TemporaryDirectory() as folder, \
                patch('studio.run', side_effect=self.audio_only_run), \
                patch('studio.card', return_value=Image.new('RGB', (64, 36))), \
                patch('studio.speech', side_effect=AssertionError('legacy speech must be reused')):
            base = Path(folder)
            old_assets = base / 'old' / 'assets'
            old_assets.mkdir(parents=True)
            for line in self.lesson['lines']:
                identity = ['elevenlabs', line['zh'], voices[line['speaker']], 0.9, 'eleven_multilingual_v2']
                digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]
                (old_assets / f'{digest}.mp3').write_bytes(b'ID3' + b'a' * 1000)
                with wave.open(str(old_assets / f'{digest}_balanced_v1.wav'), 'wb') as output:
                    output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                    output.writeframes(b'\x00\x00' * 22800)  # 0.5 seconds speech + old 0.45 gap.
            options = {'speaker_voices': voices, 'eleven_key': 'test', 'legacy_audio': True,
                       'stability': 0.5, 'turn_gap': 0.45, 'reuse_dir': base / 'old',
                       'audio_cache': base / 'cache'}
            export_video(self.lesson, base / 'upgraded', options)
            self.assertAlmostEqual(wav_duration(base / 'upgraded' / 'assets' / 'full.wav'), 1.9, places=2)
            manifest = json.loads((base / 'upgraded' / 'manifest.json').read_text(encoding='utf-8'))
            self.assertTrue(manifest['legacy_audio'])
            self.assertFalse(manifest['speech_context'])
            self.assertEqual(manifest['stability'], 0.5)
            self.assertEqual(manifest['turn_gap'], 0.45)
            for changed in ({'stability': 0.35}, {'turn_gap': 0.2}):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    export_video(self.lesson, base / 'incompatible', dict(options, **changed))

    def test_unused_cast_slots_do_not_require_voice_ids(self):
        self.lesson['lines'] = self.lesson['lines'][:1]
        with tempfile.TemporaryDirectory() as folder, \
                patch('studio.run', side_effect=self.audio_only_run), \
                patch('studio.card', return_value=Image.new('RGB', (64, 36))), \
                patch('studio.speech', side_effect=self.fake_speech) as tts:
            base = Path(folder)
            export_video(self.lesson, base / 'solo', {'speaker_voices': {'Lan': 'lanVoice'},
                         'eleven_key': 'test', 'audio_cache': base / 'cache'})
            self.assertEqual(tts.call_count, 1)
            self.assertAlmostEqual(wav_duration(base / 'solo' / 'assets' / 'full.wav'), 0.5, places=2)
            reopened = validate_lesson(json.loads((base / 'solo' / 'lesson.json').read_text(encoding='utf-8')))
            self.assertEqual(reopened['speaker_voices'], {'Lan': 'lanVoice'})
            self.assertNotIn('speaker_voices', self.lesson)
            with self.assertRaises(ValueError):
                export_video(self.lesson, base / 'invalid', {
                    'speaker_voices': {'Lan': 'lanVoice', 'Minh': 'https://invalid-voice'},
                    'eleven_key': 'test', 'audio_cache': base / 'cache'})
            self.assertEqual(tts.call_count, 1)


if __name__ == '__main__':
    unittest.main()
