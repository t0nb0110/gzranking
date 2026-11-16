"""Create synthetic data locally; never used by the deployment workflow."""
from pathlib import Path
import json
from build import aggregate
chars = [{'id': str(i), 'name': name, 'idx': i} for i, name in enumerate(['アオイ', 'ハル', 'ミナト', 'リツ', 'ユキ'])]
sessions = [dict(id=str(i), title=t, date=d, url='https://www.notion.so/', characters=ids) for i,(t,d,ids) in enumerate([
    ('星降る街の約束','2026/11/10',['0','1','2']),
    ('夜明けの図書館','2026/11/08',['0','1']),
    ('灯台守の手紙','2026/11/03',['0','1','2','3']),
    ('雨音の向こう','2026/10/29',['1','2']),
    ('冬の旅支度',None,['0','3']),
])]
data=aggregate(chars,sessions)
data.update(demo=True,timezone='Asia/Tokyo')
out=Path(__file__).resolve().parents[1]/'web'/'data.json'
out.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
print('サンプルデータを作成しました')
