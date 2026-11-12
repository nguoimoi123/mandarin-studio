"""Premium layouts, editorial checks, Shorts and a reviewable publishing kit."""
from __future__ import annotations

import csv
import json
import re
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from studio import FFMPEG, check, paragraph, run, validate_lesson

PALETTES = {
    'Midnight': ('#091426', '#10233a', '#67e8d1', '#f5c47e'),
    'Jade': ('#081f1e', '#103532', '#85efbb', '#ffd79c'),
    'Plum': ('#211425', '#352039', '#f1b4e5', '#ffd79c'),
}
TOPICS = [
    ('Công sở', 'Ngày đầu đi làm: nghe không hiểu sếp thì hỏi lại thế nào?'),
    ('Đời sống', 'Gọi đồ uống: một câu nói khiến đơn hàng bị nhầm'),
    ('Tình cảm', 'Tin nhắn đã đọc nhưng chưa trả lời: Ngọc hiểu lầm Quân'),
    ('Du lịch', 'Lạc đường ở ga tàu: hỏi đúng người, tìm đúng chuyến'),
    ('Mua sắm', 'Mua hàng online: nhận nhầm món và xin đổi trả'),
    ('Công sở', 'Đồng nghiệp nhờ làm hộ: từ chối sao cho lịch sự?'),
    ('Đời sống', 'Thuê nhà lần đầu: khoản phí không ai nhắc đến'),
    ('Tình cảm', 'Một món quà nhỏ và kế hoạch sinh nhật bị lộ'),
    ('Du lịch', 'Đặt phòng khách sạn: đến nơi lại hết phòng'),
    ('Đời sống', 'Đi khám bệnh: mô tả triệu chứng bằng tiếng Trung'),
    ('Mua sắm', 'Trả giá ở chợ: rẻ hơn nhưng có đáng mua?'),
    ('Công sở', 'Buổi phỏng vấn đầu tiên: một câu hỏi ngoài dự kiến'),
]


def audit_lesson(lesson):
    validate_lesson(lesson)
    warnings = []
    seen = set()
    counts = []
    for i, line in enumerate(lesson['lines'], 1):
        count = len(re.findall(r'[\u3400-\u9fff]', line['zh']))
        counts.append(count)
        if not count:
            warnings.append(f'Lượt {i}: chưa có chữ Hán.')
        if count > 70:
            warnings.append(f'Lượt {i}: {count} chữ Hán; nên chia nhỏ để dễ đọc trên điện thoại.')
        if re.search(r'[\u3400-\u9fff]', line['pinyin']):
            warnings.append(f'Lượt {i}: pinyin có lẫn chữ Hán.')
        if line['zh'] in seen:
            warnings.append(f'Lượt {i}: trùng nguyên văn một lượt trước đó.')
        seen.add(line['zh'])
    used = {line['speaker'] for line in lesson['lines']}
    unused = set(lesson['speakers']) - used
    if unused:
        warnings.append('Nhân vật chưa có lời thoại: ' + ', '.join(sorted(unused)))
    if len(lesson['lines']) > 148:
        warnings.append('Gần giới hạn 150 lượt; nên chia thành các tập ngắn hơn.')
    return {'turns': len(counts), 'hanzi': sum(counts),
            'estimated_minutes': round(sum(counts) / 210, 1), 'warnings': warnings,
            'note': 'Ước lượng theo số chữ; cần nghe kiểm tra phát âm, pinyin và bản dịch.'}


