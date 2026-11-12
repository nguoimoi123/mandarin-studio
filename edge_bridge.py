"""Local authenticated bridge to a user-attached ChatGPT tab in existing Edge.

No browser launch, CDP, profile copying, cookie access, or account credentials.
"""
from __future__ import annotations

import base64
import io
import json
import queue
import secrets
import threading
import time
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from agent_ads_chatgpt.errors import ChatGPTError


class EdgeBridge:
    def __init__(self, port=8765):
        self.token = secrets.token_urlsafe(32)
        self.pending = queue.Queue()
        self.jobs = {}
        self.last_seen = 0
        self.lock = threading.Lock()
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def respond(self, status, data):
                raw = json.dumps(data).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def authorized(self):
                return secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + bridge.token)

            def do_GET(self):
                if not self.authorized():
                    return self.respond(403, {'error': 'Connection code required'})
                parsed = urlparse(self.path)
                if parsed.path == '/next':
                    bridge.last_seen = time.monotonic()
                    while True:
                        try:
                            job_id, prompt, image, web, conversation_url = bridge.pending.get_nowait()
                        except queue.Empty:
                            return self.respond(200, {'job': None})
                        with bridge.lock:
                            future = bridge.jobs.get(job_id)
                        if future is not None and not future.done():
                            return self.respond(200, {'job': {'id': job_id, 'prompt': prompt, 'image': image, 'web': web,
                                                            'conversation_url': conversation_url}})
                if parsed.path == '/state':
                    bridge.last_seen = time.monotonic()
                    job_id = parse_qs(parsed.query).get('id', [''])[0]
                    with bridge.lock:
                        future = bridge.jobs.get(job_id)
                    return self.respond(200, {'cancelled': future is None or future.done()})
                return self.respond(404, {'error': 'Unknown route'})

            def do_POST(self):
                if not self.authorized():
                    return self.respond(403, {'error': 'Connection code required'})
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 32 * 1024 * 1024:
                    return self.respond(413, {'error': 'Invalid response size'})
                try:
                    data = json.loads(self.rfile.read(length))
                    if self.path != '/result' or not isinstance(data, dict):
                        return self.respond(400, {'error': 'Invalid result'})
                    with bridge.lock:
                        future = bridge.jobs.get(data.get('id'))
                        if future is not None and not future.done():
                            if data.get('error'):
                                future.set_exception(ChatGPTError(str(data['error'])[:1000]))
                            else:
                                future.set_result(data)
                    self.respond(200, {'ok': True})
                except (ValueError, TypeError):
                    self.respond(400, {'error': 'Invalid JSON'})

        try:
            self.server = ThreadingHTTPServer(('127.0.0.1', int(port)), Handler)
        except OSError:
            raise ChatGPTError('Cổng kết nối Edge đang được tool khác sử dụng. Đóng bản Mandarin Studio khác rồi mở lại.') from None
        self.server.daemon_threads = True
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, name='edge-bridge', daemon=True)
        self.thread.start()

    @property
    def connected(self):
        return self.last_seen > 0 and time.monotonic() - self.last_seen < 45

    def call(self, prompt, image=False, cancel=None, timeout=600, web=False, conversation_url=None):
        from studio import check
        check(cancel)
        if not self.connected:
            raise ChatGPTError('Chưa kết nối tab Edge. Mở tiện ích Mandarin Studio trong tab ChatGPT và bấm Kết nối.')
        job_id, future = secrets.token_hex(16), Future()
        with self.lock:
            self.jobs[job_id] = future
        self.pending.put((job_id, prompt, image, web, conversation_url))
        deadline = time.monotonic() + timeout
        try:
            while not future.done():
                check(cancel)
                if time.monotonic() > deadline:
                    raise ChatGPTError('ChatGPT chưa trả kết quả trước hạn chờ. Kiểm tra tab Edge trước khi thử lại; tool không tự gửi lại.')
                if not self.connected:
                    raise ChatGPTError('Mất kết nối tab Edge. Kiểm tra câu trả lời trong tab trước khi thử lại; yêu cầu không tự gửi lại.')
                time.sleep(0.2)
            return future.result()
        finally:
            with self.lock:
                self.jobs.pop(job_id, None)
                future.cancel()

    def close(self):
        with self.lock:
            for future in self.jobs.values():
                if not future.done():
                    future.set_exception(ChatGPTError('Tool đã đóng kết nối Edge.'))
            self.jobs.clear()
        self.server.shutdown()
        self.server.server_close()


class EdgeChatGPT:
    def __init__(self, port=8765):
        self.bridge = EdgeBridge(port)
        self.last_conversation = None

    def login(self):
        # Existing Edge stays under the user's control; never launch another browser.
        return self.bridge.connected

    def logged_in(self):
        return self.bridge.connected

    def send(self, prompt, cancel=None):
        result = self.bridge.call(prompt, cancel=cancel)
        self.last_conversation = result.get('conversation_url')
        return result.get('text', '')

    def present(self, prompt, cancel=None, conversation_url=None):
        """Submit a human-readable request on Edge; results stay on the website."""
        return self.bridge.call(prompt, cancel=cancel, web=True, conversation_url=conversation_url)

    def generate_image(self, prompt, target, cancel=None):
        result = self.bridge.call('Create an image, not a text description. ' + prompt, image=True, cancel=cancel)
        encoded = result.get('image', '')
        if not isinstance(encoded, str) or not encoded.startswith('data:image/'):
            raise ChatGPTError('Edge chưa trả ảnh gốc hợp lệ. Kiểm tra ảnh trên tab ChatGPT.')
        from PIL import Image
        try:
            raw = base64.b64decode(encoded.split(',', 1)[1], validate=True)
            with Image.open(io.BytesIO(raw)) as original:
                original.load()
                target = Path(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix('.partial.png')
                original.convert('RGB').save(temporary, format='PNG')
                temporary.replace(target)
        except (ValueError, OSError):
            raise ChatGPTError('Dữ liệu ảnh từ Edge không đọc được.') from None
        return str(target.resolve())

    def close(self):
        self.bridge.close()
