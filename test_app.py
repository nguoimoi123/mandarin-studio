"""Exercise the cast/voice dialogs without reading keys or making API requests."""
import copy
import json
import tempfile
import tkinter as tk
import unittest
from contextlib import ExitStack
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from app import Studio
from studio import ROOT


class VoiceDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            probe = tk.Tk()
            probe.destroy()
        except tk.TclError as exc:
            raise unittest.SkipTest(f'Tk display unavailable: {exc}')

    def setUp(self):
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        values = {'GEMINI_API_KEY': 'fake-gemini', 'ELEVENLABS_API_KEY': 'fake-eleven'}
        for i in range(1, 11):
            values[f'ELEVENLABS_VOICE_{i}'] = f'testVoice{i}'
            values[f'ELEVENLABS_VOICE_{i}_NAME'] = f'Giọng thử {i}'
        self.patches.enter_context(patch('app.load_settings', return_value=values))
        self.save_settings = self.patches.enter_context(patch('app.save_settings'))
        self.network = self.patches.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')))
        self.patches.enter_context(patch.object(Studio, 'show_preview'))
        self.patches.enter_context(patch.object(Studio, 'refresh_kit'))
        self.patches.enter_context(patch.object(Studio, 'iconbitmap'))
        self.app = Studio()
        self.app.update_idletasks()
        self.addCleanup(self.destroy_app)
        self.lesson = json.loads((ROOT / 'sample_lesson.json').read_text(encoding='utf-8'))

    def destroy_app(self):
        for pending in self.app.tk.call('after', 'info'):
            self.app.after_cancel(pending)
        self.app.destroy()

    @staticmethod
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from VoiceDialogTests.descendants(child)

    def dialog(self):
        dialogs = [widget for widget in self.app.winfo_children() if isinstance(widget, tk.Toplevel)]
        self.assertEqual(len(dialogs), 1)
        return dialogs[0]

    def button(self, dialog, text):
        matches = [widget for widget in self.descendants(dialog)
                   if isinstance(widget, ttk.Button) and widget.cget('text') == text]
        self.assertEqual(len(matches), 1, text)
        return matches[0]

    def run_dialog(self, open_dialog, action):
        """Run an interaction inside wait_window and surface callback failures."""
        errors = []
        def interact():
            try:
                dialog = self.dialog()
                dialog.update_idletasks()
                action(dialog)
            except BaseException as exc:
                errors.append(exc)
                for child in self.app.winfo_children():
                    if isinstance(child, tk.Toplevel):
                        child.destroy()
        def timeout():
            errors.append(AssertionError('Dialog did not close after interaction'))
            for child in self.app.winfo_children():
                if isinstance(child, tk.Toplevel):
                    child.destroy()
        self.app.after(30, interact)
        watchdog = self.app.after(1500, timeout)
        try:
            result = open_dialog()
        finally:
            self.app.after_cancel(watchdog)
        if errors:
            raise errors[0]
        self.network.assert_not_called()
        return result

    def cast_lesson(self, count):
        lesson = copy.deepcopy(self.lesson)
        lesson['speakers'] = [f'Người {i}' for i in range(1, count + 1)]
        lesson['lines'] = [dict(self.lesson['lines'][0], speaker=speaker) for speaker in lesson['speakers']]
        lesson.pop('speaker_voices', None)
        return lesson

    def test_solo_two_and_ten_speakers_can_choose_any_bank_slot(self):
        for count in (1, 2, 10):
            with self.subTest(speakers=count):
                lesson = self.cast_lesson(count)
                def choose(dialog):
                    combos = [widget for widget in self.descendants(dialog) if isinstance(widget, ttk.Combobox)]
                    self.assertEqual(len(combos), count)
                    for i, combo in enumerate(combos):
                        combo.current(9 - i)
                    self.button(dialog, 'Tạo giọng & xuất MP4').invoke()
                result = self.run_dialog(lambda: self.app.choose_voices(lesson), choose)
                self.assertEqual(result, {speaker: f'testVoice{10-i}' for i, speaker in enumerate(lesson['speakers'])})

    def test_cancel_returns_no_mapping_and_export_does_not_launch(self):
        self.app.put_lesson(self.cast_lesson(2))
        with patch.object(self.app, 'launch') as launch:
            result = self.run_dialog(self.app.export, lambda dialog: self.button(dialog, 'Hủy').invoke())
        self.assertIsNone(result)
        launch.assert_not_called()
        self.assertEqual(self.app.speaker_voices, {})

    def test_missing_voice_stays_open_until_cancelled(self):
        self.app.voice_ids[0].set('')
        lesson = self.cast_lesson(1)
        with patch('app.messagebox.showerror') as error:
            def choose(dialog):
                self.button(dialog, 'Tạo giọng & xuất MP4').invoke()
                error.assert_called_once()
                self.assertTrue(dialog.winfo_exists())
                self.button(dialog, 'Hủy').invoke()
            result = self.run_dialog(lambda: self.app.choose_voices(lesson), choose)
        self.assertIsNone(result)

    def test_episode_voice_outside_bank_is_preserved(self):
        lesson = self.cast_lesson(1)
        lesson['speaker_voices'] = {lesson['speakers'][0]: 'externalEpisodeVoice'}
        result = self.run_dialog(lambda: self.app.choose_voices(lesson),
                                 lambda dialog: self.button(dialog, 'Tạo giọng & xuất MP4').invoke())
        self.assertEqual(result, lesson['speaker_voices'])

    def test_editing_selected_bank_slot_uses_updated_id(self):
        lesson = self.cast_lesson(1)
        def update_bank(parent):
            self.app.voice_ids[0].set('replacementVoice')
        with patch.object(self.app, 'edit_voice_bank', side_effect=update_bank):
            def choose(dialog):
                self.button(dialog, 'Sửa kho 10 giọng…').invoke()
                self.button(dialog, 'Tạo giọng & xuất MP4').invoke()
            result = self.run_dialog(lambda: self.app.choose_voices(lesson), choose)
        self.assertEqual(result, {lesson['speakers'][0]: 'replacementVoice'})

    def assert_footer_visible_in_short_dialog(self, dialog, confirm_text):
        dialog.geometry('760x320')
        dialog.update()
        dialog.update_idletasks()
        for text in (confirm_text, 'Hủy'):
            button = self.button(dialog, text)
            self.assertTrue(button.winfo_ismapped())
            self.assertGreaterEqual(button.winfo_rooty(), dialog.winfo_rooty())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), dialog.winfo_rooty() + dialog.winfo_height())
        canvases = [widget for widget in self.descendants(dialog) if isinstance(widget, tk.Canvas)]
        self.assertEqual(len(canvases), 1)
        self.assertLess(canvases[0].yview()[1], 1.0)
        self.button(dialog, 'Hủy').invoke()

    def test_ten_speaker_footer_remains_visible_when_dialog_is_short(self):
        lesson = self.cast_lesson(10)
        result = self.run_dialog(lambda: self.app.choose_voices(lesson),
            lambda dialog: self.assert_footer_visible_in_short_dialog(dialog, 'Tạo giọng & xuất MP4'))
        self.assertIsNone(result)

    def test_voice_bank_footer_remains_visible_when_dialog_is_short(self):
        self.run_dialog(self.app.edit_voice_bank,
            lambda dialog: self.assert_footer_visible_in_short_dialog(dialog, 'Lưu kho giọng'))

    def test_generated_script_is_saved_for_review_without_tts(self):
        lesson = self.cast_lesson(1)
        self.app.speaker_count.set('1')
        self.app.cast.set(lesson['speakers'][0])
        self.app.ai_provider.set('Gemini API')
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(self.app, 'launch', side_effect=lambda work: work()), \
                patch('app.generate_lesson', return_value=lesson) as generate, \
                patch('app.publishing_kit'), patch('app.export_video') as export:
            self.app.folder.set(folder)
            self.app.generate()
            export.assert_not_called()
            self.assertEqual(generate.call_args.kwargs['speakers'], lesson['speakers'])
            saved = list(Path(folder).glob('*/lesson.json'))
            self.assertEqual(len(saved), 1)
            restored = json.loads(saved[0].read_text(encoding='utf-8'))
            self.assertEqual(restored['lines'], lesson['lines'])
            self.assertEqual(restored['speaker_voices'], {'Người 1': 'testVoice1'})
            self.assertEqual(list(saved[0].parent.iterdir()), saved)
            self.assertNotIn('publishing', restored)
            self.assertNotIn('thumbnail_images', restored)
        self.network.assert_not_called()

    def test_chatgpt_is_used_without_a_gemini_key(self):
        from unittest.mock import Mock
        lesson = self.cast_lesson(1)
        self.app.speaker_count.set('1')
        self.app.cast.set(lesson['speakers'][0])
        self.app.ai_provider.set('ChatGPT Web')
        self.app.ai_thumbnails.set(False)
        self.app.key.set('')
        chat = Mock()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(self.app, 'get_chatgpt', return_value=chat), \
                patch.object(self.app, 'launch', side_effect=lambda work: work()), \
                patch('app.generate_lesson', return_value=lesson) as generate, \
                patch('app.publishing_kit'), patch('app.export_video') as export:
            self.app.folder.set(folder)
            self.app.generate()
            self.assertIn('text_sender', generate.call_args.kwargs)
            generate.call_args.kwargs['text_sender']('episode prompt')
            chat.send.assert_called_once_with('episode prompt', self.app.cancel)
            export.assert_not_called()
            self.assertEqual(len(list(Path(folder).glob('*/lesson.json'))), 1)

    def test_count_and_voice_dropdowns_do_not_need_typed_names(self):
        self.app.speaker_count.set('10')
        self.app.change_speaker_count()
        combos = [widget for widget in self.descendants(self.app.cast_frame) if isinstance(widget, ttk.Combobox)]
        self.assertEqual(len(combos), 10)
        self.assertTrue(all(str(combo.cget('state')) == 'readonly' for combo in combos))
        combos[0].current(9)
        combos[0].event_generate('<<ComboboxSelected>>')
        self.app.update()
        speakers, voices = self.app.cast_selection()
        self.assertEqual(speakers, [f'Người {i}' for i in range(1, 11)])
        self.assertEqual(voices['Người 1'], 'testVoice10')
        self.app.speaker_count.set('1')
        self.app.change_speaker_count()
        self.assertEqual(len([w for w in self.descendants(self.app.cast_frame) if isinstance(w, ttk.Combobox)]), 1)
        self.assertEqual(self.app.cast_selection()[1], {'Người 1': 'testVoice10'})
        self.assertFalse(self.app.export_options()['local_publishing'])

    def test_web_publishing_stays_on_edge_without_saving_or_downloading(self):
        from unittest.mock import Mock
        chat = Mock()
        chat.present.return_value = {'presented': True}
        original = self.app.editor.get('1.0', 'end')
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(self.app, 'get_chatgpt', return_value=chat), \
                patch.object(self.app, 'launch', side_effect=lambda work: work()), \
                patch('app.publishing_kit') as kit, patch('app.export_video') as export:
            self.app.folder.set(folder)
            self.app.asset_video_name.set('tap-moi.mp4')
            self.app.asset_title.set('Tiêu đề đã sửa')
            self.app.asset_description.insert('1.0', 'Mô tả đã sửa để đăng YouTube.')
            self.app.present_asset_copy()
            chat.present.assert_called_once()
            prompt = chat.present.call_args.args[0]
            self.assertIn('không trả JSON', prompt)
            self.assertIn('Tiêu đề đã sửa', prompt)
            self.assertIn('Mô tả đã sửa', prompt)
            self.assertNotIn('fake-eleven', prompt)
            self.assertNotIn('testVoice1', prompt)
            chat.send.assert_not_called()
            chat.generate_image.assert_not_called()
            kit.assert_not_called()
            export.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()), [])
            self.assertEqual(self.app.editor.get('1.0', 'end'), original)

    def test_imported_script_voice_dropdown_updates_json_without_renaming(self):
        lesson = self.cast_lesson(1)
        lesson['speakers'] = ['Lan']
        lesson['lines'][0]['speaker'] = 'Lan'
        lesson['speaker_voices'] = {'Lan': 'externalSavedVoice'}
        self.app.put_lesson(lesson)
        combo = next(w for w in self.descendants(self.app.cast_frame) if isinstance(w, ttk.Combobox))
        self.assertIn('externalSavedVoice', combo.get())
        combo.current(9)
        combo.event_generate('<<ComboboxSelected>>')
        self.app.update()
        restored = self.app.get_lesson()
        self.assertEqual(restored['speakers'], ['Lan'])
        self.assertEqual(restored['lines'], lesson['lines'])
        self.assertEqual(restored['speaker_voices'], {'Lan': 'testVoice10'})

    def test_resume_uses_saved_render_settings_with_current_key(self):
        lesson = self.cast_lesson(1)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out/'lesson.json').write_text(json.dumps(lesson), encoding='utf-8')
            (out/'export_job.json').write_text(json.dumps({'options': {
                'speed': 0.9, 'stability': 0.35, 'turn_gap': 0.2,
                'speaker_voices': {'Người 1':'savedVoice'}, 'premium': True}}), encoding='utf-8')
            self.app.rate.set('1.2')
            with patch('app.filedialog.askdirectory', return_value=folder), \
                    patch.object(self.app,'launch',side_effect=lambda work:work()), \
                    patch('app.export_video',return_value=out/'video.mp4') as export:
                self.app.resume_export()
            args = export.call_args.args
            self.assertEqual(args[1],out)
            self.assertEqual(args[2]['speed'],0.9)
            self.assertEqual(args[2]['eleven_key'],'fake-eleven')
            self.assertEqual(args[2]['speaker_voices'],{'Người 1':'savedVoice'})

    def test_asset_prompt_is_reviewable_before_any_image_request(self):
        from unittest.mock import Mock
        from test_publishing_workflow import sample_draft
        chat=Mock()
        chat.send.return_value=json.dumps(sample_draft(),ensure_ascii=False)
        chat.last_conversation='https://chatgpt.com/c/test-conversation'
        chat.present.return_value={'presented':True}
        original=self.app.editor.get('1.0','end')
        with patch.object(self.app,'get_chatgpt',return_value=chat), \
                patch.object(self.app,'launch',side_effect=lambda work:work()):
            self.app.prepare_assets()
            chat.present.assert_not_called()
            chat.generate_image.assert_not_called()
            event,value=self.app.events.get_nowait()
            self.assertEqual(event,'asset_draft')
            self.app.apply_asset_draft(value)
            self.assertEqual(self.app.asset_video_name.get(),'chuyen-cong-so.mp4')
            self.assertEqual(len(self.app.asset_title_choices.cget('values')),3)
            self.app.asset_image_prompt.delete('1.0','end')
            self.app.asset_image_prompt.insert('1.0','Ảnh đã sửa: hai nhân vật mặc áo xanh, bố cục 16:9')
            self.app.create_asset_image()
            chat.present.assert_called_once()
            self.assertIn('hai nhân vật mặc áo xanh',chat.present.call_args.args[0])
            self.assertEqual(chat.present.call_args.kwargs['conversation_url'],chat.last_conversation)
            self.assertEqual(self.app.editor.get('1.0','end'),original)

    def test_new_episode_clears_old_prompt_and_stale_draft_is_not_applied(self):
        from test_publishing_workflow import sample_draft
        old=self.app.get_lesson()
        source=self.app.asset_key(old)
        self.app.asset_image_prompt.insert('1.0','Old image prompt')
        new=self.cast_lesson(1)
        new['title_vi']='Một tập khác'
        self.app.put_lesson(new)
        self.app.apply_asset_draft({'source':source,'data':sample_draft(),'conversation_url':None})
        self.assertEqual(self.app.asset_image_prompt.get('1.0','end').strip(),'')
        self.assertEqual(self.app.asset_video_name.get(),'Một tập khác.mp4')


if __name__ == '__main__':
    unittest.main()
