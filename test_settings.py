import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values
from settings_store import load_settings, save_settings


class SettingsTests(unittest.TestCase):
    def test_roundtrip_and_edit_preserve_other_settings(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
            path = Path(directory) / '.env'
            path.write_text('# Keep this comment\nOTHER_OPTION=keep\n', encoding='utf-8')
            settings = {'GEMINI_API_KEY': 'fake-gemini', 'ELEVENLABS_API_KEY': 'fake-eleven',
                        'ELEVENLABS_VOICE_1': 'ngoc-id', 'ELEVENLABS_VOICE_2': 'quan-id',
                        'CHANNEL_NAME': "Quân và Ngọc's radio", 'SPEAKING_PRACTICE': 'False',
                        'OUTPUT_FOLDER': 'D:\\Quân\\Video', 'LITERAL': '${DO_NOT_EXPAND}'}
            save_settings(path, settings)
            self.assertEqual(load_settings(path)['CHANNEL_NAME'], settings['CHANNEL_NAME'])
            self.assertEqual(dotenv_values(path, interpolate=False)['LITERAL'], '${DO_NOT_EXPAND}')
            self.assertEqual(load_settings(path)['ELEVENLABS_VOICE_2'], 'quan-id')
            save_settings(path, {'ELEVENLABS_VOICE_2': 'new-quan-id'})
            restored = load_settings(path)
            self.assertEqual(restored['ELEVENLABS_VOICE_2'], 'new-quan-id')
            self.assertEqual(restored['ELEVENLABS_API_KEY'], 'fake-eleven')
            self.assertEqual(restored['OTHER_OPTION'], 'keep')
            self.assertIn('# Keep this comment', path.read_text(encoding='utf-8'))

    def test_failed_write_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('EXISTING=keep\n', encoding='utf-8')
            with patch('settings_store.set_key', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    save_settings(path, {'EXISTING': 'replace'})
            self.assertEqual(path.read_text(), 'EXISTING=keep\n')
            self.assertEqual(list(Path(directory).glob('.settings-*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
