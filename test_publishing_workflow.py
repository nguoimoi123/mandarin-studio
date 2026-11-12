import json
import unittest

from publishing_workflow import draft_prompt, validate_draft, copy_prompt, image_prompt
from studio import ROOT


def sample_draft():
    return {'video_name':'chuyen-cong-so.mp4', 'titles':['Một câu hỏi khó','Làm trái ngành?','Buổi phỏng vấn đầu tiên'],
            'description':'Một cuộc trò chuyện trước giờ phỏng vấn. #HocTiengTrung',
            'image_prompt':'Thumbnail 16:9, hai người lớn trước tòa nhà văn phòng, một người lo lắng, ánh sáng ban mai; chữ LÀM TRÁI NGÀNH? ở bên trái.'}


class PublishingWorkflowTests(unittest.TestCase):
    def test_draft_uses_episode_content_without_voice_ids_or_local_paths(self):
        lesson=json.loads((ROOT/'sample_lesson.json').read_text(encoding='utf-8'))
        lesson.update(speaker_voices={lesson['speakers'][0]:'privateVoiceIdentifier'},thumbnail_images=['C:/private/file.png'])
        text=draft_prompt(lesson,'Kênh nghe tiếng Trung','HSK 3–4')
        self.assertIn(lesson['lines'][0]['zh'],text)
        self.assertIn('chưa tạo ảnh',text)
        self.assertIn('image_prompt',text)
        self.assertNotIn('privateVoiceIdentifier',text)
        self.assertNotIn('C:/private',text)

    def test_required_fields_and_title_length_are_validated(self):
        self.assertEqual(validate_draft(sample_draft()),sample_draft())
        for field in sample_draft():
            data=sample_draft();data.pop(field)
            with self.subTest(field=field),self.assertRaises(ValueError): validate_draft(data)
        data=sample_draft();data['titles'][0]='x'*101
        with self.assertRaises(ValueError):validate_draft(data)

    def test_copy_and_image_requests_are_separate_and_use_edits(self):
        copy=copy_prompt('tap-da-sua.mp4','Tiêu đề đã sửa','Mô tả đã sửa')
        self.assertIn('Tiêu đề đã sửa',copy)
        self.assertIn('Mô tả đã sửa',copy)
        self.assertIn('không tạo ảnh',copy)
        image=image_prompt('Prompt ảnh đã sửa, nhân vật mặc áo xanh')
        self.assertIn('TẠO ẢNH',image)
        self.assertIn('nhân vật mặc áo xanh',image)
        with self.assertRaises(ValueError):image_prompt(' ')
        with self.assertRaises(ValueError):copy_prompt('video.mp4','','Mô tả')

    def test_suggested_filename_does_not_contain_path_characters(self):
        data=sample_draft();data['video_name']='CON'
        self.assertEqual(validate_draft(data)['video_name'],'video_CON.mp4')
        data['video_name']='văn phòng: câu hỏi?.mp4'
        self.assertEqual(validate_draft(data)['video_name'],'văn phòng_ câu hỏi_.mp4')