def publishing_data(lesson, options):
    title = lesson['title_vi'].strip()
    level = options.get('level', 'HSK 1–2')
    if lesson.get('publishing'):
        from chatgpt_web import validate_publishing
        result = dict(validate_publishing(lesson['publishing']))
        result.update(level=level, source='ChatGPT viết từ nội dung tập; cần duyệt trước khi đăng.')
        return result
    return {
        'description': f'{title}\nPodcast tiếng Trung {level} có chữ Hán, pinyin và nghĩa Việt.',
        'titles': [f'{title} | Luyện nghe tiếng Trung {level}'[:100],
                   f'Podcast tiếng Trung: {title} | Có pinyin & nghĩa Việt'[:100],
                   f'{title} — Nghe hội thoại Trung–Việt mỗi ngày'[:100]],
        'thumbnail_text': [title, lesson['title_zh'], 'NGHE & HIỂU\n' + title],
        'pinned_comment': 'Bạn sẽ trả lời thế nào trong tình huống này? Viết một câu tiếng Trung bên dưới. '
                          'Bạn muốn nghe chủ đề gì ở tập tiếp theo?',
        'cta': 'Theo dõi để nghe tập tiếp theo. Bạn muốn luyện tình huống nào?',
        'level': level,
        'source': 'Gợi ý biên tập từ kịch bản, chưa có dữ liệu hiệu suất kênh hoặc xu hướng trực tiếp.',
    }


def scene(lesson, index, options, *, portrait=False):
    # Draw at output resolution so portrait text never comes from a cropped landscape.
    width, height = (1080, 1920) if portrait else ((1280, 720) if options.get('resolution') == '720p' else (1920, 1080))
    scale = width / (1080 if portrait else 1920)
    bg, panel, accent, warm = PALETTES.get(options.get('theme'), PALETTES['Midnight'])
    im = Image.new('RGB', (width, height), bg)
    d = ImageDraw.Draw(im)
    def box(text, coords, size, color='#f3f6fa', bold=False):
        paragraph(d, text, tuple(round(v*scale) for v in coords), round(size*scale), color, bold)
    if portrait:
        d.ellipse((620, -140, 1380, 620), fill=panel)
        d.rounded_rectangle((52, 400, 1028, 1510), radius=40, fill=panel)
        d.rounded_rectangle((78, 448, 84, 1462), radius=3, fill=accent)
        box(options.get('brand', 'Mandarin Studio')[:60], (80, 140, 880, 100), 33, accent, True)
        box(lesson['title_vi'], (80, 255, 880, 110), 49, bold=True)
        line = lesson['lines'][index]
        box(line['zh'], (116, 505, 820, 360), 76, bold=True)
        box(line['pinyin'], (116, 905, 820, 200), 42, warm)
        d.line((116, 1140, 936, 1140), fill=accent, width=2)
        box(line['vi'], (116, 1190, 820, 245), 47)
        box('Bản đầy đủ trên kênh · Luyện nghe mỗi ngày', (80, 1570, 870, 120), 31, accent)
    else:
        d.ellipse((int(width*.64), -int(height*.4), int(width*1.13), int(height*.5)), fill=panel)
        def rect(coords, **kwargs):
            d.rounded_rectangle(tuple(round(v*scale) for v in coords), **kwargs)
        box(options.get('brand', 'Mandarin Studio')[:70], (100, 65, 1320, 70), 28, accent, True)
        box(options.get('level', 'HSK 1–2'), (1520, 65, 300, 70), 27, accent, True)
        box(lesson['title_vi'], (100, 163, 1720, 100), 52, bold=True)
        box(lesson['title_zh'], (100, 270, 1720, 70), 34, '#9fb2cb')
        rect((80, 390, 1840, 935), radius=round(32*scale), fill=panel)
        rect((100, 435, 106, 885), radius=max(1,round(3*scale)), fill=accent)
        line = lesson['lines'][index]
        box(line['zh'], (150, 445, 1610, 180), 72, bold=True)
        box(line['pinyin'], (150, 648, 1610, 95), 41, warm)
        box(line['vi'], (150, 788, 1610, 115), 42)
        box('Nghe hiểu mỗi ngày  /  Chữ Hán · Pinyin · Nghĩa Việt', (100, 976, 1500, 65), 25, accent)
    return im


