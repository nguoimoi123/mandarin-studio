import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import wave
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from speech_recovery import recover_audio
from studio import ROOT, SpeechNetworkError, export_video, run


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.pending = {'requested_at': 1000, 'text': '钥匙在这里。', 'voice': 'voice1',
                        'model': 'eleven_multilingual_v2', 'speed': 0.9, 'stability': 0.35}
        self.item = {'history_item_id': 'history1', 'date_unix': 1010, 'text': self.pending['text'],
                     'voice_id': 'voice1', 'model_id': self.pending['model'],
                     'settings': {'speed': 0.9, 'stability': 0.35, 'similarity_boost': 0.75}}

    def test_recovery_downloads_existing_audio_using_only_get(self):
        methods = []
        def urlopen(request, timeout):
            methods.append(request.get_method())
            self.assertEqual(request.get_header('Xi-api-key'), 'not-for-logs')
            self.assertNotIn('not-for-logs', request.full_url)
            if request.full_url.endswith('/history/history1/audio'):
                result = io.BytesIO(b'ID3' + b'a'*1000)
                result.headers = Message()
                result.headers['Content-Type'] = 'audio/mpeg'
                return result
            return io.BytesIO(json.dumps({'history': [self.item], 'has_more': False}).encode())
        with tempfile.TemporaryDirectory() as folder, patch('urllib.request.urlopen', urlopen):
            target = Path(folder)/'speech.mp3'
            self.assertTrue(recover_audio(self.pending, 'not-for-logs', target))
            self.assertGreater(target.stat().st_size, 500)
        self.assertEqual(methods, ['GET', 'GET'])

    def test_ambiguous_or_different_history_never_downloads_or_posts(self):
        variants = [[self.item, self.item], [], [dict(self.item, text='other')],
                    [dict(self.item, settings={'speed': 1.0, 'stability': 0.35, 'similarity_boost': 0.75})]]
        with tempfile.TemporaryDirectory() as folder:
            for items in variants:
                with self.subTest(items=items), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps({'history':items}).encode())) as network:
                    target=Path(folder)/'speech.mp3'
                    self.assertFalse(recover_audio(self.pending, 'test', target))
                    self.assertEqual(network.call_count, 1)
                    self.assertFalse(target.exists())

    def test_transient_history_network_failure_retries_only_get(self):
        audio=io.BytesIO(b'ID3'+b'a'*1000)
        audio.headers=Message()
        audio.headers['Content-Type']='audio/mpeg'
        listing=io.BytesIO(json.dumps({'history':[self.item]}).encode())
        with tempfile.TemporaryDirectory() as folder, \
                patch('urllib.request.urlopen', side_effect=[urllib.error.URLError('temporary'), listing, audio]) as network, \
                patch('speech_recovery.time.sleep'):
            self.assertTrue(recover_audio(self.pending,'test',Path(folder)/'audio.mp3'))
            self.assertEqual(network.call_count,3)
            self.assertTrue(all(call.args[0].get_method()=='GET' for call in network.call_args_list))

    @staticmethod
    def fake_recover(pending, key, target, cancel=None):
        with wave.open(str(target), 'wb') as wav:
            wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0'*12000)
        return True

    @staticmethod
    def audio_run(args, cancel=None):
        if '-af' in args:
            return run(args, cancel)
        Path(args[-1]).write_bytes(b'fake video; recovery pipeline fixture')
        return b''

    def test_failed_request_resumes_from_history_without_second_tts_post(self):
        lesson=json.loads((ROOT/'sample_lesson.json').read_text(encoding='utf-8'))
        lesson['lines']=lesson['lines'][:1]
        with tempfile.TemporaryDirectory() as folder, \
                patch('studio.run', side_effect=self.audio_run), \
                patch('studio.card', return_value=Image.new('RGB',(64,36))):
            out=Path(folder)
            options={'voices':['voice1','voice2'], 'eleven_key':'must-not-be-saved',
                     'audio_cache':out/'cache', 'local_publishing':False}
            with patch('studio.speech', side_effect=SpeechNetworkError('lost response')) as tts, \
                    patch('speech_recovery.recover_audio', return_value=False):
                with self.assertRaisesRegex(RuntimeError, '0/1'):
                    export_video(lesson,out,options)
                self.assertEqual(tts.call_count,1)
            job=json.loads((out/'export_job.json').read_text(encoding='utf-8'))
            self.assertEqual(job['state'],'error')
            self.assertNotIn('must-not-be-saved',json.dumps(job))
            self.assertEqual(len(list((out/'assets').glob('*.request.json'))),1)
            with patch('studio.speech', side_effect=AssertionError('must not post again')) as tts, \
                    patch('speech_recovery.recover_audio', side_effect=self.fake_recover):
                export_video(lesson,out,options)
                tts.assert_not_called()
            job=json.loads((out/'export_job.json').read_text(encoding='utf-8'))
            self.assertEqual(job['state'],'complete')
            self.assertEqual(job['completed_turns'],1)
            self.assertEqual(list((out/'assets').glob('*.request.json')),[])


if __name__ == '__main__':
    unittest.main()
