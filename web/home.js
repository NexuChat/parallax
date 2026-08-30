(() => {
  'use strict';

  const sites = [
    ['workspace', 5], ['shop', 4], ['docs', 3], ['admin', 3], ['control', 0],
  ];
  const summaryUrl = '/graded-summary.json';
  const sweepIndexUrl = '/console/runs/index.json';
  const applicationOrder = ['workspace', 'shop', 'admin', 'docs', 'control'];
  const table = document.getElementById('scoreboard-data');
  const note = document.getElementById('scoreboard-note');
  const controlFigures = document.getElementById('control-figures');
  const controlRatio = document.getElementById('control-ratio');
  const gallery = document.getElementById('app-gallery');
  const feedStatus = document.getElementById('feed-status');
  const consoleFrame = document.getElementById('console-frame');
  const generatedSpec = document.getElementById('generated-spec');

  function drawScoreboard(summary) {
    const rows = sites.map(([site, planted]) => {
      const run = summary && summary[site];
      const found = run && Number.isFinite(run.found) ? String(run.found) : '<span class="not-run">not yet run</span>';
      const missed = run && Number.isFinite(run.missed) ? String(run.missed) : '<span class="not-run">not yet run</span>';
      const falsePositives = run && Number.isFinite(run.false_positives) ? String(run.false_positives) : '<span class="not-run">not yet run</span>';
      const reportedPlants = run && Number.isFinite(run.planted) ? String(run.planted) : String(planted);
      return `<tr><td class="${site === 'control' ? 'control' : ''}">${site}${site === 'control' ? ' / clean control' : ''}</td><td>${reportedPlants}</td><td>${found}</td><td>${missed}</td><td>${falsePositives}</td></tr>`;
    });
    table.innerHTML = rows.join('');
    if (summary) note.textContent = 'Run figures loaded from /graded-summary.json. Planted counts remain the demo declarations.';
  }

  function drawControlSummary(data) {
    const summary = data && data.sites ? data.sites : data;
    const totals = data && data.totals;
    const control = summary && summary.control;
    const planted = totals && totals.planted;
    const found = totals && totals.found;
    const falsePositives = control && control.false_positives;
    if (![planted, found, falsePositives].every(Number.isFinite)) {
      controlFigures.innerHTML = '<span class="control-figure"><b>Unavailable</b><small>defects found</small></span><span class="control-figure"><b>Unavailable</b><small>defects planted</small></span><span class="control-figure"><b>Unavailable</b><small>findings on control</small></span>';
      controlRatio.textContent = 'Control result unavailable: /graded-summary.json could not provide the measured figures.';
      return;
    }
    controlFigures.innerHTML = `<span class="control-figure"><b>${found}</b><small>defects found</small></span><span class="control-figure"><b>${planted}</b><small>defects planted</small></span><span class="control-figure"><b>${falsePositives}</b><small>findings on control</small></span>`;
    controlRatio.textContent = `${found} of ${planted} defects found. ${falsePositives} findings appeared on the clean control.`;
  }

  async function loadGeneratedSpec() {
    try {
      const response = await fetch('/generated-example.spec.ts', { cache: 'no-store' });
      if (!response.ok) return;
      generatedSpec.textContent = await response.text();
    } catch (_) { /* The committed example remains available when served. */ }
  }

  async function loadScoreboard() {
    drawScoreboard(null);
    try {
      const response = await fetch(summaryUrl, { cache: 'no-store' });
      if (!response.ok) throw new Error('summary unavailable');
      const data = await response.json();
      if (!data || typeof data !== 'object') throw new Error('summary invalid');
      drawScoreboard(data.sites || data);
      drawControlSummary(data);
    } catch (_) {
      drawControlSummary(null);
    }
  }

  function feedUrl(entry) {
    return `/console/${entry.feed.replace(/^\/+/, '')}`;
  }

  function updateWall(entry, updateUrl) {
    const feed = feedUrl(entry);
    consoleFrame.src = `/console?feed=${encodeURIComponent(feed)}`;
    consoleFrame.title = `Parallax live witness mosaic — ${entry.name}`;
    feedStatus.textContent = `${entry.name}: ${entry.findings} findings across ${entry.mosaics} mosaics · ${feed}`;
    gallery.querySelectorAll('.app-card').forEach((card) => {
      const selected = card.dataset.app === entry.name;
      card.classList.toggle('is-selected', selected);
      card.querySelector('.app-select').setAttribute('aria-pressed', String(selected));
    });
    if (updateUrl) {
      const url = new URL(location.href);
      url.searchParams.set('app', entry.name);
      history.replaceState(null, '', url);
    }
  }

  function drawGallery(entries) {
    gallery.innerHTML = entries.map((entry) => {
      const kinds = Object.entries(entry.by_kind).map(([kind, count]) => `${kind} ${count}`).join(' · ');
      const controlNote = entry.name === 'control' ? '<span class="app-control-note">Clean control: nothing is planted; anything found is a false positive.</span>' : '';
      return `<article class="app-card${entry.name === 'control' ? ' is-control' : ''}" data-app="${entry.name}"><button class="app-select" type="button" aria-pressed="false"><span class="app-name">${entry.name}</span><span class="app-count">${entry.findings} findings</span><span class="app-kinds">${kinds}</span>${controlNote}</button><a class="app-live" href="https://demo.mlki.app/${entry.name}/" target="_blank" rel="noopener">open application ↗</a></article>`;
    }).join('');
    gallery.setAttribute('aria-busy', 'false');
    entries.forEach((entry) => {
      gallery.querySelector(`[data-app="${entry.name}"] .app-select`).addEventListener('click', () => updateWall(entry, true));
    });
    const requestedApp = new URLSearchParams(location.search).get('app');
    const selected = entries.find((entry) => entry.name === requestedApp)
      || entries.find((entry) => entry.name === 'workspace')
      || entries[0];
    updateWall(selected, requestedApp !== selected.name);
  }

  async function loadGallery() {
    try {
      const response = await fetch(sweepIndexUrl, { cache: 'no-store' });
      if (!response.ok) throw new Error('index unavailable');
      const index = await response.json();
      const entries = applicationOrder
        .filter((name) => index && index[name] && typeof index[name].feed === 'string')
        .map((name) => ({ name, ...index[name] }));
      if (!entries.length) throw new Error('index empty');
      drawGallery(entries);
    } catch (_) {
      gallery.innerHTML = '<p class="gallery-fallback">Published sweep index unavailable. Showing one published sweep instead.</p>';
      gallery.setAttribute('aria-busy', 'false');
      feedStatus.textContent = 'Published sweep index unavailable; attached to /console/runs/latest/feed.jsonl.';
    }
  }

  loadScoreboard();
  loadGeneratedSpec();
  loadGallery();
})();
