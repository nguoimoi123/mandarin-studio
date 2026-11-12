import base64
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from edge_bridge import EdgeBridge, EdgeChatGPT
from studio import Cancelled


class EdgeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = EdgeBridge(0)
        self.addCleanup(self.bridge.close)

    def request(self, path, body=None, authorized=True):
        headers = {'Authorization': 'Bearer ' + self.bridge.token} if authorized else {}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(f'http://127.0.0.1:{self.bridge.port}'+path,
            data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_pairing_is_local_and_requires_connection_code(self):
        self.assertEqual(self.bridge.server.server_address[0], '127.0.0.1')
        self.assertFalse(self.bridge.connected)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/next', authorized=False)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        self.assertFalse(self.bridge.connected)
        self.request('/state?id=')
        self.assertTrue(self.bridge.connected)

    def test_job_is_delivered_once_and_result_is_returned(self):
        self.request('/state?id=')
        result, errors = [], []
        def caller():
            try:
                result.append(self.bridge.call('write this episode', timeout=5, web=True))
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=caller)
        thread.start()
        self.addCleanup(lambda: thread.join(timeout=6))
        deadline = time.monotonic()+3
        job = None
        while not job and time.monotonic()<deadline:
            job = self.request('/next')['job']
            time.sleep(0.01)
        self.assertIsNotNone(job)
        self.assertEqual(job['prompt'], 'write this episode')
        self.assertTrue(job['web'])
        self.assertIsNone(self.request('/next')['job'])
        self.request('/result', {'id': job['id'], 'text': '{"ok":true}'})
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result[0]['text'], '{"ok":true}')
        self.assertTrue(self.request('/state?id='+job['id'])['cancelled'])
        self.assertEqual(self.bridge.jobs, {})

    def test_cancelled_prompt_is_not_redelivered(self):
        self.request('/state?id=')
        cancelled, errors = threading.Event(), []
        def caller():
            try:
                self.bridge.call('one request', cancel=cancelled, timeout=5)
            except Cancelled:
                errors.append('cancelled')
        thread = threading.Thread(target=caller)
        thread.start()
        self.addCleanup(lambda: thread.join(timeout=6))
        deadline=time.monotonic()+3
        while self.bridge.pending.empty() and time.monotonic()<deadline:
            time.sleep(0.01)
        cancelled.set()
        thread.join(timeout=3)
        self.assertEqual(errors, ['cancelled'])
        self.assertIsNone(self.request('/next')['job'])

    def test_adapter_saves_valid_original_image_and_never_launches_browser(self):
        output=io.BytesIO()
        Image.new('RGB',(800,450),'#1b604f').save(output,format='PNG')
        encoded='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()
        with patch('subprocess.Popen',side_effect=AssertionError('must not launch a browser')):
            adapter=EdgeChatGPT(0)
            try:
                with tempfile.TemporaryDirectory() as folder, patch.object(adapter.bridge,'call',return_value={'image':encoded}):
                    target=Path(folder)/'thumbnail.png'
                    adapter.generate_image('test prompt',target)
                    with Image.open(target) as image:
                        self.assertEqual(image.size,(800,450))
                        self.assertEqual(image.getpixel((0,0)),(27,96,79))
            finally:
                adapter.close()


if __name__ == '__main__':
    unittest.main()