def thumbnail(lesson, options, variant=0):
    bg, panel, accent, warm = PALETTES.get(options.get('theme'), PALETTES['Midnight'])
    im = Image.new('RGB', (1280, 720), bg)
    images = lesson.get('thumbnail_images', [])
    if images and variant < len(images):
        source = Path(images[variant])
        if not source.is_file():
            raise ValueError('Không tìm thấy ảnh nền thumbnail: ' + str(source))
        with Image.open(source) as original:
            im = ImageOps.fit(original.convert('RGB'), (1280, 720))
        overlay = Image.new('RGBA', im.size)
        shade = ImageDraw.Draw(overlay)
        for x in range(1280):
            shade.line((x, 0, x, 720), fill=(0, 0, 0, round(210 * (1-x/1280))))
        im = Image.alpha_composite(im.convert('RGBA'), overlay).convert('RGB')
    d = ImageDraw.Draw(im)
    if not images:
        d.ellipse((730, -180, 1450, 580), fill=panel)
    d.rounded_rectangle((55, 45, 470, 100), radius=20, fill=accent)
    paragraph(d, 'PODCAST TIẾNG TRUNG', (75, 52, 370, 44), 24, bg, True)
    text = publishing_data(lesson, options)['thumbnail_text'][variant]
    paragraph(d, text, (65, 150, 1100, 340), 99, '#f3f6fa', True)
    paragraph(d, options.get('level', 'HSK 1–2') + '  ·  CHỮ HÁN + PINYIN + NGHĨA VIỆT',
              (65, 550, 1120, 70), 28, warm, True)
    paragraph(d, options.get('brand', 'Mandarin Studio')[:70], (65, 640, 1120, 55), 24, accent)
    return im


def short_ranges(lesson, durations, limit=3, max_seconds=58):
    """Pick non-overlapping whole turns; every selected clip fits under 59 seconds."""
    if len(durations) != len(lesson['lines']):
        raise ValueError('Thời lượng không khớp kịch bản.')
    candidates = []
    for start in range(len(durations)):
        total, stop = 0.0, start
        while stop < len(durations) and total + durations[stop] <= max_seconds:
            total += durations[stop]
            stop += 1
        if stop > start:
            question = bool(re.search(r'[?？]', lesson['lines'][start]['zh'] + lesson['lines'][start]['vi']))
            score = min(total, 40) + 10 * question + 5 * (start == 0)
            candidates.append((score, start, stop, total))
    selected, occupied = [], set()
    for _, start, stop, total in sorted(candidates, reverse=True):
        indexes = set(range(start, stop))
        if not indexes & occupied:
            selected.append({'start': start, 'stop': stop, 'duration': total})
            occupied |= indexes
        if len(selected) >= limit:
            break
    return sorted(selected, key=lambda clip: clip['start'])


