"""ChatGPT helpers and adapter for the existing Microsoft Edge tab.

No API keys, cookie extraction, private endpoints or browser launches.
Requests go to the explicitly paired Edge tab through a local bridge.
"""
from __future__ import annotations

import json
from pathlib import Path

from agent_ads_chatgpt.errors import ChatGPTError


def json_response(text):
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise ChatGPTError('ChatGPT chưa trả JSON hoàn chỉnh. Xem tab ChatGPT trong Edge để kiểm tra phản hồi; không tự gửi lại.') from None
    if not isinstance(value, dict):
        raise ChatGPTError('ChatGPT cần trả một JSON object.')
    return value


def validate_publishing(value):
    if not isinstance(value, dict):
        raise ChatGPTError('Thiếu bộ đăng do ChatGPT viết.')
    for name in ('titles', 'thumbnail_text', 'thumbnail_prompts'):
        items = value.get(name)
        if not isinstance(items, list) or len(items) != 3 or any(not isinstance(x, str) or not x.strip() for x in items):
            raise ChatGPTError(f'{name} cần đúng 3 nội dung khác nhau để thử.')
    for name in ('description', 'pinned_comment', 'cta'):
        if not isinstance(value.get(name), str) or not value[name].strip():
            raise ChatGPTError(f'Bộ đăng thiếu {name}.')
    if any(len(title) > 100 for title in value['titles']):
        raise ChatGPTError('Tiêu đề YouTube dài quá 100 ký tự; hãy sửa trước khi xuất.')
    return value


PUBLISHING_INSTRUCTION = '''Also include a "publishing" object in the JSON:
{"titles":["3 different Vietnamese YouTube titles, each at most 100 characters"],
"description":"A specific Vietnamese YouTube description grounded in this episode, with a short hook, what happens, learner level, and relevant hashtags. Do not invent timestamps or results.",
"thumbnail_text":["3 short Vietnamese thumbnail headlines, 2–6 words each"],
"thumbnail_prompts":["3 different detailed visual prompts for a 16:9 YouTube thumbnail background showing this episode's actual dilemma, expressive adult characters, strong visual storytelling, no lettering, no logos, leave left half uncluttered for text"],
"pinned_comment":"a concrete question about this episode in Vietnamese", "cta":"a brief natural Vietnamese subscription invitation"}.
Every array must contain exactly THREE strings. No generic boilerplate, fabricated trends or exaggerated promises.
'''


# Public facade now connects exclusively to the user's existing Edge tab.
# The Agent_ads worker remains attributed in agent_ads_chatgpt/UPSTREAM.md.
from edge_bridge import EdgeChatGPT


class ChatGPT(EdgeChatGPT):
    def __init__(self, profile=None):
        # Accept the old argument for callers; never launch or copy this profile.
        super().__init__()


def create_thumbnails(chat, lesson, out, cancel=None, log=lambda text: None):
    publishing = validate_publishing(lesson.get('publishing'))
    paths = []
    for i, prompt in enumerate(publishing['thumbnail_prompts'], 1):
        from studio import check
        check(cancel)
        target = Path(out) / 'assets' / f'chatgpt_thumbnail_{i}.png'
        log(f'ChatGPT đang tạo ảnh nền thumbnail {i}/3…')
        chat.generate_image(prompt + ' Landscape 16:9. No text, no watermarks.', target, cancel)
        paths.append(str(target.resolve()))
        lesson['thumbnail_images'] = list(paths)  # Preserve each completed image on partial failure.
        (Path(out) / 'lesson.json').write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding='utf-8')
    return paths
