"""Recover an uncertain ElevenLabs request using GET history, never another POST."""
import json
import http.client
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

def _get(request, timeout, cancel):
    from studio import check
    for attempt in range(3):
        check(cancel)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), response.headers.get('Content-Type', '') if hasattr(response, 'headers') else ''
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead, ssl.SSLError):
            if attempt == 2:
                raise
        if cancel:
            cancel.wait(attempt+1)
        else:
            time.sleep(attempt+1)
    raise RuntimeError('History GET did not complete')


def recover_audio(pending, api_key, target, cancel=None):
    from studio import check
    check(cancel)
    start = int(pending['requested_at'])
    params = {'page_size': 100, 'source': 'TTS', 'voice_id': pending['voice'],
              'model_id': pending['model'], 'search': pending['text'],
              'date_after_unix': start-5, 'date_before_unix': start+600}
    headers = {'xi-api-key': api_key.strip()}
    try:
        request = urllib.request.Request('https://api.elevenlabs.io/v1/history?' + urllib.parse.urlencode(params), headers=headers)
        raw, _ = _get(request, 30, cancel)
        data = json.loads(raw)
        matches = []
        for item in data.get('history', []):
            settings = item.get('settings') or {}
            expected = pending.get('voice_settings') or {
                'speed': pending['speed'], 'stability': pending['stability'], 'similarity_boost': 0.75}
            if (item.get('text') == pending['text'] and item.get('voice_id') == pending['voice']
                    and item.get('model_id') == pending['model']
                    and start-5 <= item.get('date_unix', 0) < start+600
                    and all(settings.get(key) == value for key, value in expected.items())):
                matches.append(item)
        if len(matches) != 1 or data.get('has_more'):
            return False
        check(cancel)
        history_id = urllib.parse.quote(matches[0]['history_item_id'], safe='')
        request = urllib.request.Request(f'https://api.elevenlabs.io/v1/history/{history_id}/audio', headers=headers)
        audio, content_type = _get(request, 60, cancel)
        check(cancel)
        if 'audio/' not in content_type or len(audio) < 500:
            return False
        temporary = target.with_suffix('.recovered.partial.mp3')
        temporary.write_bytes(audio)
        temporary.replace(target)
        return True
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead,
            ssl.SSLError, ValueError, KeyError, TypeError):
        # Failure to prove a unique exact match must never trigger another billed POST.
        return False
