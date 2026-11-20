import { matches, notionURL } from './logic.mjs';
const $ = id => document.getElementById(id);
const selected = new Set();
let data, mode = 'all', limit = 50;
const node = (tag, text, cls) => { const el = document.createElement(tag); if(text !== undefined) el.textContent = text; if(cls) el.className = cls; return el; };
function drawCharacters() {
  const q = $('character-search').value.trim().toLocaleLowerCase();
  $('characters').replaceChildren();
  for(const c of data.characters.filter(c => c.name.toLocaleLowerCase().includes(q))) {
    const label = node('label', undefined, 'chip');
    const input = node('input'); input.type = 'checkbox'; input.checked = selected.has(c.id);
    input.addEventListener('change', () => { input.checked ? selected.add(c.id) : selected.delete(c.id); limit=50; drawResults(); });
    label.append(input, document.createTextNode(c.name)); $('characters').append(label);
  }
  if (!$('characters').children.length) $('characters').append(node('p','該当するキャラクターはいません。'));
}
function drawResults() {
  const names = data.characters.filter(c=>selected.has(c.id)).map(c=>c.name);
  $('selected').textContent = names.length ? `選択中：${names.join('・')}` : '未選択：対象セッションをすべて表示します。';
  const results = selected.size ? data.sessions.filter(s => matches(s,selected,mode)) : data.sessions;
  $('result-count').textContent = `${results.length}件`;
  $('sessions').replaceChildren();
  for(const s of results.slice(0,limit)) {
    const li = node('li'); li.append(node('span',s.title),node('time',s.date || '日付未設定','muted'));
    const url = notionURL(s.url);
    if(url) { const a = node('a','↗'); a.href=url; a.target='_blank'; a.rel='noopener noreferrer'; a.setAttribute('aria-label',`${s.title}をNotionで開く`); a.title='Notionで開く'; li.append(a); }
    $('sessions').append(li);
  }
  if(!results.length) $('sessions').append(node('li','条件に合うセッションはありません。'));
  $('more').hidden = results.length <= limit;
}
async function init() {
  try {
    const res = await fetch('./data.json', {cache:'no-store'});
    if(!res.ok) throw Error('fetch');
    data = await res.json();
    if(data.schemaVersion !== 1 || !Array.isArray(data.characters) || !Array.isArray(data.sessions)) throw Error('schema');
    const names = new Map(data.characters.map(c=>[c.id,c.name]));
    for(const [key,title] of [['combo','コンビ TOP 3'],['trio','トリオ TOP 3'],['duel','タイマン TOP 3']]) {
      const card=node('article',undefined,'card'); card.append(node('h3',title)); const list=node('ol');
      let previousCount, rank = 0;
      for(const [index,r] of data.rankings[key].entries()) {
        if(r.count !== previousCount) rank = index + 1;
        previousCount = r.count;
        const li=node('li'); li.value = r.rank ?? rank;
        li.append(node('span',r.characters.map(id=>names.get(id)).join(' × ')),node('strong',`${r.count} 卓`)); list.append(li);
      }
      card.append(list.children.length ? list : node('p','まだ共演の記録がありません。')); $('rankings').append(card);
    }
    $('updated').textContent=`更新 ${new Date(data.generatedAt).toLocaleString('ja-JP',{timeZone:data.timezone || 'Asia/Tokyo'})} / ${data.characters.length}キャラ・${data.sessions.length}卓`;
    $('notice').textContent = data.demo ? 'サンプル表示です。セットアップ後、実データに置き換わります。' : '';
    $('character-search').disabled=false; $('clear').disabled=false; $('modes').disabled=false;
    drawCharacters(); drawResults();
  } catch { $('notice').textContent='データを読み込めませんでした。時間をおいて再読み込みしてください。初回はGitHub Actionsの実行結果を確認してください。'; }
}
$('character-search').addEventListener('input',drawCharacters);
$('clear').addEventListener('click',()=>{selected.clear();limit=50;drawCharacters();drawResults();});
$('modes').addEventListener('change',e=>{mode=e.target.value;limit=50;drawResults();});
$('more').addEventListener('click',()=>{limit+=50;drawResults();});
init();
