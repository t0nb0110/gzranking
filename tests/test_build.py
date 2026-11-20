import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build import Notion, aggregate, day, export, identifier, session_date, check_schema

class Tests(unittest.TestCase):
    def test_ranks_and_ties(self):
        chars = [{'id': k, 'name': k, 'idx': n} for k,n in [('c',3),('a',1),('d',None),('b',2)]]
        sessions = [{'id':str(i),'characters':ids,'date':None} for i,ids in enumerate([['c','b','a'],['b','a'],['c','a'],['b','b','a']])]
        result = aggregate(chars,sessions)
        self.assertEqual(result['rankings']['combo'][0], {'characters':['a','b'],'count':3,'rank':1})
        self.assertEqual(result['rankings']['trio'], [{'characters':['a','b','c'],'count':1,'rank':1}])
        self.assertEqual(result['rankings']['duel'][0]['count'],2)
        self.assertEqual([c['id'] for c in result['characters']], list('abcd'))
        tie = aggregate(chars,[{'id':'s','characters':['c','b','a'],'date':None}])
        self.assertEqual([r['characters'] for r in tie['rankings']['combo']], [['a','b'],['a','c'],['b','c']])

    def test_rankings_include_cutoff_ties(self):
        chars = [{'id': k, 'name': k, 'idx': n} for k,n in [('a',1),('b',2),('c',3),('d',4),('e',5)]]
        def sessions(groups):
            return [{'id':str(i),'characters':ids,'date':None} for i,ids in enumerate(groups)]
        # 5, 4, 3, 3: both third-place pairs must survive, sorted by idx.
        groups = [['a','b']]*5 + [['a','c']]*4 + [['a','e']]*3 + [['a','d']]*3 + [['b','c']]*2
        result = aggregate(chars, sessions(groups))
        for key in ('combo','duel'):
            self.assertEqual([r['rank'] for r in result['rankings'][key]], [1,2,3,3])
            self.assertEqual([r['characters'] for r in result['rankings'][key]], [['a','b'],['a','c'],['a','d'],['a','e']])
        # Four first-place groups are all shown, with no fourth-place group.
        result = aggregate(chars, sessions([['a','e'],['a','d'],['a','c'],['a','b']]))
        self.assertEqual([r['rank'] for r in result['rankings']['combo']], [1,1,1,1])
        # Dense ranking: ties do not skip the next count level.
        result = aggregate(chars, sessions([['a','b']]*3 + [['a','c']]*3 + [['a','d']]*2 + [['a','e']]))
        self.assertEqual([r['rank'] for r in result['rankings']['combo']], [1,1,2,3])
        groups = ([['a','b']]*13 + [['a','c']]*13 + [['a','d']]*9 + [['a','e']]*9 + [['b','c']]*9 + [['b','d']]*7 + [['b','e']]*6)
        result = aggregate(chars, sessions(groups))
        for key in ('combo','duel'):
            self.assertEqual([r['rank'] for r in result['rankings'][key]], [1,1,2,2,2,3])
            self.assertEqual([r['count'] for r in result['rankings'][key]], [13,13,9,9,9,7])
        # Trio cutoff uses the same policy.
        result = aggregate(chars, sessions([['a','b','c']]*4 + [['a','b','d']]*3 + [['a','b','e']]*2 + [['b','c','d']]*2))
        self.assertEqual([r['rank'] for r in result['rankings']['trio']], [1,2,3,3])
        self.assertEqual(aggregate(chars, [])['rankings']['combo'], [])

    def test_dates(self):
        tz=ZoneInfo('Asia/Tokyo')
        self.assertEqual(day('2026-11-10T23:30:00Z',tz),'2026/11/11')
        self.assertEqual(day('2026-11-10',tz),'2026/11/10')
        self.assertIsNone(day(None,tz))
        self.assertEqual(day('2026-11-10T23:30:00',tz,'UTC'),'2026/11/11')

    def test_formula_dates(self):
        tz = ZoneInfo('Asia/Tokyo')
        for kind in ('date', 'formula'):
            for value, expected in [
                ({'start': '2026-11-18T23:30:00Z'}, '2026/11/19'),
                ({'start': '2026-11-18'}, '2026/11/18'),
                ({'start': '2026-11-18', 'end': '2026-11-20'}, '2026/11/18'),
                (None, None),
            ]:
                prop = {'type': 'date', 'date': value} if kind == 'date' else {'type': 'formula', 'formula': {'type': 'date', 'date': value}}
                with self.subTest(kind=kind, value=value):
                    self.assertEqual(session_date(prop, tz), expected)
        self.assertIsNone(session_date({'type': 'formula', 'formula': {'type': 'string', 'string': ''}}, tz))
        for result in [{'type': 'string', 'string': '2026/11/18'}, {'type': 'number', 'number': 0}, {'type': 'boolean', 'boolean': False}]:
            with self.assertRaises(ValueError): session_date({'type': 'formula', 'formula': result}, tz)

    def test_formula_export(self):
        class Fake:
            def request(self, method, path, body=None):
                schema = {'名前':'title','idx':'number'} if path.endswith('/chars') else {'名前':'title','*start':'formula','状況':'status','▶ PC':'relation'}
                return {'properties': {k: {'type':v} for k,v in schema.items()}}
            def query(self, source, body=None):
                if source == 'chars': return []
                return [{'id': str(i), 'url':'https://app.notion.com/p/test', 'properties': {
                    '名前': {'title':[{'plain_text':'卓'}]},
                    '*start': {'type':'formula','formula': result},
                    '状況': {'status':{'name':'終了'}}, '▶ PC': {'relation':[]}
                }} for i,result in enumerate([
                    {'type':'date','date':{'start':'2026-11-18T23:30:00Z'}},
                    {'type':'date','date':None}, {'type':'string','string':''}
                ])]
        result = export(Fake(), 'sessions', 'chars', ZoneInfo('Asia/Tokyo'))
        self.assertEqual([s['date'] for s in result['sessions']], ['2026/11/19',None,None])
        api = Notion('test')
        with patch.object(api, 'request', return_value={'properties':{'*start':{'type':'rollup'}}}):
            with self.assertRaises(ValueError): check_schema(api, 'sessions', {'*start':('date','formula')})

    def test_pagination(self):
        api=Notion('test')
        with patch.object(api,'request',side_effect=[{'results':[1],'has_more':True,'next_cursor':'opaque'},{'results':[2],'has_more':False}]) as req:
            self.assertEqual(list(api.query('source')), [1,2])
            self.assertEqual(req.call_args_list[1].args[2]['start_cursor'],'opaque')
        with patch.object(api,'request',side_effect=[{'results':[1],'has_more':True,'next_cursor':'x'}]*2):
            with self.assertRaises(RuntimeError): list(api.query('source'))

    def test_property_pagination_encoding(self):
        api=Notion('test')
        with patch.object(api,'request',side_effect=[{'results':[1],'has_more':True,'next_cursor':'a/b'},{'results':[2],'has_more':False}]) as req:
            self.assertEqual(api.property_items('p','a%3Ab'),[1,2])
            self.assertIn('a%3Ab?page_size=100',req.call_args_list[0].args[1])
            self.assertIn('start_cursor=a%2Fb',req.call_args_list[1].args[1])

    def test_relation_expansion_and_unresolved(self):
        class Fake:
            def request(self,method,path,body=None):
                schema={'名前':'title','idx':'number'} if path.endswith('/chars') else {'名前':'title','*start':'date','状況':'status','▶ PC':'relation'}
                return {'properties':{k:{'type':v} for k,v in schema.items()}}
            def query(self,source,body=None):
                if source=='chars':
                    return [{'id':k,'properties':{'名前':{'title':[{'plain_text':k}]},'idx':{'number':i}}} for i,k in enumerate(['a','b','c'])]
                return [{'id':'s','url':'https://app.notion.com/p/s','properties':{'名前':{'title':[{'plain_text':'卓'}]},'*start':{'date':None},'状況':{'status':{'name':'終了'}},'▶ PC':{'id':'rel','relation':[{'id':'a'},{'id':'b'}],'has_more':True}}}]
            def property_items(self,page,prop):
                return [{'relation':{'id':k}} for k in ['a','b','c']]
        api=Fake()
        result=export(api,'sessions','chars',ZoneInfo('Asia/Tokyo'))
        self.assertEqual(len(result['sessions'][0]['characters']),3)
        self.assertEqual(result['rankings']['duel'],[])
        api.property_items=lambda *args:[{'relation':{'id':'unknown'}}]
        with self.assertRaises(ValueError): export(api,'sessions','chars',ZoneInfo('Asia/Tokyo'))

    def test_retry_and_safe_error(self):
        import io
        from urllib.error import HTTPError
        api=Notion('private-token')
        limited=HTTPError('https://api.notion.com',429,'private-token',{'Retry-After':'2'},None)
        with patch('build.urlopen',side_effect=[limited,io.BytesIO(b'{"ok":true}')]), patch('build.time.sleep') as sleep:
            self.assertEqual(api.request('GET','test'),{'ok':True})
            self.assertTrue(any(call.args==(2.0,) for call in sleep.call_args_list))
        unauthorized=HTTPError('https://api.notion.com',401,'private-token',{},None)
        with patch('build.urlopen',side_effect=unauthorized), patch('build.time.sleep'):
            with self.assertRaises(RuntimeError) as error: api.request('GET','test')
            self.assertNotIn('private-token',str(error.exception))
            self.assertIn('401',str(error.exception))

    def test_token_and_id_validation(self):
        for token in ['', 'abc\nsecret']:
            with self.assertRaises(ValueError): Notion(token)
        with self.assertRaises(ValueError): identifier('https://notion.so/x')

if __name__=='__main__': unittest.main()
