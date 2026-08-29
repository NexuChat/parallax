(() => {
  'use strict';

  const severityRank = { high: 0, medium: 1, low: 2, info: 3 };
  const source = new URLSearchParams(location.search).get('feed') || 'fixtures/feed.jsonl';
  const state = { seen: new Set(), findings: [], mosaicsBySurface: new Map(), latestMosaic: null, tiles: [], lastFileText: '', byteOffset: 0, activeWitnesses: [], selectedFindingId: null, eventCount: 0 };
  const $ = (id) => document.getElementById(id);
  const el = {
    image: $('mosaicImage'), stage: $('mosaicStage'), layer: $('tileLayer'), mosaicEmpty: $('mosaicEmpty'),
    sequence: $('sequence'), findings: $('findings'), findingsEmpty: $('findingsEmpty'), runState: $('runState'),
    feedIndicator: $('feedIndicator'), feedSource: $('feedSource'), caption: $('mosaicCaption'), title: $('mosaicTitle'), wallMode: $('wallMode')
  };

  const contexts = [
    'owner-en-light-desktop', 'member-en-light-desktop', 'anon-en-light-desktop', 'owner-ar-light-desktop',
    'owner-en-dark-desktop', 'owner-en-light-mobile', 'owner-en-light-tablet'
  ];
  const tiles = contexts.map((context, index) => ({ context, x: (index % 4) * 350, y: index < 4 ? 0 : 400, w: 350, h: 400 }));
  const fixtureSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="800" viewBox="0 0 1400 800"><rect width="1400" height="800" fill="#121b27"/><g font-family="monospace">${tiles.map((tile, i) => { const x = tile.x, y = tile.y, dark = i === 4; return `<g><rect x="${x + 8}" y="${y + 8}" width="334" height="384" rx="4" fill="${dark ? '#17202d' : '#eef3f5'}"/><rect x="${x + 8}" y="${y + 8}" width="334" height="42" fill="${dark ? '#263849' : '#263f57'}"/><circle cx="${x + 30}" cy="${y + 29}" r="7" fill="#56d3e6"/><text x="${x + 48}" y="${y + 34}" fill="#e8f7fb" font-size="15">${['BASELINE','MEMBER','ANON','RTL / AR','DARK','MOBILE','TABLET'][i]}</text><rect x="${x + 30}" y="${y + 78}" width="180" height="17" rx="3" fill="${dark ? '#b8c8d2' : '#263849'}"/><rect x="${x + 30}" y="${y + 112}" width="280" height="9" rx="3" fill="${dark ? '#647787' : '#a7b6c1'}"/><rect x="${x + 30}" y="${y + 137}" width="238" height="9" rx="3" fill="${dark ? '#647787' : '#a7b6c1'}"/><rect x="${x + 30}" y="${y + 181}" width="280" height="105" rx="5" fill="${i === 3 ? '#b8cbd9' : dark ? '#233142' : '#d4e1e8'}"/><rect x="${x + 30}" y="${y + 314}" width="122" height="33" rx="4" fill="#1593a9"/><rect x="${x + 30}" y="${y + 362}" width="245" height="8" rx="3" fill="${dark ? '#647787' : '#a7b6c1'}"/></g>`; }).join('')}</g></svg>`;
  const fallback = [
    { kind: 'status', at: '2026-08-29T16:04:00Z', payload: { state: 'running', message: 'Seven isolated witnesses are replaying the discovered surface map.', witnesses: 7, surfaces: 18 } },
    { kind: 'mosaic', at: '2026-08-29T16:04:01Z', payload: { seq: 42, image: `data:image/svg+xml,${encodeURIComponent(fixtureSvg)}`, tiles } },
    { kind: 'finding', at: '2026-08-29T16:04:03Z', payload: { id: 'escalation-privilege-share', kind: 'escalation', severity: 'high', axis: 'privilege', surface: 'Share workspace on /settings', surface_id: 'a9f01e12bd45c789', summary: 'Anonymous witness can reach the owner-only workspace sharing control.', evidence: 'owner-en-light-desktop=reached · anon-en-light-desktop=reached', witnesses: ['owner-en-light-desktop', 'anon-en-light-desktop'] } },
    { kind: 'finding', at: '2026-08-29T16:04:05Z', payload: { id: 'drift-locale-billing', kind: 'drift', severity: 'high', axis: 'locale', surface: '/billing', surface_id: 'e0c2d614f2a8920b', summary: 'Arabic witness is redirected away from billing while the baseline reaches it.', evidence: 'owner-en-light-desktop=reached · owner-ar-light-desktop=blocked', witnesses: ['owner-en-light-desktop', 'owner-ar-light-desktop'] } },
    { kind: 'finding', at: '2026-08-29T16:04:07Z', payload: { id: 'render-viewport-menu', kind: 'render', severity: 'medium', axis: 'viewport', surface: 'Export menu on /reports', surface_id: '44cc1b2852a8d941', summary: 'Export action is outside the mobile viewport.', evidence: 'owner-en-light-mobile=partial', witnesses: ['owner-en-light-mobile'] } },
    { kind: 'finding', at: '2026-08-29T16:04:09Z', payload: { id: 'divergence-theme-summary', kind: 'divergence', severity: 'low', axis: 'theme', surface: '/reports', surface_id: '75a6f9bc64c4e391', summary: 'Dark theme report summary omits the reconciliation note.', evidence: 'owner-en-light-desktop=reached · owner-en-dark-desktop=reached', witnesses: ['owner-en-light-desktop', 'owner-en-dark-desktop'] } },
    { kind: 'finding', at: '2026-08-29T16:04:11Z', payload: { id: 'inversion-privilege-audit', kind: 'inversion', severity: 'medium', axis: 'privilege', surface: '/audit-log', surface_id: '331ff680899ed2ac', summary: 'Member reaches the audit log while the owner witness is denied.', evidence: 'owner-en-light-desktop=blocked · member-en-light-desktop=reached', witnesses: ['owner-en-light-desktop', 'member-en-light-desktop'] } },
    { kind: 'finding', at: '2026-08-29T16:04:13Z', payload: { id: 'dead-baseline-archive', kind: 'dead', severity: 'info', axis: 'baseline', surface: '/archive/2023', surface_id: 'c017a2eae547e2dc', summary: 'No witness can reach the archived export route.', evidence: 'owner-en-light-desktop=blocked · member-en-light-desktop=blocked · anon-en-light-desktop=blocked', witnesses: ['owner-en-light-desktop', 'member-en-light-desktop', 'anon-en-light-desktop'] } },
    { kind: 'status', at: '2026-08-29T16:04:14Z', payload: { state: 'settled', message: 'Frame 42 settled; specialists issued six anchored findings.', witnesses: 7, surfaces: 18 } }
  ];

  function safeEvent(value) {
    return value && ['mosaic', 'finding', 'status'].includes(value.kind) && value.payload && typeof value.payload === 'object' ? value : null;
  }
  function keyFor(event) { return event.kind === 'finding' ? `finding:${event.payload.id}` : `${event.kind}:${event.payload.seq || event.at}:${event.payload.message || ''}`; }
  function processLine(line) { try { const event = safeEvent(JSON.parse(line)); if (event) processEvent(event); } catch (_) { /* A bad feed line must never disturb the wall. */ } }
  function processEvent(event) {
    const key = keyFor(event); if (state.seen.has(key)) return; state.seen.add(key); state.eventCount += 1;
    if (event.kind === 'mosaic') renderMosaic(event.payload);
    if (event.kind === 'finding') addFinding(event.payload);
    if (event.kind === 'status') renderStatus(event.payload);
  }
  function renderStatus(payload) {
    if (Number.isFinite(payload.witnesses)) $('witnessCount').textContent = payload.witnesses;
    if (Number.isFinite(payload.surfaces)) $('surfaceCount').textContent = payload.surfaces;
    el.runState.textContent = `${String(payload.state || 'status').toUpperCase()} · ${payload.message || 'feed received'}`;
  }
  function renderMosaic(payload) {
    if (!Array.isArray(payload.tiles) || !payload.image) return;
    const surfaceId = typeof payload.surface_id === 'string' ? payload.surface_id : null;
    if (surfaceId && Number.isFinite(payload.seq)) {
      if (!state.mosaicsBySurface.has(surfaceId)) state.mosaicsBySurface.set(surfaceId, new Map());
      state.mosaicsBySurface.get(surfaceId).set(payload.seq, payload);
    }
    state.latestMosaic = payload;
    if (state.selectedFindingId) showSelectedFinding(); else showLiveMosaic();
  }
  function displayMosaic(payload, { title, mode, caption, dim = false } = {}) {
    state.tiles = payload.tiles; el.title.textContent = title || 'Live witness mosaic'; el.wallMode.textContent = mode || 'LIVE FRAME';
    el.wallMode.className = `wall-mode${mode === 'EVIDENCE FRAME' ? ' is-evidence' : ''}`;
    el.sequence.textContent = `FRAME ${payload.seq ?? '—'} · ${payload.tiles.length} WITNESSES`;
    el.stage.classList.toggle('is-unavailable', dim);
    el.image.onload = () => { el.image.style.display = 'block'; el.mosaicEmpty.style.display = 'none'; layoutTiles(); };
    // A mosaic path in the feed is relative to the FEED, not to this page. A run
    // published under runs/<id>/ names its images `mosaics/…`, and resolving that
    // against the document gave /console/mosaics/… — a broken image on every frame.
    el.image.src = /^(data:|https?:|\/)/.test(payload.image)
      ? payload.image
      : new URL(payload.image, new URL(source, document.baseURI)).href; el.caption.textContent = caption || `Live frame ${payload.seq ?? '—'} · ${payload.tiles.length} contexts aligned to their source pixels.`;
  }
  function showLiveMosaic() {
    if (!state.latestMosaic) return;
    displayMosaic(state.latestMosaic, { caption: `Live frame ${state.latestMosaic.seq ?? '—'} · ${state.latestMosaic.tiles.length} contexts aligned to their source pixels.` });
  }
  function showUnavailableEvidence(message, { showLatest = false } = {}) {
    const latest = showLatest && state.latestMosaic;
    if (latest) {
      displayMosaic(latest, { title: 'Evidence frame unavailable', mode: 'EVIDENCE UNAVAILABLE', dim: true, caption: `${message} Showing the latest live frame only; it is not this finding's evidence.` });
    } else {
      state.tiles = []; el.layer.replaceChildren(); el.image.style.display = 'none'; el.stage.classList.add('is-unavailable');
      el.title.textContent = 'Evidence frame unavailable'; el.wallMode.textContent = 'EVIDENCE UNAVAILABLE'; el.wallMode.className = 'wall-mode is-unavailable'; el.sequence.textContent = 'NO CAPTURED FRAME'; el.mosaicEmpty.textContent = message; el.mosaicEmpty.style.display = 'block'; el.caption.textContent = 'No pixels are being presented as evidence for this finding.';
    }
  }
  function showSelectedFinding() {
    const finding = state.findings.find((item) => item.id === state.selectedFindingId); if (!finding) return;
    const reference = finding.mosaic;
    if (!reference || typeof reference.surface_id !== 'string' || !Number.isFinite(reference.seq)) {
      showUnavailableEvidence(reference === undefined ? 'This older feed has no evidence-frame reference for the selected finding.' : 'No settled mosaic frame was captured for the selected finding.', { showLatest: reference === undefined });
      highlightWitnesses([]); return;
    }
    const mosaic = state.mosaicsBySurface.get(reference.surface_id)?.get(reference.seq);
    if (!mosaic) { showUnavailableEvidence(`The captured mosaic for this finding (surface ${reference.surface_id}, frame ${reference.seq}) was not received.`); highlightWitnesses([]); return; }
    displayMosaic(mosaic, { title: 'Finding evidence mosaic', mode: 'EVIDENCE FRAME', caption: `Evidence frame ${reference.seq} for this finding's surface. Outlined tiles are the witnesses behind the claim.` });
    highlightWitnesses(finding.witnesses);
  }
  function layoutTiles() {
    const naturalWidth = el.image.naturalWidth, naturalHeight = el.image.naturalHeight;
    if (!naturalWidth || !naturalHeight) return;
    const imageBox = el.image.getBoundingClientRect(), stageBox = el.stage.getBoundingClientRect();
    el.layer.style.left = `${imageBox.left - stageBox.left}px`; el.layer.style.top = `${imageBox.top - stageBox.top}px`;
    el.layer.style.width = `${imageBox.width}px`; el.layer.style.height = `${imageBox.height}px`; el.layer.replaceChildren();
    state.tiles.forEach((tile) => {
      const box = document.createElement('div'); box.className = 'tile'; box.dataset.context = tile.context;
      box.style.left = `${tile.x / naturalWidth * 100}%`; box.style.top = `${tile.y / naturalHeight * 100}%`;
      box.style.width = `${tile.w / naturalWidth * 100}%`; box.style.height = `${tile.h / naturalHeight * 100}%`;
      const label = document.createElement('span'); label.className = 'tile-label'; label.textContent = tile.context; box.append(label); el.layer.append(box);
    });
    highlightWitnesses(state.activeWitnesses);
  }
  function highlightWitnesses(witnesses) {
    state.activeWitnesses = Array.isArray(witnesses) ? witnesses : [];
    el.layer.querySelectorAll('.tile').forEach((tile) => tile.classList.toggle('is-witness', state.activeWitnesses.includes(tile.dataset.context)));
  }
  function addFinding(finding) {
    if (!finding.id || !finding.severity || !finding.summary) return;
    state.findings.push(finding); state.findings.sort((a, b) => severityRank[a.severity] - severityRank[b.severity]);
    const card = document.createElement('article'); card.className = 'finding'; card.dataset.id = finding.id; card.style.setProperty('--severity', `var(--${finding.severity})`);
    card.innerHTML = `<div class="finding-head"><span class="pill">${escape(finding.severity).toUpperCase()}</span><span class="finding-kind">${escape(finding.kind).toUpperCase()}</span><span class="finding-axis">AXIS: ${escape(finding.axis)}</span></div><div class="finding-summary"></div><div class="finding-surface"></div><div class="evidence"><strong>EVIDENCE</strong> · <span></span></div>`;
    card.querySelector('.finding-summary').textContent = finding.summary; card.querySelector('.finding-surface').textContent = finding.surface || finding.surface_id || 'surface unknown'; card.querySelector('.evidence span').textContent = finding.evidence || 'No evidence line supplied';
    card.addEventListener('click', () => activateFinding(finding.id)); card.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activateFinding(finding.id); } }); card.tabIndex = 0; card.setAttribute('role', 'button'); card.setAttribute('aria-pressed', 'false');
    const before = [...el.findings.children].find((node) => {
      const existing = state.findings.find((item) => item.id === node.dataset.id);
      return existing && severityRank[existing.severity] >= severityRank[finding.severity];
    });
    el.findings.insertBefore(card, before || null); el.findingsEmpty?.remove(); updateTotals();
  }
  function activateFinding(id) {
    const finding = state.findings.find((item) => item.id === id); if (!finding) return;
    state.selectedFindingId = state.selectedFindingId === id ? null : id;
    el.findings.querySelectorAll('.finding').forEach((card) => { const active = card.dataset.id === state.selectedFindingId; card.classList.toggle('is-active', active); card.setAttribute('aria-pressed', String(active)); });
    if (state.selectedFindingId) showSelectedFinding(); else { highlightWitnesses([]); showLiveMosaic(); }
  }
  function updateTotals() { const counts = { high:0, medium:0, low:0, info:0 }; state.findings.forEach((f) => { if (f.severity in counts) counts[f.severity] += 1; }); Object.entries(counts).forEach(([severity, count]) => { $(`${severity}Count`).textContent = count; }); $('findingCount').textContent = state.findings.length; }
  function escape(value) { const node = document.createElement('span'); node.textContent = value ?? ''; return node.innerHTML; }
  function setFeedMode(label) { el.feedIndicator.textContent = label; el.feedSource.textContent = `feed: ${source}`; }
  async function poll() {
    try {
      const headers = state.byteOffset ? { Range: `bytes=${state.byteOffset}-` } : {};
      const response = await fetch(source, { headers, cache: 'no-store' }); if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const text = await response.text(); let incoming = text;
      if (response.status === 206) state.byteOffset += new TextEncoder().encode(text).length;
      else { incoming = text.startsWith(state.lastFileText) ? text.slice(state.lastFileText.length) : text; state.lastFileText = text; state.byteOffset = new TextEncoder().encode(text).length; }
      incoming.split(/\r?\n/).filter(Boolean).forEach(processLine); setFeedMode('POLLING');
    } catch (_) { setFeedMode('OFFLINE FIXTURE'); }
  }
  function connectSse() {
    if (!('EventSource' in window) || location.protocol === 'file:') return;
    // A static feed file is not an event stream. Opening an EventSource on one
    // still works — polling takes over — but it logs a MIME-type error, and a
    // red console line during a live demo reads as a broken product.
    if (/\.(jsonl|json|txt)(\?|$)/i.test(source)) return;
    try { const stream = new EventSource(source); stream.onopen = () => setFeedMode('SSE LIVE'); stream.onmessage = (message) => processLine(message.data); stream.onerror = () => { stream.close(); setTimeout(poll, 100); }; } catch (_) { /* Polling remains available. */ }
  }
  function useFixture() {
    fallback.forEach(processEvent);
    setFeedMode(location.protocol === 'file:' ? 'OFFLINE SAMPLE' : 'SAMPLE — NO RUN FOUND');
  }
  async function boot() {
    $('clock').textContent = new Date().toISOString().slice(11, 19) + ' UTC'; setInterval(() => { $('clock').textContent = new Date().toISOString().slice(11, 19) + ' UTC'; }, 1000);
    addEventListener('resize', layoutTiles);
    // The sample used to be drawn FIRST, unconditionally, so a console attached
    // to a real sweep still opened on frame 42 and six invented findings. It is
    // a fallback, not a seed: it appears only when no real feed can be read.
    if (location.protocol === 'file:') { useFixture(); return; }
    await poll();
    if (!state.eventCount) useFixture();
    setInterval(poll, 2500); connectSse();
  }
  boot();
})();
