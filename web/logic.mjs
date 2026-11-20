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

// Group equal counts while retaining the server's idx ordering within each group.
export function groupRankings(rows) {
  const groups = [];
  for (const row of rows) {
    let group = groups[groups.length - 1];
    if (!group || group.count !== row.count) {
      if (groups.length === 3) break;
      group = { rank: groups.length + 1, count: row.count, rows: [] };
      groups.push(group);
    }
    group.rows.push(row);
  }
  return groups;
}
