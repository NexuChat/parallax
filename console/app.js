(() => {
  'use strict';

  const severityRank = { high: 0, medium: 1, low: 2, info: 3 };
  // A caller who names a feed is asking about a specific run. If that feed cannot
  // be read we must say so: rendering the bundled sample in its place would show
  // invented findings under the caption of the run they asked for.
  const requestedFeed = new URLSearchParams(location.search).get('feed');
  const source = requestedFeed || 'fixtures/feed.jsonl';
  const state = { seen: new Set(), findings: [], mosaicsBySurface: new Map(), latestMosaic: null, tiles: [], lastFileText: '', byteOffset: 0, activeWitnesses: [], selectedFindingId: null, eventCount: 0, surfacesSeen: new Set(), witnessCount: 0, polled: false, shownMosaic: null, inspecting: null, frames: [], frameAt: 0, playing: false, timer: null };
  const $ = (id) => document.getElementById(id);
  const el = {
    image: $('mosaicImage'), stage: $('mosaicStage'), layer: $('tileLayer'), mosaicEmpty: $('mosaicEmpty'),
    sequence: $('sequence'), findings: $('findings'), findingsEmpty: $('findingsEmpty'), runState: $('runState'),
    feedIndicator: $('feedIndicator'), feedSource: $('feedSource'), caption: $('mosaicCaption'), title: $('mosaicTitle'), wallMode: $('wallMode'),
    inspector: $('inspector'), inspectorImage: $('inspectorImage'), inspectorStage: $('inspectorStage'),
    inspectorTitle: $('inspectorTitle'), inspectorCaption: $('inspectorCaption'), inspectorWitnesses: $('inspectorWitnesses'),
    inspectButton: $('inspectButton'), inspectorClose: $('inspectorClose'),
    inspectorWindow: $('inspectorWindow'),
    playButton: $('playButton'), scrubber: $('scrubber'), scrubberRange: $('scrubberRange'), scrubberLabel: $('scrubberLabel')
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
    // A real sweep announces one surface at a time and never carries a witness or
    // surface total, so counting the surfaces it has announced is the only source
    // for these two figures. Reading payload.witnesses/payload.surfaces left both
    // stuck at zero for every genuine feed.
    if (typeof payload.surface_id === 'string') state.surfacesSeen.add(payload.surface_id);
    else if (typeof payload.surface === 'string') state.surfacesSeen.add(payload.surface);
    $('surfaceCount').textContent = state.surfacesSeen.size;
    if (Number.isFinite(payload.witnesses)) state.witnessCount = payload.witnesses;
    $('witnessCount').textContent = state.witnessCount;
    el.runState.textContent = `${String(payload.state || 'status').toUpperCase()} · ${payload.message || 'feed received'}`;
  }
  function renderMosaic(payload) {
    if (!Array.isArray(payload.tiles) || !payload.image) return;
    // The wall itself is the record of how many witnesses reported.
    if (payload.tiles.length > state.witnessCount) {
      state.witnessCount = payload.tiles.length;
      $('witnessCount').textContent = state.witnessCount;
    }
    const surfaceId = typeof payload.surface_id === 'string' ? payload.surface_id : null;
    if (surfaceId && Number.isFinite(payload.seq)) {
      if (!state.mosaicsBySurface.has(surfaceId)) state.mosaicsBySurface.set(surfaceId, new Map());
      state.mosaicsBySurface.get(surfaceId).set(payload.seq, payload);
    }
    state.latestMosaic = payload;
    state.frames.push(payload);
    state.frameAt = state.frames.length - 1;
    updateTransport();
    if (state.selectedFindingId) showSelectedFinding(); else showLiveMosaic();
  }
  function displayMosaic(payload, { title, mode, caption, dim = false } = {}) {
    state.tiles = payload.tiles; state.shownMosaic = payload; el.title.textContent = title || 'Live witness mosaic'; el.wallMode.textContent = mode || 'SETTLED FRAME';
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
      const label = document.createElement('span'); label.className = 'tile-label'; label.textContent = tile.context; box.append(label);
      box.addEventListener('click', () => openInspector(tile.context)); el.layer.append(box);
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
    // Pinning a finding's evidence and running the replay are two answers to the
    // question "what am I looking at". Choosing one has to end the other.
    stopPlaying();
    state.selectedFindingId = state.selectedFindingId === id ? null : id;
    el.findings.querySelectorAll('.finding').forEach((card) => { const active = card.dataset.id === state.selectedFindingId; card.classList.toggle('is-active', active); card.setAttribute('aria-pressed', String(active)); });
    if (state.selectedFindingId) showSelectedFinding(); else { highlightWitnesses([]); showLiveMosaic(); }
  }
  function updateTotals() { const counts = { high:0, medium:0, low:0, info:0 }; state.findings.forEach((f) => { if (f.severity in counts) counts[f.severity] += 1; }); Object.entries(counts).forEach(([severity, count]) => { $(`${severity}Count`).textContent = count; }); $('findingCount').textContent = state.findings.length; }
  function escape(value) { const node = document.createElement('span'); node.textContent = value ?? ''; return node.innerHTML; }
  function setFeedMode(label) { el.feedIndicator.textContent = label; el.feedSource.textContent = `feed: ${source}`; }
  // A finished sweep is a recording. Polling a file that has stopped growing is
  // not a live run, and saying so would misrepresent the wall as a run in flight.
  function setLiveness(receivingNow) {
    const dot = $('liveDot');
    if (!dot) return;
    dot.textContent = receivingNow ? 'LIVE' : 'REPLAY';
    dot.classList.toggle('is-replay', !receivingNow);
  }
  async function poll() {
    try {
      const headers = state.byteOffset ? { Range: `bytes=${state.byteOffset}-` } : {};
      const response = await fetch(source, { headers, cache: 'no-store' }); if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const text = await response.text(); let incoming = text;
      if (response.status === 206) state.byteOffset += new TextEncoder().encode(text).length;
      else { incoming = text.startsWith(state.lastFileText) ? text.slice(state.lastFileText.length) : text; state.lastFileText = text; state.byteOffset = new TextEncoder().encode(text).length; }
      const lines = incoming.split(/\r?\n/).filter(Boolean);
      lines.forEach(processLine);
      const growing = lines.length > 0 && state.eventCount > 0 && state.polled;
      state.polled = true;
      setFeedMode(growing ? 'STREAMING' : 'RECORDED FEED');
      setLiveness(growing);
    } catch (_) { setFeedMode('FEED UNREADABLE'); setLiveness(false); }
  }
  function connectSse() {
    if (!('EventSource' in window) || location.protocol === 'file:') return;
    // A static feed file is not an event stream. Opening an EventSource on one
    // still works — polling takes over — but it logs a MIME-type error, and a
    // red console line during a live demo reads as a broken product.
    if (/\.(jsonl|json|txt)(\?|$)/i.test(source)) return;
    try { const stream = new EventSource(source); stream.onopen = () => { setFeedMode('SSE LIVE'); setLiveness(true); }; stream.onmessage = (message) => processLine(message.data); stream.onerror = () => { stream.close(); setTimeout(poll, 100); }; } catch (_) { /* Polling remains available. */ }
  }
  function useFixture() {
    fallback.forEach(processEvent);
    setFeedMode('SAMPLE — NOT A RUN');
  }
  // Shown when a named feed could not be read. It must stay empty of findings:
  // an unreadable run has produced no evidence, and anything drawn here would be
  // read as that run's result.
  function showNoFeed() {
    const fileScheme = location.protocol === 'file:';
    setFeedMode(fileScheme ? 'BLOCKED BY file://' : 'FEED UNREADABLE');
    if (el.findingsEmpty) {
      el.findingsEmpty.textContent = fileScheme
        ? `The browser blocks reading ${source} over file://. Serve the repository — python -m http.server — and open the console over http:// with the same ?feed= value.`
        : `No feed could be read from ${source}. Nothing is shown because this run produced no readable evidence.`;
      el.findingsEmpty.hidden = false;
    }
    if (el.mosaicEmpty) {
      el.mosaicEmpty.textContent = 'No mosaic — the feed was not read.';
      el.mosaicEmpty.hidden = false;
    }
    if (el.runState) el.runState.textContent = 'no feed';
  }
  async function boot() {
    $('clock').textContent = new Date().toISOString().slice(11, 19) + ' UTC'; setInterval(() => { $('clock').textContent = new Date().toISOString().slice(11, 19) + ' UTC'; }, 1000);
    addEventListener('resize', layoutTiles);
    el.image.addEventListener('click', () => openInspector());
    el.inspectButton.addEventListener('click', () => openInspector());
    el.inspectorClose.addEventListener('click', closeInspector);
    el.playButton.addEventListener('click', togglePlay);
    el.scrubberRange.addEventListener('input', () => { stopPlaying(); showFrame(Number(el.scrubberRange.value)); });
    el.inspector.addEventListener('click', (event) => { if (event.target === el.inspector) closeInspector(); });
    addEventListener('keydown', (event) => {
      if (el.inspector.hidden) return;
      if (event.key === 'Escape') { closeInspector(); return; }
      // Arrow keys walk the wall, which is how you compare two witnesses of the
      // same moment without hunting for the right thumbnail.
      const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
      if (!step || !state.shownMosaic) return;
      const names = state.shownMosaic.tiles.map((tile) => tile.context);
      const at = names.indexOf(state.inspecting);
      event.preventDefault();
      openInspector(names[(at + step + names.length) % names.length]);
    });
    // The sample used to be drawn FIRST, unconditionally, so a console attached
    // to a real sweep still opened on frame 42 and six invented findings. It is
    // a fallback, not a seed: it appears only when no real feed can be read.
    // Always attempt the real feed first, file:// included — some setups do read
    // a sibling file, and when the browser refuses we owe the reader the reason
    // rather than a wall of fabricated findings.
    await poll();
    if (!state.eventCount) {
      if (requestedFeed) showNoFeed(); else useFixture();
      if (location.protocol === 'file:') return;
    }
    setInterval(poll, 2500); connectSse();
  }
  boot();

  // ---------------------------------------------------------------- inspector

  function openInspector(context) {
    const mosaic = state.shownMosaic;
    if (!mosaic || !Array.isArray(mosaic.tiles) || !mosaic.tiles.length) return;
    const tile = mosaic.tiles.find((item) => item.context === context) || mosaic.tiles[0];
    state.inspecting = tile.context;
    el.inspector.hidden = false;
    el.inspectorImage.src = el.image.src;
    el.inspectorImage.alt = `Witness ${tile.context} at full size`;
    el.inspectorTitle.textContent = tile.context;
    const evidence = state.activeWitnesses.includes(tile.context);
    // Enlarged from the composited wall, so say so. The wall is stored at tile
    // scale on purpose — it is re-encoded on every moment and sent to the vision
    // model — and claiming native pixels here would be claiming detail that was
    // never captured.
    el.inspectorCaption.textContent = evidence
      ? `${tile.context} — one of the witnesses behind the selected finding, enlarged from the composited wall. Arrow keys compare it against the others.`
      : `${tile.context}, enlarged from the composited wall. Arrow keys move between witnesses of this same frame.`;
    renderInspectorWitnesses(mosaic);
    cropToTile(tile);
  }

  function cropToTile(tile) {
    // The mosaic is one image, so a witness is a window onto it: scale so the
    // tile fills the stage, then scroll the stage to put that tile in view.
    const apply = () => {
      const natural = el.inspectorImage.naturalWidth;
      if (!natural || !tile.w) return;
      const stage = el.inspectorStage.getBoundingClientRect();
      // The smaller of the two fits, so the whole witness is on screen rather
      // than its top half; never below 1:1, because shrinking the evidence is
      // the thing this exists to stop.
      const scale = Math.max(1, Math.min((stage.width - 28) / tile.w, (stage.height - 28) / tile.h));
      el.inspectorImage.style.width = `${natural * scale}px`;
      // Centre what is left over, so a tile narrower than the stage does not sit
      // against one edge with the neighbouring witness bleeding in beside it.
      const slackX = Math.max(0, (stage.width - tile.w * scale) / 2);
      const slackY = Math.max(0, (stage.height - tile.h * scale) / 2);
      el.inspectorWindow.style.left = `${tile.x * scale}px`;
      el.inspectorWindow.style.top = `${tile.y * scale}px`;
      el.inspectorWindow.style.width = `${tile.w * scale}px`;
      el.inspectorWindow.style.height = `${tile.h * scale}px`;
      el.inspectorWindow.classList.toggle('is-evidence', state.activeWitnesses.includes(tile.context));
      el.inspectorStage.scrollTo({ left: tile.x * scale - slackX, top: tile.y * scale - slackY });
    };
    if (el.inspectorImage.complete && el.inspectorImage.naturalWidth) apply();
    else el.inspectorImage.onload = apply;
  }

  function renderInspectorWitnesses(mosaic) {
    el.inspectorWitnesses.replaceChildren();
    mosaic.tiles.forEach((tile) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'inspector-witness'; button.textContent = tile.context;
      button.setAttribute('role', 'tab');
      button.classList.toggle('is-active', tile.context === state.inspecting);
      button.setAttribute('aria-selected', String(tile.context === state.inspecting));
      // A witness behind the selected finding stays marked here too, so the
      // inspector never loses the reason you opened it.
      button.classList.toggle('is-evidence', state.activeWitnesses.includes(tile.context));
      button.addEventListener('click', () => openInspector(tile.context));
      el.inspectorWitnesses.append(button);
    });
  }

  function closeInspector() {
    el.inspector.hidden = true; state.inspecting = null;
    el.inspectButton.focus();
  }

  // ------------------------------------------------------------- frame replay

  // A live sweep pushes frames as they settle and the wall follows along. A
  // recorded one arrives in a single read, so without a player the console drew
  // thirteen to forty captured moments and showed only the last.
  const FRAME_MS = 700;

  function updateTransport() {
    const many = state.frames.length > 1;
    el.playButton.hidden = !many;
    el.scrubber.hidden = !many;
    if (!many) return;
    el.scrubberRange.max = String(state.frames.length - 1);
    el.scrubberRange.value = String(state.frameAt);
    el.scrubberLabel.textContent = `FRAME ${state.frameAt + 1} / ${state.frames.length}`;
    el.playButton.textContent = state.playing ? '❚❚ PAUSE' : '▶ PLAY';
  }

  function showFrame(index) {
    const frame = state.frames[index];
    if (!frame) return;
    state.frameAt = index;
    displayMosaic(frame, {
      title: 'Witness mosaic',
      mode: state.playing ? 'REPLAYING' : 'SETTLED FRAME',
      caption: `Frame ${index + 1} of ${state.frames.length} · ${frame.tiles.length} contexts aligned to their source pixels.`,
    });
    highlightWitnesses([]);
    updateTransport();
    if (!el.inspector.hidden) openInspector(state.inspecting);
  }

  function stopPlaying() {
    state.playing = false;
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    updateTransport();
  }

  function togglePlay() {
    if (state.playing) { stopPlaying(); return; }
    if (state.frames.length < 2) return;
    // Playing is a deliberate look at the whole sweep, so it takes the wall back
    // from a pinned finding rather than fighting it for the image.
    state.selectedFindingId = null;
    document.querySelectorAll('.finding.is-active').forEach((node) => node.classList.remove('is-active'));
    state.playing = true;
    if (state.frameAt >= state.frames.length - 1) state.frameAt = -1;
    state.timer = setInterval(() => {
      const next = state.frameAt + 1;
      if (next >= state.frames.length) { stopPlaying(); showFrame(state.frames.length - 1); return; }
      showFrame(next);
    }, FRAME_MS);
    showFrame(state.frameAt + 1);
  }
})();
