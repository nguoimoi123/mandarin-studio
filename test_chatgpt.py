import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from agent_ads_chatgpt.worker import BrowserWorker
from chatgpt_web import ChatGPTError, create_thumbnails, json_response, validate_publishing
from premium import publishing_data, publishing_kit, thumbnail, audit_lesson
from studio import ROOT, generate_lesson, validate_lesson


def publishing():
    return {'titles': ['Ngày đầu đi làm', 'Một câu hỏi khó', 'Bạn sẽ nói gì?'],
            'description': 'Một buổi sáng đi làm và câu hỏi khiến Lan bối rối. #HocTiengTrung',
            'thumbnail_text': ['NGHE NHẦM RỒI!', 'HỎI LẠI SAO?', 'NGÀY ĐẦU ĐI LÀM'],
            'thumbnail_prompts': ['Office misunderstanding ' + str(i) for i in range(3)],
            'pinned_comment': 'Bạn sẽ hỏi lại câu nào?', 'cta': 'Theo dõi để nghe tập sau.'}


class ChatGPTTests(unittest.TestCase):
    def setUp(self):
        self.lesson = json.loads((ROOT/'sample_lesson.json').read_text(encoding='utf-8'))
        self.lesson['publishing'] = publishing()

    def test_chatgpt_generation_requires_no_gemini_key_and_validates_cast(self):
        prompts = []
        def sender(prompt):
            prompts.append(prompt)
            return '```json\n' + json.dumps(self.lesson, ensure_ascii=False) + '\n```'
        with patch('urllib.request.urlopen', side_effect=AssertionError('No Gemini request')):
            result = generate_lesson('Đi làm', 'HSK 1–2', 3, '', '', speakers=self.lesson['speakers'], text_sender=sender)
        self.assertNotIn('publishing', result)
        self.assertNotIn('thumbnail_prompts', prompts[0])
        self.assertNotIn('thumbnail_images', result)
        self.assertEqual(result['lines'], self.lesson['lines'])
        with self.assertRaises(ValueError):
            generate_lesson('Đi làm', 'HSK 1–2', 3, '', '', speakers=['Other'], text_sender=sender)

    def test_invalid_json_and_incomplete_publishing_are_rejected(self):
        for raw in ('```json\n{"a":', '[]', 'not JSON'):
            with self.subTest(raw=raw), self.assertRaises(ChatGPTError):
                json_response(raw)
        for key in publishing():
            value = publishing()
            value.pop(key)
            with self.subTest(key=key), self.assertRaises(ChatGPTError):
                validate_publishing(value)

    def test_ai_kit_uses_generated_copy_and_real_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root/'original.png'
            Image.new('RGB', (1600, 900), '#c05020').save(original)
            self.lesson['thumbnail_images'] = [str(original)] * 3
            with patch('urllib.request.urlopen', side_effect=AssertionError('local export only')):
                publishing_kit(self.lesson, root/'kit', {})
            self.assertEqual((root/'kit/description.txt').read_text(encoding='utf-8'), publishing()['description'])
            self.assertIn(publishing()['description'], (root/'kit/youtube_kit.txt').read_text(encoding='utf-8'))
            self.assertEqual(publishing_data(self.lesson, {})['titles'], publishing()['titles'])
            image = thumbnail(self.lesson, {})
            self.assertEqual(image.size, (1280, 720))
            self.assertGreater(image.getpixel((1200, 400))[0], 100)

    def test_thumbnail_failure_preserves_finished_assets_and_script(self):
        class FakeChat:
            count = 0
            def generate_image(self, prompt, target, cancel):
                self.count += 1
                if self.count == 2:
                    raise ChatGPTError('quota')
                target.parent.mkdir(parents=True, exist_ok=True)
                Image.new('RGB', (800, 450)).save(target)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ChatGPTError):
                create_thumbnails(FakeChat(), self.lesson, directory)
            saved = json.loads((Path(directory)/'lesson.json').read_text(encoding='utf-8'))
            self.assertEqual(len(saved['thumbnail_images']), 1)
            self.assertTrue(Path(saved['thumbnail_images'][0]).is_file())

    def test_worker_keeps_calls_on_one_thread_and_closes(self):
        class Client:
            threads = []
            closed = False
            def ask(self, prompt, cancel_event=None):
                self.threads.append(threading.get_ident())
                return prompt
            def stop(self):
                self.closed = True
        client = Client()
        worker = BrowserWorker(client)
        try:
            self.assertEqual(worker.call('ask', 'one'), 'one')
            self.assertEqual(worker.call('ask', 'two'), 'two')
        finally:
            worker.close()
        self.assertEqual(len(set(client.threads)), 1)
        self.assertNotEqual(client.threads[0], threading.get_ident())
        self.assertTrue(client.closed)

    def test_single_narrator_is_not_flagged_as_missing_second_voice(self):
        lesson = copy.deepcopy(self.lesson)
        lesson['speakers'] = [lesson['speakers'][0]]
        lesson['lines'] = [lesson['lines'][0]]
        self.assertFalse(any('hai giọng' in warning for warning in audit_lesson(lesson)['warnings']))


if __name__ == '__main__':
    unittest.main()
