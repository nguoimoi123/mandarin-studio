from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk
from studio import ROOT, Cancelled, card, export_video, generate_lesson, validate_lesson
from settings_store import load_settings, save_settings


class Studio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Mandarin Studio · ElevenLabs Video Maker')
        self.iconbitmap(str(ROOT / 'artwork' / 'mandarin_studio.ico'))
        self.geometry(f'{min(1200, self.winfo_screenwidth()-40)}x{min(760, self.winfo_screenheight()-70)}+20+15')
        self.minsize(1000, 620)
        self.configure(bg='#0b1120')
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.last_output = None
        self.preview_image = None
        self.settings_path = ROOT / '.env'
        self.saved_settings = load_settings(self.settings_path)
        self.save_job = None
        self.configure_style()
        self.topic = tk.StringVar(value='Lần đầu đi làm: vượt qua sự lo lắng')
        self.level = tk.StringVar(value='HSK 1–2')
        self.minutes = tk.StringVar(value='15')
        self.key = tk.StringVar(value=os.environ.get('GEMINI_API_KEY', ''))
        self.model = tk.StringVar(value='gemini-3.8-flash')
        self.brand = tk.StringVar(value='Chuyện nhỏ · Tiếng Trung')
        self.eleven_key = tk.StringVar(value=os.environ.get('ELEVENLABS_API_KEY', ''))
        self.tts_model = tk.StringVar(value='eleven_multilingual_v2')
        self.voice1 = tk.StringVar(value=os.environ.get('ELEVENLABS_VOICE_1', ''))
        self.voice2 = tk.StringVar(value=os.environ.get('ELEVENLABS_VOICE_2', ''))
        self.rate = tk.StringVar(value='0.9')
        self.resolution = tk.StringVar(value='1080p')
        self.folder = tk.StringVar(value=str(ROOT / 'outputs'))
        self.settings_variables = {
            'GEMINI_API_KEY': self.key, 'GEMINI_MODEL': self.model,
            'ELEVENLABS_API_KEY': self.eleven_key, 'ELEVENLABS_VOICE_1': self.voice1,
            'ELEVENLABS_VOICE_2': self.voice2, 'ELEVENLABS_MODEL': self.tts_model,
            'VOICE_SPEED': self.rate, 'VIDEO_RESOLUTION': self.resolution,
            'OUTPUT_FOLDER': self.folder, 'CHANNEL_NAME': self.brand,
            'LESSON_TOPIC': self.topic, 'LESSON_LEVEL': self.level,
            'LESSON_MINUTES': self.minutes, 
        }
        for name, variable in self.settings_variables.items():
            if name in self.saved_settings:
                value = self.saved_settings[name]
                variable.set(value.lower() in ('true', '1', 'yes') if name == 'SPEAKING_PRACTICE' else value)
        self.status = tk.StringVar(value='Sẵn sàng · Nhập chủ đề hoặc thử kịch bản mẫu')
        self.build()
        for variable in self.settings_variables.values():
            variable.trace_add('write', self.schedule_settings_save)
        self.after(100, self.poll)
        self.protocol('WM_DELETE_WINDOW', self.close)

    def configure_style(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#111d30', foreground='#e5edf7')
        style.configure('TFrame', background='#0b1120')
        style.configure('TLabel', background='#0b1120')
        style.configure('TButton', padding=(12, 5), background='#20344f')
        style.map('TButton', background=[('active', '#305778')])
        style.configure('Accent.TButton', background='#16796f', foreground='white')
        style.configure('TEntry', fieldbackground='#18273d', foreground='#eef4fc', insertcolor='white', padding=6)
        style.configure('TCombobox', fieldbackground='#18273d', foreground='#eef4fc', padding=5)
        style.map('TCombobox', fieldbackground=[('readonly', '#18273d')], foreground=[('readonly', '#eef4fc')])
        style.configure('TNotebook', background='#0b1120', borderwidth=0)
        style.configure('TNotebook.Tab', padding=(16, 10))
        style.map('TNotebook.Tab', background=[('selected', '#20344f'), ('!selected', '#111d30')], foreground=[('selected', '#62ded0'), ('!selected', '#b5c6da')])
        style.configure('TProgressbar', background='#62ded0')

    def entry(self, frame, label, var, row, values=None, secret=False):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=4, padx=(0, 12))
        if values:
            widget = ttk.Combobox(frame, textvariable=var, values=values, width=27, state='readonly')
        else:
            widget = ttk.Entry(frame, textvariable=var, show='•' if secret else '', width=30)
        widget.grid(row=row, column=1, sticky='ew', pady=4)
        return widget

    def build(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='MANDARIN STUDIO', font=('Segoe UI', 21, 'bold'), foreground='#62ded0').pack(anchor='w')
        ttk.Label(outer, text='Podcast hội thoại · Chữ Hán + Pinyin + Nghĩa Việt · Giọng ElevenLabs', foreground='#9badc5').pack(anchor='w', pady=(2, 10))
        panes = ttk.Panedwindow(outer, orient='horizontal')
        left = ttk.Frame(panes, padding=(0, 0, 18, 0))
        right = ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=3)
        notebook = ttk.Notebook(left)
        notebook.pack(fill='both', expand=True)
        create = ttk.Frame(notebook, padding=10)
        settings = ttk.Frame(notebook, padding=10)
        notebook.add(create, text='Bài học')
        notebook.add(settings, text='Cấu hình')
        voice_settings = ttk.Frame(notebook, padding=10)
        voice_settings.columnconfigure(1, weight=1)
        notebook.add(voice_settings, text='ElevenLabs')
        create.columnconfigure(1, weight=1)
        settings.columnconfigure(1, weight=1)
        self.entry(create, 'Chủ đề', self.topic, 0)
        self.entry(create, 'Trình độ', self.level, 1, ['HSK 1–2', 'HSK 3–4', 'HSK 5–6'])
        self.entry(create, 'Tổng phút ≈', self.minutes, 2, ['3', '5', '10', '12', '15', '20'])
        self.entry(create, 'Tên kênh', self.brand, 3)
        ttk.Label(create, text='Podcast phát một lần, liền mạch.\nThời lượng phụ thuộc kịch bản và tốc độ đọc.', foreground='#9badc5', wraplength=330).grid(row=4, column=0, columnspan=2, sticky='w', pady=8)
        self.generate_button = ttk.Button(create, text='Tạo video tự động từ chủ đề', style='Accent.TButton', command=self.generate)
        self.generate_button.grid(row=5, column=0, columnspan=2, sticky='ew', pady=8)
        files = ttk.Frame(create)
        files.grid(row=6, column=0, columnspan=2, sticky='ew', pady=4)
        for title, action in [('Bài mẫu', self.sample), ('Mở JSON', self.load), ('Lưu JSON', self.save)]:
            ttk.Button(files, text=title, command=action).pack(side='left', fill='x', expand=True, padx=2)
        self.export_button = ttk.Button(create, text='2. Tạo giọng & xuất MP4', style='Accent.TButton', command=self.export)
        self.export_button.grid(row=7, column=0, columnspan=2, sticky='ew', pady=(8, 4))
        ttk.Button(create, text='Dừng tác vụ', command=self.cancel.set).grid(row=8, column=0, columnspan=2, sticky='ew', pady=4)
        ttk.Button(create, text='Mở thư mục kết quả', command=self.open_output).grid(row=9, column=0, columnspan=2, sticky='ew', pady=4)
        self.entry(settings, 'Gemini API key', self.key, 0, secret=True)
        self.entry(settings, 'Model', self.model, 1)
        ttk.Label(settings, text='Tự lưu key và cấu hình vào .env trên máy.', foreground='#9badc5').grid(row=2, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Button(settings, text='Lấy key tại Google AI Studio', command=lambda: __import__('webbrowser').open('https://aistudio.google.com/apikey')).grid(row=3, column=0, columnspan=2, sticky='ew', pady=6)
        self.entry(voice_settings, 'ElevenLabs key', self.eleven_key, 0, secret=True)
        self.entry(voice_settings, 'Voice ID · Ngọc', self.voice1, 1)
        self.entry(voice_settings, 'Voice ID · Quân', self.voice2, 2)
        self.entry(voice_settings, 'Model giọng', self.tts_model, 3, ['eleven_multilingual_v2', 'eleven_flash_v2_5', 'eleven_turbo_v2_5'])
        self.entry(voice_settings, 'Tốc độ', self.rate, 4, ['0.7', '0.8', '0.9', '1.0', '1.1', '1.2'])
        ttk.Label(voice_settings, text='Tự lưu key và Voice ID vào .env, mở lại sẽ tự nạp.\nLời thoại gửi tới ElevenLabs.\nTạo giọng có thể trừ credit theo tài khoản.', foreground='#9badc5', wraplength=350).grid(row=6, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Button(voice_settings, text='Mở ElevenLabs', command=lambda: __import__('webbrowser').open('https://elevenlabs.io/app/voice-library')).grid(row=7, column=0, columnspan=2, sticky='ew', pady=4)
        self.entry(settings, 'Chất lượng', self.resolution, 7, ['1080p', '720p'])
        ttk.Button(voice_settings, text='Lưu cấu hình ngay', command=lambda: self.persist_settings(notify=True)).grid(row=8, column=0, columnspan=2, sticky='ew', pady=4)
        self.entry(settings, 'Thư mục xuất', self.folder, 8)
        ttk.Button(settings, text='Chọn thư mục…', command=self.choose_folder).grid(row=9, column=0, columnspan=2, sticky='ew', pady=4)
        ttk.Label(settings, text='Gemini viết chữ Hán, pinyin và bản dịch Việt.\nCấu hình giọng ở tab ElevenLabs.', foreground='#9badc5', wraplength=340).grid(row=10, column=0, columnspan=2, sticky='w', pady=4)
        tabs = ttk.Notebook(right)
        tabs.pack(fill='both', expand=True)
        edit = ttk.Frame(tabs)
        view = ttk.Frame(tabs)
        tabs.add(edit, text='Kịch bản · có thể chỉnh sửa')
        tabs.add(view, text='Xem bố cục')
        ttk.Label(edit, text='JSON: title_zh, title_vi, speakers, lines (speaker/zh/pinyin/vi), vocabulary', foreground='#9badc5').pack(anchor='w', pady=8)
        self.editor = tk.Text(edit, wrap='word', bg='#111d30', fg='#e5edf7', insertbackground='#62ded0', font=('Consolas', 11), relief='flat', padx=16, pady=12, undo=True)
        scroll = ttk.Scrollbar(edit, command=self.editor.yview)
        scroll.pack(side='right', fill='y')
        self.editor.configure(yscrollcommand=scroll.set)
        self.editor.pack(fill='both', expand=True)
        self.preview = ttk.Label(view)
        self.preview.pack(fill='both', expand=True, pady=12)
        toolbar = ttk.Frame(view)
        toolbar.pack(fill='x')
        for part, title in enumerate(['Xem trước podcast']):
            ttk.Button(toolbar, text=title, command=lambda p=part: self.show_preview(p)).pack(side='left', padx=4, pady=8)
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(side='bottom', fill='x', pady=(8, 4))
        ttk.Label(outer, textvariable=self.status, foreground='#a9c4db', wraplength=1120).pack(side='bottom', anchor='w', pady=(8, 0))
        panes.pack(fill='both', expand=True)

    def schedule_settings_save(self, *_):
        if self.save_job is not None:
            self.after_cancel(self.save_job)
        self.save_job = self.after(700, self.persist_settings)

    def persist_settings(self, notify=False):
        if self.save_job is not None:
            self.after_cancel(self.save_job)
            self.save_job = None
        values = {name: str(variable.get()) for name, variable in self.settings_variables.items()}
        try:
            save_settings(self.settings_path, values)
        except OSError:
            self.status.set('Chưa lưu được .env. Kiểm tra quyền ghi thư mục dự án.')
            if notify:
                messagebox.showerror('Chưa lưu cấu hình', 'Không ghi được .env. App vẫn giữ giá trị hiện tại; hãy kiểm tra quyền ghi rồi lưu lại.')
            return False
        if notify:
            self.status.set('Đã lưu cấu hình vào .env. Mở lại app sẽ tự nạp lại.')
        return True

    def get_lesson(self):
        return validate_lesson(json.loads(self.editor.get('1.0', 'end')))

    def put_lesson(self, lesson):
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', json.dumps(lesson, ensure_ascii=False, indent=2))
        self.show_preview(1)

    def sample(self):
        if self.busy:
            return
        self.put_lesson(json.loads((ROOT / 'sample_lesson.json').read_text(encoding='utf-8')))
        self.status.set('Đã nạp bài tiếng Trung. Điền key và Voice ID trong tab ElevenLabs trước khi xuất.')

    def load(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(filetypes=[('Kịch bản JSON', '*.json')])
        if path:
            try:
                self.put_lesson(validate_lesson(json.loads(Path(path).read_text(encoding='utf-8-sig'))))
                count = len(self.get_lesson()['lines'])
                self.status.set(f'Đã nạp {Path(path).name} · {count} lượt thoại · podcast phát một lần.')
            except Exception as exc:
                messagebox.showerror('Kịch bản chưa hợp lệ', str(exc))

    def save(self):
        try:
            lesson = self.get_lesson()
            path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('Kịch bản JSON', '*.json')])
            if path:
                Path(path).write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            messagebox.showerror('Chưa lưu được', str(exc))

    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder.set(path)

    def show_preview(self, part):
        try:
            im = card(self.get_lesson(), part, self.brand.get(), 0, (640, 360))
            self.preview_image = ImageTk.PhotoImage(im)
            self.preview.configure(image=self.preview_image)
        except Exception as exc:
            self.status.set('Chưa xem trước được: ' + str(exc))

    def launch(self, work):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.generate_button.configure(state='disabled')
        self.export_button.configure(state='disabled')
        self.progress.start(12)
        def worker():
            try:
                work()
            except Cancelled as exc:
                self.events.put(('status', str(exc)))
            except Exception as exc:
                self.events.put(('error', str(exc)))
            finally:
                self.events.put(('idle', None))
        threading.Thread(target=worker, daemon=True).start()

    def generate(self):
        if not self.persist_settings(notify=True):
            return
        topic, level, minutes, key, model = (v.get() for v in [self.topic, self.level, self.minutes, self.key, self.model])
        if not topic.strip() or not key.strip() or not model.strip():
            messagebox.showinfo('Cần cấu hình', 'Nhập chủ đề, Gemini API key và model trong mục Cấu hình. Có thể nạp bài mẫu để thử xuất MP4 trước.')
            return
        if not self.check_eleven():
            return
        self.status.set('AI đang viết hội thoại và dịch sang tiếng Việt…')
        options = self.export_options()
        out = Path(self.folder.get()).expanduser() / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        def work():
            lesson = generate_lesson(topic, level, minutes, key, model, self.cancel)
            self.events.put(('lesson', lesson))
            result = export_video(lesson, out, options, lambda s: self.events.put(('status', s)), self.cancel)
            self.events.put(('done', result))
        self.launch(work)

    def export_options(self):
        return {'brand': self.brand.get(), 'voices': [self.voice1.get(), self.voice2.get()],
                'speed': self.rate.get(), 'resolution': self.resolution.get(),
                'eleven_key': self.eleven_key.get(), 'tts_model': self.tts_model.get(),
                'mode': 'podcast'}

    def check_eleven(self):
        if not all(v.get().strip() for v in [self.eleven_key, self.voice1, self.voice2]):
            messagebox.showinfo('Cần ElevenLabs', 'Nhập API key và Voice ID của hai nhân vật trong tab ElevenLabs. Không cần gửi key vào chat.')
            return False
        return True

    def export(self):
        if not self.persist_settings(notify=True):
            return
        if not self.check_eleven():
            return
        try:
            lesson = self.get_lesson()
        except Exception as exc:
            messagebox.showerror('Cần kịch bản hợp lệ', str(exc))
            return
        options = self.export_options()
        out = Path(self.folder.get()).expanduser() / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.status.set('Chuẩn bị tạo giọng đọc…')
        def work():
            result = export_video(lesson, out, options, lambda s: self.events.put(('status', s)), self.cancel)
            self.events.put(('done', result))
        self.launch(work)

    def open_output(self):
        path = self.last_output or Path(self.folder.get())
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == 'status':
                    self.status.set(value)
                elif event == 'lesson':
                    self.put_lesson(value)
                elif event == 'error':
                    self.status.set('Tác vụ chưa hoàn tất: ' + value)
                    messagebox.showerror('Tác vụ chưa hoàn tất', value)
                elif event == 'done':
                    self.last_output = value.parent
                    self.status.set('Đã xuất: ' + str(value))
                    messagebox.showinfo('Xuất video thành công', f'{value}\n\nĐã kèm kịch bản, SRT, thumbnail và mô tả YouTube.')
                elif event == 'idle':
                    self.busy = False
                    self.progress.stop()
                    self.generate_button.configure(state='normal')
                    self.export_button.configure(state='normal')
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('Tác vụ đang chạy', 'Bấm Dừng tác vụ và đợi trạng thái hoàn tất trước khi đóng ứng dụng.')
            return
        if self.persist_settings(notify=True):
            self.destroy()


if __name__ == '__main__':
    Studio().mainloop()
