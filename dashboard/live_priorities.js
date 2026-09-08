/* Live Priorities tab. Renders the payload dashboard/live_priorities.py wrote;
   derives nothing. The only input it processes is a pasted Slack message or a
   dropped .jsonl of threads, and for that it applies the parser tables the payload carries
   (golden/parse.py cues, golden/resolver.py layers, build_golden.py OFFER_RE)
   in the same order the Python does — tests/test_live_priorities.py runs this
   file under node against the Python parser on every thread on disk. */
const LP = (function () {
  'use strict';

  // ---------------------------------------------------------------- helpers
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const cap1 = s => s ? s[0].toUpperCase() + s.slice(1) : s;
  const co = ref => ref && ref.href ? `<a href="${esc(ref.href)}">${esc(ref.company_name)}</a>` : esc(ref ? ref.company_name : '');
  const plural = (n, w) => `${n} ${n === 1 ? w : w.endsWith('y') ? w.slice(0, -1) + 'ies' : w.endsWith('ch') ? w + 'es' : w + 's'}`;
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  // a section that starts closed: the h2 is the summary, the arrow toggles the body
  const fold = h2 => `<details class="fold"><summary><h2>${h2}</h2></summary>`;
  // a fresh ask on a company whose last intro fizzled: the row says so, and names that intro
  const retryTag = r => r.retry ? `<br><b class="warn">retry intro</b> <span class="foot">${esc(r.retry.note)}</span>` : '';
  // a request filed Closed - no path or Intro sent that the allocator took back because nothing was ever logged
  const reopenedTag = r => r.reopened ? `<br><b class="warn">reopened</b> <span class="foot">${esc(r.reopened)}</span>` : '';
  // the account owner(s) owed a heads-up (golden_allocation.notify_owner): the drafted message behind a
  // copy button. A flag only: the row is routed regardless. `id` must be unique on the page
  const notifyBlock = (n, id, lead = '') => `<div class="notify" id="${esc(id)}">${lead}<b>${n.owners.map(esc).join('<br>')}</b><br><span class="foot">${esc(n.request_id)} · ${esc(n.stage)} · Not ${esc(n.requester)}'s account</span><br><button type="button" class="copy secondary" data-copy="${esc(id)}" title="${esc(n.message)}">Copy heads-up</button><pre class="msg" hidden>${esc(n.message)}</pre></div>`;
  // on a queue row: the heads-up goes out with the ask, so it sits beside the tick
  const notifyTag = r => r.notify ? notifyBlock(r.notify, `notify-queue-${r.request_id}`, '<b class="warn">notify owner</b><br>') : '';
  const openFoldAt = root => {
    const s = location.hash.length > 1 && root.querySelector(`${location.hash} > details.fold`);
    if (s) s.open = true;
  };
  const get = (o, k, d) => has(o, k) ? o[k] : d;
  // a row of sub-tab buttons and one panel per button, the first open; wireTabs() makes them switch
  const tabs = (id, items, panel) => `<div class="subtabs" data-tabs="${id}">${items.map((x, i) => `<button data-i="${i}" class="${[i ? '' : 'on', x.cls || ''].join(' ').trim()}">${esc(x.label)}${x.n == null ? '' : `<span class="n">${esc(x.n)}</span>`}</button>`).join('')}</div>`
    + items.map((x, i) => `<div class="tabpanel" data-tabs="${id}" data-i="${i}" ${i ? 'hidden' : ''}>${panel(x, i)}</div>`).join('');
  const wireTabs = root => root.querySelectorAll('.subtabs').forEach(bar => bar.querySelectorAll('button').forEach(b => b.onclick = () => {
    bar.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    root.querySelectorAll(`.tabpanel[data-tabs="${bar.dataset.tabs}"]`).forEach(p => p.hidden = p.dataset.i !== b.dataset.i);
  }));
  const csvCell = v => { const s = String(v ?? ''); return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const toCsv = (cols, rows) => [cols.join(',')].concat(rows.map(r => cols.map(c => csvCell(r[c])).join(','))).join('\r\n') + '\r\n';
  function download(name, text) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // ------------------------------------------------ golden/resolver.py, ported
  const ascii = s => (s || '').normalize('NFKD').replace(/[^\x00-\x7f]/g, '').toLowerCase();
  const normStrict = s => ascii(s).replace(/[^a-z0-9]+/g, '');
  const domainStem = d => (d || '').trim().toLowerCase().replace(/^(https?:\/\/)?(www\.)?/, '').replace(/\..*$/, '');
  const isDomain = s => /^(https?:\/\/)?(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)+\/?$/.test((s || '').trim().toLowerCase());

  function makeResolver(R) {
    const noise = new RegExp(R.noise.source, R.noise.flags);
    const normLoose = s => ascii(s).replace(/[^a-z0-9]+/g, ' ').replace(noise, ' ').replace(/\s+/g, '');
    const E = R.entities;
    const MIN = R.min_prefix_stem;
    const strictT = new Map(Object.entries(R.strict)), looseT = new Map(Object.entries(R.loose)),
          stemT = new Map(Object.entries(R.stem)), domainT = new Map(Object.entries(R.by_domain));
    const looseEntries = [...looseT.entries()];
    const stemEntries = [...stemT.entries()].map(([k, v]) => [k, [v]]);
    const res = (raw, id, method, candidates) => {
      const confidence = R.confidence[method];
      const review = confidence < R.review_threshold;
      const e = id ? E[id] : null;
      return { raw, entity: e, method, confidence, needs_review: review, candidates: candidates || [],
               entity_id: e && !review ? e.id : '', name: e && !review ? e.name : '', kind: e && !review ? e.kind : '' };
    };
    const refuse = (raw, ids) => {
      const cands = [...ids].sort().map(id => E[id]);
      const kinds = new Set(cands.map(c => c.kind));
      const method = kinds.size === 2 && kinds.has('company') && kinds.has('fund') ? 'fund-or-customer' : 'ambiguous';
      return res(raw, null, method, cands);
    };
    const byDomainString = (dom, raw) => {
      dom = dom.trim().toLowerCase().replace(/^(https?:\/\/)?(www\.)?/, '').replace(/\/+$/, '');
      if (domainT.has(dom)) return res(raw, domainT.get(dom), 'domain');
      const st = stemT.get(domainStem(dom));
      return st ? res(raw, st, 'domain-stem') : null;
    };
    function resolve(raw, domainHint) {
      raw = (raw || '').trim(); domainHint = domainHint || '';
      if (domainHint || isDomain(raw)) {
        const r = byDomainString(domainHint || raw, raw);
        if (r) return r;
        if (!raw) return res(domainHint, null, 'unmatched');
      }
      const strict = normStrict(raw);
      if (!strict) return res(raw, null, 'empty');
      let hits = new Set(strictT.get(strict) || []);
      if (hits.size === 1) {
        const e = E[[...hits][0]];
        const method = strict === domainStem(e.domain) && !e.names.some(n => normStrict(n) === strict) ? 'domain-stem' : 'name-exact';
        return res(raw, e.id, method);
      }
      if (hits.size > 1) return refuse(raw, hits);
      const loose = normLoose(raw);
      hits = new Set(looseT.get(loose) || []);
      if (stemT.has(loose)) hits.add(stemT.get(loose));
      if (hits.size && loose.length < MIN) {
        for (const [key, ids] of looseEntries.concat(stemEntries)) if (key.startsWith(loose)) ids.forEach(id => hits.add(id));
      }
      if (hits.size === 1) return res(raw, [...hits][0], 'name-loose');
      if (hits.size > 1) return refuse(raw, hits);
      if (loose.length >= MIN) {
        const cands = new Set();
        for (const [key, ids] of looseEntries.concat(stemEntries)) {
          if (key.length >= MIN && (key.startsWith(loose) || loose.startsWith(key))) ids.forEach(id => cands.add(id));
        }
        if (cands.size === 1) { const id = [...cands][0]; return res(raw, id, 'name-prefix', [E[id]]); }
        if (cands.size > 1) return refuse(raw, cands);
      }
      return res(raw, null, 'unmatched');
    }
    return { resolve, normStrict, normLoose };
  }

  // --------------------------------------------------- golden/parse.py, ported
  // a span in any case is a company when it is a known spelling entire, or the resolver reads it as the
  // start of a name it knows (a match or a refusal with candidates), not a run of words containing one
  function isCompany(resolver, part, kfull) {
    if (kfull && kfull.test(part)) return true;
    const r = resolver.resolve(part);
    if (r.method === 'unmatched' || r.method === 'empty') return false;
    const loose = resolver.normLoose(part);
    const ents = r.candidates.length ? r.candidates : (r.entity ? [r.entity] : []);
    return ents.length > 0 && ents.every(e => [...e.names.map(resolver.normLoose), domainStem(e.domain)].some(k => k.startsWith(loose)));
  }

  function extract(text, P, resolver) {
    text = text || '';
    const seen = new Map();
    const kfull = P.known ? new RegExp('^(?:' + P.known.source + ')$', P.known.flags) : null;
    const split = new RegExp(P.split.source, P.split.flags);
    for (const cue of P.cues) {
      const re = new RegExp(cue.source, cue.flags + 'gd');
      for (const m of text.matchAll(re)) {
        let start = m.indices.groups.co[0];
        for (let part of m.groups.co.split(split)) {
          part = part.trim();
          if (!part) continue;
          const at = text.indexOf(part, start);
          const key = at + '\u0000' + part;
          if (!seen.has(key)) seen.set(key, { text: part, cue: cue.label, score: cue.score, start: at, is_domain: false });
          start = at + part.length;
        }
      }
    }
    if (resolver && P.lower_cues) {
      // the same cues over a span in any case; the resolver says how many words are the company, longest first
      const starts = new Set([...seen.values()].map(x => x.start));
      const wre = new RegExp(P.word.source, P.word.flags + 'g');
      for (const cue of P.lower_cues) {
        const re = new RegExp(cue.source, cue.flags + 'gd');
        for (const m of text.matchAll(re)) {
          const start = m.indices.groups.co[0], span = m.groups.co;
          if (starts.has(start)) continue;
          for (const w of [...span.matchAll(wre)].reverse()) {
            const part = span.slice(0, w.index + w[0].length);
            if (isCompany(resolver, part, kfull)) {
              seen.set(start + '\u0000' + part, { text: part, cue: cue.label, score: cue.score, start, is_domain: false });
              starts.add(start);
              break;
            }
          }
        }
      }
    }
    const dre = new RegExp(P.domain.source, P.domain.flags + 'gd');
    for (const m of text.matchAll(dre)) {
      const dom = m[1].toLowerCase(), at = m.indices[1][0];
      const key = at + '\u0000' + dom;
      if (!seen.has(key)) seen.set(key, { text: dom, cue: P.domain_cue, score: P.domain_score, start: at, is_domain: true });
    }
    if (resolver && P.known) {
      // every name the resolver knows, in any case; a bare one is the target only when it is alone and no cue fired positively
      const taken = [...seen.values()].map(x => [x.start, x.start + x.text.length]);
      const kre = new RegExp(P.known.source, P.known.flags + 'g');
      const found = [...text.matchAll(kre)].filter(m => !taken.some(([s, e]) => m.index < e && s < m.index + m[0].length));
      const positive = [...seen.values()].some(x => x.score > 0);
      const score = found.length === 1 && !positive ? P.known_score : 0;
      for (const m of found) seen.set(m.index + '\u0000' + m[0], { text: m[0], cue: P.known_cue, score, start: m.index, is_domain: false });
    }
    if (resolver && P.bare && !seen.size) {
      // a message that is nothing but a few words goes to the resolver whole: a match or a refusal with candidates is a mention
      const m = new RegExp(P.bare.source, P.bare.flags + 'd').exec(text);
      if (m && isCompany(resolver, m.groups.co, kfull)) {
        const start = m.indices.groups.co[0];
        seen.set(start + '\u0000' + m.groups.co, { text: m.groups.co, cue: P.bare_cue, score: P.bare_score, start, is_domain: false });
      }
    }
    const mentions = [...seen.values()].sort((a, b) => a.start - b.start);
    if (resolver) for (const x of mentions) x.resolution = x.is_domain ? resolver.resolve('', x.text) : resolver.resolve(x.text);
    let target = null;
    for (const m of mentions) {
      if (m.score <= 0) continue;
      if (!target || m.score > target.score || (m.score === target.score && m.start < target.start)) target = m;
    }
    return { text, mentions, target };
  }

  // ------------------------------------------------------------ upload preview
  function parseJsonl(text) {
    const threads = [], errors = [];
    text.split(/\r?\n/).forEach((line, i) => {
      if (!line.trim()) return;
      try {
        const t = JSON.parse(line);
        if (!t.request_id || !Array.isArray(t.messages) || !t.messages.length) errors.push(`line ${i + 1}: needs request_id and a non-empty messages list`);
        else threads.push(t);
      } catch (e) { errors.push(`line ${i + 1}: ${e.message}`); }
    });
    return { threads, errors };
  }

  // a CSV in the shape of intro_requests.csv, one thread per row: the raw ask is the first message,
  // posted by requested_by on request_date; the columns the thread would lack (deal value, urgency,
  // title, the company as the requester wrote it) ride along on t.request
  const REQUEST_COLUMNS = ['request_id', 'raw_ask'], THREAD_COLUMNS = ['request_id', 'raw_ask', 'request_date', 'requested_by'];
  // the deal value column carries its currency as a suffix (deal_value_<ccy>); the row keeps it as deal_value + currency
  const DEAL_COLUMN = /^deal_value_([a-z]{3})$/i;
  function requestsToThreads(text) {
    const threads = [], errors = [];
    let parsed;
    try { parsed = parseCsv(text); } catch (e) { return { threads, errors: [e.message] }; }
    const missing = REQUEST_COLUMNS.filter(c => !parsed.columns.includes(c));
    if (missing.length) return { threads, errors: [`not in the shape of intro_requests.csv: no ${missing.join(', ')} column`] };
    const seen = new Set();
    parsed.rows.forEach((r, i) => {
      const rid = (r.request_id || '').trim(), ask = (r.raw_ask || '').trim();
      if (!rid) { errors.push(`line ${i + 2}: no request_id`); return; }
      if (seen.has(rid)) { errors.push(`line ${i + 2}: ${rid} repeated in the file, first row kept`); return; }
      if (!ask && !(r.target_company_raw || '').trim()) { errors.push(`line ${i + 2}: ${rid} has no raw_ask and no target_company_raw`); return; }
      seen.add(rid);
      const request = Object.fromEntries(parsed.columns.filter(c => !THREAD_COLUMNS.includes(c)).map(c => [c, (r[c] || '').trim()]));
      const dealCol = parsed.columns.find(c => DEAL_COLUMN.test(c));
      if (dealCol) { request.deal_value = request[dealCol]; request.currency = DEAL_COLUMN.exec(dealCol)[1].toUpperCase(); delete request[dealCol]; }
      threads.push({ request_id: rid, messages: [{ ts: (r.request_date || '').trim(), user: (r.requested_by || '').trim(), text: ask }], request });
    });
    return { threads, errors };
  }
  // a pasted or dropped file is a CSV of requests when it says so, or when its first line is a header naming request_id
  const looksLikeRequestsCsv = (text, filename) => /\.csv$/i.test(filename || '') || (!text.startsWith('{') && /^[^\n{]*\brequest_id\b[^\n]*,/.test(text.replace(/^\uFEFF/, '')));

  // ------------------------------------------------ golden/intake.py, ported
  // "Intake: Add More Live Data". A dropped CSV or Slack export is diffed here against the
  // file as the last build read it (U.files, from golden/current/) with the same rules
  // golden/intake.py applies when the rebuild pulls the accepted upload from the
  // intake_uploads table; tests/lp_parity.js runs these under node against the Python.
  const THREAD_FIELDS = ['request_id', 'messages'], MESSAGE_FIELDS = ['ts', 'user', 'text'];
  const encodeUtf8 = s => typeof TextEncoder !== 'undefined' ? new TextEncoder().encode(s) : Buffer.from(s, 'utf8');
  // FNV-1a 64: the half of upload_id both sides compute; the same bytes accepted twice are one upload
  function fnv1a(text) {
    let h = 0xCBF29CE484222325n;
    for (const b of encodeUtf8(text.replace(/^\uFEFF/, ''))) h = ((h ^ BigInt(b)) * 0x100000001B3n) & 0xFFFFFFFFFFFFFFFFn;
    return h.toString(16).padStart(16, '0');
  }
  // -g<n> once a revert has happened (n = reverts so far): the same file accepted again after a revert is a new upload
  const uploadId = (target, content, generation = 0) => `${target.replace(/\.[^.]+$/, '')}-${fnv1a(content)}${generation ? `-g${generation}` : ''}`;
  const REVERT = 'revert';
  const revertId = at => `${REVERT}-${fnv1a(at)}`;
  // the uploads that apply: those accepted after the last revert row
  const activeUploads = ledger => { const last = ledger.map(r => r.target).lastIndexOf(REVERT); return ledger.slice(last + 1).filter(r => r.target !== REVERT); };
  const formatOf = target => target.endsWith('.jsonl') ? 'jsonl' : 'csv';
  // the SCHEMAS entry a file name falls under (U.schemas: pattern, keys, family)
  function schemaOf(target, schemas) {
    for (const s of schemas) if (s.pattern === target) return s;
    for (const s of schemas) if (s.family && new RegExp('^' + s.pattern.replace('.', '\\.').replace('*', '[a-z0-9_\\-]+') + '$').test(target)) return s;
    return null;
  }
  // csv.reader: quoted fields, doubled quotes, either line ending, a BOM. Throws on no header,
  // a blank or repeated column name, or a row wider than the header
  function parseCsv(text) {
    text = text.replace(/^\uFEFF/, '');
    const rows = [];
    let row = [], cell = '', q = false, i = 0;
    while (i < text.length) {
      const c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
        else cell += c;
      } else if (c === '"') q = true;
      else if (c === ',') { row.push(cell); cell = ''; }
      else if (c === '\r' || c === '\n') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(cell); rows.push(row); row = []; cell = '';
      } else cell += c;
      i++;
    }
    if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
    while (rows.length && !rows[rows.length - 1].some(c => c.trim())) rows.pop();
    if (!rows.length || !rows[0].some(c => c.trim())) throw new Error('no header row');
    const columns = rows[0].map(c => c.trim());
    if (new Set(columns).size !== columns.length || columns.includes('')) throw new Error('header has a blank or repeated column name');
    const out = [];
    rows.slice(1).forEach((r, j) => {
      if (!r.some(c => c.trim())) return;
      if (r.length > columns.length) throw new Error(`line ${j + 2}: ${r.length} cells, header has ${columns.length}`);
      out.push(Object.fromEntries(columns.map((c, k) => [c, k < r.length ? r[k] : ''])));
    });
    return { columns, rows: out };
  }
  // the threads in a Slack upload: JSONL, a JSON array, {"threads": [...]} or one thread object
  function parseThreads(text) {
    text = text.replace(/^\uFEFF/, '').trim();
    if (!text) throw new Error('empty file');
    let whole, threads = [];
    try { whole = JSON.parse(text); } catch (e) { whole = undefined; }
    if (Array.isArray(whole)) threads = whole;
    else if (whole && typeof whole === 'object' && Array.isArray(whole.threads) && !has(whole, 'request_id')) threads = whole.threads;
    else if (whole && typeof whole === 'object') threads = [whole];
    else if (whole === undefined) {
      text.split(/\r\n|\r|\n/).forEach((line, i) => {
        if (!line.trim()) return;
        try { threads.push(JSON.parse(line)); } catch (e) { throw new Error(`line ${i + 1}: ${e.message}`); }
      });
    }
    if (!Array.isArray(threads) || !threads.length) throw new Error('no threads');
    const isObj = x => x && typeof x === 'object' && !Array.isArray(x);
    threads.forEach((t, i) => {
      if (!isObj(t) || typeof t.request_id !== 'string' || !t.request_id.trim()) throw new Error(`thread ${i + 1}: needs a request_id`);
      if (!Array.isArray(t.messages) || !t.messages.length) throw new Error(`thread ${i + 1} (${t.request_id}): needs a non-empty messages list`);
      t.messages.forEach((m, j) => {
        if (!isObj(m) || MESSAGE_FIELDS.some(k => typeof m[k] !== 'string')) throw new Error(`thread ${i + 1} (${t.request_id}) message ${j + 1}: needs ts, user and text`);
      });
    });
    return threads;
  }
  const rowKey = (r, keys) => keys.map(k => (r[k] || '').trim());
  // apply a CSV upload to the rows on file: a key not on file is a new row; on file, every non-empty
  // cell that differs overrides (listed); new columns are added after the existing ones
  function mergeCsv(baseCols, baseRows, upCols, upRows, keys) {
    const missing = keys.filter(k => !upCols.includes(k));
    if (missing.length) throw new Error(`no ${missing.join(', ')} column`);
    const columns = [...baseCols, ...upCols.filter(c => !baseCols.includes(c))];
    const newColumns = columns.slice(baseCols.length);
    const rows = baseRows.map(r => Object.fromEntries(columns.map(c => [c, has(r, c) ? r[c] : ''])));
    const index = new Map(rows.map(r => [rowKey(r, keys).join('\u0000'), r]));
    const newRows = [], changes = [], seen = new Set(), fresh = new Set();
    let dup = 0, unchanged = 0;
    upRows.forEach((u, i) => {
      const k = rowKey(u, keys), kk = k.join('\u0000');
      if (k.some(x => !x)) throw new Error(`line ${i + 2}: empty ${keys[k.indexOf('')]}`);
      if (seen.has(kk)) dup++;
      seen.add(kk);
      let r = index.get(kk);
      if (!r) {
        r = Object.fromEntries(columns.map(c => [c, has(u, c) ? u[c] : '']));
        rows.push(r); index.set(kk, r); newRows.push(r); fresh.add(r);
        return;
      }
      if (fresh.has(r)) {  // a repeat of a row this upload added: the later row wins, nothing on file is touched
        for (const c of upCols) if (has(u, c) && u[c].trim()) r[c] = u[c];
        return;
      }
      let touched = false;
      for (const c of upCols) {
        const v = has(u, c) ? u[c] : '';
        if (!v.trim() || r[c] === v) continue;
        changes.push({ key: k.join(' / '), column: c, from: r[c], to: v });
        r[c] = v; touched = true;
      }
      if (!touched) unchanged++;
    });
    const summary = { format: 'csv', rows: upRows.length, new_rows: newRows.length, changed_rows: new Set(changes.map(c => c.key)).size,
                      changes, new_columns: newColumns, unchanged_rows: unchanged, duplicate_keys: dup, columns, keys, sample: newRows.slice(0, 20) };
    return { columns, rows, summary };
  }
  const messageSig = m => MESSAGE_FIELDS.map(k => has(m, k) ? m[k] : '').join('\u0000');
  // apply a Slack upload to the threads on file: a new request_id is a new thread; one on file gets
  // the messages it lacks appended and any other non-empty field that differs overridden (listed)
  function mergeThreads(base, up) {
    const threads = base.map(t => JSON.parse(JSON.stringify(t)));
    const by = new Map(threads.map(t => [t.request_id, t]));
    const baseFields = new Set(base.flatMap(t => Object.keys(t)));
    const fresh = [], changes = [], seen = new Set(), newFields = [];
    let extended = 0, messages = 0, unchanged = 0, dup = 0;
    for (const u of up) {
      const rid = u.request_id.trim();
      if (seen.has(rid)) dup++;
      seen.add(rid);
      for (const k of Object.keys(u)) if (!baseFields.has(k) && !newFields.includes(k)) newFields.push(k);
      let t = by.get(rid);
      if (!t) {
        t = { ...u, request_id: rid };
        threads.push(t); by.set(rid, t); fresh.push(t);
        continue;
      }
      const have = new Set(t.messages.map(messageSig));
      const more = u.messages.filter(m => !have.has(messageSig(m)));
      t.messages.push(...more);
      let touched = more.length > 0;
      if (more.length) { extended++; messages += more.length; }
      for (const [k, v] of Object.entries(u)) {
        if (THREAD_FIELDS.includes(k) || v === '' || v == null || JSON.stringify(t[k]) === JSON.stringify(v)) continue;
        changes.push({ key: rid, column: k, from: t[k] == null ? '' : String(t[k]), to: String(v) });
        t[k] = v; touched = true;
      }
      if (!touched) unchanged++;
    }
    const summary = { format: 'jsonl', rows: up.length, new_rows: fresh.length, changed_rows: new Set(changes.map(c => c.key)).size,
                      changes, new_columns: newFields, unchanged_rows: unchanged, duplicate_keys: dup, extended_threads: extended, new_messages: messages, keys: ['request_id'],
                      sample: fresh.slice(0, 20).map(t => ({ request_id: t.request_id, channel: String(t.channel ?? ''), posted: t.messages[0].ts.slice(0, 10), user: t.messages[0].user, text: t.messages[0].text, replies: t.messages.length - 1 })) };
    return { threads, summary };
  }
  // which file an upload updates: [target, why]; '' when nothing fits or two fit equally. `columns` is
  // null for a JSON upload; `files` is target -> its columns as on file (U.files' columns)
  function guessTarget(filename, columns, files, schemas) {
    const name = filename.replace(/^.*[\\/]/, '').toLowerCase();
    if (columns === null) return ['slack_threads.jsonl', 'Slack threads'];
    const have = new Set(columns), names = Object.keys(files);
    const fits = t => { const s = schemaOf(t, schemas); return !!s && s.keys.every(k => have.has(k)); };
    if (has(files, name) && fits(name)) return [name, 'same file name'];
    const family = schemas.find(s => s.family);
    const connCols = new Set(family.keys);
    for (const t of names) if (schemaOf(t, schemas) === family) for (const c of files[t]) connCols.add(c);
    const conn = family.keys.every(k => have.has(k)) ? [...connCols].filter(c => have.has(c)).length : -1;
    const scored = names.filter(t => schemaOf(t, schemas) !== family && formatOf(t) === 'csv' && fits(t))
      .map(t => [files[t].filter(c => have.has(c)).length, t]).sort((a, b) => b[0] - a[0] || (a[1] < b[1] ? 1 : -1));
    const best = scored.length ? scored[0] : [-1, ''];
    if (best[0] > conn && (scored.length === 1 || scored[1][0] < best[0])) return [best[1], `${best[0]} of ${files[best[1]].length} columns match`];
    if (conn >= 0 && conn >= best[0]) {
      const stem = name.replace(/\.[^.]+$/, '').replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
      const m = /^connections?_(.+)$/.exec(stem);
      if (m) { const t = `connections_${m[1]}.csv`; return [t, has(files, t) ? 'same file name' : 'connections columns; a new file, named from the upload']; }
      if (['connections', 'connection', ''].includes(stem)) return ['', 'connections columns: pick whose (connections_<surname>.csv)'];
      return [`connections_${stem}.csv`, 'connections columns; a new file, named from the upload'];
    }
    if (best[0] >= 0) return ['', `could be ${scored.filter(([n]) => n === best[0]).map(([, t]) => t).join(' or ')}: pick one`];
    return ['', 'no file on record has these columns'];
  }
  // what accepting `text` as `target` would change, against U.files; throws when it cannot be applied
  function previewUpload(U, target, text) {
    const f = U.files[target], schema = schemaOf(target, U.schemas);
    if (!schema) throw new Error(`${target} is not a file the build reads`);
    let summary;
    if (formatOf(target) === 'jsonl') summary = mergeThreads(f ? f.threads : [], parseThreads(text)).summary;
    else {
      const up = parseCsv(text);
      const base = f ? f.rows.map(r => Object.fromEntries(f.columns.map((c, i) => [c, r[i]]))) : [];
      summary = mergeCsv(f ? f.columns : [], base, up.columns, up.rows, schema.keys).summary;
    }
    summary.target = target; summary.new_file = !f;
    return summary;
  }
  // the row Accept posts to the intake_uploads table (golden/intake.py apply_table_rows reads it back)
  const uploadRow = (target, filename, text, summary, who, at, note = '', generation = 0) => ({
    upload_id: uploadId(target, text, generation), received_at: at, received_by: who, target, filename, content: text.replace(/^\uFEFF/, ''),
    rows: summary.rows, new_rows: summary.new_rows, changed_rows: summary.changed_rows, new_columns: summary.new_columns.join(';'), note,
  });
  // the row "Revert to Sep Raw Data State" posts: no file; the build applies no upload accepted before it
  const revertRow = (who, at, note = '') => ({
    upload_id: revertId(at), received_at: at, received_by: who, target: REVERT, filename: '', content: '',
    rows: null, new_rows: null, changed_rows: null, new_columns: '', note,
  });
  async function postUpload(U, row, doFetch = (u, o) => fetch(u, o)) {
    if (!U.supabase_url || !U.anon_key) throw new Error('this build has no Supabase URL / anon key (SUPABASE_URL and SUPABASE_ANON_KEY were not set when the site was built)');
    let res;
    try {
      res = await doFetch(`${U.supabase_url}/${U.table}`, {
        method: 'POST',
        headers: { apikey: U.anon_key, Authorization: `Bearer ${U.anon_key}`, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
        body: JSON.stringify(row),
      });
    } catch (e) { throw new Error(`could not reach ${U.supabase_url} (${e.message})`); }
    if (res.ok) return { recorded: true, already: false };
    if (res.status === 409) return { recorded: false, already: true };
    let detail = '';
    try { const j = await res.json(); detail = j.message || j.error_description || j.error || ''; } catch (e) { /* no body */ }
    throw new Error(`Supabase answered HTTP ${res.status}${detail ? `: ${detail}` : ''} for ${row.upload_id}`);
  }

  // a target the canonical resolver does not know: a company on file with no CRM
  // account (P.known_no_crm -> its company_id), else one only the network reaches
  // (P.known_network -> its 'network:...' key in P.companies), else nothing
  function offFile(tg, P, resolver) {
    const name = tg.is_domain ? domainStem(tg.text) : tg.text;
    const look = table => get(table, resolver.normStrict(name), '') || get(table, resolver.normLoose(name), '');
    const cid = look(P.known_no_crm);
    if (cid) return { cid, network: false };
    const key = look(P.known_network || {});
    return { cid: key, network: !!key };
  }

  // the company column of a request row, when the ask itself names no target: read as if it were the whole message
  const companyHint = t => t.request && t.request.target_company_raw ? t.request.target_company_raw : '';
  const targetOf = (text, hint, P, resolver) => {
    const ex = extract(text, P, resolver);
    if (ex.target || !hint) return { ...ex, from_hint: false };
    const hx = extract(hint, P, resolver);
    return hx.target ? { ...hx, from_hint: true } : { ...ex, from_hint: false };
  };

  // `input` is .jsonl text, or the { threads, errors } of parseJsonl / requestsToThreads
  function previewThreads(input, P) {
    const resolver = makeResolver(P.resolver);
    const offerRe = new RegExp(P.offer.source, P.offer.flags);
    const { threads, errors } = typeof input === 'string' ? parseJsonl(input) : input;
    const rows = threads.map(t => {
      const first = t.messages[0], replies = t.messages.slice(1), req = t.request || null;
      const offers = replies.filter(m => offerRe.test(m.text || '')).map(m => ({ who: m.user, text: m.text, date: (m.ts || '').slice(0, 10) }));
      const human = [];
      const row = { request_id: t.request_id, posted: (first.ts || '').slice(0, 10), requested_by: first.user || '', raw_ask: first.text || '',
                    company_as_written: '', company_id: '', network: '', company_name: '', resolved_by: '', href: '', offers, offer_by: '', offer_text: '',
                    route_to: '', path: '', expected_value: '', needs_human: '', flags: human, filed: false, mentions: [], cands: [], priority: null,
                    target_company_raw: req ? req.target_company_raw || '' : '', target_title: req ? req.target_title_raw || '' : '',
                    deal_value: req ? req.deal_value || '' : '', currency: req ? req.currency || '' : '', urgency: req ? req.urgency || '' : '' };
      const filed = get(P.filed, t.request_id, null);
      if (filed) {
        Object.assign(row, { filed: true, company_id: filed.company_id, company_name: filed.company_name, href: filed.href,
                             resolved_by: `already filed (${filed.status}); filed facts are kept, only new offers land` });
        if (filed.asked) human.push('already asked, so an offer in the thread changes nothing');
      } else {
        const ex = targetOf(first.text || '', companyHint(t), P, resolver);
        row.mentions = ex.mentions;
        const tg = ex.target;
        const via = ex.from_hint ? ', from the target_company_raw column' : '';
        if (!tg) {
          const bare = ex.mentions.filter(m => m.cue === P.known_cue).length;
          row.resolved_by = bare > 1 ? `${bare} companies named, nothing says which is wanted` : 'no company named in the ask';
          human.push(bare > 1 ? 'several companies named and none asked for, so the build files it with no company_id' : 'no company named, so the build files it with no company_id');
        }
        else {
          row.company_as_written = tg.text;
          const r = tg.resolution;
          if (r.entity_id && r.kind === 'company') {
            Object.assign(row, { company_id: r.entity_id, resolved_by: `${r.method} (${r.confidence.toFixed(2)})${via}` });
          } else if (r.entity_id && r.kind === 'fund') {
            row.resolved_by = `${r.method}: names the fund ${r.name} rather than a customer`;
            human.push(`"${tg.text}" is an investor fund, so the build would file a new company under that name`);
          } else if (r.method === 'fund-or-customer' || r.method === 'ambiguous') {
            row.resolved_by = `${r.method}: ${r.candidates.map(c => `${c.id} ${c.name} (${c.kind})`).join(' | ')}`;
            human.push(r.method === 'fund-or-customer' ? 'bare name is both a fund and a customer, ask the requester which' : 'ambiguous between two companies, pick one');
          } else {
            const known = offFile(tg, P, resolver);
            if (known.network) { row.network = known.cid; row.resolved_by = 'a company the network reaches but nobody has filed: the build creates it with no domain and no CRM account'; human.push('no CRM account, create one (see CRM Updates)'); }
            else if (known.cid) { row.company_id = known.cid; row.resolved_by = 'matches a company on file that has no CRM account'; human.push('no CRM account, create one (see CRM Updates)'); }
            else { row.resolved_by = 'new company, so the build creates it with no domain and no CRM account'; human.push('new company with no CRM account and no domain, confirm the spelling'); }
          }
        }
        const C = get(P.companies, row.company_id || row.network || '', null);
        if (C) { row.company_name = C.company_name; row.href = C.href; if (C.stage === 'Closed Lost') human.push('CRM account is Closed Lost, reopen it or close the request'); }
        else if (row.company_as_written) row.company_name = row.company_as_written;
        if (!req) human.push('thread carries no deal value, urgency or target title, add them to the request file');
        else {
          const lacks = [['deal_value', 'deal value'], ['urgency', 'urgency'], ['target_title_raw', 'target title']].filter(([c]) => !req[c]).map(([, l]) => l);
          if (lacks.length) human.push(`row carries no ${lacks.join(', ')}, fill it in before filing`);
        }
      }
      // who it would route to: the best existing path vs any offer in the thread, scored as the build scores them
      // (path strength x focus fit x delivery rate); expected value then multiplies by the request priority
      // and the slots left, as the allocator does. Every factor comes from the payload. A connector sitting on
      // an unresolved ask at this company (C.holds) is stepped over: they agreed and sent no intro (nudge them),
      // or have not answered yet (chase them); one who never answered an ask older than the window is askable
      // again but ranks behind everyone else, offer or path.
      const C = get(P.companies, row.company_id || row.network || '', null);
      const priority = C ? C.priority : { request_priority: 0, deal_source: 'no deal value on file',
                                          components: { deal_value_musd: 0, stage_weight: P.no_crm_weight, age: 1, reps_waiting: 1 } };
      const holdOf = who => C ? get(C.holds, who, null) : null;
      const cand = (who, score, label, strength, fit, rate, capacity_left) => ({
        who, score, label, connector_score: score * capacity_left, hold: (holdOf(who) || { hold: '' }).hold,
        expected_value: priority.request_priority * score * capacity_left, if_slot: priority.request_priority * score,
        components: { path_strength: strength, focus_fit: fit, delivery_rate: rate, capacity_left },
      });
      const cands = [], held = [];
      if (C && C.best) cands.push(cand(C.best.connector, C.best.score, C.best.label, C.best.strength, C.best.fit, C.best.rate, C.best.capacity_left));
      for (const o of offers) {
        const h = holdOf(o.who);
        if (h && !h.askable) { held.push(h); human.push(`${o.who} offers, but ${h.reason}: ${h.hold === 'nudge' ? 'nudge' : 'chase'} them instead of asking afresh`); continue; }
        const score = C ? get(C.offer_score, o.who, C.offer_score_unknown) : get(P.offer_score_no_industry, o.who, P.offer_score_unknown);
        const conn = get(P.connectors, o.who, null);
        const fit = C ? get(C.offer_fit, o.who, P.unknown_fit) : P.unknown_fit, rate = conn ? conn.rate : P.prior_rate;
        const cap = conn ? conn.capacity : P.off_roster_capacity, idle = conn ? conn.idle : cap;
        cands.push(cand(o.who, score, 'offered in Slack', P.offer_base, fit, rate, cap ? Math.max(0, idle) / cap : 0));
      }
      if (C) for (const p of C.paths) { const h = holdOf(p.connector); if (h && !h.askable && !held.includes(h)) held.push(h); }
      cands.sort((a, b) => (a.hold === 'last') - (b.hold === 'last') || b.score - a.score);
      row.cands = cands; row.priority = priority; row.held = held.map(h => h.reason);
      if (offers.length) { row.offer_by = offers.map(o => o.who).join(' | '); row.offer_text = offers.map(o => o.text).join(' | '); }
      if (filed && filed.asked) {
        row.path = 'already asked, so not re-routed';
      } else if (cands.length) {
        const best = cands[0], conn = get(P.connectors, best.who, null);
        row.route_to = best.who; row.path = `${best.label} (${best.score.toFixed(2)})`; row.expected_value = best.expected_value.toFixed(3);
        if (conn && conn.idle <= 0) human.push(`${best.who} has no slot left this cycle, so this would be "capacity exhausted" unless a slot frees`);
        if (conn && !conn.on_roster) human.push(`${best.who} is not on the connector roster`);
        if (!conn) human.push(`${best.who} is unknown to the roster and the outcome log`);
        if (best.hold === 'last') human.push(`${best.who} never answered an earlier ask here; every other path is held, so they are asked again`);
      } else if (held.length) {
        row.path = 'unresolved ask on every path';
        human.push(`unresolved ask on every path, an exception unless someone else offers: ${held.map(h => h.reason).join('; ')}`);
      } else {
        row.path = 'no path';
        if (row.company_id || row.network) human.push('no path to this company in the network, an exception unless someone offers');
      }
      row.flags = human.filter(Boolean);
      row.needs_human = row.flags.join('; ');
      return row;
    });
    return { rows, errors, count: threads.length };
  }

  // --------------------------------------------------------- route a request
  // What the router would do with one pasted message: apply the cues, take the
  // highest positive score, look the key up, rank the company's exported paths.
  // Nothing here is a rule; every number and every path comes from the payload.
  // `hint` is the target_company_raw of a request row, read when the message itself names no target
  function route(text, P, hint = '') {
    text = (text || '').trim();
    const resolver = makeResolver(P.resolver);
    const ex = targetOf(text, hint, P, resolver);
    const tm = new RegExp(P.title.source, P.title.flags).exec(text);
    const tg = ex.target;
    const out = { text, title: tm ? tm.groups.t : '', mentions: ex.mentions, target: null, company: null, crm: false, from_hint: ex.from_hint,
                  others: [], candidates: [], paths: [], top: null, priority: null, status: '', note: '' };
    const bare = ex.mentions.filter(m => m.cue === P.known_cue).length;
    const lost = m => {
      if (m.cue === P.known_cue) return 'a known company, named but not asked for';
      if (m.score <= 0) return `mentioned, but as a bridge or in passing: “${m.cue}” scores ${m.score}`;
      if (m.score < tg.score) return `asked for too, but with a weaker cue: “${m.cue}” scores +${m.score} against +${tg.score}`;
      return `same cue strength (+${m.score}), but named later in the message`;
    };
    out.others = ex.mentions.filter(m => m !== tg).map(m => ({
      text: m.text, cue: m.cue, score: m.score, why: tg ? lost(m) : `“${m.cue}” scores ${m.score}; nothing in the message asks for anyone`,
      name: m.resolution.entity_id ? m.resolution.name : '', company_id: m.resolution.kind === 'company' ? m.resolution.entity_id : '',
    }));
    if (!tg) {
      out.status = 'no-target';
      out.note = bare > 1 ? `no target: ${bare} known companies are named and nothing says which one is wanted; lead with the company or ask`
        : ex.mentions.length ? 'no target: every company named is negative or in passing' : 'no target: no company is named in the message';
      return out;
    }
    const r = tg.resolution;
    out.target = { text: tg.text, cue: tg.cue, score: tg.score, is_domain: tg.is_domain, method: r.method, confidence: r.confidence, name: r.name };
    if (r.method === 'fund-or-customer' || r.method === 'ambiguous') {
      out.status = 'refused';
      out.candidates = r.candidates.map(c => ({ ...c, ref: get(P.companies, c.id, null) }));
      out.note = r.method === 'fund-or-customer'
        ? `“${tg.text}” is both a fund and a customer, so the router refuses it. Ask which one is meant.`
        : `“${tg.text}” matches more than one company, so the router refuses it. Ask which one is meant.`;
      return out;
    }
    if (r.entity_id && r.kind === 'fund') {
      out.status = 'fund';
      out.note = `“${tg.text}” resolves to ${r.name}, which is an investor fund rather than a customer. The build would file a new company under that name.`;
      return out;
    }
    const cid = r.entity_id || offFile(tg, P, resolver).cid;
    const C = get(P.companies, cid, null);
    if (!C) {
      out.status = 'unknown';
      out.note = `“${tg.text}” is a company the build has not seen: no CRM record, nobody in the network reaches it. It would be filed as a new company.`;
      return out;
    }
    out.company = C; out.crm = C.crm; out.network = !!C.network;
    out.paths = C.paths;
    out.top = C.paths.find(p => p.score > 0 && p.askable) || null;
    out.priority = out.top ? {
      ...C.priority, connector_score: out.top.connector_score,
      expected_value: +(C.priority.request_priority * out.top.connector_score).toFixed(4),
      connector_components: { path_strength: out.top.strength, focus_fit: out.top.fit, delivery_rate: out.top.rate, capacity_left: out.top.capacity_left },
    } : { ...C.priority, connector_score: 0, expected_value: 0, connector_components: null };
    const heldOnly = !out.top && C.paths.some(p => p.score > 0 && !p.askable);
    out.status = out.top ? 'routed' : 'no-path';
    out.note = out.top ? ''
      : heldOnly ? `Unresolved ask on every path into ${C.company_name}: ${C.paths.filter(p => !p.askable).map(p => p.reason.split(' · ').pop()).join('; ')}. Nobody is asked again; it would be an exception this cycle unless someone else offers.`
      : `No path on the roster: nobody in the network reaches ${C.company_name}. It would be an exception this cycle unless someone offers.`;
    if (out.top && out.top.hold === 'last') out.note = `${out.top.connector} never answered an earlier ask here; every other path is held, so they are asked again.`;
    if (C.network) out.note = `${C.company_name} is not on file: no CRM account, never requested. The network reaches it${C.path_count ? ` (${plural(C.path_count, 'path')})` : ''}; filing this request creates the company and the next rebuild routes it as ranked below. Create the CRM account (see CRM Updates).${out.note ? ' ' + out.note : ''}`;
    if (ex.from_hint) out.note = `The ask names no target; “${tg.text}” is read from the target_company_raw column.${out.note ? ' ' + out.note : ''}`;
    return out;
  }

  // ------------------------------------------------------------ completions
  // A tick is one thing someone did: an ask sent (Top priorities), a nudge or a
  // chase sent (Core bottlenecks, a connector's "already sitting on"). Ticks wait
  // in this browser until Submit posts them, one row each, to the Supabase
  // `completions` table (X.supabase_url, anon key: insert only). The scheduled
  // rebuild pulls the table into golden/completions.csv and the ticked items
  // leave the queue. completion_id is <request_id>:<action>:<day>, so submitting
  // the same tick twice hits the primary key and lands nothing new; the build
  // applies it once.
  const tickKey = t => `${t.action}:${t.request_id || t.company_id}`;
  const store = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } };
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) || d; } catch (e) { return d; } };
  function loadTicks(X) {
    const onFile = new Set(X && X.ids || []);
    const ticks = new Map(load('lp-ticks', []).filter(t => t.action).map(t => [tickKey(t), t]));
    // submitted, not yet rebuilt into the site: still shown as done, not submitted again.
    // Once the build has the row (its completion_id is in X.ids) the memory is dropped.
    const submitted = new Map(Object.entries(load('lp-submitted', {})).filter(([k, id]) => !onFile.has(id)));
    for (const k of submitted.keys()) ticks.delete(k);
    return { ticks, submitted };
  }
  const completionId = (t, day) => `${t.request_id || t.company_id}:${t.action}:${day}`;
  // the rows Submit posts: one per tick, in tick order; `at` is the ISO timestamp for completed_at
  function completionRows(X, ticks, who, at) {
    const day = at.slice(0, 10), seen = new Set(X && X.ids || []), rows = [];
    for (const t of ticks) {
      const completion_id = completionId(t, day);
      if (seen.has(completion_id)) continue;
      seen.add(completion_id);
      rows.push({ completion_id, completed_at: at, completed_by: who, action: t.action, request_id: t.request_id || null, company_id: t.company_id || null, connector: t.connector || null, note: t.note || null });
    }
    return rows;
  }
  // POST the rows, one request each: a plain insert (the anon role has insert
  // only, and Supabase's ignore-duplicates needs select), so a completion_id
  // already in the table answers 409 — recorded earlier, counted as such, not an
  // error. Resolves to { recorded, already }; rejects with a readable message on
  // the first row that fails, so nothing is reported as saved that was not.
  async function postCompletions(X, rows, doFetch = (u, o) => fetch(u, o)) {
    if (!X.supabase_url || !X.anon_key) throw new Error('this build has no Supabase URL / anon key (SUPABASE_URL and SUPABASE_ANON_KEY were not set when the site was built)');
    const out = { recorded: [], already: [] };
    for (const row of rows) {
      let res;
      try {
        res = await doFetch(`${X.supabase_url}/${X.table}`, {
          method: 'POST',
          headers: { apikey: X.anon_key, Authorization: `Bearer ${X.anon_key}`, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
          body: JSON.stringify(row),
        });
      } catch (e) { throw new Error(`could not reach ${X.supabase_url} (${e.message})`); }
      if (res.ok) { out.recorded.push(row); continue; }
      let detail = '';
      try { const j = await res.json(); detail = j.message || j.error_description || j.error || ''; } catch (e) { /* no body */ }
      if (res.status === 409) { out.already.push(row); continue; }
      throw new Error(`Supabase answered HTTP ${res.status}${detail ? `: ${detail}` : ''} for ${row.completion_id}`);
    }
    return out;
  }
  const SUBMITTED_TITLE = 'Recorded; leaves the list when the site rebuilds';
  const isDone = (state, k) => state.ticks.has(k) || state.submitted.has(k);
  // the tick-box for one row; the data- attributes are what Submit posts. The same key
  // (action + request) can sit in several sections; they are kept in step by syncTicks
  const tickInput = (state, t) => {
    const key = tickKey(t), sub = state.submitted.has(key);
    return `<input type="checkbox" class="tick" ${isDone(state, key) ? 'checked' : ''} ${sub ? `disabled title="${SUBMITTED_TITLE}"` : ''} aria-label="done" data-key="${esc(key)}" data-action="${esc(t.action)}" data-rid="${esc(t.request_id || '')}" data-cid="${esc(t.company_id || '')}" data-connector="${esc(t.connector || '')}" data-note="${esc(t.note || '')}">`;
  };
  const tick = (state, t) => `<td>${tickInput(state, t)}</td>`;
  const doneClass = (state, t) => isDone(state, tickKey(t)) ? 'done' : '';
  // one box for several ticks at once (a company's live requests, all asked of one connector)
  const groupTick = (state, ticks) => {
    const keys = ticks.map(tickKey), sub = keys.every(k => state.submitted.has(k));
    return `<td><input type="checkbox" class="tick" ${keys.every(k => isDone(state, k)) ? 'checked' : ''} ${sub ? `disabled title="${SUBMITTED_TITLE}"` : ''} aria-label="done" data-connector="${esc(ticks[0].connector || '')}" data-group="${esc(JSON.stringify(ticks))}"></td>`;
  };
  const groupDone = (state, ticks) => ticks.every(t => isDone(state, tickKey(t))) ? 'done' : '';
  // a row that is done-state only: lit when every key it mirrors is ticked, nothing to click
  const mirror = (state, ticks) => `class="${groupDone(state, ticks)}" data-mirror="${esc(ticks.map(tickKey).join(' '))}"`;
  // an ask with no path on file: the box plus a picker for whoever was actually asked (a roster
  // connector, or someone off it who offered); picking a name is the tick
  const OTHER = '__other__';
  const pickTick = (state, t, names) => {
    const on = state.ticks.get(tickKey(t)), who = on && on.connector || t.connector || '';
    const opts = [...new Set([...names, ...(who ? [who] : [])])];
    return `<td class="pick">${tickInput(state, { ...t, connector: who })}<select class="pick" aria-label="who was asked"><option value="">Who was asked…</option>${opts.map(n => `<option value="${esc(n)}"${n === who ? ' selected' : ''}>${esc(n)}</option>`).join('')}<option value="${OTHER}">Someone else…</option></select><span class="pick-note foot"></span></td>`;
  };
  const ticksOf = cb => cb.dataset.group ? JSON.parse(cb.dataset.group).map(t => ({ ...t, connector: cb.dataset.connector }))
    : [{ action: cb.dataset.action, request_id: cb.dataset.rid, company_id: cb.dataset.cid, connector: cb.dataset.connector, note: cb.dataset.note }];
  // every box and mirrored row on the page, re-read from state
  function syncTicks(root, state) {
    root.querySelectorAll('.tick').forEach(cb => {
      const keys = ticksOf(cb).map(tickKey), done = keys.filter(k => isDone(state, k)).length, sub = keys.every(k => state.submitted.has(k));
      cb.checked = done === keys.length; cb.indeterminate = done > 0 && done < keys.length;
      cb.disabled = sub;
      const sel = cb.parentElement.querySelector('select.pick'), picked = sel && state.ticks.get(keys[0]);
      if (sel) { if (picked && picked.connector) { setPick(sel, picked.connector); cb.dataset.connector = picked.connector; } sel.disabled = sub; }
      const by = keys.map(k => state.ticks.get(k)).find(t => t && t.connector && t.connector !== cb.dataset.connector);
      cb.title = sub ? SUBMITTED_TITLE : by ? `Ticked as an ask to ${by.connector}` : '';
      const tr = cb.closest('tr'); if (tr) tr.classList.toggle('done', cb.checked);
    });
    root.querySelectorAll('[data-mirror]').forEach(tr => tr.classList.toggle('done', tr.dataset.mirror.split(' ').every(k => isDone(state, k))));
  }
  const setPick = (sel, v) => {
    if (![...sel.options].some(o => o.value === v)) sel.insertBefore(new Option(v, v), sel.querySelector(`option[value="${OTHER}"]`));
    sel.value = v;
  };
  const askTick = (X, r) => ({ action: X.actions.top, request_id: r.request_id, company_id: r.company_id, connector: r.connector, note: `${r.company_name} · ${r.target_title}` });
  // a connector's outstanding ask: `nudge` (they agreed — the same row as Core bottlenecks) or `chase` (never replied)
  const followTick = (X, s) => ({ action: X.actions[s.action], request_id: s.request_id, company_id: s.company_id, connector: s.connector, note: `${s.company_name} · asked ${s.asked_date}` });
  const actionLabel = { ask_sent: 'ask sent', nudged: 'nudged', chased: 'chased' };
  const describe = r => `${actionLabel[r.action] || r.action} ${esc(r.request_id || r.company_id)}${r.connector ? ` → ${esc(r.connector)}` : ''}`;

  // asked once per browser; after that the name is shown next to Submit / Accept, with a link to change it
  const askWho = () => {
    const who = (window.prompt('Who are you? (goes in completed_by / received_by, remembered in this browser)', load('lp-who', '') || '') || '').trim();
    if (who) store('lp-who', who);
    return who;
  };

  const submitBar = X => `<div class="submitbar" id="lp-submit" hidden><span id="lp-submit-n"></span><button id="lp-submit-go">Submit</button><button id="lp-submit-clear" class="secondary">Clear</button><span id="lp-submit-who"></span><span class="foot">${X.supabase_url ? `Records your ticks in the <code>${esc(X.table)}</code> table; the site rebuilds from it within a few minutes and the ticked items leave the queue.` : '<b class="warn">This build cannot submit: no Supabase URL / anon key</b>'}</span></div>`;

  // capOf: roster connector → their card (used, capacity), for the picker's over-capacity note
  function wireCompletions(root, X, state, capOf = {}) {
    const bar = root.querySelector('#lp-submit'), n = root.querySelector('#lp-submit-n'), go = root.querySelector('#lp-submit-go');
    const whoEl = root.querySelector('#lp-submit-who');
    const show = () => {
      const k = state.ticks.size, who = load('lp-who', '');
      bar.hidden = !k && !bar.dataset.msg;
      bar.classList.toggle('failed', bar.dataset.state === 'failed');
      n.innerHTML = bar.dataset.msg || `<b>${plural(k, 'tick')}</b>`;
      whoEl.innerHTML = who ? `as <b>${esc(who)}</b> · <a href="#" id="lp-submit-rename">Change</a>` : '';
      const rename = whoEl.querySelector('#lp-submit-rename');
      if (rename) rename.onclick = e => { e.preventDefault(); askWho(); show(); };
      go.disabled = !k || !X.supabase_url;
    };
    const changed = () => { store('lp-ticks', [...state.ticks.values()]); delete bar.dataset.msg; delete bar.dataset.state; syncTicks(root, state); show(); };
    root.querySelectorAll('.tick').forEach(cb => cb.addEventListener('change', () => {
      const sel = cb.parentElement.querySelector('select.pick');
      if (sel && cb.checked && !cb.dataset.connector) { cb.checked = false; sel.classList.add('need'); sel.focus(); return; }
      for (const t of ticksOf(cb)) cb.checked ? state.ticks.set(tickKey(t), t) : state.ticks.delete(tickKey(t));
      changed();
    }));
    const pickNote = (sel, v) => {
      const n = sel.parentElement.querySelector('.pick-note'), c = capOf[v];
      const over = c && c.capacity && c.used >= c.capacity;
      n.classList.toggle('warn', !!over);
      n.textContent = !v ? '' : !c ? 'Off the roster: recorded against them, no capacity to count'
        : over ? `${c.used + 1} / ${c.capacity} with this ask: over stated capacity` : `${c.used + 1} / ${c.capacity} with this ask`;
    };
    root.querySelectorAll('select.pick').forEach(sel => sel.addEventListener('change', () => {
      let v = sel.value;
      if (v === OTHER) {
        v = (window.prompt('Who was asked? (their name, as it should read in the completions table)') || '').trim();
        if (!v) { sel.value = ''; return; }
        setPick(sel, v);
      }
      const cb = sel.parentElement.querySelector('.tick');
      cb.dataset.connector = v; sel.classList.remove('need'); pickNote(sel, v);
      if (!v) return;
      for (const t of ticksOf(cb)) state.ticks.set(tickKey(t), t);
      changed();
    }));
    root.querySelectorAll('select.pick').forEach(sel => pickNote(sel, sel.value));
    root.querySelector('#lp-submit-clear').onclick = () => {
      state.ticks.clear(); changed();
    };
    go.onclick = async () => {
      if (!state.ticks.size) return;
      const who = load('lp-who', '') || askWho();
      if (!who) return;
      const ticks = [...state.ticks.entries()], at = new Date().toISOString();
      const rows = completionRows(X, ticks.map(([, t]) => t), who, at);
      go.disabled = true; delete bar.dataset.state;
      bar.dataset.msg = `Recording ${plural(rows.length, 'row')}…`; show();
      let got;
      try {
        got = await postCompletions(X, rows);
      } catch (e) {
        // the ticks stay ticked and pending, so Submit can be tried again
        bar.dataset.state = 'failed';
        bar.dataset.msg = `<b class="warn">Not recorded.</b> ${esc(e.message)}. Your ${plural(ticks.length, 'tick')} are still here. Try Submit again, or if Supabase is down, tell whoever runs the build to apply them by hand.`;
        show();
        return;
      }
      for (const [k, t] of ticks) state.submitted.set(k, completionId(t, at.slice(0, 10)));
      state.ticks.clear(); store('lp-ticks', []); store('lp-submitted', Object.fromEntries(state.submitted));
      syncTicks(root, state);
      const already = got.already.length ? ` ${plural(got.already.length, 'row')} already recorded today (${got.already.map(describe).join('; ')}).` : '';
      bar.dataset.msg = `<b>Recorded ${plural(got.recorded.length, 'row')}</b> as ${esc(who)}${got.recorded.length ? `: ${got.recorded.map(describe).join('; ')}` : ''}.${already} The site rebuilds from the table within a few minutes; refresh after that and these leave the queue.`;
      show();
    };
    syncTicks(root, state);
    show();
  }

  // when this site was last built, from docs/build_stamp.json (deployed with
  // the rest of docs/ on every rebuild), and the last run of the rebuild
  // workflow from the public GitHub Actions API when the repo is known — that
  // run is what says the page is current even when nothing changed. Stale = no
  // successful run in 3 hours: the workflow runs on every Submit and on a
  // 15-minute cron, but GitHub fires that cron every hour or two in practice, so
  // anything tighter warns on a healthy site. With no API, a build over a day
  // old. Both are best-effort: a page opened from disk shows the as-of date.
  const STALE_RUN_MS = 3 * 3600 * 1000, STALE_BUILD_MS = 24 * 3600 * 1000;
  const ago = (iso, now = Date.now()) => {
    const m = Math.round((now - Date.parse(iso)) / 60000);
    return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 2880 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} days ago`;
  };
  const utc = iso => iso.replace('T', ' ').replace(/(:\d\d)(\.\d+)?Z$/, '$1 UTC');
  async function fetchJson(url, opts) {
    try { const r = await fetch(url, opts); return r.ok ? await r.json() : null; } catch (e) { return null; }
  }
  async function buildStamp(D, el) {
    if (!el) return;
    const X = D.completions || {};
    const m = /^https:\/\/github\.com\/([^/]+\/[^/]+)$/.exec(X.repo_url || '');
    const [st, runs] = await Promise.all([
      fetchJson(X.stamp || 'build_stamp.json', { cache: 'no-store' }),
      m && X.workflow ? fetchJson(`https://api.github.com/repos/${m[1]}/actions/workflows/${X.workflow}/runs?per_page=1&status=success`, { headers: { Accept: 'application/vnd.github+json' } }) : null,
    ]);
    const run = runs && (runs.workflow_runs || [])[0];
    const stale = run ? Date.now() - Date.parse(run.updated_at || run.created_at) > STALE_RUN_MS
      : st ? Date.now() - Date.parse(st.built_at) > STALE_BUILD_MS : false;
    const parts = [];
    if (st) parts.push(`Site built <b>${esc(utc(st.built_at))}</b> (${ago(st.built_at)}; as of ${esc(st.as_of)}, ${plural(st.completions, 'completion')} applied)`);
    else parts.push(`As of <b>${esc(D.as_of)}</b>`);
    if (run) parts.push(`Last rebuild check <a href="${esc(run.html_url)}" target="_blank" rel="noopener">${ago(run.updated_at || run.created_at)}</a>`);
    if (stale) parts.push('<b class="warn">Stale: no rebuild in over 3 hours; the site may not reflect recent Submits</b>');
    el.innerHTML = parts.join(' · ');
  }

  // ------------------------------------------------------------------ render
  // a connector never asked has no rate of their own: the scoring assumes the network average (the prior)
  const rateKpi = c => c.asks_all_time
    ? `<div class="kpi"><div class="v">${Math.round(c.delivery_rate * 100)}%</div><div class="l">Delivery rate</div><div class="s">${c.intros_all_time} intros / ${c.asks_all_time} asks, shrunk toward the ${Math.round(c.prior_rate * 100)}% network average</div></div>`
    : `<div class="kpi"><div class="v words">No track record</div><div class="l">Delivery rate</div><div class="s">Never asked; scoring assumes the ${Math.round(c.prior_rate * 100)}% network average</div></div>`;
  // capacity used against stated: an ask recorded outside the allocation can take a connector past it, flagged rather than capped
  const capKpi = c => c.capacity
    ? `<div class="kpi ${c.over_capacity ? 'warn' : ''}"><div class="v">${c.used} / ${c.capacity}</div><div class="l">capacity used this cycle</div><div class="s">${c.asked_this_cycle} asked + ${c.allocated_this_cycle} allocated · ${c.over_capacity ? `<b class="warn">${c.over_capacity} over stated capacity</b>` : `${c.idle} idle`}</div></div>`
    : `<div class="kpi"><div class="v">${c.used}</div><div class="l">asks this cycle</div><div class="s">${c.asked_this_cycle} asked + ${c.allocated_this_cycle} allocated</div></div>`;
  const comp = (r, k, fmt) => `<span class="c" title="${esc(k.replace(/_/g, ' '))}">${fmt(r.components[k])}</span>`;
  const FM_HEAD = '<th class="num">Expected value</th><th>Request priority<br><span class="fm">deal $M × stage × age × reps</span></th><th>Connector score<br><span class="fm">path × fit × rate × capacity</span></th>';
  const fmCells = r => `<td class="num ev">${r.expected_value.toFixed(3)}</td><td class="parts"><b>${r.request_priority.toFixed(3)}</b><span class="math">${comp(r, 'deal_value_musd', v => v.toFixed(2))} × ${comp(r, 'stage_weight', v => v.toFixed(2))} × ${comp(r, 'age', v => v.toFixed(2))} × ${comp(r, 'reps_waiting', v => v)}</span><span class="foot">${r.days_waiting} days waiting</span></td><td class="parts"><b>${r.connector_score.toFixed(3)}</b><span class="math">${comp(r, 'path_strength', v => v.toFixed(2))} × ${comp(r, 'focus_fit', v => v.toFixed(2))} × ${comp(r, 'delivery_rate', v => v.toFixed(2))} × ${comp(r, 'capacity_left', v => v.toFixed(2))}</span><span class="foot">${esc(r.capacity_note)}</span></td>`;

  // rows of ranked() with tick-boxes (an ask sent); `rankKey` picks the number shown in the # column
  function priorityTable(rows, X, state, rankKey, withConnector) {
    return `<table class="top prio"><thead><tr><th></th><th>#</th><th>Company · request</th><th>Who wants</th>${withConnector ? '<th>Ask</th>' : '<th>Path</th>'}${FM_HEAD}</tr></thead><tbody>`
      + rows.map(r => { const t = askTick(X, r); return `<tr class="${doneClass(state, t)}" data-rid="${esc(r.request_id)}">${tick(state, t)}<td class="order">${r[rankKey]}</td><td class="co">${co(r)}<br><span class="foot">${esc(r.target_title)}</span><br><span class="foot"><span class="rid">${esc(r.request_id)}</span> · ${esc(r.value_fmt)} · ${esc(r.crm_stage)}</span>${retryTag(r)}${reopenedTag(r)}${notifyTag(r)}</td><td class="who">${esc(r.requested_by)}${r.reps.length > 1 ? `<br><span class="foot">+${r.reps.length - 1} more waiting</span>` : ''}</td><td class="via">${withConnector ? `<b>${esc(r.connector)}</b><br><span class="foot">${r.on_roster ? 'roster · ' : ''}${esc(r.path)}</span>` : esc(r.path)}${r.allocated ? '' : '<br><b class="warn">no slot this cycle</b>'}</td>${fmCells(r)}</tr>`; }).join('')
      + `</tbody></table>`;
  }

  function formulaNote(F) {
    return `<div class="formula"><p><code>${esc(F.expected_value)}</code></p><p><code>${esc(F.request_priority)}</code><br><code>${esc(F.connector_score)}</code></p>
      <p class="foot">Stage weight by CRM stage: ${Object.entries(F.stage_weight).map(([k, v]) => `${esc(k)} ${v}`).join(' · ')}. Age: ${esc(F.age)}. Reps waiting: ${esc(F.reps_waiting)}. Path strength: ${esc(F.path_strength)}. Focus fit: ${esc(F.focus_fit)}. Delivery rate: ${esc(F.delivery_rate)}. Capacity left: ${esc(F.capacity_left)}. Tick a row once the ask is sent; Submit records the ticks and the next rebuild takes them off the list.</p></div>`;
  }

  // asks a connector is sitting on, with a tick-box per row (nudged / chased); a row
  // followed up in the last quietDays has no box and says when. `withConnector` names
  // who owes each row, for the table that spans every connector
  const sittingTable = (rows, quietDays, X, state, withConnector) => rows.length ? `<table class="top"><thead><tr><th></th><th>Action</th><th>Request</th><th>Company</th><th>Wanted</th><th>For</th>${withConnector ? '<th>Connector</th>' : ''}<th>Asked</th><th>Agreed</th><th class="num">Days</th><th>Responded</th><th>Value</th></tr></thead><tbody>`
    + rows.map(s => { const k = followTick(X, s); return `<tr class="${s.quiet ? 'quiet' : doneClass(state, k)}">${s.quiet ? `<td title="${esc(actionLabel[k.action])} ${esc(s.nudged_on)}; back in ${quietDays - s.days_since_nudged}d"></td>` : tick(state, k)}<td><b>${esc(s.action)}</b>${s.quiet ? `<br><span class="foot">${esc(actionLabel[k.action])} ${s.days_since_nudged}d ago</span>` : ''}</td><td class="rid">${esc(s.request_id)}<br><span class="foot">${esc(s.status)}</span></td><td>${co(s)}${s.blocking && s.blocking.length ? `<br><span class="foot" title="no one else reaches the company: these requests are exceptions until this resolves">Holds up ${s.blocking.map(esc).join(', ')}</span>` : ''}${retryTag(s)}</td><td>${esc(s.target_title)}</td><td>${esc(s.requested_by)}</td>${withConnector ? `<td>${esc(s.connector)}${s.on_roster ? '' : ' <span class="foot">off roster</span>'}</td>` : ''}<td class="date">${esc(s.asked_date)}</td><td class="date">${esc(s.agreed_date)}</td><td class="num"><b>${s.days_since_asked}</b></td><td>${s.responded ? '<b>Yes, so nudge rather than re-ask</b>' : 'No'}</td><td>${esc(s.value_fmt)}${s.value_source === 'crm' ? ' <span class="foot">CRM</span>' : s.value_source === 'deal' ? ' <span class="foot">latest ask</span>' : ''}</td></tr>`; }).join('') + `</tbody></table><p class="foot">Tick a row once you have nudged or chased; it is off the list for ${quietDays} days after the next rebuild.</p>` : `<p class="empty">Nothing outstanding</p>`;

  const pctOf = v => v == null ? 'n/a' : `${Math.round(v * 100)}%`;

  // cycle-by-cycle record: asks against capacity, intros made, running total
  const cycleTable = (rows, who) => `<table class="cycles"><thead><tr><th>Cycle</th><th class="num">Asks</th><th class="num">Of capacity</th><th class="num">Intros made</th><th class="num">Cumulative intros</th></tr></thead><tbody>`
    + rows.map(r => `<tr${r.current ? ' class="now"' : ''}><td class="date">${esc(r.cycle)}${r.current ? ' <span class="foot">this cycle</span>' : ''}</td>`
      + `<td class="num">${r.asks}${r.allocated ? ` <span class="foot">+ ${r.allocated} allocated</span>` : ''}</td>`
      + `<td class="num">${pctOf(r.capacity_pct)}${r.capacity ? ` <span class="foot">${r.used} / ${r.capacity}</span>` : ''}</td>`
      + `<td class="num">${r.intros}</td><td class="num">${r.intros_cumulative}</td></tr>`).join('')
    + `</tbody></table><p class="foot">A cycle is a calendar month, the allocator's unit. Asks by <code>asked_date</code>, intros by <code>intro_date</code> from <code>intro_outcomes.csv</code>; capacity is ${esc(who)}'s stated monthly capacity in <code>connector_roster.csv</code>. This cycle's allocation counts as slots used because those asks are about to go out.</p>`;

  // ------------------------------------------------- batched-ask composer
  // The drafted message dashboard/batch_ask.py wrote for one connector's cycle batch,
  // with a copy button. A drafting aid only: copying writes nothing anywhere; the
  // ask_sent tick on the queue rows stays the record that the ask went out.
  // `cycleSize` is the current cycle's allocation (the population the count is of); a message kept
  // from an earlier cycle states that cycle instead
  const composeBlock = (m, id, tick = 'tick <i>ask sent</i> on the rows below once it has gone out', cycleSize = 0) => !m ? '' : `<div class="compose" id="${esc(id)}"><div class="bar"><b>Batched ask · ${esc(m.connector)}</b>
      <span class="foot">Cycle ${esc(m.cycle)} · ${plural(m.request_count, 'request')} ${cycleSize ? `of the ${cycleSize} in this cycle` : `of cycle ${esc(m.cycle)}`} across ${plural(m.company_count, 'company')} · ${m.template === 'offerer' ? 'offerer template (off the roster, asked because they offered)' : m.template === 'network' ? 'network template (investor network, asked for a warm intro as a favour)' : 'roster template'}${m.over_capacity ? ` · <b class="warn">${m.request_count} asks against a stated capacity of ${m.capacity}</b>` : ''}</span>
      <button type="button" class="copy" data-copy="${esc(id)}">Copy message</button></div>
      <pre class="msg">${esc(m.message)}</pre>
      <p class="foot">Paste into the thread or a DM. Copying writes nothing; ${tick}.</p></div>`;
  const wireCopy = root => root.querySelectorAll('button.copy').forEach(b => b.onclick = async () => {
    const pre = root.querySelector(`#${b.dataset.copy} pre.msg`), text = pre ? pre.textContent : '';
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
      const ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.left = '-9999px';
      document.body.appendChild(ta); ta.select();
      try { ok = document.execCommand('copy'); } catch (e2) { ok = false; }
      ta.remove();
    }
    const label = b.textContent;
    b.textContent = ok ? 'Copied' : 'Select and copy';
    b.classList.toggle('copied', ok);
    if (!ok && pre) { const r = document.createRange(); r.selectNodeContents(pre); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
    setTimeout(() => { b.textContent = label; b.classList.remove('copied'); }, 1600);
  });

  // the Batched-Ask tab (docs/batchask.html): every drafted message, current cycle first
  function bootBatch(D, root) {
    const now = D.messages.filter(m => m.cycle === D.cycle), past = D.messages.filter(m => m.cycle !== D.cycle);
    const detail = m => `<details><summary>${plural(m.request_count, 'request')} ${m.cycle === D.cycle ? `of the ${D.cycle_size} in this cycle` : `of cycle ${esc(m.cycle)}`} behind this message (ids, scores, values and urgency stay here, out of the text)</summary>
      <table><thead><tr><th>Request</th><th>Company</th><th>Wanted</th><th>For</th><th>Path</th><th class="num">Score</th><th>Value</th><th>Urgency</th></tr></thead><tbody>`
      + m.requests.map(q => `<tr><td class="rid">${esc(q.request_id)}</td><td>${co(q)}</td><td>${esc(q.target_title)}</td><td>${esc(q.requested_by)}</td><td>${esc(q.path_type)}${q.contact_name ? ` <span class="foot">via ${esc(q.contact_name)}</span>` : q.offer_date ? ` <span class="foot">offered ${esc(q.offer_date)}</span>` : ''}</td><td class="num">${esc(q.route_score)}</td><td>${esc(q.value_fmt)}</td><td>${esc(q.urgency)}</td></tr>`).join('')
      + `</tbody></table></details>`;
    const card = m => `<section id="${esc(m.slug)}"><h2>${esc(m.connector)} <span class="foot">${m.on_roster ? esc(m.type) : 'Not on the roster'} · Batch <code>${esc(m.batch_id)}</code>${m.page ? ` · <a href="${esc(m.page)}">Their page</a>` : ''}</span></h2>`
      + composeBlock(m, `ask-${m.cycle}-${m.slug}`, `tick <i>ask sent</i> on ${m.page ? `<a href="${esc(m.page)}">their page</a>` : 'their page'} or <a href="livepriorities.html#connectors">Live Priorities</a> once it has gone out`, m.cycle === D.cycle ? D.cycle_size : 0) + detail(m) + `</section>`;
    let out = `<p class="stamp" id="lp-stamp">As of <b>${esc(D.as_of)}</b></p>
      <section id="about"><p class="lede">One message per connector for cycle <b>${esc(D.cycle)}</b>: their whole batch from <code>golden_allocation.csv</code>, grouped by company and ordered by the batch's best route, requesters named from <code>golden_requests.csv</code>. Connectors on the roster get the roster wording; someone off the roster who is being asked because they offered in a thread gets the offerer wording, quoting the thread date; an investor-network person asked over their own portfolio or prior-employer path gets the network wording, a thank-you and a request for a warm introduction rather than a work queue. The wording lives in <code>${esc(D.templates)}</code>. No dollar value, route score, request id or urgency label appears in the text; those stay in the table under each message.</p>
      <p class="foot">${plural(now.length, 'message')} this cycle: ${now.map(m => `<a href="#${esc(m.slug)}">${esc(m.connector)}</a>`).join(' · ') || 'nothing allocated'}. Copying writes nothing; the <i>ask sent</i> tick on Live Priorities and the connector's page remains the record that the ask went out.</p></section>`;
    out += now.map(card).join('') || `<p class="empty">Nothing allocated in cycle ${esc(D.cycle)}</p>`;
    if (past.length) out += `<section id="past">${fold(`Earlier cycles <span class="foot">${plural(past.length, 'message')} kept for reference</span>`)}${past.map(card).join('')}</details></section>`;
    root.innerHTML = out;
    wireCopy(root);
    openFoldAt(root);
    buildStamp(D, root.querySelector('#lp-stamp'));
  }

  // read-only: the strongest raw path into a company is this connector's, but the allocator sent every
  // live request elsewhere (capacity, or a focus area they decline outside of). Not an ask, so no tick.
  const strongestTable = c => {
    const rows = c.strongest_elsewhere || [];
    if (!rows.length) return '';
    const cap = c.capacity ? `you're at ${c.used}/${c.capacity}` : `${c.used} asked this cycle`;
    const why = s => [s.capacity && s.used >= s.capacity ? `at capacity ${s.used}/${s.capacity}` : '', s.outside_focus ? `${esc(s.industry)} is outside your focus` : ''].filter(Boolean).join(' · ');
    const went = s => [s.routed_to.length ? `routed to ${s.routed_to.map(esc).join(', ')}` : '', s.unrouted ? `${plural(s.unrouted, 'request')} of the ${c.cycle_size} in this cycle unrouted` : ''].filter(Boolean).join(' · ');
    return `<h3>Strongest path here, not routed to you <span class="foot">Read-only: ${plural(rows.length, 'company')} where your path is the strongest on file and this cycle's requests went elsewhere; ${cap}. Nobody has asked you; there is nothing to tick.</span></h3>`
      + `<table class="top"><thead><tr><th>Company</th><th>Your path</th><th class="num">Strength</th><th class="num">Route score</th><th>Why not you</th><th>This cycle</th><th>Requests</th></tr></thead><tbody>`
      + rows.map(s => `<tr class="quiet"><td>${co(s)}</td><td>${esc(s.reach_type)}</td><td class="num">${s.strength.toFixed(3)}</td><td class="num">${s.route_score.toFixed(3)}</td><td>${why(s) || 'The allocator ranked another path higher'}</td><td>${went(s)}</td><td class="rid">${s.requests.map(esc).join(', ')}</td></tr>`).join('')
      + `</tbody></table><p class="foot">Route score = strength × focus fit × delivery rate, the allocator's sort key; a 0.000 is a focus area you decline outside of. An ask only appears above, under "Already sitting on", once it is logged in intro_outcomes.csv.</p>`;
  };

  // one connector's page (docs/connector-<slug>.html): the drafted ask, top 5, then the longer list
  function bootConnector(c, root) {
    const X = c.completions, state = loadTicks(X);
    const now = c.cycles[c.cycles.length - 1];
    let out = c.batch_ask ? `<section id="ask"><h2>This Cycle's Ask <span class="foot">The batch drafted as one message: copy it, send it, then tick the rows below as the asks go out</span></h2>${composeBlock(c.batch_ask, `ask-${c.slug}`, undefined, c.cycle_size)}</section>` : '';
    out += `<section id="top"><h2>Top ${c.top.length} for ${esc(c.connector)} <span class="foot">Do these next: ${esc(c.connector)}'s share of the ${c.ranked_count} live requests routed to them, of the ${c.cycle_size} in this cycle, sorted by expected value${c.no_slot ? `; ${c.no_slot} have no slot until capacity frees up` : ''}</span></h2>
      <p class="lede">${c.on_roster ? `${esc(c.role)} · ${esc(c.type)} · Focus: ${c.focus.map(esc).join(', ')}${c.hard_decline ? ' · <b>declines anything outside</b>' : ''}` : `<b>Not on the roster</b> · ${esc(c.type)} · no stated capacity or focus areas`}${c.notes ? `<br><span class="foot">${esc(c.notes)}</span>` : ''}</p>
      <div class="kpis">${capKpi(c)}
        <div class="kpi"><div class="v">${c.intros_this_cycle}</div><div class="l">intros made this cycle</div><div class="s">${esc(now.cycle)} · ${c.capacity ? `${pctOf(now.capacity_pct)} of capacity used` : 'no stated capacity'}</div></div>
        <div class="kpi"><div class="v">${c.intros_all_time}</div><div class="l">cumulative intros</div><div class="s">since ${esc(c.cycles[0].cycle)}, over ${c.asks_all_time} asks</div></div>
        ${rateKpi(c)}
        <div class="kpi"><div class="v">${c.ranked_count}</div><div class="l">requests on their list</div><div class="s">of the ${c.cycle_size} in this cycle · ${esc(c.ranked_value_fmt)} of deal value</div></div>
        <div class="kpi ${c.sitting_on.length ? 'warn' : ''}"><div class="v">${c.sitting_on.length}</div><div class="l">already sitting on</div><div class="s">asked, live, no intro yet</div></div></div>`
      + (c.top.length ? priorityTable(c.top, X, state, 'rank_here', false) : `<p class="empty">Nothing routed to ${esc(c.connector)} this cycle</p>`)
      + `<p class="foot"># is the rank within ${esc(c.connector)}'s list; the same rows rank ${c.top.map(r => r.rank).join(', ') || 'nowhere'} on the <a href="livepriorities.html#top">overall list</a>.</p></section>`;

    out += `<section id="rest"><h2>The Longer List <span class="foot">Everything else on ${esc(c.connector)}'s plate: ${plural(c.rest.length, 'more request')} to ask (of the ${c.cycle_size} in this cycle), then ${plural(c.sitting_on.length, 'ask')} already made and waiting on them</span></h2>
      <h3>After the top ${c.top.length}</h3>` + (c.rest.length ? priorityTable(c.rest, X, state, 'rank_here', false) : `<p class="empty">${c.ranked_count ? 'The top ' + c.top.length + ' is the whole list' : 'Nothing to ask'}</p>`)
      + `<h3>Already sitting on</h3>` + sittingTable(c.sitting_on, c.quiet_days, X, state, false)
      + strongestTable(c)
      + formulaNote(c.formula) + `</section>`;

    out += `<section id="cycles"><h2>By Cycle <span class="foot">${esc(c.connector)}'s asks against capacity, intros made and the running total, one row per month since ${esc(c.cycles[0].cycle)}</span></h2>`
      + cycleTable(c.cycles, c.connector) + `</section>`;

    root.innerHTML = `<p class="stamp" id="lp-stamp">As of <b>${esc(c.as_of)}</b></p>` + out + submitBar(X);
    wireCompletions(root, X, state);
    wireCopy(root);
    buildStamp(c, root.querySelector('#lp-stamp'));
  }

  function boot(D, root) {
    const P = D.parser, X = D.completions;
    const state = loadTicks(X);
    // every section, keyed by id; D.bands says which band each belongs to and in what order
    const sec = {};

    // ---- band 1 · intake: input the build does not have yet. One box: a pasted message is one
    // thread, a dropped or pasted .jsonl is many; either way one row per thread, each opening
    // on what the router would do with it
    sec.route = `<section id="route"><h2>Route a Live Request <span class="foot">Paste a Slack message, drop a <code>.jsonl</code> export, or drop a <code>.csv</code> in the shape of <code>intro_requests.csv</code>, and see what the router would do with it</span></h2>
      <p class="lede">Runs the build's own rules in the browser: names the company, spots any offer, ranks the paths and picks who to ask. One row per thread or request; click it for the arithmetic. Nothing is saved: export the preview to file it.</p>
      <div class="presets">Try a real shape:${P.route_presets.map((p, i) => `<button class="secondary" data-i="${i}">${esc(p.label)}</button>`).join('')}</div>
      <div class="ask"><textarea id="lp-route-text" rows="5" placeholder="Who do we know at … — or paste .jsonl lines, one {request_id, messages:[{ts,user,text}…]} per line — or CSV rows with the intro_requests.csv header" aria-label="Slack message, .jsonl or .csv"></textarea><button id="lp-route-go">Route it</button></div>
      <div class="drop" id="lp-drop"><input type="file" id="lp-file" accept=".jsonl,.json,.txt,.csv"><span>Or drop a .jsonl of threads or a .csv of requests (new request IDs, the <code>intro_requests.csv</code> columns) here, or click to choose</span></div>
      <div id="lp-preview"></div></section>`;

    // ---- band 2 · intake: more live data. A fresh CSV of any dataset/ file, or a Slack export,
    // diffed here against the file as the build last read it; Accept files it (uploadSection)
    sec.upload = `<section id="upload">${uploadSection(D.intake || { files: {}, schemas: [], ledger: [], ids: [], rejected: [] })}</section>`;

    // ---- band 3 · orientation: one strip, no rows — a masthead, not a section
    const S = D.stages;
    sec.stages = `<section id="stages" class="masthead">
      <div class="strip">${S.stages.map(s => `<div class="cell"><div class="v">${esc(s.usd_fmt)}</div><div class="n">${s.count === s.unresolved ? plural(s.count, 'unresolved request') : plural(s.count - s.unresolved, 'company') + (s.unresolved ? `<span class="foot"> · ${s.unresolved} unresolved</span>` : '')}</div><div class="l">${esc(s.stage)}</div></div>`).join('')}</div>
      <details class="note"><summary>${plural(S.total.companies, 'company')}${S.total.unresolved ? ` + ${plural(S.total.unresolved, 'unresolved request')} of ${D.on_file} on file` : ''}, ${esc(S.total.usd_fmt)} · point in time, as of ${esc(S.as_of)}. Each company counted once, at its furthest stage, at one $ value · How it is counted</summary>
      <p class="foot">One $ per company: CRM ARR potential where the company has an account (${S.value_source.crm}), else the deal value on its latest request (${S.value_source.deal})${S.value_source.none ? `, ${S.value_source.none} with neither` : ''}, never the sum of its requests. A company sits at the furthest stage any of its requests reached: once a meeting is booked, fresh asks on it do not move it back. ${S.total.unresolved ? `${plural(S.total.unresolved, 'request')} that resolved to no company (${esc(S.total.unresolved_usd_fmt)}) cannot be tied to an account or to each other, so each stands alone at its own deal value. ` : ''}${plural(S.excluded.count - S.excluded.unresolved, 'company')} whose every request is filed <i>Closed - no path</i>${S.excluded.unresolved ? `, and ${plural(S.excluded.unresolved, 'unresolved request')} filed the same,` : ''} (${esc(S.excluded.usd_fmt)}) are not on the strip. "needs data" = no company or no deal value on any request; "to be routed" = live with nobody assigned; "routed" = a connector is assigned or allocated this cycle but not yet asked; "asked" = in <code>intro_outcomes.csv</code> with no intro; "introduced" = intro logged or filed; "meeting booked" = the intro landed a meeting.</p></details></section>`;

    // ---- band 4 · actionable now: ticking a row changes what the queue proposes tomorrow — spends a connector slot
    const T = D.priorities;
    const retries = T.considered_by.reduce((n, b) => n + b.retries, 0);
    const considered = T.considered_by.map(b => `${b.count} ${esc(b.label)}` + (b.retries ? ` (${b.retries === b.count ? (b.count === 1 ? 'a retry' : 'all retries') : `${b.retries} of them retries`})` : '')).join('; ');
    sec.top = `<section id="top"><h2>Top ${T.top.length} Priorities <span class="foot">Do these next: sorted by expected value across ${T.considered} live requests with a connector to act on, of the ${D.cycle_size} in this cycle — ${considered}${retries ? ` · a retry re-asks after a fizzled intro (${plural(retries, 'request')} in all of the ${D.cycle_size})` : ''} · each spends a connector slot</span></h2>`
      + priorityTable(T.top, X, state, 'rank', true)
      + (T.rest.length ? `<details class="rest"><summary><h3>The Rest of the Queue <span class="foot">${plural(T.rest.length, 'more request')} of the ${D.cycle_size} in this cycle, ranked ${T.top.length + 1}–${T.considered} by the same expected value · ${esc(T.rest_value_fmt)}${T.rest_no_slot ? ` · ${T.rest_no_slot} have no slot this cycle` : ''} · Tick here too once an ask goes out</span></h3></summary>`
        + priorityTable(T.rest, X, state, 'rank', true) + `</details>` : '')
      + `<p class="foot">Per connector: ${D.connector_pages.map(c => `<a href="${esc(c.page)}">${esc(c.connector)}</a>`).join(' · ')}. Each tab opens on their own top 5, with the longer list below.</p>`
      + formulaNote(T.formula) + `</section>`;

    // ---- band 5 · current cycle: decisions the allocator already made — read-only
    // one tab per connector with a stake in the cycle (the roster, then the off-roster batch
    // holders): what they are carrying, the drafted message, their batch grouped by company; the
    // Aggregate tab is every batch's companies, biggest first
    // The box on a company row is the ask_sent tick for every live request in the batch there, the same
    // tick as Top Priorities and the connector's page; the Aggregate tab is done-state only
    const A = D.asks;
    const batchTicks = (c, connector) => c.request_ids.map(rid => askTick(X, { request_id: rid, company_id: c.company_id, company_name: c.company_name, connector, target_title: c.wanted.join(', ') }));
    const sent = '<span class="sent foot">ask sent</span>';
    // one heads-up per flagged request in the company's batch row
    const notifyCell = (c, tab) => c.notify.map(n => notifyBlock(n, `notify-${tab}-${n.request_id}`)).join('');
    const companyCell = (c, tag = '') => `<td>${co(c)}${tag ? ` ${tag}` : ''}<br><span class="foot">${esc(c.value_fmt)} · ${esc(c.urgency)} · ${c.request_ids.map(esc).join(', ')}</span>${retryTag(c)}${reopenedTag(c)}</td>`;
    const offRoster = D.connectors.filter(c => !c.on_roster).length;
    sec.connectors = `<section id="connectors">${fold(`This Cycle, by Connector <span class="foot">Cycle ${esc(A.cycle)}: ${A.allocated} requests allocated of the ${A.cycle_size} in this cycle, in ${plural(A.batches.length, 'batch')}, one consolidated ask per connector, from <code>golden_allocation.csv</code> and <code>supply_reach.csv</code> · A tab per connector (${D.connectors.length - offRoster} on the roster${offRoster ? `, ${offRoster} off it` : ''}) with capacity, delivery rate, the drafted message and the batch behind it · The drafted messages are also on <a href="${esc(D.batch_page)}">Batched-Ask</a>${A.notify_count ? ` · ${plural(A.notify_count, 'request')} on a late-stage account someone other than its owner asked for: the owner gets a heads-up, nothing is held` : ''}</span>`)}`
      + tabs('connectors', [...D.connectors.map(c => ({ label: c.connector, n: c.capacity ? `${c.used}/${c.capacity}` : `${c.used}`, c })), { label: 'Aggregate', n: A.allocated, cls: 'agg' }], ({ c }, i) => c
        ? `<p class="lede">${c.on_roster ? `${esc(c.role)} · ${esc(c.type)} · Focus: ${c.focus.map(esc).join(', ')}${c.hard_decline ? ' · <b>declines anything outside</b>' : ''}` : `<b>Not on the roster</b> · ${esc(c.type)} · no stated capacity or focus areas`} · <a href="${esc(c.page)}">Their top 5</a>${c.notes ? `<br><span class="foot">${esc(c.notes)}</span>` : ''}</p>
        <div class="kpis">${capKpi(c)}
          ${rateKpi(c)}
          <div class="kpi ${c.sitting_on.length ? 'warn' : ''}"><div class="v">${c.sitting_on.length}</div><div class="l">already sitting on</div><div class="s">asked, live, no intro yet · <a href="#followups">follow-ups owed</a></div></div>
          <div class="kpi"><div class="v">${c.allocated_this_cycle}</div><div class="l">in this cycle's ask</div><div class="s">${c.companies.length ? `of the ${A.cycle_size} in this cycle · ${plural(c.companies.length, 'company')} · ${esc(c.batch_value_fmt)} · batch <code>${esc(c.batch_id)}</code>` : 'Nothing allocated'}</div></div></div>`
        + composeBlock(c.batch_ask, `ask-${c.slug}`, undefined, A.cycle_size)
        + `<h3>The batch, by company <span class="foot">Tick a company once its ask has gone out: one <i>ask sent</i> per request there, the same tick as <a href="#top">Top Priorities</a> and <a href="${esc(c.page)}">their page</a></span></h3>` + (c.companies.length ? `<table><thead><tr><th></th><th>Company</th><th>Everyone wanted</th><th>Who is waiting</th><th>Path</th><th>Why this connector</th><th>Notify owner</th></tr></thead><tbody>`
          + c.companies.map(x => { const g = batchTicks(x, c.connector); return `<tr class="${groupDone(state, g)}">${groupTick(state, g)}${companyCell(x)}<td>${x.wanted.map(esc).join('<br>')}</td><td>${x.waiting.map(esc).join('<br>')}</td><td>${esc(x.path_type)}${x.contact ? `<br><span class="foot">${esc(x.contact)}</span>` : ''}</td><td class="foot">${esc(x.why)}</td><td>${notifyCell(x, i)}</td></tr>`; }).join('') + `</tbody></table>` : `<p class="empty">Nothing allocated to ${esc(c.connector)} this cycle</p>`)
        : `<p class="foot">Everything going out this cycle · ${plural(A.allocated, 'request')} of the ${A.cycle_size} in this cycle, across ${plural(A.batches.length, 'connector')} · ${esc(A.value_fmt)} · Biggest first; a company listed twice is being asked of two connectors</p>
        <table><thead><tr><th>Company</th><th>Connector</th><th>Everyone wanted</th><th>Who is waiting</th><th>Path</th><th>Notify owner</th></tr></thead><tbody>`
        + A.all.map(x => `<tr ${mirror(state, batchTicks(x, x.connector))}>${companyCell(x, sent)}<td><b>${esc(x.connector)}</b><br><a class="foot" href="${esc(D.batch_page)}#${esc(x.slug)}">The message</a></td><td>${x.wanted.map(esc).join('<br>')}</td><td>${x.waiting.map(esc).join('<br>')}</td><td>${esc(x.path_type)}${x.contact ? `<br><span class="foot">${esc(x.contact)}</span>` : ''}</td><td>${notifyCell(x, 'all')}</td></tr>`).join('')
        + `</tbody></table>`)
      + `</details></section>`;

    // already in the door: the allocator parked these rather than spend a slot
    const I = D.introduced;
    sec.introduced = `<section id="introduced">${fold(`Already Introduced — Extend the Intro <span class="foot">${plural(I.requests, 'request')} of the ${A.cycle_size} in this cycle, on ${plural(I.count, 'company')}, ${esc(I.value_fmt)} · An intro already landed there (meeting booked, or sent within ${I.days} days), so no connector slot is spent</span>`)}
      <p class="lede">The action is with the rep who was introduced, not a connector: they ask the contact they already have for the other names. An intro with no meeting after ${I.days} days counts as fizzled, as does a meeting with no opportunity after ${I.days} days once newer requests are filed on the company, and the company goes back into the queue, flagged <b class="warn">retry intro</b>.</p>`
      + (I.rows.length ? `<table><thead><tr><th>Company</th><th>Everyone wanted</th><th>Who is waiting</th><th>The intro that landed</th><th>Next step</th><th>Fallback path</th></tr></thead><tbody>`
        + I.rows.map(r => `<tr><td>${co(r)}<br><span class="foot">${esc(r.value_fmt)} · ${esc(r.urgency)} · ${esc(r.crm_stage)} · ${r.request_ids.map(esc).join(', ')}</span></td><td>${r.wanted.map(esc).join('<br>')}</td><td>${r.waiting.map(esc).join('<br>')}</td><td><b>${esc(r.intro.connector)}</b> → ${esc(r.intro.requested_by || 'unattributed')}<br><span class="foot">${esc(r.intro.intro_date)} · ${esc(r.intro.request_id)} · ${esc(r.intro.target_title)}${r.intro.meeting_booked ? ' · <b>meeting booked</b>' : ` · ${r.intro.days} days ago, no meeting yet`}</span></td><td><b>${esc(r.owner || 'nobody')}</b><br><span class="foot">${esc(r.action)}</span></td><td class="foot">${esc(r.best_path || 'None in the network')}</td></tr>`).join('')
        + `</tbody></table>` : `<p class="empty">Nothing parked behind a live intro this cycle</p>`)
      + (I.retries.length ? `<h3>Back in the queue as a retry <span class="foot">${plural(I.retry_requests, 'request')} of the ${A.cycle_size} in this cycle, on ${plural(I.retries.length, 'company')} whose last intro fizzled · Nothing to tick here: a row greys out once its asks are ticked under <a href="#connectors">the connector</a> or <a href="#top">Top Priorities</a></span></h3>
        <table><thead><tr><th>Company</th><th>Everyone wanted</th><th>The intro that fizzled</th><th>Asked again this cycle</th></tr></thead><tbody>`
        + I.retries.map(r => `<tr ${mirror(state, batchTicks(r, r.connectors.join(', ')))}><td>${co(r)} ${sent}<br><span class="foot">${esc(r.value_fmt)} · ${r.request_ids.map(esc).join(', ')}</span></td><td>${r.wanted.map(esc).join('<br>')}</td><td>${esc(r.retry.connector)} → ${esc(r.retry.requested_by || 'unattributed')}<br><span class="foot">${esc(r.retry.intro_date)} · ${esc(r.retry.request_id)} · ${esc(r.retry.outcome)}</span></td><td>${r.connectors.map(c => `<b>${esc(c)}</b>`).join(', ')}<br><span class="foot">${r.connectors.includes(r.retry.connector) ? 'Same connector: ask for a second name, or <a href="#followups">nudge the first</a>' : 'Different connector this time'}</span></td></tr>`).join('')
        + `</tbody></table>` : '')
      + `</details></section>`;

    // requests the allocator could not place this cycle, by reason. A request whose connector simply
    // has no slot left is not here: it keeps its connector and its expected value on the ranked list
    const EXCEPTION_TITLE = { 'no path to this company in the network': 'No direct path to this company in the network', 'already introduced': 'Already introduced — extend the intro',
                              'unresolved ask on every path': 'Unresolved ask on every path — nudge or chase, don’t ask afresh',
                              'intro claimed, none logged': 'Repair queue: filed Intro sent, no intro logged' };
    const EXCEPTION_NOTE = { 'no path to this company in the network': 'Not routable this cycle (sourcing issue vs. allocation): the named person is who to ask whether they know anyone. If someone got asked anyway — a roster connector whose path is not on file, or someone off the roster who offered — pick who and the row is ticked as an ask sent to them: after the next rebuild it leaves here, sits under that name as a follow-up owed, and counts against a roster connector’s capacity even past their stated number (flagged on their tab). Nobody’s path is added to the network by it.',
                             'unresolved ask on every path': 'Everyone who reaches the company is sitting on an ask there: agreed and sent no intro (nudge), or not yet answered (chase). Nobody is asked again until it resolves or, unanswered, ages past the window.',
                             'intro claimed, none logged': `The request says an intro went out; intro_outcomes.csv has no row for it. Not routed, so nobody is asked around an intro that may have happened off the log. The requester or account owner logs who introduced and when, or corrects the status; a row still here ${A.repair_days} days after it was first flagged goes to the allocator as Stalled and is routed like any other request (marked reopened).` };
    const parked = A.exceptions.find(e => e.reason === 'already introduced'), Fo = A.focus;
    sec.exceptions = `<section id="exceptions">${fold(`Unrouted Exceptions <span class="foot">${plural(A.exception_count, 'request')} of the ${A.cycle_size} in this cycle not allocated, grouped by the same state Live Data uses: ${A.exceptions.map(e => `${e.count} ${esc((EXCEPTION_TITLE[e.reason] || e.reason).replace(' to this company in the network', '').toLowerCase())}`).join(', ')} · From <code>golden_allocation.csv</code>${A.no_slot ? ` · ${A.no_slot} more wait only for a slot and stay on the <a href="#top">ranked list</a>` : ''}</span>`)}
      <p class="lede">In-focus asks convert at <b>${esc(Fo.in_focus_pct)}</b> versus ${esc(Fo.out_focus_pct)} outside, yet only ${Fo.in_focus_asks} of ${Fo.total_asks} asks landed in focus; <i>who covers this sector</i> names the roster connector whose focus areas include the company's industry, and whether they were ever asked about it.${parked ? ` ${plural(parked.count, 'request')} · ${esc(parked.value_fmt)} parked behind a live intro → <a href="#introduced">Already Introduced</a>, not repeated here.` : ''}</p>`;
    const routedHere = r => r.routed_here && r.routed_here.length
      ? `<br><span class="foot" title="another request on this account was routed this cycle: that connector can be asked for this name too">Also this cycle: ${r.routed_here.map(x => `${esc(x.request_id)} → ${esc(x.connector)}`).join(', ')}</span>` : '';
    const cover = sc => !sc ? '<span class="foot">No company, so no industry</span>' : sc.connectors.length
      ? sc.connectors.map(c => `<b>${esc(c.connector)}</b> <span class="foot">${c.asked ? `asked ${esc(c.asked)}` : 'never asked'}</span>`).join('<br>')
      : `<span class="foot">${esc(sc.note)}</span>`;
    for (const e of A.exceptions) {
      if (e === parked) continue;
      const unresolved = e.reason.startsWith('company'), noPath = e.reason.startsWith('no path'), blocked = e.rows.some(r => r.blocked_reason);
      const names = r => [...new Set([...(r.routed_here || []).map(x => x.connector), ...(r.sector_cover && r.sector_cover.connectors || []).map(x => x.connector), ...A.roster])];
      const note = r => r.detail || r.best_path || (unresolved ? r.company_as_written || '(nothing parseable)' : '');
      const withNote = e.rows.some(note);
      sec.exceptions += `<h3>${esc(EXCEPTION_TITLE[e.reason] || cap1(e.reason))} <span class="foot">${e.count} of the ${A.cycle_size} in this cycle · ${esc(e.value_fmt)}</span></h3>${EXCEPTION_NOTE[e.reason] ? `<p class="foot">${esc(EXCEPTION_NOTE[e.reason])}</p>` : ''}<table><thead><tr>${noPath ? '<th>Asked anyway · by whom</th>' : ''}<th>Request</th><th>Company</th>${unresolved ? '' : '<th>CRM stage</th>'}<th>Wanted</th><th>Who</th><th>Value</th><th>Urgency</th><th>Status</th>${blocked ? '<th>Blocked on</th>' : ''}<th>Who covers this sector</th>${withNote ? `<th>${unresolved ? 'As written' : 'Note'}</th>` : ''}</tr></thead><tbody>`
        + e.rows.map(r => `<tr${noPath ? ` class="${doneClass(state, askTick(X, r))}"` : ''}>${noPath ? pickTick(state, askTick(X, { ...r, connector: '' }), names(r)) : ''}<td class="rid">${esc(r.request_id)}</td><td>${co(r)}${routedHere(r)}</td>${unresolved ? '' : `<td>${esc(r.crm_stage)}</td>`}<td>${esc(r.target_title)}</td><td>${esc(r.requested_by)}</td><td>${esc(r.value_fmt)}</td><td>${esc(r.urgency)}</td><td>${esc(r.status)}${reopenedTag(r)}</td>${blocked ? `<td>${esc(r.blocked_reason)}</td>` : ''}<td>${cover(r.sector_cover)}</td>${withNote ? `<td class="foot">${esc(note(r))}</td>` : ''}</tr>`).join('')
        + `</tbody></table>`;
    }
    sec.exceptions += `</details></section>`;

    // no slot spent: every ask anyone is sitting on, oldest first, then the same per connector.
    // A nudge where they agreed and sent no intro, a chase where they never answered
    const Fu = D.followups;
    sec.followups = `<section id="followups">${fold(`Follow-Ups Owed <span class="foot">${plural(Fu.count, 'ask')} made, live and with no intro yet: ${Fu.nudge} to nudge, ${Fu.chase} to chase, across ${plural(Fu.by_connector.length, 'connector')} · <code>intro_outcomes.csv</code></span>`)}
      <p class="lede">A <b>nudge</b> where the connector said yes and never sent the intro; a <b>chase</b> where they never answered. Asking again would spend a fresh slot for an answer you already have or are still owed, so while a row stands the connector is not routed a new ask at that company. Tick the row once you have nudged or chased; it comes back after ${Fu.quiet_days} quiet days.</p>`
      + tabs('followups', [{ label: 'All connectors', n: Fu.count, rows: Fu.rows, all: true, note: `${plural(Fu.count, 'ask')} · Oldest ask first` }]
          .concat(Fu.by_connector.map(c => ({ label: c.connector, n: c.count, rows: c.rows, note: `${c.nudge} to nudge, ${c.chase} to chase${c.on_roster ? '' : ' · off roster'} · <a href="${esc(c.page)}">Their page</a>` }))),
        t => `<p class="foot">${t.note}</p>` + sittingTable(t.rows, Fu.quiet_days, X, state, !!t.all))
      + `</details></section>`;

    // ---- band 6 · other: admin that fits none of the bands above
    const C = D.crm;
    sec.crm = `<section id="crm">${fold(`CRM Updates <span class="foot">${C.groups.map(g => `${g.count} ${esc(g.group)}`).join(' · ')}</span>`)}
      <div class="dl"><button id="lp-dl-import">Download ${esc(C.import.filename)}</button><span>${plural(C.import.count, 'account')} to create, importer-shaped columns only (<code>${C.import.columns.map(esc).join(', ')}</code>). It can be uploaded straight into the CRM.</span></div>
      <div class="dl"><button id="lp-dl-review" class="secondary">Download ${esc(C.review.filename)}</button><span>${plural(C.review.count, 'recommendation')} (${C.review.groups.map(g => `${g.count} ${esc(g.group)}`).join(', ')}), every row <code>status = ${esc(C.status)}</code>. Merges and owner conflicts are recommended, never executed, because ownership is compensation.</span></div>`;
    for (const g of C.groups) {
      sec.crm += `<h3>${esc(g.title)} <span class="foot">${g.count} · ${esc(g.value_fmt)}</span></h3>`;
      sec.crm += g.rows.length ? `<table><thead><tr><th>Company</th><th>CRM accounts</th><th>Owner</th><th>Stage</th><th>Action</th><th>Why</th><th class="num">At stake</th></tr></thead><tbody>`
        + g.rows.map(r => `<tr><td>${co(r)}<br><span class="foot">${r.request_ids.map(esc).join(', ')}</span></td><td class="rid">${esc(r.crm_account_ids || 'None')}</td><td>${esc(r.owner || 'Nobody')}</td><td>${esc(r.stage || 'None')}</td><td><b>${esc(r.action)}</b></td><td class="foot">${esc(r.why)}<br>${esc(r.evidence)}</td><td class="num">${esc(r.value_fmt)}</td></tr>`).join('') + `</tbody></table>`
        : `<p class="empty">Nothing to do</p>`;
    }
    sec.crm += `</details></section>`;

    // ---- assemble: six titled bands
    let out = `<p class="stamp" id="lp-stamp">As of <b>${esc(D.as_of)}</b></p>`;
    D.bands.forEach(b => {
      out += `<div class="band" id="band-${esc(b.id)}"><div class="band-h"><span class="t">${esc(b.title)}</span></div>`
        + b.sections.map(id => sec[id]).join('') + `</div>`;
    });

    root.innerHTML = out + submitBar(X);
    openFoldAt(root);
    window.addEventListener('hashchange', () => openFoldAt(root));

    // wiring: ticks + Submit, build stamp, sub-tabs, downloads, intake
    wireCompletions(root, X, state, Object.fromEntries(D.connectors.map(c => [c.connector, c])));
    wireCopy(root);
    buildStamp(D, root.querySelector('#lp-stamp'));
    wireTabs(root);
    root.querySelector('#lp-dl-import').onclick = () => download(C.import.filename, C.import.csv);
    root.querySelector('#lp-dl-review').onclick = () => download(C.review.filename, C.review.csv);

    // one intake: pasted text that is .jsonl is many threads, a CSV with the intro_requests.csv header is many
    // requests, anything else is one thread; a dropped file is read the same way
    const ta = root.querySelector('#lp-route-text'), drop = root.querySelector('#lp-drop'), file = root.querySelector('#lp-file'), prev = root.querySelector('#lp-preview');
    const intake = (text, filename) => {
      text = (text || '').trim();
      if (!text) { prev.innerHTML = ''; return; }
      const csv = looksLikeRequestsCsv(text, filename), jsonl = !csv && text.startsWith('{');
      const threads = csv ? requestsToThreads(text) : jsonl ? text : JSON.stringify({ request_id: 'pasted', messages: [{ ts: new Date().toISOString(), user: '', text }] });
      renderPreview(previewThreads(threads, P), filename || '', P, prev, !jsonl && !csv, csv);
    };
    const go = () => intake(ta.value, '');
    const handle = f => { if (f) f.text().then(text => { ta.value = ''; intake(text, f.name); }); };
    root.querySelector('#lp-route-go').onclick = go;
    ta.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) go(); });
    root.querySelectorAll('#route .presets button').forEach(b => b.onclick = () => { ta.value = P.route_presets[+b.dataset.i].text; go(); });
    drop.addEventListener('click', e => { if (e.target !== file) file.click(); });
    file.addEventListener('change', () => handle(file.files[0]));
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', e => handle(e.dataTransfer.files[0]));
    wireUpload(root, D.intake || { files: {}, schemas: [], ledger: [], ids: [], rejected: [] });
  }

  // ------------------------------------------------ Intake: Add More Live Data
  const UPLOAD_TYPES = '.csv,.json,.jsonl,.txt';
  function uploadSection(U) {
    const names = Object.keys(U.files).sort();
    const led = U.ledger.slice().reverse(), rej = U.rejected || [], live = activeUploads(U.ledger);
    const lastRevert = U.ledger.map(r => r.target).lastIndexOf(REVERT);
    const ledgerRows = led.length ? `<table><thead><tr><th>Received</th><th>By</th><th>File</th><th>Applied to</th><th class="num">Rows</th><th class="num">New</th><th class="num">Updated</th><th>New columns</th><th>Note</th></tr></thead><tbody>`
      + led.map((r, j) => r.target === REVERT
        ? `<tr class="revert"><td class="date">${esc(utc(r.received_at))}</td><td>${esc(r.received_by)}</td><td colspan="6"><b>Reverted to the September export</b> <span class="foot">every upload above this line was set aside · ${esc(r.upload_id)}</span></td><td class="foot">${esc(r.note)}</td></tr>`
        : `<tr class="${led.length - 1 - j < lastRevert ? 'reverted' : ''}"><td class="date">${esc(utc(r.received_at))}</td><td>${esc(r.received_by)}</td><td><code>${esc(r.filename || r.upload_id)}</code><br><span class="foot">${esc(r.upload_id)}</span></td><td><code>${esc(r.target)}</code></td><td class="num">${esc(r.rows)}</td><td class="num">${esc(r.new_rows)}</td><td class="num">${esc(r.changed_rows)}</td><td class="foot">${esc((r.new_columns || '').split(';').filter(Boolean).join(', ') || '—')}</td><td class="foot">${esc(r.note)}</td></tr>`).join('')
      + `</tbody></table>` : `<p class="empty">Nothing accepted yet: every file is the September export as filed</p>`;
    const revert = `<div class="dl" id="lp-up-revert-box"><button id="lp-up-revert" class="secondary" ${live.length ? '' : 'disabled'}>Revert to Sep Raw Data State</button><span>${live.length
      ? `Sets aside ${plural(live.length, 'accepted upload')}: the next rebuild reads <code>dataset/</code> exactly as exported, on every tab. Nothing is deleted - the uploads stay listed below, and files accepted after the revert apply again.`
      : 'Nothing to revert: every file is the September export as filed.'}</span></div>`;
    const rejected = rej.length ? `<h3>Set aside by the build <span class="foot">${plural(rej.length, 'upload')} that could not be applied · <code>intake/rejected.csv</code></span></h3><table><thead><tr><th>Received</th><th>By</th><th>File</th><th>Applied to</th><th>Problem</th></tr></thead><tbody>`
      + rej.map(r => `<tr><td class="date">${esc(utc(r.received_at))}</td><td>${esc(r.received_by)}</td><td><code>${esc(r.filename || r.upload_id)}</code></td><td><code>${esc(r.target)}</code></td><td class="warn">${esc(r.problem)}</td></tr>`).join('') + `</tbody></table>` : '';
    return `<h2>Add Live Data <span class="foot">Drop a fresh CSV of any file in <code>dataset/</code>, or a Slack export (<code>.json</code> / <code>.jsonl</code>); see what it adds and what it overrides; Accept to file it</span></h2>
      <p class="lede">Net-new rows or a fuller version of a file on record, either way: the upload is diffed here, in the browser, against the file as the last build read it (${names.length ? names.map(n => `<code>${esc(n)}</code>`).join(', ') : 'nothing on file'}). Rows are matched on the file's key (<code>request_id</code>, <code>account_id</code>, <code>name</code>, …): a key not on file is a new row; one on file is an update, and every value it would override is listed below before anything happens. Columns the file lacks are added. Nothing is written until you click Accept, and <code>dataset/</code> is never written: accepted files go to <code>${esc(U.path || 'intake/')}</code>, the next rebuild layers them on, and every tab reads the result.</p>
      <div class="drop" id="lp-up-drop"><input type="file" id="lp-up-file" accept="${UPLOAD_TYPES}"><span>Drop a .csv, .json or .jsonl here, or click to choose</span></div>
      <div id="lp-up-preview"></div>
      ${revert}
      <details class="fold" id="lp-up-ledger"><summary><h3>Accepted so far <span class="foot">${plural(live.length, 'upload')} applied on top of the export${U.ledger.length - live.length ? ` · ${plural(U.ledger.length - live.length - (U.generation || 0), 'earlier upload')} reverted` : ''}${U.ledger.length ? `, newest first · <code>${esc(U.path)}</code>` : ''}</span></h3></summary>${ledgerRows}${rejected}</details>`;
  }

  // the KPI strip + override list + sample rows for one upload, as previewUpload summarised it
  function renderUploadSummary(s, filename, targets, target, why, U, pending) {
    const sel = `<select id="lp-up-target" aria-label="the file this upload updates">${targets.map(t => `<option value="${esc(t)}" ${t === target ? 'selected' : ''}>${esc(t)}${U.files[t] ? '' : ' (new file)'}</option>`).join('')}</select>`;
    let out = `<div class="upload-head"><b>${esc(filename)}</b> → applies to ${sel} <span class="foot">${esc(why)}</span></div>`;
    if (s.error) return out + `<div class="finding warn"><b>Cannot be applied</b>${esc(s.error)}</div>`;
    const cells = s.changes.length;
    out += `<div class="kpis"><div class="kpi"><div class="v">${s.rows}</div><div class="l">${s.format === 'jsonl' ? 'threads' : 'rows'} in the upload</div><div class="s">${s.duplicate_keys ? `<b class="warn">${plural(s.duplicate_keys, 'key')} repeated within the file: the last row wins</b>` : `each ${esc(s.keys.join(' + '))} once`}</div></div>
      <div class="kpi"><div class="v">${s.new_rows}</div><div class="l">new ${s.format === 'jsonl' ? 'threads' : 'rows'}</div><div class="s">${s.new_file ? 'a new file: every row is new' : 'keys not on file, appended'}</div></div>
      ${s.format === 'jsonl' ? `<div class="kpi"><div class="v">${s.extended_threads}</div><div class="l">threads extended</div><div class="s">${plural(s.new_messages, 'new message')} appended to threads on file</div></div>` : ''}
      <div class="kpi ${cells ? 'warn' : ''}"><div class="v">${s.changed_rows}</div><div class="l">${s.format === 'jsonl' ? 'threads' : 'rows'} with values overridden</div><div class="s">${cells ? `${plural(cells, 'value')} on file replaced, listed below` : 'nothing on file changes'}</div></div>
      <div class="kpi"><div class="v">${s.unchanged_rows}</div><div class="l">unchanged</div><div class="s">on file already, nothing new in them</div></div>
      <div class="kpi ${s.new_columns.length ? 'warn' : ''}"><div class="v">${s.new_columns.length}</div><div class="l">new columns</div><div class="s">${s.new_columns.length ? esc(s.new_columns.join(', ')) + ' · added after the existing ones, blank on rows that lack them' : 'the header matches the file'}</div></div></div>`;
    if (pending) out += `<div class="finding"><b>Already accepted</b>This exact file is ${pending === 'file' ? 'already applied in the build' : 'accepted and waiting for the next rebuild'}; accepting it again changes nothing.</div>`;
    const SHOW = 200;
    if (cells) out += `<h3>Values the upload would override <span class="foot">${plural(cells, 'cell')} on ${plural(s.changed_rows, s.format === 'jsonl' ? 'thread' : 'row')}${cells > SHOW ? ` · the first ${SHOW}` : ''} · an empty cell in the upload never overrides</span></h3>
      <table class="changes"><thead><tr><th>${esc(s.keys.join(' / '))}</th><th>Column</th><th>On file</th><th>Upload</th></tr></thead><tbody>${s.changes.slice(0, SHOW).map(c => `<tr><td class="rid">${esc(c.key)}</td><td><code>${esc(c.column)}</code></td><td class="from">${esc(c.from) || '<i>empty</i>'}</td><td class="to">${esc(c.to)}</td></tr>`).join('')}</tbody></table>`;
    if (s.sample.length) {
      const cols = s.format === 'jsonl' ? ['request_id', 'channel', 'posted', 'user', 'text', 'replies'] : s.columns.filter(c => s.sample.some(r => (r[c] || '').trim()));
      out += `<h3>New ${s.format === 'jsonl' ? 'threads' : 'rows'} <span class="foot">${s.new_rows > s.sample.length ? `the first ${s.sample.length} of ${s.new_rows}` : plural(s.new_rows, 'row')}${s.format === 'jsonl' ? ' · a request_id not in intro_requests.csv becomes a request when the build runs' : ''}</span></h3>
        <table class="sample"><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${s.sample.map(r => `<tr>${cols.map(c => `<td>${esc(r[c])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
    }
    return out;
  }

  function wireUpload(root, U) {
    const drop = root.querySelector('#lp-up-drop'), file = root.querySelector('#lp-up-file'), box = root.querySelector('#lp-up-preview');
    if (!drop) return;
    const onFile = new Set(U.ids || []);
    // accepted from this browser, not yet rebuilt into the site; dropped once the build has the id
    const pending = new Map(Object.entries(load('lp-uploads', {})).filter(([id]) => !onFile.has(id)));
    store('lp-uploads', Object.fromEntries(pending));
    // reverts so far, counting one posted from this browser and not yet rebuilt in: what the next upload_id carries
    const generation = () => (U.generation || 0) + [...pending.values()].filter(p => p.target === REVERT).length;
    let cur = null;  // { filename, text, columns|null, target, why, summary }
    const targetsFor = (columns, guess) => {
      const names = Object.keys(U.files).filter(n => columns === null ? formatOf(n) === 'jsonl' : formatOf(n) === 'csv').sort();
      if (guess && !names.includes(guess)) names.push(guess);
      return names;
    };
    const render = () => {
      const id = uploadId(cur.target, cur.text, generation());
      const state = onFile.has(id) ? 'file' : pending.has(id) ? 'pending' : '';
      let s;
      try { s = previewUpload(U, cur.target, cur.text); } catch (e) { s = { error: e.message }; }
      cur.summary = s;
      const ok = !s.error, canPost = !!(U.supabase_url && U.anon_key);
      const foot = !ok ? '' : canPost
        ? `Files it in the <code>${esc(U.table)}</code> table as <code>${esc(id)}</code>; the site rebuilds from it within a few minutes and every tab reads the new data. <code>dataset/</code> stays as it is.`
        : `<b class="warn">This build cannot post: no Supabase URL / anon key.</b> Accept downloads the file as <code>${esc(id)}.${formatOf(cur.target)}</code>; from the repo root:<br><code>${esc(U.command.replace('{file}', `${id}.${formatOf(cur.target)}`).replace('{target}', cur.target).replace('{who}', load('lp-who', '') || 'me'))}</code>`;
      box.innerHTML = renderUploadSummary(s, cur.filename, targetsFor(cur.columns, cur.target), cur.target, cur.why, U, state)
        + `<div class="dl" id="lp-up-actions">${ok ? '<button id="lp-up-accept">Accept</button>' : ''}<button id="lp-up-discard" class="secondary">Discard</button><span>${ok ? foot : 'Fix the file, or pick another target above, and drop it again.'}</span></div>`;
      box.querySelector('#lp-up-target').onchange = e => { cur.target = e.target.value; cur.why = 'chosen'; render(); };
      box.querySelector('#lp-up-discard').onclick = () => { cur = null; box.innerHTML = ''; file.value = ''; };
      if (ok) box.querySelector('#lp-up-accept').onclick = accept;
    };
    const accept = async () => {
      if (!cur || cur.summary.error) return;
      const who = load('lp-who', '') || askWho();
      if (!who) return;
      const at = new Date().toISOString(), row = uploadRow(cur.target, cur.filename, cur.text, cur.summary, who, at, '', generation());
      const actions = box.querySelector('#lp-up-actions'), note = actions.querySelector('span'), go = actions.querySelector('#lp-up-accept');
      if (!(U.supabase_url && U.anon_key)) {
        download(`${row.upload_id}.${formatOf(cur.target)}`, row.content);
        note.innerHTML = `<b>Downloaded ${esc(row.upload_id)}.${formatOf(cur.target)}</b>. Nothing is filed until it is added from the repo root:<br><code>${esc(U.command.replace('{file}', `${row.upload_id}.${formatOf(cur.target)}`).replace('{target}', cur.target).replace('{who}', who))}</code>`;
        return;
      }
      go.disabled = true; note.innerHTML = 'Filing…';
      let got;
      try { got = await postUpload(U, row); } catch (e) {
        go.disabled = false; actions.classList.add('failed');
        note.innerHTML = `<b class="warn">Not filed.</b> ${esc(e.message)}. Try Accept again, or if Supabase is down, download the file and add it by hand: <a href="#" id="lp-up-dl">download</a>.`;
        note.querySelector('#lp-up-dl').onclick = ev => { ev.preventDefault(); download(`${row.upload_id}.${formatOf(cur.target)}`, row.content); };
        return;
      }
      pending.set(row.upload_id, { target: row.target, filename: row.filename, at }); store('lp-uploads', Object.fromEntries(pending));
      actions.classList.remove('failed');
      note.innerHTML = got.already ? `<b>Already filed</b> as <code>${esc(row.upload_id)}</code>: this exact file was accepted before; nothing new was written.`
        : `<b>Accepted</b> as ${esc(who)}: <code>${esc(row.upload_id)}</code> → <code>${esc(row.target)}</code>, ${plural(row.new_rows, 'new row')}, ${plural(row.changed_rows, 'row')} updated${cur.summary.new_columns.length ? `, ${plural(cur.summary.new_columns.length, 'new column')}` : ''}. The site rebuilds from the table within a few minutes; refresh after that and every tab reads it.`;
    };
    const take = (text, filename) => {
      let columns = null;
      if (!/\.jsonl?$/i.test(filename) && !text.replace(/^\uFEFF/, '').trim().startsWith('{') && !text.replace(/^\uFEFF/, '').trim().startsWith('[')) {
        try { columns = parseCsv(text).columns; } catch (e) { columns = []; }
      }
      const [target, why] = guessTarget(filename, columns, Object.fromEntries(Object.entries(U.files).map(([n, f]) => [n, f.columns || []])), U.schemas);
      const names = targetsFor(columns, target);
      cur = { filename, text, columns, target: target || names[0] || '', why: target ? why : `${why}; pick the file it updates` };
      if (!cur.target) { box.innerHTML = `<div class="finding warn"><b>Cannot be applied</b>${esc(why)}</div>`; return; }
      render();
    };
    const handle = f => { if (f) f.text().then(text => take(text, f.name)); };
    const revertBox = root.querySelector('#lp-up-revert-box'), revertGo = revertBox.querySelector('#lp-up-revert'), revertNote = revertBox.querySelector('span');
    revertGo.onclick = async () => {
      const live = activeUploads(U.ledger);
      if (!live.length) return;
      if (!window.confirm(`Revert to the September export? ${plural(live.length, 'accepted upload')} will no longer apply after the next rebuild (they stay in the ledger; nothing is deleted).`)) return;
      const who = load('lp-who', '') || askWho();
      if (!who) return;
      const at = new Date().toISOString(), row = revertRow(who, at);
      const cmd = esc(U.revert_command.replace('{who}', who));
      if (!(U.supabase_url && U.anon_key)) {
        revertNote.innerHTML = `<b class="warn">This build cannot post: no Supabase URL / anon key.</b> From the repo root:<br><code>${cmd}</code>`;
        return;
      }
      revertGo.disabled = true; revertNote.innerHTML = 'Filing…';
      let got;
      try { got = await postUpload(U, row); } catch (e) {
        revertGo.disabled = false; revertBox.classList.add('failed');
        revertNote.innerHTML = `<b class="warn">Not filed.</b> ${esc(e.message)}. Try again, or if Supabase is down, from the repo root:<br><code>${cmd}</code>`;
        return;
      }
      pending.set(row.upload_id, { target: REVERT, filename: '', at }); store('lp-uploads', Object.fromEntries(pending));
      revertBox.classList.remove('failed');
      revertNote.innerHTML = got.already ? `<b>Already filed</b> as <code>${esc(row.upload_id)}</code>.`
        : `<b>Reverted</b> as ${esc(who)}: <code>${esc(row.upload_id)}</code>. The site rebuilds within a few minutes; after that every tab reads <code>dataset/</code> as exported, and anything accepted from now on applies on top of it.`;
      if (cur) render();
    };
    drop.addEventListener('click', e => { if (e.target !== file) file.click(); });
    file.addEventListener('change', () => handle(file.files[0]));
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', e => handle(e.dataTransfer.files[0]));
  }

  function renderRoute(x, P) {
    const T = x.target, C = x.company;
    const hover = (o, keys) => keys.map(k => `${k.replace(/_/g, ' ')} ${o[k]}`).join(' × ');
    const cue = m => `<span class="cue">“${esc(m.cue)}” ${m.score > 0 ? '+' : ''}${m.score}</span>`;
    const row = (dt, dd, cls) => `<dt>${dt}</dt><dd${cls ? ` class="${cls}"` : ''}>${dd}</dd>`;
    let target, account, priority;
    if (!T) target = `<i>None</i> <span class="foot">${esc(x.note)}</span>`;
    else if (x.status === 'refused') target = `<i>Refused</i>: “${esc(T.text)}” ${cue(T)}<br><span class="foot">${x.candidates.map(c => c.kind === 'company' && c.ref ? `${co(c.ref)} <span class="foot">(customer, ${esc(c.id)})</span>` : `${esc(c.name)} <span class="foot">(${esc(c.kind)}, ${esc(c.id)})</span>`).join(' · or · ')}</span>`;
    else if (x.status === 'fund') target = `${esc(T.name)} <span class="foot">(an investor fund rather than a customer)</span> ${cue(T)}`;
    else if (!C) target = `${esc(T.text)} <span class="foot">(new to the build)</span> ${cue(T)}`;
    else if (C.network) target = `${esc(C.company_name)} <span class="foot">Not on file, known to the network${T.is_domain || T.text !== C.company_name ? ` from “${esc(T.text)}”` : ''}</span> ${cue(T)}`;
    else target = `${co(C)} <span class="foot">${esc(C.company_id)} · ${C.crm ? `${esc(T.method)} ${T.confidence.toFixed(2)}` : 'On file, no CRM account'}${T.is_domain || T.text !== C.company_name ? ` from “${esc(T.text)}”` : ''}</span> ${cue(T)}`;
    if (!C) account = x.status === 'refused' ? `<i>${x.candidates.filter(c => c.kind === 'company').length ? 'Two records answer to this name' : 'None'}</i>` : `<b class="warn">No CRM record</b>`;
    else if (C.network) account = `<b class="warn">No CRM record</b> <span class="foot">The company is in the network's connections but on nobody's file; create the account (see CRM Updates)</span>`;
    else if (!C.crm) account = `<b class="warn">No CRM record</b> <span class="foot">The company is on file from earlier asks; create the account (see CRM Updates)</span>`;
    else account = `${esc(C.stage)} · ${esc(C.industry || 'no industry')} · ${esc(C.owner || 'nobody')} · ${C.arr_fmt ? esc(C.arr_fmt) + ' ARR potential' : 'no ARR potential on file'}${C.stage === 'Closed Lost' ? ' · <b class="warn">Closed Lost: reopen it or close the request</b>' : ''}`;
    const others = x.others.length
      ? x.others.map(o => `<b>${esc(o.text)}</b> <span class="foot">${o.name && o.name !== o.text ? `(${esc(o.name)}) ` : ''}${esc(o.why)}</span>`).join('<br>')
      : `<span class="foot">No other company is named</span>`;
    if (x.priority) {
      const p = x.priority;
      const req = `<span class="c" title="${esc(hover(p.components, ['deal_value_musd', 'stage_weight', 'age', 'reps_waiting']))}; deal value is ${esc(p.deal_source)}; age 1.0 = posted today">request priority ${p.request_priority.toFixed(3)}</span>`;
      if (!x.top) priority = `${req} <span class="foot">× No connector score: nobody reaches ${esc(C.company_name)}, so nothing to rank</span>`;
      else priority = `<span class="ev" title="expected value = request priority × connector score">${p.expected_value.toFixed(3)}</span> = ${req} × <span class="c" title="${esc(hover(p.connector_components, ['path_strength', 'focus_fit', 'delivery_rate', 'capacity_left']))}">connector score ${p.connector_score.toFixed(3)}</span>${x.top.capacity_left <= 0 ? ` <span class="foot"><b class="warn">Zero: ${esc(x.top.connector)} has no slot left this cycle</b>; ${(p.request_priority * x.top.score).toFixed(3)} the moment one frees</span>` : ''}`;
    } else priority = `<span class="foot">Not scored${x.status === 'no-target' || x.status === 'refused' ? '' : ': nothing to route'}</span>`;
    let out = `<dl class="route parts">${row('Target', target, 'key')}${row('Account', account)}${row('Title', x.title ? esc(x.title) : '<span class="foot">None named</span>')}${row('Not the target', others)}${row('Priority', priority)}</dl>`;
    if (x.note) out += `<div class="route-note${x.status === 'routed' ? ' ok' : ''}">${esc(x.note)}</div>`;
    if (x.paths.length) {
      const shown = C && C.path_count > x.paths.length ? ` · the best ${x.paths.length} of ${C.path_count}` : '';
      const heldNote = x.paths.some(p => p.hold) ? '; a connector sitting on an unresolved ask here is skipped (nudge or chase them), or ranked last once it is older than the window' : '';
      out += `<h3>Ranked connectors <span class="foot">Best first: path strength × focus fit × delivery rate, as <code>build_golden.py</code> scores them${heldNote}${shown}</span></h3>
        <table><thead><tr><th>#</th><th>Connector</th><th>Path</th><th class="num">Score</th><th>Why</th></tr></thead><tbody>`
        + x.paths.map((p, i) => `<tr class="${p.score > 0 && p.askable ? '' : 'foot'}"><td class="order">${i + 1}</td><td><b>${esc(p.connector)}</b>${p.on_roster ? '' : '<br><span class="foot">not on the roster</span>'}</td><td class="path">${esc(p.reach_type)}${p.contact ? `<br><span class="foot">${esc(p.contact)}</span>` : ''}</td><td class="num"><span class="c" title="${p.strength} strength × ${p.fit} fit × ${p.rate} delivery rate">${p.score.toFixed(3)}</span></td><td class="foot">${esc(p.reason)}${p.score <= 0 ? '; <b>would not be routed</b>' : p.askable ? '' : '; <b>not asked again here</b>'}</td></tr>`).join('')
        + `</tbody></table>`;
    } else if (C) out += `<p class="empty">No path on the roster</p>`;
    return out;
  }

  // one row per thread; a row opens on what the router would do with its first message (renderRoute),
  // rendered on click. `open` opens the first row at once: a single pasted message
  // `csv` = the rows came from a CSV of requests rather than threads: request rows carry a title, urgency and
  // deal value, and are filed under Add Live Data as intro_requests.csv rather than with the threads command
  function renderPreview(pv, filename, P, el, open, csv = false) {
    const flagged = pv.rows.filter(r => r.flags.length).length, offers = pv.rows.filter(r => r.offers.length).length;
    const name = (filename || (csv ? 'requests.csv' : 'threads.jsonl')).replace(/\.[^.]+$/, '');
    const money = r => !r.deal_value ? '' : isNaN(+r.deal_value) ? r.deal_value : (+r.deal_value).toLocaleString('en-US', r.currency ? { style: 'currency', currency: r.currency, maximumFractionDigits: 0 } : {});
    const reqFoot = r => csv ? `<br><span class="foot">${[r.target_title, r.urgency, money(r)].filter(Boolean).map(esc).join(' · ') || 'no title, urgency or deal value'}</span>` : '';
    let out = `<div class="kpis"><div class="kpi"><div class="v">${pv.count}</div><div class="l">${csv ? 'requests' : 'threads'}</div><div class="s">${pv.rows.filter(r => r.filed).length} already filed</div></div>
      <div class="kpi"><div class="v">${pv.rows.filter(r => r.company_id).length}</div><div class="l">resolved to a company</div><div class="s">${pv.rows.filter(r => !r.filed && !r.company_id).length} not</div></div>
      <div class="kpi"><div class="v">${offers}</div><div class="l">with an offer in the replies</div></div>
      <div class="kpi ${flagged ? 'warn' : ''}"><div class="v">${flagged}</div><div class="l">need a human</div></div></div>`;
    // hover on a name: how its expected value was reached, factor by factor, from the payload's numbers
    const f2 = v => (+v).toFixed(2), f3 = v => (+v).toFixed(3);
    const workings = (r, who) => {
      const c = r.cands.find(x => x.who === who), p = r.priority;
      if (!c || !p) return '';
      const q = p.components, k = c.components;
      return [`expected value ${f3(c.expected_value)} = request priority ${f3(p.request_priority)} × connector score ${f3(c.connector_score)}`,
              `request priority ${f3(p.request_priority)} = deal $M ${f2(q.deal_value_musd)} × stage ${f2(q.stage_weight)} × age ${f2(q.age)} × reps ${q.reps_waiting} (deal value is ${p.deal_source}; age 1.0 = posted today)`,
              `connector score ${f3(c.connector_score)} = path ${f2(k.path_strength)} (${c.label}) × fit ${f2(k.focus_fit)} × rate ${f2(k.delivery_rate)} × capacity ${f2(k.capacity_left)}`,
              k.capacity_left <= 0 ? `zero: ${who} has no slot left this cycle; ${f3(c.if_slot)} the moment one frees` : '',
              r.cands.length > 1 ? `ranked by path × fit × rate: ${r.cands.map(x => `${x.who} ${f3(x.score)}${x.hold === 'last' ? ' (ranked last: unanswered ask here past the window)' : ''}`).join(' > ')}` : '',
              r.held && r.held.length ? `not asked again here: ${r.held.join('; ')}` : ''].filter(Boolean).join('\n');
    };
    const named = (r, who) => `<b class="c" title="${esc(workings(r, who))}">${esc(who)}</b>`;
    if (pv.errors.length) out += `<div class="finding warn"><b>${plural(pv.errors.length, 'line')} skipped</b>${pv.errors.slice(0, 5).map(esc).join('<br>')}</div>`;
    out += `<div class="dl"><button id="lp-dl-preview">Export preview CSV</button><span>Nothing has been written. To apply it for real, ${csv
      ? `drop the same file under <a href="#upload">Add Live Data</a> as <code>intro_requests.csv</code> and Accept it: new request IDs are appended, the next rebuild routes them.`
      : `from the repo root:<br><code>${esc(P.command.replace('{file}', filename || 'threads.jsonl'))}</code>`}</span></div>`;
    out += `<table class="preview"><thead><tr><th>Request</th><th>Posted · by</th><th>Resolved company</th><th>Offer in replies</th><th>Would route to<br><span class="fm">Hover a name for the arithmetic</span></th><th>Needs a human<br><span class="fm">Click the row for the ranked paths</span></th></tr></thead><tbody>`
      + pv.rows.map((r, i) => `<tr class="pick ${r.flags.length ? 'flag' : ''}" data-i="${i}"><td class="rid">${esc(r.request_id)}${r.filed ? '<br><span class="foot">filed</span>' : ''}${reqFoot(r)}</td><td class="date">${esc(r.posted)}<br><span class="foot">${esc(r.requested_by)}</span></td><td>${r.company_id ? `${co(r)} <span class="foot">${esc(r.company_id)}</span>` : `<i>${esc(r.company_name || 'None')}</i>`}<br><span class="foot">${esc(r.company_as_written ? `"${r.company_as_written}" · ` : '')}${esc(r.resolved_by)}</span></td><td>${r.offers.length ? r.offers.map(o => `${named(r, o.who)} <span class="foot">${esc(o.date)}</span><br><q>${esc(o.text)}</q>`).join('<br>') : '<span class="foot">None</span>'}</td><td>${r.route_to ? `${named(r, r.route_to)}<br><span class="foot">${esc(cap1(r.path))} · expected value ${esc(r.expected_value)}</span>` : `<span class="foot">${esc(cap1(r.path) || 'None')}</span>`}</td><td class="foot">${r.flags.length ? r.flags.map(f => esc(cap1(f))).join('<br>') : 'Nothing'}</td></tr><tr class="detail" data-i="${i}" hidden><td colspan="6"></td></tr>`).join('')
      + `</tbody></table>`;
    el.innerHTML = out;
    el.querySelector('#lp-dl-preview').onclick = () => download(`${name}_preview.csv`, toCsv(P.preview_columns, pv.rows));
    const toggle = i => {
      const d = el.querySelector(`tr.detail[data-i="${i}"]`), td = d.firstElementChild;
      if (!td.innerHTML) td.innerHTML = renderRoute(route(pv.rows[i].raw_ask, P, pv.rows[i].target_company_raw), P);
      d.hidden = !d.hidden;
    };
    el.querySelectorAll('tr.pick').forEach(tr => tr.onclick = e => { if (!e.target.closest('a')) toggle(+tr.dataset.i); });
    if (open && pv.rows.length) toggle(0);
  }

  return { boot, bootConnector, bootBatch, extract, makeResolver, previewThreads, parseJsonl, requestsToThreads, looksLikeRequestsCsv, route, normStrict, toCsv, completionRows, completionId, tickKey, postCompletions,
           fnv1a, uploadId, revertId, revertRow, activeUploads, schemaOf, parseCsv, parseThreads, mergeCsv, mergeThreads, guessTarget, previewUpload, uploadRow, postUpload };
})();
if (typeof module !== 'undefined') module.exports = LP;
