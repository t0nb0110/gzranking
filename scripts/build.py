"""Notion read-only export. Python 3.12+, standard library only."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlparse
from uuid import UUID
from zoneinfo import ZoneInfo

VERSION = '2026-03-11'

def identifier(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('データソースIDにはUUIDを指定してください（DBのURLではありません）') from None

class Notion:
    def __init__(self, token):
        if not token or any(c.isspace() for c in token):
            raise ValueError('NOTION_TOKEN が未設定、または空白を含んでいます')
        self.token = token
        self.last = 0

    def request(self, method, path, body=None):
        for attempt in range(7):
            time.sleep(max(0, .36 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            req = Request('https://api.notion.com/v1/' + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Authorization': 'Bearer ' + self.token,
                         'Notion-Version': VERSION, 'Content-Type': 'application/json'}, method=method)
            try:
                with urlopen(req, timeout=60) as res:
                    return json.load(res)
            except HTTPError as e:
                # Never print request headers, server bodies, or tokens.
                if (e.code == 429 or e.code >= 500) and attempt < 6:
                    try:
                        delay = float(e.headers.get('Retry-After', 2 ** attempt))
                    except ValueError:
                        delay = 2 ** attempt
                    time.sleep(max(0, delay))
                    continue
                raise RuntimeError(f'Notion API HTTP {e.code}。接続権限・ID・プロパティ設定を確認してください') from None
            except (URLError, TimeoutError):
                if attempt == 6:
                    raise RuntimeError('Notion APIへの接続がタイムアウトしました') from None
                time.sleep(2 ** attempt)

    def paginate(self, method, path, body=None):
        cursor = None
        seen = set()
        while True:
            payload = dict(body or {}, page_size=100)
            if cursor:
                payload['start_cursor'] = cursor
            result = self.request(method, path + ('?' + urlencode(payload) if method == 'GET' else ''),
                                  payload if method == 'POST' else None)
            yield from result['results']
            if not result.get('has_more'):
                break
            cursor = result.get('next_cursor')
            if not cursor or cursor in seen:
                raise RuntimeError('Notion APIのページネーションが進みません')
            seen.add(cursor)

    def query(self, source, body=None):
        return self.paginate('POST', f'data_sources/{source}/query', body)

    def property_items(self, page, prop):
        prop = quote(unquote(prop), safe='')
        return list(self.paginate('GET', f'pages/{page}/properties/{prop}'))


def check_schema(api, source, expected):
    schema = api.request('GET', f'data_sources/{source}')['properties']
    for name, kind in expected.items():
        if name not in schema or schema[name]['type'] != kind:
            raise ValueError(f'プロパティ「{name}」は {kind} 型で用意してください')


def title(api, page):
    prop = page['properties']['名前']
    items = prop['title']
    # Page title values can also be truncated at 25 references.
    if len(items) >= 25:
        items = [x['title'] for x in api.property_items(page['id'], prop['id'])]
    return ''.join(x.get('plain_text', x.get('text', {}).get('content', '')) for x in items) or '（無題）'


def day(value, tz, source_timezone=None):
    if not value:
        return None
    if len(value) == 10:
        return datetime.strptime(value, '%Y-%m-%d').strftime('%Y/%m/%d')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(source_timezone) if source_timezone else tz)
    return parsed.astimezone(tz).strftime('%Y/%m/%d')


def aggregate(characters, sessions):
    characters = sorted(characters, key=lambda c: (c['idx'] is None, c['idx'] if c['idx'] is not None else 0, c['id']))
    order = {c['id']: i for i, c in enumerate(characters)}
    counts = {k: Counter() for k in ('combo', 'trio', 'duel')}
    for s in sessions:
        ids = sorted(set(s['characters']), key=order.__getitem__)
        for k, n in (('combo', 2), ('trio', 3)):
            counts[k].update(combinations(ids, n))
        if len(ids) == 2:
            counts['duel'][tuple(ids)] += 1
    ranks = {k: [{'characters': list(group), 'count': n} for group, n in
                sorted(counter.items(), key=lambda row: (-row[1], tuple(order[i] for i in row[0])))[:3]]
             for k, counter in counts.items()}
    sessions.sort(key=lambda s: s['id'])
    sessions.sort(key=lambda s: s['date'] or '', reverse=True)
    return {'schemaVersion': 1, 'generatedAt': datetime.now(timezone.utc).isoformat(),
            'characters': characters, 'sessions': sessions, 'rankings': ranks}


def export(api, session_source, character_source, tz):
    check_schema(api, character_source, {'名前': 'title', 'idx': 'number'})
    check_schema(api, session_source, {'名前': 'title', '*start': 'date', '状況': 'status', '▶ PC': 'relation'})
    chars = []
    for p in api.query(character_source):
        if not p.get('in_trash'):
            chars.append({'id': p['id'], 'name': title(api, p), 'idx': p['properties']['idx']['number']})
    known = {c['id'] for c in chars}
    sessions = []
    query = {'filter': {'or': [{'property': '状況', 'status': {'equals': s}} for s in ('終了', '現行')]}}
    for p in api.query(session_source, query):
        props = p['properties']
        if p.get('in_trash') or (props['状況']['status'] or {}).get('name') not in ('終了', '現行'):
            continue
        rel = props['▶ PC']
        values = rel['relation']
        if rel.get('has_more'):
            values = [r['relation'] for r in api.property_items(p['id'], rel['id'])]
        ids = sorted({r['id'] for r in values})
        if set(ids) - known:
            raise ValueError('参加キャラにキャラDBから取得できないページがあります。共有権限・削除済みキャラ・relation先を確認してください')
        url = p['url']
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not (parsed.hostname == 'notion.so' or (parsed.hostname or '').endswith('.notion.so') or parsed.hostname == 'notion.com' or (parsed.hostname or '').endswith('.notion.com') or (parsed.hostname or '').endswith('.notion.site')):
            raise ValueError('想定外のNotionページURLです')
        date = props['*start']['date']
        sessions.append({'id': p['id'], 'title': title(api, p), 'date': day(date['start'] if date else None, tz, date.get('time_zone') if date else None), 'url': url, 'characters': ids})
    result = aggregate(chars, sessions)
    result['timezone'] = str(tz)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='web/data.json')
    parser.add_argument('--list-sources', metavar='DATABASE_ID', help='DB IDからdata source IDを確認（秘密情報は表示しません）')
    args = parser.parse_args()
    api = Notion(os.environ.get('NOTION_TOKEN', ''))
    if args.list_sources:
        db = api.request('GET', 'databases/' + identifier(args.list_sources))
        for s in db['data_sources']:
            print(s['id'], s.get('name', ''))
        return
    data = export(api, identifier(os.environ.get('SESSION_SOURCE_ID')), identifier(os.environ.get('CHARACTER_SOURCE_ID')), ZoneInfo(os.environ.get('DISPLAY_TIMEZONE', 'Asia/Tokyo')))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(out)
    print(f'取得完了: {len(data["characters"])}キャラ / {len(data["sessions"])}セッション')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, KeyError) as e:
        raise SystemExit(str(e)) from None
