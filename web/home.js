(() => {
  'use strict';

  // Nothing about the fleet is hardcoded here any more. A hardcoded list of
  // five sites with their planted counts is a second source of truth that goes
  // stale the moment a fixture is added — which is exactly what happened.
  const CONTROLS = ['control', 'call'];
  // Sweeps of applications nobody built for Parallax. They are the strongest
  // evidence on the page and belong in the gallery, marked as what they are.
  const EXTERNAL = {
    'the-internet': 'a public automation-practice site',
    arbchat: 'a live Arabic chat product, signed in',
    'workspace-proposed': 'scenarios proposed by Gemini, not declared',
  };
  const summaryUrl = '/graded-summary.json';
  const generatedSpecVerificationUrl = '/generated-spec-verification.json';
  const sweepIndexUrl = '/console/runs/index.json';

  const table = document.getElementById('scoreboard-data');
  const note = document.getElementById('scoreboard-note');
  const controlFigures = document.getElementById('control-figures');
  const controlRatio = document.getElementById('control-ratio');
  const gallery = document.getElementById('app-gallery');
  const feedStatus = document.getElementById('feed-status');
  const consoleFrame = document.getElementById('console-frame');
  const generatedSpec = document.getElementById('generated-spec');
  const generatedSpecFigures = document.getElementById('generated-spec-figures');
  const generatedSpecSummaryNote = document.getElementById('generated-spec-summary-note');
  const footerLinks = document.getElementById('footer-links');

  function cell(value) {
    return Number.isFinite(value) ? String(value) : '<span class="not-run">not yet run</span>';
  }

  function drawScoreboard(summary) {
    if (!summary) {
      table.innerHTML = '<tr><td colspan="5" class="not-run">Graded summary unavailable.</td></tr>';
      note.textContent = 'The graded summary could not be read from /graded-summary.json.';
      return;
    }
    // Sorted by what each site is worth reading: the ones carrying defects
    // first, the controls last, where a reader expects the zeroes.
    const names = Object.keys(summary).sort((a, b) => {
      const weight = (name) => (CONTROLS.includes(name) ? 1 : 0);
      return weight(a) - weight(b) || (summary[b].planted ?? 0) - (summary[a].planted ?? 0) || a.localeCompare(b);
    });
    table.innerHTML = names.map((name) => {
      const run = summary[name];
      const isControl = CONTROLS.includes(name) || run.planted === 0;
      const label = isControl ? `${name} <span class="control">/ clean control</span>` : name;
      return `<tr><td>${label}</td><td>${cell(run.planted)}</td><td>${cell(run.found)}</td>`
        + `<td>${cell(run.missed)}</td><td>${cell(run.false_positives)}</td></tr>`;
    }).join('');
  }

  function drawControlSummary(data) {
    const summary = data && data.sites ? data.sites : data;
    const totals = data && data.totals;
    const planted = totals && totals.planted;
    const found = totals && totals.found;
    // Every control in the fleet, not one named site. With a second control
    // added, reading only `control` under-reported the false-positive count.
    const falsePositives = summary
      ? Object.entries(summary)
          .filter(([name, run]) => CONTROLS.includes(name) || run.planted === 0)
          .reduce((total, [, run]) => total + (Number(run.false_positives) || 0), 0)
      : undefined;
    if (![planted, found, falsePositives].every(Number.isFinite)) {
      controlFigures.innerHTML = '<span class="control-figure"><b>Unavailable</b><small>defects found</small></span><span class="control-figure"><b>Unavailable</b><small>defects planted</small></span><span class="control-figure"><b>Unavailable</b><small>findings on the controls</small></span>';
      controlRatio.textContent = 'Control result unavailable: /graded-summary.json could not provide the measured figures.';
      return;
    }
    controlFigures.innerHTML = `<span class="control-figure"><b>${found}</b><small>defects found</small></span><span class="control-figure"><b>${planted}</b><small>defects planted</small></span><span class="control-figure"><b>${falsePositives}</b><small>findings on the controls</small></span>`;
    const controls = Object.keys(summary).filter((name) => CONTROLS.includes(name) || summary[name].planted === 0);
    controlRatio.textContent = `${found} of ${planted} defects found across ${Object.keys(summary).length} applications. `
      + `${falsePositives} findings appeared on the ${controls.length} clean control${controls.length === 1 ? '' : 's'}.`;
  }

  function unavailableGeneratedSpec() {
    generatedSpecFigures.innerHTML = '<span class="generated-spec-figure"><b>Unavailable</b><small>expected</small></span><span class="generated-spec-figure"><b>Unavailable</b><small>total</small></span><span class="generated-spec-figure"><b>Unavailable</b><small>failed</small></span><span class="generated-spec-figure"><b>Unavailable</b><small>passed</small></span><span class="generated-spec-figure"><b>Unavailable</b><small>skipped</small></span><span class="generated-spec-figure"><b>Unavailable</b><small>setup failures</small></span>';
    generatedSpecSummaryNote.textContent = 'Generated spec figures are unavailable: /generated-spec-verification.json could not be loaded.';
  }

  function drawGeneratedSpec(data) {
    const expected = Number(data && data.expected);
    const total = Number(data && data.total);
    const failed = Number(data && data.failed);
    const passed = Number(data && data.passed);
    const skipped = Number(data && data.skipped);
    const setupFailures = Array.isArray(data && data.setup_failures) ? data.setup_failures.length : Number(data && data.setup_failures);
    if (![expected, total, failed, passed, skipped, setupFailures].every(Number.isFinite)) {
      unavailableGeneratedSpec();
      return;
    }
    generatedSpecFigures.innerHTML = `<span class=\"generated-spec-figure\"><b>${expected}</b><small>expected</small></span><span class=\"generated-spec-figure\"><b>${total}</b><small>total</small></span><span class=\"generated-spec-figure\"><b>${failed}</b><small>failed</small></span><span class=\"generated-spec-figure\"><b>${passed}</b><small>passed</small></span><span class=\"generated-spec-figure\"><b>${skipped}</b><small>skipped</small></span><span class=\"generated-spec-figure\"><b>${setupFailures}</b><small>setup failures</small></span>`;
    const verdict = typeof data.verdict === 'string' ? data.verdict.toUpperCase() : '';
    generatedSpecSummaryNote.textContent = `${verdict || 'PASS'} is the gate result here: each generated spec is a planted-defect assertion. A passing generated spec means the planted defect did not reproduce in this check, so failures are the expected signal.`;
  }

  async function loadGeneratedSpec() {
    try {
      const response = await fetch('/generated-example.spec.ts', { cache: 'no-store' });
      if (!response.ok) return;
      generatedSpec.textContent = await response.text();
    } catch (_) { /* The committed example remains available when served. */ }
  }

  async function loadGeneratedSpecVerification() {
    try {
      const response = await fetch(generatedSpecVerificationUrl, { cache: 'no-store' });
      if (!response.ok) throw new Error('spec verification unavailable');
      const data = await response.json();
      if (!data || typeof data !== 'object') throw new Error('spec verification invalid');
      drawGeneratedSpec(data);
    } catch (_) {
      unavailableGeneratedSpec();
    }
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
      const external = EXTERNAL[entry.name];
      const isControl = CONTROLS.includes(entry.name);
      const note = external
        ? `<span class="app-badge">${external}</span>`
        : isControl
          ? '<span class="app-control-note">Clean control: nothing is planted; anything found is a false positive.</span>'
          : '';
      const className = external ? ' is-external' : isControl ? ' is-control' : '';
      // A sweep of a site we do not host has nowhere local to open.
      const open = external
        ? ''
        : `<a class="app-live" href="https://demo.mlki.app/${entry.name}/" target="_blank" rel="noopener">open application ↗</a>`;
      return `<article class="app-card${className}" data-app="${entry.name}"><button class="app-select" type="button" aria-pressed="false"><span class="app-name">${entry.name}</span><span class="app-count">${entry.findings} findings</span><span class="app-kinds">${kinds}</span>${note}</button>${open}</article>`;
    }).join('');
    gallery.setAttribute('aria-busy', 'false');
    entries.forEach((entry) => {
      gallery.querySelector(`[data-app="${entry.name}"] .app-select`).addEventListener('click', () => updateWall(entry, true));
    });
    // The footer used to name five demo targets by hand, which is the same
    // second source of truth that went stale in the scoreboard.
    const local = entries.filter((entry) => !EXTERNAL[entry.name]);
    if (footerLinks && local.length) {
      footerLinks.innerHTML = local
        .map((entry) => `<a href="https://demo.mlki.app/${entry.name}/">${entry.name}</a>`)
        .join('');
    }
    const requestedApp = new URLSearchParams(location.search).get('app');
    const selected = entries.find((entry) => entry.name === requestedApp)
      || entries.find((entry) => entry.name === 'the-internet')
      || entries[0];
    updateWall(selected, requestedApp !== selected.name);
  }

  async function loadGallery() {
    try {
      const response = await fetch(sweepIndexUrl, { cache: 'no-store' });
      if (!response.ok) throw new Error('index unavailable');
      const index = await response.json();
      // Everything published, ordered by how much a reader gets from it:
      // real applications first, then the demo fleet, then the controls.
      const entries = Object.keys(index || {})
        .filter((name) => name !== 'latest' && index[name] && typeof index[name].feed === 'string')
        .map((name) => ({ name, ...index[name] }))
        .sort((a, b) => {
          const weight = (entry) => (EXTERNAL[entry.name] ? 0 : CONTROLS.includes(entry.name) ? 2 : 1);
          return weight(a) - weight(b) || b.findings - a.findings || a.name.localeCompare(b.name);
        });
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
  loadGeneratedSpecVerification();
  loadGallery();
})();
