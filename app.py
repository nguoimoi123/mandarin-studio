from __future__ import annotations

import json
import copy
import os
import queue
import re
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk
from studio import ROOT, Cancelled, card, export_video, generate_lesson, validate_lesson
from settings_store import load_settings, save_settings
from premium import PALETTES, TOPICS, audit_lesson, publishing_data, publishing_kit, scene, thumbnail
from speech_performance import (EMOTIONS, EXPRESSIVE_MODELS, LEVELS, annotation_prompt,
                                apply_annotations, check_expression)


class Studio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Mandarin Studio Premium · Creator MVP')
        self.iconbitmap(str(ROOT / 'artwork' / 'mandarin_studio.ico'))
        self.geometry(f'{min(1380, self.winfo_screenwidth()-40)}x{min(900, self.winfo_screenheight()-70)}+20+15')
        self.minsize(1000, 620)
        self.configure(bg='#0b1120')
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.last_output = None
        self.preview_image = None
        self.reuse_dir = None
        self.legacy_audio_settings = None
        self.settings_path = ROOT / '.env'
        self.saved_settings = load_settings(self.settings_path)
        self.save_job = None
        self.configure_style()
        self.topic = tk.StringVar(value='Lần đầu đi làm: vượt qua sự lo lắng')
        self.level = tk.StringVar(value='HSK 1–2')
        self.minutes = tk.StringVar(value='15')
        self.key = tk.StringVar(value=os.environ.get('GEMINI_API_KEY', ''))
        self.model = tk.StringVar(value='gemini-3.8-flash')
        self.ai_provider = tk.StringVar(value='ChatGPT Web')
        self.chatgpt_profile = tk.StringVar(value=str(ROOT / '.cache' / 'chatgpt-profile'))
        self.ai_thumbnails = tk.BooleanVar(value=False)
        self.chatgpt = None
        self.chatgpt_profile_used = None
        self.brand = tk.StringVar(value='Chuyện nhỏ · Tiếng Trung')
        self.eleven_key = tk.StringVar(value=os.environ.get('ELEVENLABS_API_KEY', ''))
        self.tts_model = tk.StringVar(value='eleven_v4')
        self.expression = tk.StringVar(value='Nhẹ')
        self.preview_start = tk.StringVar(value='1')
        self.preview_count = tk.StringVar(value='3')
        self.preview_audio_path = None
        self.voice_ids = [tk.StringVar(value=os.environ.get(f'ELEVENLABS_VOICE_{i}', '')) for i in range(1, 11)]
        self.voice_names = [tk.StringVar(value=os.environ.get(f'ELEVENLABS_VOICE_{i}_NAME', '')) for i in range(1, 11)]
        self.cast = tk.StringVar(value='Ngọc, Quân')
        self.speaker_count = tk.StringVar(value='2')
        self.cast_slots = [tk.StringVar(value=str(i)) for i in range(1, 11)]
        self.cast_choices = [tk.StringVar() for _ in range(10)]
        self.speaker_voices = {}
        self.rate = tk.StringVar(value='1.0')
        self.stability = tk.StringVar(value='0.35')
        self.turn_gap = tk.StringVar(value='0.2')
        self.resolution = tk.StringVar(value='1080p')
        self.folder = tk.StringVar(value=str(ROOT / 'outputs'))
        self.premium = tk.BooleanVar(value=True)
        self.shorts = tk.BooleanVar(value=True)
        self.theme = tk.StringVar(value='Midnight')
        self.settings_variables = {
            'AI_PROVIDER': self.ai_provider,
            'GEMINI_API_KEY': self.key, 'GEMINI_MODEL': self.model,
            'ELEVENLABS_API_KEY': self.eleven_key, 'ELEVENLABS_MODEL': self.tts_model,
            'VOICE_SPEED': self.rate, 'VIDEO_RESOLUTION': self.resolution,
            'VOICE_STABILITY': self.stability, 'VOICE_TURN_GAP': self.turn_gap,
            'VOICE_EXPRESSION': self.expression,
            'OUTPUT_FOLDER': self.folder, 'CHANNEL_NAME': self.brand,
            'LESSON_TOPIC': self.topic, 'LESSON_LEVEL': self.level,
            'LESSON_MINUTES': self.minutes, 'LESSON_SPEAKERS': self.cast,
            'LESSON_SPEAKER_COUNT': self.speaker_count,
            'PREMIUM_ENABLED': self.premium, 'EXPORT_SHORTS': self.shorts, 'VIDEO_THEME': self.theme,
        }
        for i, (voice_id, voice_name) in enumerate(zip(self.voice_ids, self.voice_names), 1):
            self.settings_variables[f'ELEVENLABS_VOICE_{i}'] = voice_id
            self.settings_variables[f'ELEVENLABS_VOICE_{i}_NAME'] = voice_name
            self.settings_variables[f'LESSON_VOICE_SLOT_{i}'] = self.cast_slots[i-1]
        for name, variable in self.settings_variables.items():
            if name in self.saved_settings:
                value = self.saved_settings[name]
                variable.set(value.lower() in ('true', '1', 'yes') if isinstance(variable, tk.BooleanVar) else value)
        # Upgrade the old flat-reading preset once; saved episodes restore their own settings.
        if 'VOICE_EXPRESSION' not in self.saved_settings:
            self.tts_model.set('eleven_v4')
            self.rate.set('1.0')
        if self.expression.get() not in LEVELS:
            self.expression.set('Nhẹ')
        try:
            count = self.get_speaker_count()
        except ValueError:
            self.speaker_count.set('2')
            count = 2
        self.cast.set(', '.join(f'Người {i}' for i in range(1, count+1)))
        self.status = tk.StringVar(value='Sẵn sàng · Nhập chủ đề hoặc thử kịch bản mẫu')
        self.build()
        for variable in self.settings_variables.values():
            variable.trace_add('write', self.schedule_settings_save)
        self.after(100, self.poll)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.sample(sync_cast=False)

    def configure_style(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#111d30', foreground='#e5edf7')
        style.configure('TFrame', background='#0b1120')
        style.configure('TLabel', background='#0b1120')
        style.configure('Treeview', background='#111d30', fieldbackground='#111d30',
                        foreground='#e5edf7', rowheight=28)
        style.configure('Treeview.Heading', background='#20334c', foreground='#e5edf7')
        style.map('Treeview', background=[('selected', '#176d68')], foreground=[('selected', '#ffffff')])
        style.configure('TCheckbutton', background='#0b1120', foreground='#e5edf7')
        style.map('TCheckbutton', background=[('active', '#111d30')])
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
        ttk.Label(outer, text='MANDARIN STUDIO  /  PREMIUM', font=('Segoe UI', 21, 'bold'), foreground='#62ded0').pack(anchor='w')
        ttk.Label(outer, text='CREATOR MVP   ·   Podcast Trung–Việt   /   Shorts   /   Bộ đăng YouTube', foreground='#9badc5').pack(anchor='w', pady=(2, 10))
        panes = ttk.Panedwindow(outer, orient='horizontal')
        left = ttk.Frame(panes, padding=(0, 0, 18, 0))
        right = ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=3)
        notebook = ttk.Notebook(left)
        notebook.pack(fill='both', expand=True)
        create = self.form_tab(notebook, 'Bài học')
        settings = self.form_tab(notebook, 'Cấu hình')
        produce = self.form_tab(notebook, 'Sản xuất')
        produce.columnconfigure(1, weight=1)
        ttk.Checkbutton(produce, text='Bố cục Premium', variable=self.premium).grid(row=0, column=0, columnspan=2, sticky='w', pady=10)
        ttk.Checkbutton(produce, text='Xuất tối đa 3 Shorts (1080 × 1920)', variable=self.shorts).grid(row=1, column=0, columnspan=2, sticky='w', pady=10)
        self.entry(produce, 'Bảng màu', self.theme, 2, list(PALETTES))
        ttk.Label(produce, text='Shorts lấy trọn lượt thoại, tối đa 58 giây.\nKhông gọi thêm TTS để cắt Shorts.\nAudio cùng nội dung/giọng/tốc độ được dùng lại.', wraplength=320, foreground='#9badc5').grid(row=3, column=0, columnspan=2, sticky='w', pady=15)
        ttk.Button(produce, text='Mở tập cũ để nâng cấp…', command=self.open_episode).grid(row=4, column=0, columnspan=2, sticky='ew', pady=6)
        ttk.Button(produce, text='Viết prompt ảnh & bộ đăng', command=self.prepare_assets).grid(row=5, column=0, columnspan=2, sticky='ew', pady=6)
        ideas = ttk.Frame(notebook, padding=10)
        notebook.add(ideas, text='Ý tưởng')
        ttk.Label(ideas, text='12 ý tưởng cho series đời thường\nGợi ý biên tập, không phải bảng xu hướng trực tiếp.', wraplength=330, foreground='#9badc5').pack(anchor='w', pady=(0, 10))
        self.topic_list = tk.Listbox(ideas, bg='#111d30', fg='#e5edf7', selectbackground='#16796f', font=('Segoe UI', 10), width=38, height=15, exportselection=False)
        for group, topic in TOPICS:
            self.topic_list.insert('end', f'{group} · {topic}')
        self.topic_list.pack(fill='both', expand=True)
        ttk.Button(ideas, text='Dùng ý tưởng đã chọn', command=self.use_idea).pack(fill='x', pady=10)
        ttk.Button(ideas, text='Tìm chủ đề trên YouTube', command=self.research_topic).pack(fill='x', pady=4)
        voice_settings = self.form_tab(notebook, 'ElevenLabs')
        voice_settings.columnconfigure(1, weight=1)
        create.columnconfigure(1, weight=1)
        settings.columnconfigure(1, weight=1)
        self.entry(create, 'Chủ đề', self.topic, 0)
        self.entry(create, 'Trình độ', self.level, 1, ['HSK 1–2', 'HSK 3–4', 'HSK 5–6'])
        self.entry(create, 'Tổng phút ≈', self.minutes, 2, ['3', '5', '10', '12', '15', '20'])
        self.entry(create, 'Tên kênh', self.brand, 3)
        count_control = self.entry(create, 'Số người nói', self.speaker_count, 4, [str(i) for i in range(1, 11)])
        count_control.bind('<<ComboboxSelected>>', self.change_speaker_count)
        self.cast_frame = ttk.Frame(create)
        self.cast_frame.grid(row=5, column=0, columnspan=2, sticky='ew', pady=8)
        self.render_cast_voices()
        self.generate_button = ttk.Button(create, text='1. Tạo kịch bản JSON', style='Accent.TButton', command=self.generate)
        self.generate_button.grid(row=6, column=0, columnspan=2, sticky='ew', pady=8)
        files = ttk.Frame(create)
        files.grid(row=7, column=0, columnspan=2, sticky='ew', pady=4)
        for title, action in [('Bài mẫu', self.sample), ('Mở JSON', self.load), ('Lưu JSON', self.save)]:
            ttk.Button(files, text=title, command=action).pack(side='left', fill='x', expand=True, padx=2)
        self.draft_button = ttk.Button(files, text='Viết bài', command=lambda: self.generate(draft_only=True))
        self.draft_button.pack(side='left', fill='x', expand=True, padx=2)
        self.export_button = ttk.Button(create, text='2. Chọn giọng & xuất MP4…', style='Accent.TButton', command=self.export)
        self.export_button.grid(row=8, column=0, columnspan=2, sticky='ew', pady=(8, 4))
        ttk.Button(create, text='Tiếp tục lần xuất bị gián đoạn…', command=self.resume_export).grid(row=9, column=0, columnspan=2, sticky='ew', pady=4)
        ttk.Button(create, text='Dừng tác vụ', command=self.cancel.set).grid(row=10, column=0, columnspan=2, sticky='ew', pady=4)
        ttk.Button(create, text='Mở thư mục kết quả', command=self.open_output).grid(row=11, column=0, columnspan=2, sticky='ew', pady=4)
        self.entry(settings, 'Nguồn viết bài', self.ai_provider, 0, ['ChatGPT Web', 'Gemini API'])
        ttk.Label(settings, text='Dùng tab ChatGPT đang mở trên Edge của bạn.', foreground='#9badc5', wraplength=330).grid(row=1, column=0, columnspan=2, sticky='w', pady=6)
        ttk.Button(settings, text='Kết nối Edge hiện tại…', command=self.login_chatgpt).grid(row=2, column=0, columnspan=2, sticky='ew', pady=4)
        ttk.Button(settings, text='Kiểm tra kết nối Edge', command=lambda: self.login_chatgpt(verify=True)).grid(row=3, column=0, columnspan=2, sticky='ew', pady=4)
        ttk.Label(settings, text='Viết bài chỉ lưu JSON. Bộ đăng và ảnh tạo riêng trên tab Edge để bạn tự tải/đăng.', foreground='#9badc5', wraplength=330).grid(row=4, column=0, columnspan=2, sticky='w', pady=4)
        self.entry(settings, 'Gemini key (dự phòng)', self.key, 5, secret=True)
        self.entry(settings, 'Model Gemini', self.model, 6)
        self.entry(voice_settings, 'ElevenLabs key', self.eleven_key, 0, secret=True)
        ttk.Button(voice_settings, text='Kho 10 giọng…', command=self.edit_voice_bank).grid(row=1, column=0, columnspan=2, sticky='ew', pady=8)
        ttk.Label(voice_settings, text='Lưu tối đa 10 Voice ID, đặt tên dễ nhớ.\nMỗi kịch bản được chọn giọng riêng cho từng nhân vật.', foreground='#9badc5', wraplength=330).grid(row=2, column=0, columnspan=2, sticky='w', pady=4)
        self.entry(voice_settings, 'Model giọng', self.tts_model, 3, [*EXPRESSIVE_MODELS, 'eleven_multilingual_v2', 'eleven_flash_v2_5', 'eleven_turbo_v2_5'])
        self.entry(voice_settings, 'Tốc độ', self.rate, 4, ['0.7', '0.8', '0.9', '1.0', '1.1', '1.2'])
        self.entry(voice_settings, 'Độ ổn định', self.stability, 5, ['0.2', '0.35', '0.5', '0.75', '1.0'])
        self.entry(voice_settings, 'Nghỉ giữa lượt (s)', self.turn_gap, 6, ['0', '0.1', '0.2', '0.3', '0.45'])
        ttk.Label(voice_settings, text='Giọng biểu cảm: chọn v4, sang tab Cảm xúc & nghe thử.\nV4 đổi tốc độ bằng xử lý audio tại máy; không đổi cao độ.\nTạo giọng gửi lời thoại tới ElevenLabs và có thể trừ credit.', foreground='#9badc5', wraplength=350).grid(row=7, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Button(voice_settings, text='Mở ElevenLabs', command=lambda: __import__('webbrowser').open('https://elevenlabs.io/app/voice-library')).grid(row=8, column=0, columnspan=2, sticky='ew', pady=4)
        self.entry(settings, 'Chất lượng', self.resolution, 7, ['1080p', '720p'])
        ttk.Button(voice_settings, text='Lưu cấu hình ngay', command=lambda: self.persist_settings(notify=True)).grid(row=9, column=0, columnspan=2, sticky='ew', pady=4)
        self.entry(settings, 'Thư mục xuất', self.folder, 8)
        ttk.Button(settings, text='Chọn thư mục…', command=self.choose_folder).grid(row=9, column=0, columnspan=2, sticky='ew', pady=4)
        ttk.Label(settings, text='ChatGPT dùng tab đang đăng nhập trên Microsoft Edge. Chọn model trong tab đó. Cài tiện ích kết nối cục bộ một lần; không tạo trình duyệt hay hồ sơ mới.\nCấu hình giọng ở tab ElevenLabs.', foreground='#9badc5', wraplength=340).grid(row=10, column=0, columnspan=2, sticky='w', pady=4)
        tabs = ttk.Notebook(right)
        tabs.pack(fill='both', expand=True)
        edit = ttk.Frame(tabs)
        view = ttk.Frame(tabs)
        tabs.add(edit, text='Kịch bản · có thể chỉnh sửa')
        tabs.add(view, text='Xem bố cục')
        publish = self.form_tab(tabs, 'Ảnh & bộ đăng')
        ttk.Button(publish, text='Kiểm tra kịch bản & làm mới bộ đăng', command=self.refresh_kit).pack(fill='x', pady=8)
        self.asset_action_buttons = []
        self.build_performance_tab(tabs)
        def asset_button(text, command):
            button = ttk.Button(publish, text=text, command=command)
            button.pack(fill='x', pady=5)
            self.asset_action_buttons.append(button)
        asset_button('1. Viết prompt ảnh + tên video, tiêu đề, mô tả', self.prepare_assets)
        self.asset_video_name = tk.StringVar()
        self.asset_title = tk.StringVar()
        self.asset_source = None
        self.asset_conversation = None
        ttk.Label(publish, text='Tên video / tên file gợi ý').pack(anchor='w', pady=(8, 2))
        ttk.Entry(publish, textvariable=self.asset_video_name).pack(fill='x')
        ttk.Label(publish, text='Tiêu đề YouTube · chọn 1 trong 3 hoặc sửa trực tiếp').pack(anchor='w', pady=(8, 2))
        self.asset_title_choices = ttk.Combobox(publish, textvariable=self.asset_title, state='normal')
        self.asset_title_choices.pack(fill='x')
        ttk.Label(publish, text='Mô tả YouTube · có thể chỉnh sửa').pack(anchor='w', pady=(8, 2))
        self.asset_description = tk.Text(publish, height=6, wrap='word', bg='#111d30', fg='#e5edf7', insertbackground='#62ded0', padx=10, pady=8, undo=True)
        self.asset_description.pack(fill='x')
        asset_button('Gửi tên video, tiêu đề & mô tả lên chat để copy', self.present_asset_copy)
        ttk.Label(publish, text='Prompt ảnh / thumbnail · xem và sửa trước khi tạo').pack(anchor='w', pady=(8, 2))
        self.asset_image_prompt = tk.Text(publish, height=7, wrap='word', bg='#111d30', fg='#e5edf7', insertbackground='#62ded0', padx=10, pady=8, undo=True)
        self.asset_image_prompt.pack(fill='x')
        asset_button('2. Tạo ảnh từ prompt trên ChatGPT', self.create_asset_image)
        ttk.Label(publish, text='Bước 1 chỉ viết prompt. Bước 2 mới tạo ảnh trên Edge để bạn tự tải. Kịch bản JSON được giữ riêng.', foreground='#9badc5', wraplength=650).pack(anchor='w', pady=8)
        self.kit_text = tk.Text(publish, height=7, wrap='word', bg='#111d30', fg='#e5edf7', font=('Segoe UI', 11), padx=16, pady=14)
        self.kit_text.pack(fill='x')
        self.kit_text.insert('end', 'Nạp bài mẫu, mở JSON hoặc viết kịch bản để xem kiểm tra nội dung và bộ tiêu đề.')
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
        for part, title in enumerate(['Video ngang', 'Shorts dọc']):
            ttk.Button(toolbar, text=title, command=lambda p=part: self.show_preview(p)).pack(side='left', padx=4, pady=8)
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(side='bottom', fill='x', pady=(8, 4))
        ttk.Label(outer, textvariable=self.status, foreground='#a9c4db', wraplength=1120).pack(side='bottom', anchor='w', pady=(8, 0))
        panes.pack(fill='both', expand=True)

    def change_speaker_count(self, *_):
        count = self.get_speaker_count()
        self.cast.set(', '.join(f'Người {i}' for i in range(1, count+1)))
        self.render_cast_voices()

    def get_speaker_count(self):
        try:
            count = int(self.speaker_count.get())
        except ValueError:
            raise ValueError('Chọn số người nói từ 1 đến 10.') from None
        if not 1 <= count <= 10:
            raise ValueError('Chọn số người nói từ 1 đến 10.')
        return count

    def render_cast_voices(self):
        for child in self.cast_frame.winfo_children():
            child.destroy()
        self.cast_frame.columnconfigure(1, weight=1)
        try:
            count = self.get_speaker_count()
        except ValueError:
            self.speaker_count.set('2')
            count = 2
        names = [name.strip() for name in re.split('[,，]', self.cast.get())]
        if len(names) != count:
            names = [f'Người {i}' for i in range(1, count+1)]
        available = {}
        for i, (name, voice) in enumerate(zip(self.voice_names, self.voice_ids), 1):
            if voice.get().strip():
                label = f'{i:02d} · {name.get().strip() or voice.get().strip()}'
                available[label] = str(i)
        for i, name in enumerate(names):
            choices = dict(available)
            slot_value = self.cast_slots[i].get()
            if slot_value.startswith('saved:'):
                saved_voice = slot_value.removeprefix('saved:')
                choices[f'Giọng trong JSON · {saved_voice}'] = slot_value
            ttk.Label(self.cast_frame, text=name, wraplength=110).grid(row=i, column=0, sticky='w', padx=(0, 12), pady=4)
            value = next((label for label, slot in choices.items() if slot == slot_value), None)
            if value is None and choices:
                value = list(choices)[min(i, len(choices)-1)]
                self.cast_slots[i].set(choices[value])
            self.cast_choices[i].set(value or 'Chưa có Voice ID trong kho')
            combo = ttk.Combobox(self.cast_frame, textvariable=self.cast_choices[i], values=list(choices), state='readonly', width=27)
            combo.grid(row=i, column=1, sticky='ew', pady=4)
            def selected(_, index=i, choices=choices):
                self.cast_slots[index].set(choices[self.cast_choices[index].get()])
                # Update this script's assignment too, without changing its speaker names.
                if index < len(names):
                    voice = self.voice_from_slot(self.cast_slots[index].get())
                    self.speaker_voices[names[index]] = voice
                    self.save_voice_to_editor(names[index], voice)
            combo.bind('<<ComboboxSelected>>', selected)
        ttk.Button(self.cast_frame, text='Kho 10 giọng…', command=self.edit_voice_bank).grid(row=count, column=0, columnspan=2, sticky='ew', pady=5)

    def save_voice_to_editor(self, speaker, voice):
        if not hasattr(self, 'editor'):
            return
        try:
            lesson = self.get_lesson()
        except (ValueError, TypeError):
            return
        if speaker in lesson['speakers']:
            lesson.setdefault('speaker_voices', {})[speaker] = voice
            self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', json.dumps(lesson, ensure_ascii=False, indent=2))

    def cast_selection(self):
        count = self.get_speaker_count()
        # Generated scripts always get automatic speaker labels; no name entry required.
        names = [f'Người {i}' for i in range(1, count+1)]
        mapping = {}
        for i, name in enumerate(names):
            voice = self.voice_from_slot(self.cast_slots[i].get())
            if re.fullmatch(r'[A-Za-z0-9_-]+', voice):
                mapping[name] = voice
        return names, mapping

    def voice_from_slot(self, value):
        if value.startswith('saved:'):
            return value.removeprefix('saved:')
        try:
            slot = int(value)
        except ValueError:
            return ''
        return self.voice_ids[slot-1].get().strip() if 1 <= slot <= 10 else ''

    def form_tab(self, notebook, title):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text=title)
        canvas = tk.Canvas(tab, bg='#0b1120', highlightthickness=0, borderwidth=0, width=440)
        scrollbar = ttk.Scrollbar(tab, command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas, padding=10)
        content = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(content, width=event.width))
        def wheel(event):
            if str(event.widget).startswith(str(tab) + '.'):
                if body.winfo_reqheight() > canvas.winfo_height():
                    canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
                return 'break'
        self.bind('<MouseWheel>', wheel, add='+')
        return body

    def modal(self, title, width, height, parent=None):
        parent = parent or self
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.configure(bg='#0b1120')
        dialog.transient(parent)
        width = min(width, self.winfo_screenwidth() - 60)
        height = min(height, self.winfo_screenheight() - 100)
        dialog.geometry(f'{width}x{height}+{max(0, (self.winfo_screenwidth()-width)//2)}+{max(0, (self.winfo_screenheight()-height)//2)}')
        dialog.resizable(True, True)
        dialog.bind('<Escape>', lambda _: dialog.destroy())
        dialog.grab_set()
        return dialog

    def modal_body(self, dialog):
        # Keep action buttons reachable on smaller displays, even with ten rows.
        footer = ttk.Frame(dialog, padding=(20, 8, 20, 16))
        footer.pack(side='bottom', fill='x')
        area = ttk.Frame(dialog)
        area.pack(fill='both', expand=True)
        canvas = tk.Canvas(area, bg='#0b1120', highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(area, command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas, padding=20)
        content = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(content, width=event.width))
        def wheel(event):
            if body.winfo_reqheight() > canvas.winfo_height():
                canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
            return 'break'
        dialog.bind('<MouseWheel>', wheel)
        return body, footer

    def edit_voice_bank(self, parent=None):
        if self.busy:
            return
        dialog = self.modal('Kho 10 giọng · lưu trong .env', 760, 570, parent)
        body, actions = self.modal_body(dialog)
        body.columnconfigure(2, weight=1)
        ttk.Label(body, text='KHO GIỌNG ELEVENLABS', font=('Segoe UI', 15, 'bold'), foreground='#62ded0').grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Label(body, text='Chỉ cần điền các giọng bạn muốn dùng. Tên gợi nhớ không phải tên nhân vật.', foreground='#9badc5').grid(row=1, column=0, columnspan=3, sticky='w', pady=(5, 14))
        ttk.Label(body, text='Ô').grid(row=2, column=0, sticky='w')
        ttk.Label(body, text='Tên gợi nhớ (tùy chọn)').grid(row=2, column=1, sticky='w')
        ttk.Label(body, text='Voice ID').grid(row=2, column=2, sticky='w')
        ids = [tk.StringVar(value=v.get()) for v in self.voice_ids]
        names = [tk.StringVar(value=v.get()) for v in self.voice_names]
        for i, (name, voice_id) in enumerate(zip(names, ids), 1):
            ttk.Label(body, text=f'{i:02d}').grid(row=i+2, column=0, padx=(0, 12))
            ttk.Entry(body, textvariable=name, width=23).grid(row=i+2, column=1, sticky='ew', padx=(0, 12), pady=4)
            ttk.Entry(body, textvariable=voice_id, width=38).grid(row=i+2, column=2, sticky='ew', pady=4)
        ttk.Label(body, text='Đọc ELEVENLABS_VOICE_1…10 và ELEVENLABS_VOICE_1_NAME…10_NAME từ .env.', foreground='#9badc5').grid(row=13, column=0, columnspan=3, sticky='w', pady=12)
        def save_bank():
            for i, value in enumerate(ids, 1):
                if value.get().strip() and not re.fullmatch(r'[A-Za-z0-9_-]+', value.get().strip()):
                    messagebox.showerror('Voice ID chưa hợp lệ', f'Ô {i}: dán Voice ID, không dán tên hoặc URL.', parent=dialog)
                    return
            for destination, value in zip(self.voice_ids, ids):
                destination.set(value.get().strip())
            for destination, value in zip(self.voice_names, names):
                destination.set(value.get().strip())
            if self.persist_settings():
                self.status.set('Đã lưu kho giọng vào .env. Chọn giọng riêng khi xuất từng kịch bản.')
                dialog.destroy()
        ttk.Button(actions, text='Lưu kho giọng', style='Accent.TButton', command=save_bank).pack(side='right')
        ttk.Button(actions, text='Hủy', command=dialog.destroy).pack(side='right', padx=6)
        self.wait_window(dialog)
        if parent is not None and parent.winfo_exists():
            parent.grab_set()
        self.render_cast_voices()

    def choose_voices(self, lesson, preview=False):
        used = [name for name in lesson['speakers'] if any(line['speaker'] == name for line in lesson['lines'])]
        dialog = self.modal('Chọn giọng cho kịch bản', 760, 290 + len(used)*34)
        body, actions = self.modal_body(dialog)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text='GÁN GIỌNG CHO TỪNG NHÂN VẬT', font=('Segoe UI', 15, 'bold'), foreground='#62ded0').grid(row=0, column=0, columnspan=2, sticky='w')
        ttk.Label(body, text=f'{lesson["title_vi"][:75]}\n{len(used)} nhân vật có lời thoại · {len(lesson["lines"])} lượt', foreground='#9badc5', wraplength=680).grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 14))
        variables, widgets, choices = {}, {}, {}
        remembered = dict(lesson.get('speaker_voices', {}))
        remembered.update(self.speaker_voices)
        for i, speaker in enumerate(used):
            ttk.Label(body, text=speaker, wraplength=160).grid(row=i+2, column=0, sticky='w', padx=(0, 15), pady=5)
            variables[speaker] = tk.StringVar()
            widgets[speaker] = ttk.Combobox(body, textvariable=variables[speaker], state='readonly', width=50)
            widgets[speaker].grid(row=i+2, column=1, sticky='ew', pady=5)
        def refresh_choices():
            for speaker in used:
                old_label = variables[speaker].get()
                selected = choices.get(speaker, {}).get(old_label, remembered.get(speaker, ''))
                slot = re.match(r'^(\d{2}) ·', old_label) if speaker in choices else None
                available = {}
                for i, (name, voice) in enumerate(zip(self.voice_names, self.voice_ids), 1):
                    label = f'{i:02d} · {name.get().strip() or f"Giọng {i}"}'
                    label += f' · …{voice.get().strip()[-6:]}' if voice.get().strip() else ' · [chưa nhập ID]'
                    available[label] = voice.get().strip()
                if slot:
                    # Editing a bank slot should update the selected voice, not retain its old ID.
                    selected = list(available.values())[int(slot.group(1))-1]
                if selected and selected not in available.values():
                    available[f'Giọng đã lưu trong tập · {selected}'] = selected
                choices[speaker] = available
                widgets[speaker].configure(values=list(available))
                matching = (list(available)[int(slot.group(1))-1] if slot else
                            next((label for label, voice in available.items() if selected and voice == selected), None))
                variables[speaker].set(matching or list(available)[lesson['speakers'].index(speaker)])
        refresh_choices()
        row = len(used) + 2
        ttk.Button(body, text='Sửa kho 10 giọng…', command=lambda: (self.edit_voice_bank(dialog), refresh_choices())).grid(row=row, column=0, columnspan=2, sticky='w', pady=10)
        ttk.Label(body, text=f'Model: {self.tts_model.get()}  ·  Biểu cảm: {self.expression.get()}  ·  Tốc độ: {self.rate.get()}\nNghe thử hoặc xuất sẽ gửi lời thoại chưa có cache tới ElevenLabs và có thể trừ credit.', foreground='#9badc5', wraplength=680).grid(row=row+1, column=0, columnspan=2, sticky='w', pady=8)
        result = {}
        def confirm():
            selected = {speaker: choices[speaker].get(variables[speaker].get(), '') for speaker in used}
            missing = [speaker for speaker, voice in selected.items() if not voice]
            if missing:
                messagebox.showerror('Chưa chọn đủ giọng', 'Nhập Voice ID vào kho rồi chọn giọng cho: ' + ', '.join(missing), parent=dialog)
                return
            if any(not re.fullmatch(r'[A-Za-z0-9_-]+', voice) for voice in selected.values()):
                messagebox.showerror('Voice ID chưa hợp lệ', 'Sửa Voice ID trong kho giọng hoặc kịch bản; không dùng URL.', parent=dialog)
                return
            result.update(selected)
            dialog.destroy()
        ttk.Button(actions, text='Tạo giọng & nghe thử' if preview else 'Tạo giọng & xuất MP4', style='Accent.TButton', command=confirm).pack(side='right')
        ttk.Button(actions, text='Hủy', command=dialog.destroy).pack(side='right', padx=6)
        self.wait_window(dialog)
        return result or None

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

    def build_performance_tab(self, tabs):
        body = self.form_tab(tabs, 'Cảm xúc & nghe thử')
        ttk.Label(body, text='GIỌNG NÓI THEO TÌNH HUỐNG', font=('Segoe UI', 15, 'bold'), foreground='#62ded0').pack(anchor='w', pady=8)
        ttk.Label(body, text='Kịch bản mới tự có cảm xúc theo từng lượt. Với JSON cũ, bấm phân tích bên dưới. Chữ Hán, pinyin và bản dịch được giữ nguyên.', wraplength=680).pack(anchor='w', pady=5)
        settings = ttk.Frame(body)
        settings.pack(fill='x', pady=6)
        self.entry(settings, 'Mức biểu cảm', self.expression, 0, list(LEVELS))
        def action(text, command):
            button = ttk.Button(body, text=text, command=command)
            button.pack(fill='x', pady=4)
            self.asset_action_buttons.append(button)
        action('Dùng model biểu cảm v4', self.enable_expression)
        action('1. ChatGPT phân tích cảm xúc cho kịch bản hiện tại', self.annotate_emotions)
        action('Làm mới danh sách từ JSON đang sửa', self.refresh_emotions)
        table_frame = ttk.Frame(body)
        table_frame.pack(fill='both', expand=True, pady=8)
        self.emotion_table = ttk.Treeview(table_frame, columns=('turn', 'speaker', 'zh', 'emotion', 'strength'), show='headings', height=9, selectmode='browse')
        for key, label, width in [('turn', 'Lượt', 50), ('speaker', 'Người nói', 90), ('zh', 'Lời thoại', 270), ('emotion', 'Cảm xúc', 110), ('strength', 'Mức câu', 65)]:
            self.emotion_table.heading(key, text=label)
            self.emotion_table.column(key, width=width, minwidth=50, stretch=key == 'zh')
        scroll = ttk.Scrollbar(table_frame, command=self.emotion_table.yview)
        scroll.pack(side='right', fill='y')
        self.emotion_table.configure(yscrollcommand=scroll.set)
        self.emotion_table.pack(side='left', fill='both', expand=True)
        self.emotion_table.bind('<<TreeviewSelect>>', self.select_emotion)
        controls = ttk.Frame(body)
        controls.pack(fill='x', pady=5)
        self.selected_emotion = tk.StringVar(value=EMOTIONS['neutral'])
        self.selected_strength = tk.StringVar(value='2')
        self.entry(controls, 'Cảm xúc câu đang chọn', self.selected_emotion, 0, list(EMOTIONS.values()))
        self.entry(controls, 'Mức câu (1 nhẹ → 3 cao)', self.selected_strength, 1, ['1', '2', '3'])
        action('Áp dụng cảm xúc cho câu đang chọn', self.edit_emotion)
        self.entry(controls, 'Nghe từ lượt số', self.preview_start, 2, [str(i) for i in range(1, 151)])
        self.entry(controls, 'Số lượt nghe thử', self.preview_count, 3, ['1', '2', '3', '5'])
        action('2. Chọn giọng & tạo bản nghe thử', self.preview_speech)
        action('Phát lại bản nghe thử đã có', self.play_preview)
        action('Dừng nghe', self.stop_preview)
        ttk.Label(body, text='Chọn một câu trong bảng để nghe từ câu đó. Nghe thử dùng credit ElevenLabs cho audio mới; cùng cấu hình sẽ dùng lại khi xuất MP4. Độ biểu cảm phụ thuộc Voice ID. Model v2 dùng mức Tắt.', foreground='#9badc5', wraplength=680).pack(anchor='w', pady=8)

    def enable_expression(self):
        if self.busy:
            return
        self.tts_model.set('eleven_v4')
        if self.expression.get() == 'Tắt':
            self.expression.set('Nhẹ')
        self.legacy_audio_settings = None
        self.status.set('Đã chọn v4. Phân tích cảm xúc, chọn giọng và nghe thử trước khi xuất cả tập.')

    @staticmethod
    def performance_key(lesson):
        return json.dumps({k: v for k, v in lesson.items() if k != 'speaker_voices'}, ensure_ascii=False, sort_keys=True)

    def refresh_emotions(self):
        try:
            lesson = self.get_lesson()
            self.emotion_source = self.performance_key(lesson)
            self.emotion_table.delete(*self.emotion_table.get_children())
            for i, line in enumerate(lesson['lines']):
                self.emotion_table.insert('', 'end', iid=str(i), values=(i+1, line['speaker'], line['zh'], EMOTIONS[line.get('emotion', 'neutral')], line.get('emotion_strength', 2)))
        except Exception as exc:
            self.status.set('Chưa đọc được cảm xúc: ' + str(exc))

    def select_emotion(self, event=None):
        selected = self.emotion_table.selection()
        if selected:
            values = self.emotion_table.item(selected[0], 'values')
            self.selected_emotion.set(values[3])
            self.selected_strength.set(values[4])
            self.preview_start.set(str(int(selected[0])+1))

    def edit_emotion(self):
        if self.busy:
            return
        try:
            lesson = self.get_lesson()
            if self.performance_key(lesson) != self.emotion_source:
                self.refresh_emotions()
                raise ValueError('JSON đã thay đổi. Danh sách vừa làm mới; hãy chọn lại câu cần sửa.')
            selected = self.emotion_table.selection()
            if not selected:
                raise ValueError('Chọn một câu trong bảng trước.')
            emotion = next(key for key, label in EMOTIONS.items() if label == self.selected_emotion.get())
            index = int(selected[0])
            lesson['lines'][index].update(emotion=emotion, emotion_strength=int(self.selected_strength.get()))
            validate_lesson(lesson)
            self.put_lesson(lesson)
            self.emotion_table.selection_set(str(index))
            self.status.set('Đã cập nhật cảm xúc trong JSON. Bấm Lưu JSON để giữ bản chỉnh sửa.')
        except Exception as exc:
            messagebox.showerror('Chưa sửa được cảm xúc', str(exc))

    def annotate_emotions(self):
        if self.busy:
            return
        try:
            lesson = copy.deepcopy(self.get_lesson())
            source = self.performance_key(lesson)
            chat = self.get_chatgpt()
        except Exception as exc:
            messagebox.showerror('Chưa phân tích được', str(exc))
            return
        self.status.set('ChatGPT đang đọc tình huống và gán cảm xúc cho từng lượt…')
        def work():
            from chatgpt_web import json_response
            result = apply_annotations(lesson, json_response(chat.send(annotation_prompt(lesson), self.cancel)))
            self.events.put(('performance', {'source': source, 'lesson': result}))
        self.launch(work)

    def apply_performance(self, value):
        current = self.get_lesson()
        if self.performance_key(current) != value['source']:
            raise ValueError('Kịch bản đã được sửa khi ChatGPT phân tích; chưa áp dụng kết quả cũ. Bấm phân tích lại.')
        result = value['lesson']
        if 'speaker_voices' in current:
            result['speaker_voices'] = current['speaker_voices']
        self.put_lesson(result)
        out = Path(self.folder.get()).expanduser() / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_cam_xuc')
        out.mkdir(parents=True, exist_ok=True)
        (out/'lesson.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        self.last_output = out
        self.status.set('Đã gán cảm xúc và lưu JSON: ' + str(out/'lesson.json'))

    def preview_speech(self):
        if self.busy or not self.check_eleven():
            return
        try:
            lesson = self.get_lesson()
            start, count = int(self.preview_start.get()), int(self.preview_count.get())
            if not 1 <= start <= len(lesson['lines']) or count not in (1, 2, 3, 5):
                raise ValueError('Chọn lượt bắt đầu có trong kịch bản và nghe 1, 2, 3 hoặc 5 lượt.')
            check_expression(self.tts_model.get(), LEVELS[self.expression.get()])
        except Exception as exc:
            messagebox.showerror('Chưa nghe thử được', str(exc))
            return
        mapping = self.choose_voices(lesson, preview=True)
        if mapping is None:
            return
        lesson['speaker_voices'] = mapping
        self.put_lesson(lesson)
        options = dict(self.export_options(), audio_preview=True, preview_start=start, preview_count=count)
        out = Path(self.folder.get()).expanduser() / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_nghe_thu')
        def work():
            result = export_video(lesson, out, options, lambda s: self.events.put(('status', s)), self.cancel)
            self.events.put(('audio_preview', result))
        self.launch(work)

    def play_preview(self):
        if self.preview_audio_path and self.preview_audio_path.is_file():
            import winsound
            winsound.PlaySound(str(self.preview_audio_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            self.status.set('Chưa có bản nghe thử. Bấm “Chọn giọng & tạo bản nghe thử” trước.')

    def stop_preview(self):
        import winsound
        winsound.PlaySound(None, 0)

    def put_lesson(self, lesson, sync_cast=True):
        self.speaker_voices = dict(lesson.get('speaker_voices', {}))
        if sync_cast:
            self.speaker_count.set(str(len(lesson['speakers'])))
            self.cast.set(', '.join(lesson['speakers']))
            for i, speaker in enumerate(lesson['speakers']):
                voice = self.speaker_voices.get(speaker)
                match = next((str(j) for j, value in enumerate(self.voice_ids, 1) if voice and value.get().strip() == voice), None)
                if match:
                    self.cast_slots[i].set(match)
                elif voice:
                    self.cast_slots[i].set('saved:' + voice)
            self.render_cast_voices()
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', json.dumps(lesson, ensure_ascii=False, indent=2))
        self.show_preview(0)
        self.refresh_kit()
        self.reset_asset_source(lesson)
        self.refresh_emotions()

    def sample(self, sync_cast=True):
        if self.busy:
            return
        self.reuse_dir = None
        self.legacy_audio_settings = None
        self.put_lesson(json.loads((ROOT / 'sample_lesson.json').read_text(encoding='utf-8')), sync_cast=sync_cast)
        self.status.set('Đã nạp bài tiếng Trung. Điền key và Voice ID trong tab ElevenLabs trước khi xuất.')

    def load(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(filetypes=[('Kịch bản JSON', '*.json')])
        if path:
            try:
                self.reuse_dir = None
                self.legacy_audio_settings = None
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
            lesson, options = self.get_lesson(), self.export_options()
            if part == 2:
                im = thumbnail(lesson, options).resize((640, 360))
            elif self.premium.get():
                im = scene(lesson, 0, options, portrait=part == 1)
                im.thumbnail((640, 350))
            else:
                im = card(lesson, part, self.brand.get(), 0, (640, 360))
            self.preview_image = ImageTk.PhotoImage(im)
            self.preview.configure(image=self.preview_image)
        except Exception as exc:
            self.status.set('Chưa xem trước được: ' + str(exc))

    def use_idea(self):
        chosen = self.topic_list.curselection()
        if chosen:
            self.topic.set(TOPICS[chosen[0]][1])
            self.status.set('Đã chọn ý tưởng. Mở tab Bài học để viết kịch bản.')

    def research_topic(self):
        import urllib.parse
        import webbrowser
        chosen = self.topic_list.curselection()
        subject = TOPICS[chosen[0]][1] if chosen else self.topic.get()
        webbrowser.open('https://www.youtube.com/results?search_query=' + urllib.parse.quote('học tiếng Trung ' + subject))

    def refresh_kit(self):
        try:
            lesson = self.get_lesson()
            report = audit_lesson(lesson)
            text = f'KIỂM TRA KỊCH BẢN\n{report["turns"]} lượt · {report["hanzi"]} chữ Hán · khoảng {report["estimated_minutes"]} phút\n'
            text += '\n'.join(report['warnings']) or 'Chưa phát hiện lỗi cấu trúc hoặc câu trùng.'
            text += '\n' + report['note']
            text += '\n\nBỘ ĐĂNG TRÊN EDGE\nBấm “Viết prompt ảnh + tên video, tiêu đề, mô tả”, sửa nội dung nếu cần, rồi dùng nút Tạo ảnh hoặc Gửi phần chữ lên chat. Kịch bản JSON được giữ riêng.'
            self.kit_text.delete('1.0', 'end')
            self.kit_text.insert('end', text)
        except Exception as exc:
            self.status.set('Cần kịch bản hợp lệ: ' + str(exc))

    def save_kit(self):
        if self.busy:
            return
        try:
            lesson = self.get_lesson()
            out = Path(self.folder.get()).expanduser() / ('kit_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
            publishing_kit(lesson, out, self.export_options())
            self.last_output = out
            self.refresh_kit()
            self.status.set('Đã lưu bộ đăng: ' + str(out))
            os.startfile(str(out))
        except Exception as exc:
            messagebox.showerror('Chưa xuất được bộ đăng', str(exc))

    def open_episode(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(title='Chọn thư mục tập có lesson.json và assets')
        if folder:
            try:
                path = Path(folder)
                lesson = validate_lesson(json.loads((path/'lesson.json').read_text(encoding='utf-8-sig')))
                manifest_file = path/'manifest.json'
                self.legacy_audio_settings = None
                if manifest_file.is_file():
                    old = json.loads(manifest_file.read_text(encoding='utf-8'))
                    voices = old.get('voices', [])
                    mapping = old.get('speaker_voices') or dict(zip(lesson['speakers'], voices))
                    if mapping:
                        lesson['speaker_voices'] = mapping
                    if old.get('tts_model'):
                        self.tts_model.set(old['tts_model'])
                    if old.get('speed'):
                        self.rate.set(str(old['speed']))
                    self.stability.set(str(old.get('stability', 0.5)))
                    self.turn_gap.set(str(old.get('turn_gap', 0.45)))
                    self.expression.set(next((label for label, key in LEVELS.items() if key == old.get('expression', 'off')), 'Tắt'))
                    if old.get('legacy_audio', 'speech_context' not in old) and self.tts_model.get() not in EXPRESSIVE_MODELS:
                        self.legacy_audio_settings = {
                            'speaker_voices': mapping, 'tts_model': self.tts_model.get(),
                            'speed': float(self.rate.get()), 'stability': float(self.stability.get()),
                            'turn_gap': float(self.turn_gap.get()),
                        }
                self.cast.set(', '.join(lesson['speakers']))
                self.reuse_dir = path
                self.put_lesson(lesson)
                self.status.set('Đã mở tập cũ. Giữ nguyên giọng/model/tốc độ để dùng lại audio; bản mới xuất vào thư mục riêng.')
            except Exception as exc:
                messagebox.showerror('Không mở được tập', str(exc))

    def launch(self, work):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.generate_button.configure(state='disabled')
        self.export_button.configure(state='disabled')
        self.draft_button.configure(state='disabled')
        for button in self.asset_action_buttons:
            button.configure(state='disabled')
        self.progress.start(12)
        def worker():
            try:
                work()
            except Cancelled as exc:
                self.events.put(('status', str(exc)))
            except Exception as exc:
                try:
                    with (ROOT / 'task_errors.log').open('a', encoding='utf-8') as stream:
                        stream.write(datetime.now().isoformat(timespec='seconds') + ' · ' + str(exc) + '\n')
                except OSError:
                    pass
                self.events.put(('error', str(exc)))
            finally:
                self.events.put(('idle', None))
        threading.Thread(target=worker, daemon=True).start()

    def get_chatgpt(self):
        from edge_bridge import EdgeChatGPT
        if self.chatgpt is None:
            self.chatgpt = EdgeChatGPT()
        return self.chatgpt

    def login_chatgpt(self, verify=False):
        if self.busy:
            return
        try:
            chat = self.get_chatgpt()
        except Exception as exc:
            messagebox.showerror('Kết nối Edge', str(exc))
            return
        if verify:
            self.status.set('Đã kết nối tab ChatGPT trên Edge.' if chat.logged_in() else 'Chưa kết nối. Mở tiện ích Mandarin Studio trong tab ChatGPT trên Edge, dán mã từ tool và bấm Kết nối.')
            return
        dialog = self.modal('Kết nối tab ChatGPT trên Edge', 760, 440)
        body, footer = self.modal_body(dialog)
        ttk.Label(body, text='DÙNG EDGE ĐANG ĐĂNG NHẬP', font=('Segoe UI', 15, 'bold'), foreground='#62ded0').pack(anchor='w')
        ttk.Label(body, text='Cài tiện ích cục bộ một lần: trong Edge mở edge://extensions → bật Developer mode → Load unpacked → chọn thư mục bên dưới. Sau đó mở tiện ích trên tab ChatGPT và dán mã kết nối.', wraplength=660, foreground='#b5c6da').pack(anchor='w', pady=14)
        extension = str(ROOT / 'edge_extension')
        folder = ttk.Entry(body, width=72)
        folder.insert(0, extension)
        folder.configure(state='readonly')
        folder.pack(fill='x', pady=6)
        ttk.Button(body, text='Mở thư mục tiện ích', command=lambda: os.startfile(extension)).pack(anchor='w', pady=6)
        ttk.Label(body, text='Mã kết nối trên máy (đổi khi mở lại tool):').pack(anchor='w', pady=(12, 4))
        token = ttk.Entry(body, width=72)
        token.insert(0, chat.bridge.token)
        token.configure(state='readonly')
        token.pack(fill='x')
        def copy_code():
            self.clipboard_clear()
            self.clipboard_append(chat.bridge.token)
            self.status.set('Đã sao chép mã kết nối. Dán vào tiện ích Mandarin Studio trên tab ChatGPT trong Edge.')
        ttk.Button(footer, text='Sao chép mã kết nối', command=copy_code).pack(side='right')
        ttk.Button(footer, text='Đóng', command=dialog.destroy).pack(side='right', padx=6)
        self.wait_window(dialog)

    def asset_key(self, lesson):
        from publishing_workflow import episode_data
        return json.dumps(episode_data(lesson), ensure_ascii=False, sort_keys=True)

    def reset_asset_source(self, lesson):
        key = self.asset_key(lesson)
        if key == self.asset_source:
            return
        self.asset_source = key
        self.asset_conversation = None
        self.asset_video_name.set(lesson['title_vi'] + '.mp4')
        self.asset_title.set(lesson['title_vi'])
        self.asset_title_choices.configure(values=[])
        for field in (self.asset_description, self.asset_image_prompt):
            field.delete('1.0', 'end')

    def prepare_assets(self):
        if self.busy:
            return
        try:
            from publishing_workflow import draft_prompt, validate_draft
            from chatgpt_web import json_response
            lesson = self.get_lesson()
            key = self.asset_key(lesson)
            chat = self.get_chatgpt()
            prompt = draft_prompt(lesson, self.brand.get(), self.level.get())
        except Exception as exc:
            messagebox.showerror('Chưa viết được prompt', str(exc))
            return
        def work():
            data = validate_draft(json_response(chat.send(prompt, self.cancel)))
            self.events.put(('asset_draft', {'source': key, 'data': data,
                'conversation_url': getattr(chat, 'last_conversation', None)}))
        self.status.set('ChatGPT đang viết prompt ảnh, tên video, tiêu đề và mô tả; chưa tạo ảnh…')
        self.launch(work)

    def apply_asset_draft(self, value):
        if self.asset_key(self.get_lesson()) != value['source']:
            self.status.set('ChatGPT đã viết xong nhưng kịch bản đã đổi. Bấm viết prompt lại để dùng đúng nội dung; kết quả cũ vẫn trên Edge.')
            return
        data = value['data']
        self.asset_source = value['source']
        url = value.get('conversation_url')
        self.asset_conversation = url if isinstance(url, str) and url.startswith('https://chatgpt.com/c/') else None
        self.asset_video_name.set(data['video_name'])
        self.asset_title_choices.configure(values=data['titles'])
        self.asset_title.set(data['titles'][0])
        for field, name in ((self.asset_description, 'description'), (self.asset_image_prompt, 'image_prompt')):
            field.delete('1.0', 'end')
            field.insert('1.0', data[name])
        self.status.set('Đã có prompt và bộ đăng. Bạn có thể sửa rồi bấm Tạo ảnh hoặc Gửi phần chữ lên chat để copy.')

    def present_asset_request(self, prompt, status):
        chat = self.get_chatgpt()
        conversation = self.asset_conversation
        def work():
            result = chat.present(prompt, self.cancel, conversation_url=conversation)
            if not result.get('presented'):
                raise RuntimeError('Chưa xác nhận được yêu cầu đã gửi. Kiểm tra tab Edge trước khi thử lại.')
            self.events.put(('status', status))
        self.launch(work)

    def present_asset_copy(self):
        if self.busy:
            return
        try:
            from publishing_workflow import copy_prompt
            prompt = copy_prompt(self.asset_video_name.get(), self.asset_title.get(), self.asset_description.get('1.0', 'end'))
            self.present_asset_request(prompt, 'Đã gửi tên video, tiêu đề và mô tả lên chat. Xem và copy phần chữ trên Edge; lượt này không yêu cầu tạo ảnh.')
        except Exception as exc:
            messagebox.showerror('Chưa gửi được bộ đăng', str(exc))

    def create_asset_image(self):
        if self.busy:
            return
        try:
            from publishing_workflow import image_prompt
            prompt = image_prompt(self.asset_image_prompt.get('1.0', 'end'))
            self.present_asset_request(prompt, 'Đã gửi prompt tạo ảnh. Xem tiến trình và tải ảnh trong tab ChatGPT trên Edge.')
        except Exception as exc:
            messagebox.showerror('Chưa tạo được ảnh', str(exc))

    def generate_ai_kit(self):
        self.prepare_assets()

    def generate(self, draft_only=False):
        if self.busy:
            return
        if not self.persist_settings(notify=True):
            return
        topic, level, minutes, key, model = (v.get() for v in [self.topic, self.level, self.minutes, self.key, self.model])
        use_chatgpt = self.ai_provider.get() == 'ChatGPT Web'
        expression = LEVELS[self.expression.get()]
        if not topic.strip() or (not use_chatgpt and (not key.strip() or not model.strip())):
            messagebox.showinfo('Cần cấu hình', 'Nhập chủ đề; chọn ChatGPT Web hoặc điền Gemini API key và model dự phòng.')
            return
        try:
            speakers, selected_voices = self.cast_selection()
        except ValueError as exc:
            messagebox.showinfo('Số người nói', str(exc))
            return
        self.status.set('AI đang viết hội thoại và dịch sang tiếng Việt…')
        try:
            chat = self.get_chatgpt() if use_chatgpt else None
        except Exception as exc:
            messagebox.showerror('ChatGPT', str(exc))
            return
        self.reuse_dir = None
        self.legacy_audio_settings = None
        out = Path(self.folder.get()).expanduser() / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        def work():
            kwargs = {'text_sender': lambda prompt: chat.send(prompt, self.cancel)} if chat else {}
            lesson = generate_lesson(topic, level, minutes, key, model, self.cancel, speakers=speakers, expression=expression, **kwargs)
            lesson.pop('publishing', None)
            lesson.pop('thumbnail_images', None)
            if selected_voices:
                lesson['speaker_voices'] = selected_voices
            out.mkdir(parents=True, exist_ok=True)
            (out/'lesson.json').write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding='utf-8')
            self.events.put(('lesson', copy.deepcopy(lesson)))
            self.events.put(('draft', out))
        self.launch(work)

    def export_options(self):
        options = {'brand': self.brand.get(), 'speaker_voices': dict(self.speaker_voices),
                'speed': self.rate.get(), 'resolution': self.resolution.get(),
                'stability': self.stability.get(), 'turn_gap': self.turn_gap.get(),
                'expression': LEVELS[self.expression.get()],
                'eleven_key': self.eleven_key.get(), 'tts_model': self.tts_model.get(),
                'local_publishing': False, 'mode': 'podcast', 'premium': self.premium.get(), 'shorts': self.shorts.get(),
                'theme': self.theme.get(), 'level': self.level.get(), 'reuse_dir': self.reuse_dir}
        if self.legacy_audio_settings:
            old = self.legacy_audio_settings
            try:
                options['legacy_audio'] = (options['speaker_voices'] == old['speaker_voices']
                    and options['expression'] == 'off'
                    and options['tts_model'] == old['tts_model']
                    and all(float(options[key]) == old[key] for key in ('speed', 'stability', 'turn_gap')))
            except ValueError:
                options['legacy_audio'] = False
        return options

    def check_eleven(self):
        if not self.eleven_key.get().strip():
            messagebox.showinfo('Cần ElevenLabs', 'Nhập API key trong tab ElevenLabs. Voice ID được chọn theo từng nhân vật ở bước xuất.')
            return False
        return True

    def export(self):
        if self.busy:
            return
        if not self.persist_settings(notify=True) or not self.check_eleven():
            return
        try:
            lesson = self.get_lesson()
            check_expression(self.tts_model.get(), LEVELS[self.expression.get()])
        except Exception as exc:
            messagebox.showerror('Cần kịch bản hợp lệ', str(exc))
            return
        mapping = self.choose_voices(lesson)
        if mapping is None:
            return
        self.speaker_voices = mapping
        lesson['speaker_voices'] = dict(mapping)
        self.put_lesson(lesson)
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

    def resume_export(self):
        if self.busy or not self.check_eleven():
            return
        folder = filedialog.askdirectory(title='Chọn thư mục lần xuất lỗi có export_job.json')
        if not folder:
            return
        try:
            out = Path(folder)
            job = json.loads((out/'export_job.json').read_text(encoding='utf-8'))
            lesson = validate_lesson(json.loads((out/'lesson.json').read_text(encoding='utf-8')))
            options = dict(job['options'])
            # Restore the original render/voice settings, but always use the current key.
            options['eleven_key'] = self.eleven_key.get()
            options['reuse_dir'] = out
            self.put_lesson(lesson)
        except Exception as exc:
            messagebox.showerror('Không đọc được lần xuất', str(exc))
            return
        self.last_output = out
        self.status.set('Đang tiếp tục lần xuất; dùng lại audio đã lưu và kiểm tra đoạn bị ngắt trong lịch sử ElevenLabs…')
        def work():
            result = export_video(lesson, out, options, lambda s: self.events.put(('status', s)), self.cancel)
            self.events.put(('done', result))
        self.launch(work)

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == 'status':
                    self.status.set(value)
                elif event == 'lesson':
                    self.put_lesson(value)
                elif event == 'asset_draft':
                    try:
                        self.apply_asset_draft(value)
                    except Exception as exc:
                        self.status.set('Không nạp được bộ đăng: ' + str(exc))
                elif event == 'performance':
                    try:
                        self.apply_performance(value)
                    except Exception as exc:
                        self.status.set(str(exc))
                        messagebox.showerror('Chưa áp dụng được cảm xúc', str(exc))
                elif event == 'audio_preview':
                    self.preview_audio_path = value
                    self.last_output = value.parent
                    self.status.set('Đang phát bản nghe thử: ' + str(value) + ' · Có thể đổi giọng hoặc mức biểu cảm rồi thử lại.')
                    self.play_preview()
                elif event == 'draft':
                    self.last_output = value
                    self.status.set('Đã lưu kịch bản: ' + str(value) + ' · Duyệt lời thoại rồi bấm “Chọn giọng & xuất MP4”.')
                elif event == 'error':
                    self.status.set('Tác vụ chưa hoàn tất: ' + value)
                    messagebox.showerror('Tác vụ chưa hoàn tất', value)
                elif event == 'done':
                    self.last_output = value.parent
                    self.status.set('Đã xuất: ' + str(value))
                    messagebox.showinfo('Xuất video thành công', f'{value}\n\nĐã kèm kịch bản và SRT. Bản Premium có Shorts. Tiêu đề, mô tả và thumbnail tạo riêng trên Edge để bạn tự đăng.')
                elif event == 'idle':
                    self.busy = False
                    self.progress.stop()
                    self.generate_button.configure(state='normal')
                    self.export_button.configure(state='normal')
                    self.draft_button.configure(state='normal')
                    for button in self.asset_action_buttons:
                        button.configure(state='normal')
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('Tác vụ đang chạy', 'Bấm Dừng tác vụ và đợi trạng thái hoàn tất trước khi đóng ứng dụng.')
            return
        if self.persist_settings(notify=True):
            if self.chatgpt is not None:
                chat = self.chatgpt
                chat.close()
            self.destroy()


if __name__ == '__main__':
    Studio().mainloop()
