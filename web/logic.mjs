export function matches(session, selected, mode) {
  return [...selected].every(id => session.characters.includes(id)) &&
    (mode !== 'exact' || session.characters.length === selected.size);
}
export function notionURL(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && ['notion.so','notion.com','notion.site'].some(h => u.hostname === h || u.hostname.endsWith('.'+h)) ? u.href : null;
  } catch { return null; }
}
