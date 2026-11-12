"""Validate expressive delivery without sending paid TTS or browser requests."""
import copy
import io
import json
import tempfile
import unittest
import wave
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from speech_performance import apply_annotations, speech_text
from speech_recovery import recover_audio
from studio import (ROOT, SpeechNetworkError, export_video, generate_lesson, run,
                    speech, validate_lesson, wav_duration)


def lesson_fixture():
    lesson = json.loads((ROOT/'sample_lesson.json').read_text(encoding='utf-8'))
    lesson['lines'] = lesson['lines'][:3]
    for line in lesson['lines']:
        line.update(emotion='neutral', emotion_strength=2)
    lesson['lines'][1].update(emotion='surprised', emotion_strength=2)
    return lesson


class PerformanceMetadataTests(unittest.TestCase):
    def test_annotation_cannot_rewrite_dialogue_or_voices(self):
        lesson = lesson_fixture()
        lesson['speaker_voices'] = {lesson['speakers'][0]: 'privateVoice'}
        rows = [{'index': i+1, 'emotion': 'surprised', 'emotion_strength': 2,
                 'zh': 'rewritten text', 'speaker': 'new person'} for i in range(3)]
        result = apply_annotations(lesson, {'lines': rows})
        self.assertEqual(result['speaker_voices'], lesson['speaker_voices'])
        for original, changed in zip(lesson['lines'], result['lines']):
            self.assertEqual({k: changed[k] for k in ('speaker', 'zh', 'pinyin', 'vi')},
                             {k: original[k] for k in ('speaker', 'zh', 'pinyin', 'vi')})
        self.assertEqual(lesson['lines'][0]['emotion'], 'neutral')
        for bad in ({'lines': rows[:2]}, {'lines': [rows[0]]*3},
                    {'lines': [dict(row, emotion='[shouts]') for row in rows]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                apply_annotations(lesson, bad)

    def test_strength_changes_only_spoken_text_and_neutral_remains_clean(self):
        line = lesson_fixture()['lines'][1]
        self.assertEqual(speech_text(line, 'off'), line['zh'])
        self.assertEqual(speech_text(line, 'light'), '[slightly surprised] ' + line['zh'])
        self.assertEqual(speech_text(line, 'medium'), '[surprised] ' + line['zh'])
        self.assertEqual(speech_text(line, 'strong'), '[very surprised] ' + line['zh'])
        self.assertEqual(speech_text(dict(line, emotion='neutral'), 'strong'), line['zh'])
        self.assertEqual(speech_text(dict(line, emotion_strength=1), 'light'), line['zh'])
        self.assertNotIn('[', line['zh'])

    def test_invalid_metadata_rejected_but_old_json_is_supported(self):
        lesson = lesson_fixture()
        for metadata in ({'emotion': []}, {'emotion': 'unknown'}, {'emotion_strength': True},
                         {'emotion_strength': 4}, {'emotion_strength': '2'}):
            bad = copy.deepcopy(lesson)
            bad['lines'][0].update(metadata)
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                validate_lesson(bad)
        for line in lesson['lines']:
            line.pop('emotion')
            line.pop('emotion_strength')
        validate_lesson(lesson)

    def test_generation_requests_and_requires_separate_emotion_metadata(self):
        lesson = lesson_fixture()
        for speaker in lesson['speakers']:
            self.assertTrue(any(line['speaker'] == speaker for line in lesson['lines']))
        prompts = []
        def sender(prompt):
            prompts.append(prompt)
            return json.dumps(lesson, ensure_ascii=False)
        generated = generate_lesson('Bất ngờ tại công ty', 'HSK 2', 1, '', '',
                                    speakers=lesson['speakers'], text_sender=sender, expression='light')
        self.assertEqual(generated, lesson)
        self.assertIn('emotion_strength', prompts[0])
        del lesson['lines'][0]['emotion']
        with self.assertRaisesRegex(ValueError, 'cảm xúc'):
            generate_lesson('test', 'HSK 2', 1, '', '', speakers=lesson['speakers'],
                            text_sender=sender, expression='light')

    def test_v4_payload_has_supported_settings_and_clean_language(self):
        def urlopen(request, timeout):
            body = json.loads(request.data)
            self.assertEqual(body['text'], '[surprised] 啊？真的吗？')
            self.assertEqual(body['voice_settings'], {'stability': .35, 'similarity_boost': .75})
            self.assertNotIn('previous_text', body)
            self.assertNotIn('next_text', body)
            self.assertEqual(body['language_code'], 'zh')
            self.assertNotIn('secret', request.full_url)
            result = io.BytesIO(b'ID3'+b'a'*1000)
            result.headers = Message()
            result.headers['Content-Type'] = 'audio/mpeg'
            return result
        with tempfile.TemporaryDirectory() as folder, patch('urllib.request.urlopen', side_effect=urlopen):
            speech('[surprised] 啊？真的吗？', 'voice1', .9, Path(folder)/'voice.mp3', None,
                   'secret', 'eleven_v4', previous_text='你好', next_text='是啊')


class PerformanceAudioTests(unittest.TestCase):
    @staticmethod
    def fake_speech(text, voice, speed, target, cancel, key, model, **kwargs):
        with wave.open(str(target), 'wb') as audio:
            audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\0\0'*12000)

    @staticmethod
    def fast_render(args, cancel=None):
        if '-af' in args:
            return run(args, cancel)
        Path(args[-1]).write_bytes(b'fake video; real audio conversion')

    def options(self, base):
        lesson = lesson_fixture()
        return {'speaker_voices': {name: f'voice{i}' for i, name in enumerate(lesson['speakers'])},
                'eleven_key': 'never-save-key', 'tts_model': 'eleven_v4', 'expression': 'medium',
                'audio_cache': base/'cache', 'local_publishing': False, 'speed': 1.0}

    def test_preview_uses_selected_turn_and_export_reuses_it_without_tags_in_subtitles(self):
        lesson = lesson_fixture()
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            options = self.options(base)
            with patch('studio.speech', side_effect=self.fake_speech) as tts, \
                    patch('studio.card', side_effect=AssertionError('preview must not render cards')):
                preview = export_video(lesson, base/'preview', dict(options, premium=True,
                                       audio_preview=True, preview_start=2, preview_count=1))
                self.assertEqual(tts.call_count, 1)
                self.assertEqual(tts.call_args.args[0], '[surprised] '+lesson['lines'][1]['zh'])
                self.assertEqual(tts.call_args.kwargs['previous_text'], '')
                self.assertGreater(wav_duration(preview), .4)
                self.assertFalse((base/'preview'/'video.mp4').exists())
            with patch('studio.speech', side_effect=self.fake_speech) as tts, \
                    patch('studio.run', side_effect=self.fast_render), \
                    patch('studio.card', return_value=Image.new('RGB', (64, 36))):
                export_video(lesson, base/'video', options)
                self.assertEqual(tts.call_count, 2)
            subtitles = (base/'video'/'hanzi_pinyin_vietnamese.srt').read_text(encoding='utf-8')
            for line in lesson['lines']:
                for field in ('zh', 'pinyin', 'vi'):
                    self.assertIn(line[field], subtitles)
            self.assertNotIn('[surprised]', subtitles)
            job = json.loads((base/'video'/'export_job.json').read_text(encoding='utf-8'))
            self.assertEqual(job['options']['expression'], 'medium')
            self.assertNotIn('never-save-key', json.dumps(job))

    def test_speed_reuses_paid_audio_and_changed_emotion_only_regenerates_affected_turn(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            lesson = lesson_fixture()
            options = dict(self.options(base), audio_preview=True, preview_count=3)
            with patch('studio.speech', side_effect=self.fake_speech) as tts:
                original = export_video(lesson, base/'first', options)
                self.assertEqual(tts.call_count, 3)
            with patch('studio.speech', side_effect=AssertionError('speed must reuse v4 MP3')):
                slower = export_video(lesson, base/'slow', dict(options, speed=.8))
                self.assertGreater(wav_duration(slower), wav_duration(original))
            lesson['lines'][1]['emotion'] = 'worried'
            with patch('studio.speech', side_effect=self.fake_speech) as tts:
                export_video(lesson, base/'new_emotion', options)
                self.assertEqual(tts.call_count, 1)
                self.assertEqual(tts.call_args.args[0], '[worried] '+lesson['lines'][1]['zh'])

    def test_v2_with_emotion_fails_before_any_paid_call(self):
        with tempfile.TemporaryDirectory() as folder, patch('studio.speech') as tts:
            with self.assertRaisesRegex(ValueError, 'v4'):
                export_video(lesson_fixture(), folder, dict(self.options(Path(folder)), tts_model='eleven_multilingual_v2'))
            tts.assert_not_called()

    def test_uncertain_preview_is_not_posted_again_from_a_different_output_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            options = dict(self.options(base), audio_preview=True, preview_start=2, preview_count=1)
            with patch('studio.speech', side_effect=SpeechNetworkError('lost response')) as tts, \
                    patch('speech_recovery.recover_audio', return_value=False):
                for name in ('first', 'second'):
                    with self.assertRaises(RuntimeError):
                        export_video(lesson_fixture(), base/name, options)
                self.assertEqual(tts.call_count, 1)
            pending_files = list((base/'cache').glob('*.request.json'))
            self.assertEqual(len(pending_files), 1)
            pending = json.loads(pending_files[0].read_text(encoding='utf-8'))
            self.assertTrue(pending['text'].startswith('[surprised]'))
            self.assertNotIn('speed', pending['voice_settings'])
            self.assertNotIn('never-save-key', json.dumps(pending))

    def test_recovery_matches_actual_v4_settings_without_api_speed(self):
        pending = {'requested_at': 1000, 'text': '[surprised] 真的吗？', 'voice': 'voice1',
                   'model': 'eleven_v4', 'speed': .8, 'stability': .35,
                   'voice_settings': {'stability': .35, 'similarity_boost': .75}}
        item = {'history_item_id': 'one', 'date_unix': 1001, 'text': pending['text'],
                'voice_id': 'voice1', 'model_id': 'eleven_v4', 'settings': pending['voice_settings']}
        def get(request, timeout, cancel):
            self.assertEqual(request.get_method(), 'GET')
            if request.full_url.endswith('/audio'):
                return b'ID3'+b'a'*1000, 'audio/mpeg'
            return json.dumps({'history': [item]}).encode(), 'application/json'
        with tempfile.TemporaryDirectory() as folder, patch('speech_recovery._get', side_effect=get):
            self.assertTrue(recover_audio(pending, 'key', Path(folder)/'voice.mp3'))
            item['text'] = '真的吗？'
            self.assertFalse(recover_audio(pending, 'key', Path(folder)/'wrong.mp3'))


if __name__ == '__main__':
    unittest.main()
