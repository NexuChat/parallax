(() => {
  'use strict';

  const sites = [
    ['workspace', 4], ['shop', 4], ['docs', 3], ['admin', 3], ['control', 0],
  ];
  const summaryUrl = '/graded-summary.json';
  const table = document.getElementById('scoreboard-data');
  const note = document.getElementById('scoreboard-note');
  const feedStatus = document.getElementById('feed-status');
  const consoleFrame = document.getElementById('console-frame');

  function drawScoreboard(summary) {
    const rows = sites.map(([site, planted]) => {
      const run = summary && summary[site];
      const found = run && Number.isFinite(run.found) ? String(run.found) : '<span class="not-run">not yet run</span>';
      const falsePositives = run && Number.isFinite(run.false_positives) ? String(run.false_positives) : '<span class="not-run">not yet run</span>';
      return `<tr><td class="${site === 'control' ? 'control' : ''}">${site}${site === 'control' ? ' / clean control' : ''}</td><td>${planted}</td><td>${found}</td><td>${falsePositives}</td></tr>`;
    });
    table.innerHTML = rows.join('');
    if (summary) note.textContent = 'Run figures loaded from /graded-summary.json. Planted counts remain the demo declarations.';
  }

  async function loadScoreboard() {
    drawScoreboard(null);
    try {
      const response = await fetch(summaryUrl, { cache: 'no-store' });
      if (!response.ok) return;
      const data = await response.json();
      if (data && typeof data === 'object') drawScoreboard(data.sites || data);
    } catch (_) { /* Declared plants remain the offline baseline. */ }
  }

  async function attachRun() {
    const run = new URLSearchParams(location.search).get('run');
    if (!run || !/^[a-zA-Z0-9_-]+$/.test(run)) return;
    const feed = `/runs/${run}/feed.jsonl`;
    try {
      const response = await fetch(feed, { cache: 'no-store' });
      if (!response.ok) throw new Error('unavailable');
      consoleFrame.src = `/console?feed=${encodeURIComponent(feed)}`;
      feedStatus.textContent = `Live feed attached: ${feed}`;
    } catch (_) {
      feedStatus.textContent = `Live feed unavailable; fixture feed remains visible.`;
    }
  }

  loadScoreboard();
  attachRun();
})();
