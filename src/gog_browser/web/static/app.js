const API = '/api';

function setStatus(msg, isError = false) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.style.color = isError ? 'var(--danger)' : 'var(--muted)';
}

function assetUrl(gameId, relPath) {
  if (!relPath) return null;
  return `${API}/metadata/${encodeURIComponent(gameId)}/${encodeURIComponent(relPath)}`;
}

function thumbUrl(game) {
  if (game.thumbnail) return game.thumbnail.startsWith('http') ? game.thumbnail : 'https:' + game.thumbnail;
  const first = (game.screenshots_local || [])[0];
  return first ? assetUrl(game.id, first) : null;
}

function renderCards(games, filter) {
  const list = document.getElementById('gameList');
  const q = (filter || '').toLowerCase().trim();
  const filtered = q ? games.filter(g => {
    const title = (g.gog_title || g.display_name || g.id || '').toLowerCase();
    const path = (g.installer_path || '').toLowerCase();
    return title.includes(q) || path.includes(q);
  }) : games;
  list.innerHTML = filtered.map(game => {
    const thumb = thumbUrl(game);
    const title = game.gog_title || game.display_name || game.id || 'Unknown';
    const sub = game.gog_slug ? `GOG: ${game.gog_slug}` : (game.installer_path || game.id);
    return `
      <article class="game-card" data-id="${escapeHtml(game.id)}">
        ${thumb ? `<img class="game-card-thumb" src="${escapeHtml(thumb)}" alt="">` : '<div class="game-card-thumb"></div>'}
        <div class="game-card-body">
          <h3 class="game-card-title">${escapeHtml(title)}</h3>
          <p class="game-card-sub">${escapeHtml(sub)}</p>
          <div class="game-card-actions">
            <button type="button" class="btn btn-secondary open-detail">View</button>
            ${game.gog_link ? `<a href="${escapeHtml(game.gog_link)}" target="_blank" rel="noopener" class="btn">GOG</a>` : ''}
          </div>
        </div>
      </article>
    `;
  }).join('');

  list.querySelectorAll('.open-detail').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.game-card');
      if (card) openDetail(card.dataset.id);
    });
  });
}

function escapeHtml(s) {
  if (s == null) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

async function loadGames() {
  setStatus('Loading...');
  try {
    const r = await fetch(`${API}/games`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Failed to load');
    window._games = data.games || [];
    renderCards(window._games, document.getElementById('searchInput').value);
    setStatus(`${window._games.length} game(s)`);
  } catch (e) {
    setStatus('Error: ' + e.message, true);
    window._games = [];
  }
}

async function runScan() {
  const btn = document.getElementById('scanBtn');
  btn.classList.add('loading');
  setStatus('Scanning...');
  try {
    const r = await fetch(`${API}/scan`, { method: 'POST' });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Scan failed');
    setStatus(`Scan done: ${data.added} added, ${data.removed} removed, ${data.total} total.`);
    await loadGames();
  } catch (e) {
    setStatus('Scan error: ' + e.message, true);
  } finally {
    btn.classList.remove('loading');
  }
}

let currentDetailId = null;

async function openDetail(gameId) {
  currentDetailId = gameId;
  const panel = document.getElementById('detailPanel');
  const titleEl = document.getElementById('detailTitle');
  const contentEl = document.getElementById('detailContent');
  panel.classList.remove('hidden');
  titleEl.textContent = 'Loading...';
  contentEl.innerHTML = '';
  try {
    const r = await fetch(`${API}/games/${encodeURIComponent(gameId)}`);
    const g = await r.json();
    if (!r.ok) throw new Error(g.detail || 'Not found');
    titleEl.textContent = g.gog_title || g.display_name || g.id || 'Unknown';
    let html = '';
    if (g.description) html += `<p>${escapeHtml(g.description.slice(0, 500))}${g.description.length > 500 ? '…' : ''}</p>`;
    if (g.gog_link) html += `<p><a href="${escapeHtml(g.gog_link)}" target="_blank" rel="noopener">Open on GOG</a></p>`;
    if (g.installer_path) html += `<p><small>Installer: ${escapeHtml(g.installer_path)}</small></p>`;
    if ((g.screenshots_local || []).length) {
      html += '<div class="screenshots-row">';
      g.screenshots_local.forEach(rel => {
        const url = assetUrl(gameId, rel);
        if (url) html += `<img src="${escapeHtml(url)}" alt="">`;
      });
      html += '</div>';
    }
    contentEl.innerHTML = html || '<p>No extra details.</p>';

    document.getElementById('overrideName').value = g.gog_search_name_override || g.display_name || '';
    document.getElementById('refreshBtn').onclick = () => refreshGame(gameId);
    document.getElementById('saveOverrideBtn').onclick = () => saveOverride(gameId);
  } catch (e) {
    contentEl.innerHTML = '<p>Error: ' + escapeHtml(e.message) + '</p>';
  }
}

async function refreshGame(gameId) {
  setStatus('Refreshing from GOG...');
  try {
    const r = await fetch(`${API}/games/${encodeURIComponent(gameId)}/refresh`, { method: 'POST' });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Refresh failed');
    setStatus('Refreshed: ' + (data.title || gameId));
    if (currentDetailId === gameId) openDetail(gameId);
    await loadGames();
  } catch (e) {
    setStatus('Refresh error: ' + e.message, true);
  }
}

async function saveOverride(gameId) {
  const name = document.getElementById('overrideName').value.trim();
  try {
    const r = await fetch(`${API}/games/${encodeURIComponent(gameId)}/override`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gog_search_name: name || null }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Save failed');
    setStatus('Override saved. Use "Refresh from GOG" to re-fetch.');
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  }
}

document.getElementById('detailClose').addEventListener('click', () => {
  document.getElementById('detailPanel').classList.add('hidden');
  currentDetailId = null;
});

document.getElementById('scanBtn').addEventListener('click', runScan);
document.getElementById('searchInput').addEventListener('input', () => {
  if (window._games) renderCards(window._games, document.getElementById('searchInput').value);
});

loadGames();