def render_frames(images, durations, audio, target, work, cancel):
    work.mkdir(parents=True, exist_ok=True)
    listing = work / 'frames.txt'
    listing.write_text(''.join(f"file '{path.name}'\nduration {seconds:.6f}\n" for path, seconds in zip(images, durations))
                       + f"file '{images[-1].name}'\n", encoding='utf-8')
    partial = target.with_suffix('.partial.mp4')
    run([FFMPEG, '-y', '-v', 'error', '-f', 'concat', '-safe', '1', '-i', listing,
         '-i', audio, '-t', f'{sum(durations):.6f}', '-vf', 'fps=24', '-c:v', 'libx264',
         '-preset', 'veryfast', '-tune', 'stillimage', '-crf', '21', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', partial], cancel)
    partial.replace(target)


def publishing_kit(lesson, out, options, durations=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = publishing_data(lesson, options)
    report = audit_lesson(lesson)
    (out/'description.txt').write_text(data['description'], encoding='utf-8')
    (out/'publishing.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    (out/'content_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for v in range(3):
        thumbnail(lesson, options, v).save(out/f'thumbnail_{"ABC"[v]}.jpg', quality=93)
    vocabulary = '\n'.join(f'{v["zh"]} · {v["pinyin"]}: {v["vi"]}' for v in lesson['vocabulary'])
    (out/'youtube_kit.txt').write_text(
        '3 TIÊU ĐỀ ĐỂ THỬ\n' + '\n'.join(data['titles']) + '\n\nMÔ TẢ\n'
        + data['description'] + '\n'
        + 'Nghe hội thoại một lần, thử hiểu trước khi đọc bản dịch.\n\nTỪ VỰNG\n' + vocabulary
        + '\n\n' + data['cta'] + '\n#HocTiengTrung #LuyenNgheTiengTrung #ChinesePodcast\n\nBÌNH LUẬN GHIM\n'
        + data['pinned_comment'] + '\n\nSAU KHI ĐĂNG\n'
        + 'Gắn Shorts với video đầy đủ bằng Related video trong YouTube Studio nếu tài khoản có hỗ trợ.\n'
        + 'So sánh tỷ lệ nhấp, giữ chân 30 giây đầu và thời lượng xem giữa các tập cùng nhóm.\n'
        + 'Thumbnail/tiêu đề phải đúng nội dung. Đổi một yếu tố mỗi lần để dễ đánh giá.\n'
        + 'Các gợi ý này không phải dữ liệu xu hướng trực tiếp hoặc bảo đảm lượt xem.\n', encoding='utf-8')
    with (out/'content_plan.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Tuan', 'Tap', 'Nhom', 'Chu de goi y', 'Trang thai'])
        for i, (group, topic) in enumerate(TOPICS):
            writer.writerow([i//3+1, i+1, group, topic, 'Y tuong - can bien tap'])
    with (out/'performance.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Video URL', 'Ngay dang', 'Tieu de', 'Thumbnail A/B/C', 'Impressions', 'CTR %',
                         'Giu chan 30s %', 'Thoi luong xem TB giay', 'Subscriber tang', 'Ghi chu'])
    return data


def export_premium(lesson, out, options, durations, audio_paths, full_audio, log, cancel):
    check(cancel)
    work = out/'assets/premium'
    work.mkdir(parents=True, exist_ok=True)
    log('Premium · Chuẩn bị bố cục video…')
    images = []
    for i in range(len(durations)):
        check(cancel)
        image = work/f'landscape_{i:03}.png'
        scene(lesson, i, options).save(image)
        images.append(image)
    render_frames(images, durations, full_audio, out/'video.mp4', work, cancel)
    clips = []
    if options.get('shorts', True):
        clips = short_ranges(lesson, durations)
        shorts = out/'shorts'
        shorts.mkdir(exist_ok=True)
        for number, clip in enumerate(clips, 1):
            check(cancel)
            log(f'Premium · Đang xuất Shorts {number}/{len(clips)}…')
            folder = work/f'short_{number:02}'
            folder.mkdir(exist_ok=True)
            frames = []
            indexes = range(clip['start'], clip['stop'])
            track = folder/'audio.wav'
            with wave.open(str(track), 'wb') as combined:
                combined.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                for i in indexes:
                    image = folder/f'portrait_{i:03}.png'
                    scene(lesson, i, options, portrait=True).save(image)
                    frames.append(image)
                    with wave.open(str(audio_paths[i]), 'rb') as source:
                        combined.writeframes(source.readframes(source.getnframes()))
            render_frames(frames, durations[clip['start']:clip['stop']], track,
                          shorts/f'short_{number:02}.mp4', folder, cancel)
            (shorts/f'short_{number:02}.txt').write_text(
                lesson['lines'][clip['start']]['vi'] + '\n' + lesson['title_vi']
                + '\nXem bản đầy đủ trên kênh.\n#HocTiengTrung #Shorts\n', encoding='utf-8')
    if options.get('local_publishing', True):
        publishing_kit(lesson, out, options, durations)
    scene(lesson, 0, options).save(out/'preview.png')
    if options.get('local_publishing', True):
        thumbnail(lesson, options).save(out/'thumbnail.png')
    manifest_path = out/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.update({'edition': 'premium-mvp', 'theme': options.get('theme', 'Midnight'),
                     'shorts': clips, 'shorts_resolution': [1080, 1920]})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    log('Hoàn tất Premium: video dài và Shorts.' if not options.get('local_publishing', True)
        else 'Hoàn tất Premium: video dài, Shorts và bộ đăng YouTube.')
    return out/'video.mp4'
