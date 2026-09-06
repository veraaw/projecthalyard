/* Live Priorities tab. Renders the payload dashboard/live_priorities.py wrote;
   derives nothing. The only input it processes is a dropped .jsonl of Slack
   threads, and for that it applies the parser tables the payload carries
   (golden/parse.py cues, golden/resolver.py layers, build_golden.py OFFER_RE)
   in the same order the Python does — tests/test_live_priorities.py runs this
   file under node against the Python parser on every thread on disk. */
const LP = (function () {
  'use strict';

  // ---------------------------------------------------------------- helpers
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const co = ref => ref && ref.href ? `<a href="${esc(ref.href)}">${esc(ref.company_name)}</a>` : esc(ref ? ref.company_name : '');
  const plural = (n, w) => `${n} ${n === 1 ? w : w.endsWith('y') ? w.slice(0, -1) + 'ies' : w.endsWith('ch') ? w + 'es' : w + 's'}`;
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  // a section that starts closed: the h2 is the summary, the arrow toggles the body
  const fold = h2 => `<details class="fold"><summary><h2>${h2}</h2></summary>`;
  // a fresh ask on a company whose last intro fizzled: the row says so, and names that intro
  const retryTag = r => r.retry ? `<br><b class="warn">retry intro</b> <span class="foot">${esc(r.retry.note)}</span>` : '';
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
  function extract(text, P, resolver) {
    text = text || '';
    const seen = new Map();
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

  function previewThreads(jsonlText, P) {
    const resolver = makeResolver(P.resolver);
    const offerRe = new RegExp(P.offer.source, P.offer.flags);
    const { threads, errors } = parseJsonl(jsonlText);
    const rows = threads.map(t => {
      const first = t.messages[0], replies = t.messages.slice(1);
      const offers = replies.filter(m => offerRe.test(m.text || '')).map(m => ({ who: m.user, text: m.text, date: (m.ts || '').slice(0, 10) }));
      const human = [];
      const row = { request_id: t.request_id, posted: (first.ts || '').slice(0, 10), requested_by: first.user || '', raw_ask: first.text || '',
                    company_as_written: '', company_id: '', network: '', company_name: '', resolved_by: '', href: '', offers, offer_by: '', offer_text: '',
                    route_to: '', path: '', expected_value: '', needs_human: '', flags: human, filed: false, mentions: [], cands: [], priority: null };
      const filed = get(P.filed, t.request_id, null);
      if (filed) {
        Object.assign(row, { filed: true, company_id: filed.company_id, company_name: filed.company_name, href: filed.href,
                             resolved_by: `already filed (${filed.status}); filed facts are kept, only new offers land` });
        if (filed.asked) human.push('already asked, so an offer in the thread changes nothing');
      } else {
        const ex = extract(first.text || '', P, resolver);
        row.mentions = ex.mentions;
        const tg = ex.target;
        if (!tg) {
          const bare = ex.mentions.filter(m => m.cue === P.known_cue).length;
          row.resolved_by = bare > 1 ? `${bare} companies named, nothing says which is wanted` : 'no company named in the ask';
          human.push(bare > 1 ? 'several companies named and none asked for, so the build files it with no company_id' : 'no company named, so the build files it with no company_id');
        }
        else {
          row.company_as_written = tg.text;
          const r = tg.resolution;
          if (r.entity_id && r.kind === 'company') {
            Object.assign(row, { company_id: r.entity_id, resolved_by: `${r.method} (${r.confidence.toFixed(2)})` });
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
        human.push('thread carries no deal value, urgency or target title, add them to the request file');
      }
      // who it would route to: the best existing path vs any offer in the thread, scored as the build scores them
      // (path strength x focus fit x delivery rate); expected value then multiplies by the request priority
      // and the slots left, as the allocator does. Every factor comes from the payload.
      const C = get(P.companies, row.company_id || row.network || '', null);
      const priority = C ? C.priority : { request_priority: 0, deal_source: 'no deal value on file',
                                          components: { deal_value_musd: 0, stage_weight: P.no_crm_weight, age: 1, reps_waiting: 1 } };
      const cand = (who, score, label, strength, fit, rate, capacity_left) => ({
        who, score, label, connector_score: score * capacity_left,
        expected_value: priority.request_priority * score * capacity_left, if_slot: priority.request_priority * score,
        components: { path_strength: strength, focus_fit: fit, delivery_rate: rate, capacity_left },
      });
      const cands = [];
      if (C && C.best) cands.push(cand(C.best.connector, C.best.score, C.best.label, C.best.strength, C.best.fit, C.best.rate, C.best.capacity_left));
      for (const o of offers) {
        const score = C ? get(C.offer_score, o.who, C.offer_score_unknown) : get(P.offer_score_no_industry, o.who, P.offer_score_unknown);
        const conn = get(P.connectors, o.who, null);
        const fit = C ? get(C.offer_fit, o.who, P.unknown_fit) : P.unknown_fit, rate = conn ? conn.rate : P.prior_rate;
        const cap = conn ? conn.capacity : P.off_roster_capacity, idle = conn ? conn.idle : cap;
        cands.push(cand(o.who, score, 'offered in Slack', P.offer_base, fit, rate, cap ? Math.max(0, idle) / cap : 0));
      }
      cands.sort((a, b) => b.score - a.score);
      row.cands = cands; row.priority = priority;
      if (offers.length) { row.offer_by = offers.map(o => o.who).join(' | '); row.offer_text = offers.map(o => o.text).join(' | '); }
      if (filed && filed.asked) {
        row.path = 'already asked, so not re-routed';
      } else if (cands.length) {
        const best = cands[0], conn = get(P.connectors, best.who, null);
        row.route_to = best.who; row.path = `${best.label} (${best.score.toFixed(2)})`; row.expected_value = best.expected_value.toFixed(3);
        if (conn && conn.idle <= 0) human.push(`${best.who} has no slot left this cycle, so this would be "capacity exhausted" unless a slot frees`);
        if (conn && !conn.on_roster) human.push(`${best.who} is not on the connector roster`);
        if (!conn) human.push(`${best.who} is unknown to the roster and the outcome log`);
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
  function route(text, P) {
    text = (text || '').trim();
    const resolver = makeResolver(P.resolver);
    const ex = extract(text, P, resolver);
    const tm = new RegExp(P.title.source, P.title.flags).exec(text);
    const tg = ex.target;
    const out = { text, title: tm ? tm.groups.t : '', mentions: ex.mentions, target: null, company: null, crm: false,
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
    out.top = C.paths.find(p => p.score > 0) || null;
    out.priority = out.top ? {
      ...C.priority, connector_score: out.top.connector_score,
      expected_value: +(C.priority.request_priority * out.top.connector_score).toFixed(4),
      connector_components: { path_strength: out.top.strength, focus_fit: out.top.fit, delivery_rate: out.top.rate, capacity_left: out.top.capacity_left },
    } : { ...C.priority, connector_score: 0, expected_value: 0, connector_components: null };
    out.status = out.top ? 'routed' : 'no-path';
    out.note = out.top ? '' : `no path on the roster: nobody in the network reaches ${C.company_name}. It would be an exception this cycle unless someone offers.`;
    if (C.network) out.note = `${C.company_name} is not on file: no CRM account, never requested. The network reaches it${C.path_count ? ` (${plural(C.path_count, 'path')})` : ''}; filing this request creates the company and the next rebuild routes it as ranked below. Create the CRM account (see CRM Updates).${out.note ? ' ' + out.note : ''}`;
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
  const isoDay = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
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
  const SUBMITTED_TITLE = 'recorded; leaves the list when the site rebuilds';
  // the tick-box cell for one row; the data- attributes are what Submit posts
  const tick = (state, t) => {
    const key = tickKey(t), on = state.ticks.has(key), sub = state.submitted.has(key);
    return `<td><input type="checkbox" class="tick" ${on || sub ? 'checked' : ''} ${sub ? `disabled title="${SUBMITTED_TITLE}"` : ''} aria-label="done" data-key="${esc(key)}" data-action="${esc(t.action)}" data-rid="${esc(t.request_id || '')}" data-cid="${esc(t.company_id || '')}" data-connector="${esc(t.connector || '')}" data-note="${esc(t.note || '')}"></td>`;
  };
  const doneClass = (state, t) => { const k = tickKey(t); return state.ticks.has(k) || state.submitted.has(k) ? 'done' : ''; };
  const askTick = (X, r) => ({ action: X.actions.top, request_id: r.request_id, company_id: r.company_id, connector: r.connector, note: `${r.company_name} · ${r.target_title}` });
  const nudgeTick = (X, r) => ({ action: X.actions.bottlenecks, request_id: r.request_id, company_id: r.company_id, connector: r.connector, note: `${r.company_name} · agreed ${r.agreed_date || r.asked_date}` });
  // a connector's outstanding ask: `nudge` (they agreed — the same row as Core bottlenecks) or `chase` (never replied)
  const followTick = (X, s) => ({ action: X.actions[s.action], request_id: s.request_id, company_id: s.company_id, connector: s.connector, note: `${s.company_name} · asked ${s.asked_date}` });
  const actionLabel = { ask_sent: 'ask sent', nudged: 'nudged', chased: 'chased' };
  const describe = r => `${actionLabel[r.action] || r.action} ${esc(r.request_id || r.company_id)}${r.connector ? ` → ${esc(r.connector)}` : ''}`;

  const submitBar = X => `<div class="submitbar" id="lp-submit" hidden><span id="lp-submit-n"></span><button id="lp-submit-go">Submit</button><button id="lp-submit-clear" class="secondary">Clear</button><span id="lp-submit-who"></span><span class="foot">${X.supabase_url ? `records your ticks in the <code>${esc(X.table)}</code> table; the site rebuilds from it every 15 minutes and the ticked items leave the queue` : '<b class="warn">this build cannot submit: no Supabase URL / anon key</b>'}</span></div>`;

  function wireCompletions(root, X, state) {
    const bar = root.querySelector('#lp-submit'), n = root.querySelector('#lp-submit-n'), go = root.querySelector('#lp-submit-go');
    const whoEl = root.querySelector('#lp-submit-who');
    // asked once per browser; after that the name is shown next to Submit, with a link to change it
    const askWho = () => {
      const who = (window.prompt('Who are you? (goes in completed_by, remembered in this browser)', load('lp-who', '') || '') || '').trim();
      if (who) store('lp-who', who);
      return who;
    };
    const show = () => {
      const k = state.ticks.size, who = load('lp-who', '');
      bar.hidden = !k && !bar.dataset.msg;
      bar.classList.toggle('failed', bar.dataset.state === 'failed');
      n.innerHTML = bar.dataset.msg || `<b>${plural(k, 'tick')}</b>`;
      whoEl.innerHTML = who ? `as <b>${esc(who)}</b> · <a href="#" id="lp-submit-rename">change</a>` : '';
      const rename = whoEl.querySelector('#lp-submit-rename');
      if (rename) rename.onclick = e => { e.preventDefault(); askWho(); show(); };
      go.disabled = !k || !X.supabase_url;
    };
    root.querySelectorAll('.tick').forEach(cb => cb.addEventListener('change', () => {
      const d = cb.dataset, t = { action: d.action, request_id: d.rid, company_id: d.cid, connector: d.connector, note: d.note };
      cb.checked ? state.ticks.set(d.key, t) : state.ticks.delete(d.key);
      root.querySelectorAll(`.tick[data-key="${d.key}"]`).forEach(x => { x.checked = cb.checked; x.closest('tr').classList.toggle('done', cb.checked); });
      store('lp-ticks', [...state.ticks.values()]);
      delete bar.dataset.msg; delete bar.dataset.state;
      show();
    }));
    root.querySelector('#lp-submit-clear').onclick = () => {
      state.ticks.clear(); store('lp-ticks', []); delete bar.dataset.msg; delete bar.dataset.state;
      root.querySelectorAll('.tick:not(:disabled)').forEach(x => { x.checked = false; x.closest('tr').classList.remove('done'); });
      show();
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
      root.querySelectorAll('.tick:checked').forEach(x => { x.disabled = true; x.title = SUBMITTED_TITLE; });
      const already = got.already.length ? ` ${plural(got.already.length, 'row')} already recorded today (${got.already.map(describe).join('; ')}).` : '';
      bar.dataset.msg = `<b>Recorded ${plural(got.recorded.length, 'row')}</b> as ${esc(who)}${got.recorded.length ? `: ${got.recorded.map(describe).join('; ')}` : ''}.${already} The site rebuilds from the table every 15 minutes; refresh after that and these leave the queue.`;
      show();
    };
    show();
  }

  // when this site was last built, from docs/build_stamp.json (committed with
  // the rest of docs/ whenever a rebuild changed something), and the last run of
  // the scheduled rebuild from the public GitHub Actions API when the repo is
  // known — that run is what says the page is current even when nothing changed.
  // Stale = no successful run in 3 cycles (or, with no API, a build over a day
  // old). Both are best-effort: a page opened from disk shows the as-of date.
  const STALE_RUN_MS = 45 * 60000, STALE_BUILD_MS = 24 * 3600 * 1000;
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
    if (st) parts.push(`site built <b>${esc(utc(st.built_at))}</b> (${ago(st.built_at)}; as of ${esc(st.as_of)}, ${plural(st.completions, 'completion')} applied)`);
    else parts.push(`as of <b>${esc(D.as_of)}</b>`);
    if (run) parts.push(`last rebuild check <a href="${esc(run.html_url)}" target="_blank" rel="noopener">${ago(run.updated_at || run.created_at)}</a>`);
    if (stale) parts.push('<b class="warn">stale: the 15-minute rebuild has not run lately</b>');
    el.innerHTML = parts.join(' · ');
  }

  // ------------------------------------------------------------------ render
  // a connector never asked has no rate of their own: the scoring assumes the network average (the prior)
  const rateKpi = c => c.asks_all_time
    ? `<div class="kpi"><div class="v">${Math.round(c.delivery_rate * 100)}%</div><div class="l">delivery rate</div><div class="s">${c.intros_all_time} intros / ${c.asks_all_time} asks, shrunk toward the ${Math.round(c.prior_rate * 100)}% network average</div></div>`
    : `<div class="kpi"><div class="v words">no track record</div><div class="l">delivery rate</div><div class="s">never asked; scoring assumes the ${Math.round(c.prior_rate * 100)}% network average</div></div>`;
  const comp = (r, k, fmt) => `<span class="c" title="${esc(k.replace(/_/g, ' '))}">${fmt(r.components[k])}</span>`;
  const FM_HEAD = '<th class="num">expected value</th><th>request priority<br><span class="fm">deal $M × stage × age × reps</span></th><th>connector score<br><span class="fm">path × fit × rate × capacity</span></th>';
  const fmCells = r => `<td class="num ev">${r.expected_value.toFixed(3)}</td><td class="parts"><b>${r.request_priority.toFixed(3)}</b> = ${comp(r, 'deal_value_musd', v => v.toFixed(2))} × ${comp(r, 'stage_weight', v => v.toFixed(2))} × ${comp(r, 'age', v => v.toFixed(2))} × ${comp(r, 'reps_waiting', v => v)}<br><span class="foot">${r.days_waiting} days waiting</span></td><td class="parts"><b>${r.connector_score.toFixed(3)}</b> = ${comp(r, 'path_strength', v => v.toFixed(2))} × ${comp(r, 'focus_fit', v => v.toFixed(2))} × ${comp(r, 'delivery_rate', v => v.toFixed(2))} × ${comp(r, 'capacity_left', v => v.toFixed(2))}<br><span class="foot">${esc(r.capacity_note)}</span></td>`;

  // rows of ranked() with tick-boxes (an ask sent); `rankKey` picks the number shown in the # column
  function priorityTable(rows, X, state, rankKey, withConnector) {
    return `<table class="top"><thead><tr><th></th><th>#</th><th>request</th><th>company</th><th>who wants</th>${withConnector ? '<th>ask</th>' : '<th>path</th>'}${FM_HEAD}</tr></thead><tbody>`
      + rows.map(r => { const t = askTick(X, r); return `<tr class="${doneClass(state, t)}" data-rid="${esc(r.request_id)}">${tick(state, t)}<td class="order">${r[rankKey]}</td><td class="rid">${esc(r.request_id)}<br><span class="foot">${esc(r.value_fmt)} · ${esc(r.crm_stage)}</span></td><td>${co(r)}<br><span class="foot">${esc(r.target_title)}</span>${retryTag(r)}</td><td>${esc(r.requested_by)}${r.reps.length > 1 ? `<br><span class="foot">+${r.reps.length - 1} more waiting</span>` : ''}</td><td>${withConnector ? `<b>${esc(r.connector)}</b>${r.on_roster ? '<br><span class="foot">roster</span>' : ''}<br><span class="foot">${esc(r.path)}</span>` : `${esc(r.path)}${r.allocated ? '' : '<br><b class="warn">no slot this cycle</b>'}`}</td>${fmCells(r)}</tr>`; }).join('')
      + `</tbody></table>`;
  }

  function formulaNote(F) {
    return `<div class="formula"><p><code>${esc(F.expected_value)}</code></p><p><code>${esc(F.request_priority)}</code><br><code>${esc(F.connector_score)}</code></p>
      <p class="foot">stage weight by CRM stage: ${Object.entries(F.stage_weight).map(([k, v]) => `${esc(k)} ${v}`).join(' · ')}. age: ${esc(F.age)}. reps waiting: ${esc(F.reps_waiting)}. path strength: ${esc(F.path_strength)}. focus fit: ${esc(F.focus_fit)}. delivery rate: ${esc(F.delivery_rate)}. capacity left: ${esc(F.capacity_left)}. Tick a row once the ask is sent; Submit records the ticks and the next rebuild takes them off the list.</p></div>`;
  }

  // what a connector is sitting on, with a tick-box per row (nudged / chased); a row
  // followed up in the last quiet_days has no box and says when
  const sittingTable = (c, X, state) => c.sitting_on.length ? `<table class="top"><thead><tr><th></th><th>action</th><th>request</th><th>company</th><th>wanted</th><th>for</th><th>asked</th><th class="num">days</th><th>responded</th><th>value</th></tr></thead><tbody>`
    + c.sitting_on.map(s => { const k = followTick(X, s); return `<tr class="${s.quiet ? 'quiet' : doneClass(state, k)}">${s.quiet ? `<td title="${esc(actionLabel[k.action])} ${esc(s.nudged_on)}; back in ${c.quiet_days - s.days_since_nudged}d"></td>` : tick(state, k)}<td><b>${esc(s.action)}</b>${s.quiet ? `<br><span class="foot">${esc(actionLabel[k.action])} ${s.days_since_nudged}d ago</span>` : ''}</td><td class="rid">${esc(s.request_id)}</td><td>${co(s)}${retryTag(s)}</td><td>${esc(s.target_title)}</td><td>${esc(s.requested_by)}</td><td class="date">${esc(s.asked_date)}</td><td class="num">${s.days_since_asked}</td><td>${s.responded ? '<b>yes, so nudge rather than re-ask</b>' : 'no'}</td><td>${esc(s.value_fmt)}</td></tr>`; }).join('') + `</tbody></table><p class="foot">Tick a row once you have nudged or chased; it is off the list for ${c.quiet_days} days after the next rebuild.</p>` : `<p class="empty">nothing outstanding</p>`;

  const pctOf = v => v == null ? 'n/a' : `${Math.round(v * 100)}%`;

  // cycle-by-cycle record: asks against capacity, intros made, running total
  const cycleTable = (rows, who) => `<table class="cycles"><thead><tr><th>cycle</th><th class="num">asks</th><th class="num">of capacity</th><th class="num">intros made</th><th class="num">cumulative intros</th></tr></thead><tbody>`
    + rows.map(r => `<tr${r.current ? ' class="now"' : ''}><td class="date">${esc(r.cycle)}${r.current ? ' <span class="foot">this cycle</span>' : ''}</td>`
      + `<td class="num">${r.asks}${r.allocated ? ` <span class="foot">+ ${r.allocated} allocated</span>` : ''}</td>`
      + `<td class="num">${pctOf(r.capacity_pct)}${r.capacity ? ` <span class="foot">${r.used} / ${r.capacity}</span>` : ''}</td>`
      + `<td class="num">${r.intros}</td><td class="num">${r.intros_cumulative}</td></tr>`).join('')
    + `</tbody></table><p class="foot">A cycle is a calendar month, the allocator's unit. Asks by <code>asked_date</code>, intros by <code>intro_date</code> from <code>intro_outcomes.csv</code>; capacity is ${esc(who)}'s stated monthly capacity in <code>connector_roster.csv</code>. This cycle's allocation counts as slots used because those asks are about to go out.</p>`;

  // ------------------------------------------------- batched-ask composer
  // The drafted message dashboard/batch_ask.py wrote for one connector's cycle batch,
  // with a copy button. A drafting aid only: copying writes nothing anywhere; the
  // ask_sent tick on the queue rows stays the record that the ask went out.
  const composeBlock = (m, id, tick = 'tick <i>ask sent</i> on the rows below once it has gone out') => !m ? '' : `<div class="compose" id="${esc(id)}"><div class="bar"><b>Batched ask · ${esc(m.connector)}</b>
      <span class="foot">cycle ${esc(m.cycle)} · ${plural(m.request_count, 'request')} across ${plural(m.company_count, 'company')} · ${m.template === 'offerer' ? 'offerer template (off the roster, asked because they offered)' : m.template === 'network' ? 'network template (investor network, asked for a warm intro as a favour)' : 'roster template'}${m.over_capacity ? ` · <b class="warn">${m.request_count} asks against a stated capacity of ${m.capacity}</b>` : ''}</span>
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
    const detail = m => `<details><summary>${plural(m.request_count, 'request')} behind this message (ids, scores, values and urgency stay here, out of the text)</summary>
      <table><thead><tr><th>request</th><th>company</th><th>wanted</th><th>for</th><th>path</th><th class="num">score</th><th>value</th><th>urgency</th></tr></thead><tbody>`
      + m.requests.map(q => `<tr><td class="rid">${esc(q.request_id)}</td><td>${co(q)}</td><td>${esc(q.target_title)}</td><td>${esc(q.requested_by)}</td><td>${esc(q.path_type)}${q.contact_name ? ` <span class="foot">via ${esc(q.contact_name)}</span>` : q.offer_date ? ` <span class="foot">offered ${esc(q.offer_date)}</span>` : ''}</td><td class="num">${esc(q.route_score)}</td><td>${esc(q.value_fmt)}</td><td>${esc(q.urgency)}</td></tr>`).join('')
      + `</tbody></table></details>`;
    const card = m => `<section id="${esc(m.slug)}"><h2>${esc(m.connector)} <span class="foot">${m.on_roster ? esc(m.type) : 'not on the roster'} · batch <code>${esc(m.batch_id)}</code>${m.page ? ` · <a href="${esc(m.page)}">their page</a>` : ''}</span></h2>`
      + composeBlock(m, `ask-${m.cycle}-${m.slug}`, `tick <i>ask sent</i> on ${m.page ? `<a href="${esc(m.page)}">their page</a>` : 'their page'} or <a href="livepriorities.html#connectors">Live Priorities</a> once it has gone out`) + detail(m) + `</section>`;
    let out = `<p class="stamp" id="lp-stamp">as of <b>${esc(D.as_of)}</b></p>
      <section id="about"><p class="lede">One message per connector for cycle <b>${esc(D.cycle)}</b>: their whole batch from <code>golden_allocation.csv</code>, grouped by company and ordered by the batch's best route, requesters named from <code>golden_requests.csv</code>. Connectors on the roster get the roster wording; someone off the roster who is being asked because they offered in a thread gets the offerer wording, quoting the thread date; an investor-network person asked over their own portfolio or prior-employer path gets the network wording, a thank-you and a request for a warm introduction rather than a work queue. The wording lives in <code>${esc(D.templates)}</code>. No dollar value, route score, request id or urgency label appears in the text; those stay in the table under each message.</p>
      <p class="foot">${plural(now.length, 'message')} this cycle: ${now.map(m => `<a href="#${esc(m.slug)}">${esc(m.connector)}</a>`).join(' · ') || 'nothing allocated'}. Copying writes nothing; the <i>ask sent</i> tick on Live Priorities and the connector's page remains the record that the ask went out.</p></section>`;
    out += now.map(card).join('') || `<p class="empty">nothing allocated in cycle ${esc(D.cycle)}</p>`;
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
    const went = s => [s.routed_to.length ? `routed to ${s.routed_to.map(esc).join(', ')}` : '', s.unrouted ? `${plural(s.unrouted, 'request')} unrouted` : ''].filter(Boolean).join(' · ');
    return `<h3>strongest path here, not routed to you <span class="foot">read-only — ${plural(rows.length, 'company')} where your path is the strongest on file and this cycle's requests went elsewhere; ${cap}. Nobody has asked you; there is nothing to tick.</span></h3>`
      + `<table class="top"><thead><tr><th>company</th><th>your path</th><th class="num">strength</th><th class="num">route score</th><th>why not you</th><th>this cycle</th><th>requests</th></tr></thead><tbody>`
      + rows.map(s => `<tr class="quiet"><td>${co(s)}</td><td>${esc(s.reach_type)}</td><td class="num">${s.strength.toFixed(3)}</td><td class="num">${s.route_score.toFixed(3)}</td><td>${why(s) || 'the allocator ranked another path higher'}</td><td>${went(s)}</td><td class="rid">${s.requests.map(esc).join(', ')}</td></tr>`).join('')
      + `</tbody></table><p class="foot">route score = strength × focus fit × delivery rate, the allocator's sort key; a 0.000 is a focus area you decline outside of. An ask only appears above, under "already sitting on", once it is logged in intro_outcomes.csv.</p>`;
  };

  // one connector's page (docs/connector-<slug>.html): the drafted ask, top 5, then the longer list
  function bootConnector(c, root) {
    const X = c.completions, state = loadTicks(X);
    const cap = c.capacity ? `${c.used} / ${c.capacity}` : `${c.used}`;
    const now = c.cycles[c.cycles.length - 1];
    let out = c.batch_ask ? `<section id="ask"><h2>This cycle's ask <span class="foot">the batch drafted as one message: copy it, send it, then tick the rows below as the asks go out</span></h2>${composeBlock(c.batch_ask, `ask-${c.slug}`)}</section>` : '';
    out += `<section id="top"><h2>Top ${c.top.length} for ${esc(c.connector)} <span class="foot">do these next: ${esc(c.connector)}'s share of the ${c.ranked_count} live requests routed to them this cycle, sorted by expected value${c.no_slot ? `; ${c.no_slot} have no slot until capacity frees up` : ''}</span></h2>
      <p class="lede">${c.on_roster ? `${esc(c.role)} · ${esc(c.type)} · focus: ${c.focus.map(esc).join(', ')}${c.hard_decline ? ' · <b>declines anything outside</b>' : ''}` : `<b>not on the roster</b> · ${esc(c.type)} · no stated capacity or focus areas`}${c.notes ? `<br><span class="foot">${esc(c.notes)}</span>` : ''}</p>
      <div class="kpis"><div class="kpi"><div class="v">${cap}</div><div class="l">${c.capacity ? 'capacity used this cycle' : 'asks this cycle'}</div><div class="s">${c.asked_this_cycle} asked + ${c.allocated_this_cycle} allocated${c.capacity ? ` · ${c.idle} idle` : ''}</div></div>
        <div class="kpi"><div class="v">${c.intros_this_cycle}</div><div class="l">intros made this cycle</div><div class="s">${esc(now.cycle)} · ${c.capacity ? `${pctOf(now.capacity_pct)} of capacity used` : 'no stated capacity'}</div></div>
        <div class="kpi"><div class="v">${c.intros_all_time}</div><div class="l">cumulative intros</div><div class="s">since ${esc(c.cycles[0].cycle)}, over ${c.asks_all_time} asks</div></div>
        ${rateKpi(c)}
        <div class="kpi"><div class="v">${c.ranked_count}</div><div class="l">requests on their list</div><div class="s">${esc(c.ranked_value_fmt)} of deal value</div></div>
        <div class="kpi ${c.sitting_on.length ? 'warn' : ''}"><div class="v">${c.sitting_on.length}</div><div class="l">already sitting on</div><div class="s">asked, live, no intro yet</div></div></div>`
      + (c.top.length ? priorityTable(c.top, X, state, 'rank_here', false) : `<p class="empty">nothing routed to ${esc(c.connector)} this cycle</p>`)
      + `<p class="foot"># is the rank within ${esc(c.connector)}'s list; the same rows rank ${c.top.map(r => r.rank).join(', ') || 'nowhere'} on the <a href="livepriorities.html#top">overall list</a>.</p></section>`;

    out += `<section id="rest"><h2>The longer list <span class="foot">everything else on ${esc(c.connector)}'s plate: ${plural(c.rest.length, 'more request')} to ask, then ${plural(c.sitting_on.length, 'ask')} already made and waiting on them</span></h2>
      <h3>after the top ${c.top.length}</h3>` + (c.rest.length ? priorityTable(c.rest, X, state, 'rank_here', false) : `<p class="empty">${c.ranked_count ? 'the top ' + c.top.length + ' is the whole list' : 'nothing to ask'}</p>`)
      + `<h3>already sitting on</h3>` + sittingTable(c, X, state)
      + strongestTable(c)
      + formulaNote(c.formula) + `</section>`;

    out += `<section id="cycles"><h2>By cycle <span class="foot">${esc(c.connector)}'s asks against capacity, intros made and the running total, one row per month since ${esc(c.cycles[0].cycle)}</span></h2>`
      + cycleTable(c.cycles, c.connector) + `</section>`;

    root.innerHTML = `<p class="stamp" id="lp-stamp">as of <b>${esc(c.as_of)}</b></p>` + out + submitBar(X);
    wireCompletions(root, X, state);
    wireCopy(root);
    buildStamp(c, root.querySelector('#lp-stamp'));
  }

  function boot(D, root) {
    const P = D.parser, X = D.completions;
    const state = loadTicks(X);
    // every section, keyed by id; D.bands says which band each belongs to and in what order
    const sec = {};

    // ---- band 1 · intake: input the build does not have yet
    // route one message — the common case and the demo case, so it comes first
    sec.route = `<section id="route"><h2>Route a Live Request <span class="foot">paste a Slack message and see what the router would do with it</span></h2>
      <p class="lede">The browser applies the build's own rules, exported as data: the ${P.cues.length} cues from <code>golden/parse.py</code> score every company named, the highest positive score is the target, <code>golden/resolver.py</code>'s tables look the name up, and the company's paths from <code>supply_reach.csv</code> are ranked as the build ranks them. A company nobody has filed yet but someone in the network reaches shows the paths the next rebuild would file for it. Nothing is written anywhere.</p>
      <div class="presets">try a real shape:${P.route_presets.map((p, i) => `<button class="secondary" data-i="${i}">${esc(p.label)}</button>`).join('')}</div>
      <div class="ask"><textarea id="lp-route-text" rows="3" placeholder="who do we know at …" aria-label="Slack message"></textarea><button id="lp-route-go">Route it</button></div>
      <div id="lp-route-out"></div></section>`;

    // bulk upload — rare, and ends in a command run elsewhere
    sec.upload = `<section id="upload"><h2>Preview a Slack Export Before Anything Is Written</h2>
      <p class="lede">Drop a <code>.jsonl</code> of Slack threads (one <code>{request_id, messages:[{ts,user,text}…]}</code> per line). Every row shows the company the build would resolve, any offer spotted in the replies, who it would route to and what needs a human. It uses the build's own cues, resolver tables and offer pattern, so the preview matches what lands. A static page cannot write to disk: export the preview and run the command to file it.</p>
      <div class="drop" id="lp-drop"><input type="file" id="lp-file" accept=".jsonl,.json,.txt"><span>Drop a .jsonl here or click to choose</span></div>
      <div id="lp-preview"></div></section>`;

    // ---- band 2 · orientation: one strip, no rows — a masthead, not a section
    const S = D.stages;
    sec.stages = `<section id="stages" class="masthead">
      <div class="strip">${S.stages.map(s => `<div class="cell"><div class="v">${esc(s.usd_fmt)}</div><div class="n">${s.count === s.unresolved ? plural(s.count, 'unresolved request') : plural(s.count - s.unresolved, 'company') + (s.unresolved ? `<span class="foot"> · ${s.unresolved} unresolved</span>` : '')}</div><div class="l">${esc(s.stage)}</div></div>`).join('')}</div>
      <details class="note"><summary>${plural(S.total.companies, 'company')}${S.total.unresolved ? ` + ${plural(S.total.unresolved, 'unresolved request')}` : ''}, ${esc(S.total.usd_fmt)} · point in time, as of ${esc(S.as_of)}. Each company counted once, at its furthest stage, at one $ value · how it is counted</summary>
      <p class="foot">One $ per company: CRM ARR potential where the company has an account (${S.value_source.crm}), else the deal value on its latest request (${S.value_source.deal})${S.value_source.none ? `, ${S.value_source.none} with neither` : ''}, never the sum of its requests. A company sits at the furthest stage any of its requests reached: once a meeting is booked, fresh asks on it do not move it back. ${S.total.unresolved ? `${plural(S.total.unresolved, 'request')} that resolved to no company (${esc(S.total.unresolved_usd_fmt)}) cannot be tied to an account or to each other, so each stands alone at its own deal value. ` : ''}${plural(S.excluded.count - S.excluded.unresolved, 'company')} whose every request is filed <i>Closed - no path</i>${S.excluded.unresolved ? `, and ${plural(S.excluded.unresolved, 'unresolved request')} filed the same,` : ''} (${esc(S.excluded.usd_fmt)}) are not on the strip. "needs data" = no company or no deal value on any request; "to be routed" = live with nobody assigned; "routed" = a connector is assigned or allocated this cycle but not yet asked; "asked" = in <code>intro_outcomes.csv</code> with no intro; "introduced" = intro logged or filed; "meeting booked" = the intro landed a meeting.</p></details></section>`;

    // ---- band 3 · actionable now: ticking a row changes what the queue proposes tomorrow
    // spends a connector slot
    const T = D.priorities;
    sec.top = `<section id="top"><h2>Top ${T.top.length} Priorities <span class="foot">do these next: sorted by expected value across ${T.considered} live requests with a connector to act on · each spends a connector slot</span></h2>`
      + priorityTable(T.top, X, state, 'rank', true)
      + `<p class="foot">Per connector: ${D.connector_pages.map(c => `<a href="${esc(c.page)}">${esc(c.connector)}</a>`).join(' · ')}. Each tab opens on their own top 5, with the longer list below.</p>`
      + formulaNote(T.formula) + `</section>`;

    // admin
    const C = D.crm;
    sec.crm = `<section id="crm">${fold(`CRM Updates <span class="foot">${C.groups.map(g => `${g.count} ${esc(g.group)}`).join(' · ')}</span>`)}
      <div class="dl"><button id="lp-dl-import">Download ${esc(C.import.filename)}</button><span>${plural(C.import.count, 'account')} to create, importer-shaped columns only (<code>${C.import.columns.map(esc).join(', ')}</code>). It can be uploaded straight into the CRM.</span></div>
      <div class="dl"><button id="lp-dl-review" class="secondary">Download ${esc(C.review.filename)}</button><span>${plural(C.review.count, 'recommendation')} (${C.review.groups.map(g => `${g.count} ${esc(g.group)}`).join(', ')}), every row <code>status = ${esc(C.status)}</code>. Merges and owner conflicts are recommended, never executed, because ownership is compensation.</span></div>`;
    for (const g of C.groups) {
      sec.crm += `<h3>${esc(g.title)} <span class="foot">${g.count} · ${esc(g.value_fmt)}</span></h3>`;
      sec.crm += g.rows.length ? `<table><thead><tr><th>company</th><th>CRM accounts</th><th>owner</th><th>stage</th><th>action</th><th>why</th><th class="num">at stake</th></tr></thead><tbody>`
        + g.rows.map(r => `<tr><td>${co(r)}<br><span class="foot">${r.request_ids.map(esc).join(', ')}</span></td><td class="rid">${esc(r.crm_account_ids || 'none')}</td><td>${esc(r.owner || 'nobody')}</td><td>${esc(r.stage || 'none')}</td><td><b>${esc(r.action)}</b></td><td class="foot">${esc(r.why)}<br>${esc(r.evidence)}</td><td class="num">${esc(r.value_fmt)}</td></tr>`).join('') + `</tbody></table>`
        : `<p class="empty">nothing to do</p>`;
    }
    sec.crm += `</details></section>`;

    // ---- band 4 · current cycle: decisions the allocator already made — read-only
    // what is going out
    const A = D.asks;
    sec.asks = `<section id="asks">${fold(`Current Asks <span class="foot">cycle ${esc(A.cycle)}: ${A.allocated} requests allocated in ${plural(A.batches.length, 'batch')}, one consolidated ask per connector, from <code>golden_allocation.csv</code> and <code>supply_reach.csv</code> · the drafted messages are on <a href="${esc(D.batch_page)}">Batched-Ask</a></span>`)}`
      + tabs('asks', [...A.batches.map(b => ({ label: b.connector, n: b.size, b })), { label: 'Aggregate', n: A.allocated, cls: 'agg' }], ({ b }) => b
        ? `<p class="foot">${esc(b.connector_type)} · ${plural(b.size, 'request')} · ${esc(b.value_fmt)} · one consolidated ask, batch <code>${esc(b.batch_id)}</code> · <a href="${esc(D.batch_page)}#${esc(b.slug)}">the message</a></p>
        <table><thead><tr><th>company</th><th>everyone wanted</th><th>who is waiting</th><th>path</th><th>why this connector</th></tr></thead><tbody>`
        + b.companies.map(c => `<tr><td>${co(c)}<br><span class="foot">${esc(c.value_fmt)} · ${esc(c.urgency)} · ${c.request_ids.map(esc).join(', ')}</span>${retryTag(c)}</td><td>${c.wanted.map(esc).join('<br>')}</td><td>${c.waiting.map(esc).join('<br>')}</td><td>${esc(c.path_type)}${c.contact ? `<br><span class="foot">${esc(c.contact)}</span>` : ''}</td><td class="foot">${esc(c.why)}</td></tr>`).join('')
        + `</tbody></table>`
        : `<p class="foot">everything going out this cycle · ${plural(A.allocated, 'request')} across ${plural(A.batches.length, 'connector')} · ${esc(A.value_fmt)} · biggest first; a company listed twice is being asked of two connectors</p>
        <table><thead><tr><th>company</th><th>connector</th><th>everyone wanted</th><th>who is waiting</th><th>path</th></tr></thead><tbody>`
        + A.all.map(c => `<tr><td>${co(c)}<br><span class="foot">${esc(c.value_fmt)} · ${esc(c.urgency)} · ${c.request_ids.map(esc).join(', ')}</span>${retryTag(c)}</td><td><b>${esc(c.connector)}</b><br><a class="foot" href="${esc(D.batch_page)}#${esc(c.slug)}">the message</a></td><td>${c.wanted.map(esc).join('<br>')}</td><td>${c.waiting.map(esc).join('<br>')}</td><td>${esc(c.path_type)}${c.contact ? `<br><span class="foot">${esc(c.contact)}</span>` : ''}</td></tr>`).join('')
        + `</tbody></table>`);
    sec.asks += `</details></section>`;


    // already in the door: the allocator parked these rather than spend a slot
    const I = D.introduced;
    sec.introduced = `<section id="introduced">${fold(`Already Introduced — Extend the Intro <span class="foot">${plural(I.requests, 'request')} on ${plural(I.count, 'company')}, ${esc(I.value_fmt)} — an intro already landed there (meeting booked, or sent within ${I.days} days), so no connector slot is spent</span>`)}
      <p class="lede">The action is with the rep who was introduced, not a connector: they ask the contact they already have for the other names. An intro with no meeting after ${I.days} days counts as fizzled, as does a meeting with no opportunity after ${I.days} days once newer requests are filed on the company, and the company goes back into the queue, flagged <b class="warn">retry intro</b>.</p>`
      + (I.rows.length ? `<table><thead><tr><th>company</th><th>everyone wanted</th><th>who is waiting</th><th>the intro that landed</th><th>next step</th><th>fallback path</th></tr></thead><tbody>`
        + I.rows.map(r => `<tr><td>${co(r)}<br><span class="foot">${esc(r.value_fmt)} · ${esc(r.urgency)} · ${esc(r.crm_stage)} · ${r.request_ids.map(esc).join(', ')}</span></td><td>${r.wanted.map(esc).join('<br>')}</td><td>${r.waiting.map(esc).join('<br>')}</td><td><b>${esc(r.intro.connector)}</b> → ${esc(r.intro.requested_by || 'unattributed')}<br><span class="foot">${esc(r.intro.intro_date)} · ${esc(r.intro.request_id)} · ${esc(r.intro.target_title)}${r.intro.meeting_booked ? ' · <b>meeting booked</b>' : ` · ${r.intro.days} days ago, no meeting yet`}</span></td><td><b>${esc(r.owner || 'nobody')}</b><br><span class="foot">${esc(r.action)}</span></td><td class="foot">${esc(r.best_path || 'none in the network')}</td></tr>`).join('')
        + `</tbody></table>` : `<p class="empty">nothing parked behind a live intro this cycle</p>`)
      + (I.retries.length ? `<h3>Back in the queue as a retry <span class="foot">${plural(I.retry_requests, 'request')} on ${plural(I.retries.length, 'company')} whose last intro fizzled</span></h3>
        <table><thead><tr><th>company</th><th>everyone wanted</th><th>the intro that fizzled</th><th>asked again this cycle</th></tr></thead><tbody>`
        + I.retries.map(r => `<tr><td>${co(r)}<br><span class="foot">${esc(r.value_fmt)} · ${r.request_ids.map(esc).join(', ')}</span></td><td>${r.wanted.map(esc).join('<br>')}</td><td>${esc(r.retry.connector)} → ${esc(r.retry.requested_by || 'unattributed')}<br><span class="foot">${esc(r.retry.intro_date)} · ${esc(r.retry.request_id)} · ${esc(r.retry.outcome)}</span></td><td>${r.connectors.map(c => `<b>${esc(c)}</b>`).join(', ')}<br><span class="foot">${r.connectors.includes(r.retry.connector) ? 'same connector: ask for a second name or a nudge on the first' : 'different connector this time'}</span></td></tr>`).join('')
        + `</tbody></table>` : '')
      + `</details></section>`;

    // who is carrying it
    sec.connectors = `<section id="connectors">${fold(`Roster Connectors Capacity <span class="foot">one panel each: queue this cycle, capacity used against stated capacity, delivery rate, what they are already sitting on. The coloured tabs at the top open each connector's own page</span>`)}`
      + tabs('connectors', D.connectors.map(c => ({ label: c.connector, n: `${c.used}/${c.capacity}`, c })), ({ c }) => `
        <p class="lede">${esc(c.role)} · ${esc(c.type)} · focus: ${c.focus.map(esc).join(', ')}${c.hard_decline ? ' · <b>declines anything outside</b>' : ''} · <a href="${esc(c.page)}">their top 5</a><br><span class="foot">${esc(c.notes)}</span></p>
        <div class="kpis"><div class="kpi"><div class="v">${c.used} / ${c.capacity}</div><div class="l">capacity used this cycle</div><div class="s">${c.asked_this_cycle} asked + ${c.allocated_this_cycle} allocated · ${c.idle} idle</div></div>
          ${rateKpi(c)}
          <div class="kpi ${c.sitting_on.length ? 'warn' : ''}"><div class="v">${c.sitting_on.length}</div><div class="l">already sitting on</div><div class="s">asked, live, no intro yet</div></div>
          <div class="kpi"><div class="v">${c.queue.length}</div><div class="l">in this cycle's ask</div><div class="s">${c.queue.length ? 'one consolidated batch' : 'nothing allocated'}</div></div></div>`
        + composeBlock(c.batch_ask, `ask-${c.slug}`, `tick <i>ask sent</i> under <a href="#top">Top Priorities</a> or on <a href="${esc(c.page)}">their page</a> once it has gone out`)
        + `<h3>queue this cycle</h3>` + (c.queue.length ? `<table><thead><tr><th>request</th><th>company</th><th>wanted</th><th>for</th><th>path</th><th class="num">score</th><th>value</th><th>urgency</th></tr></thead><tbody>`
          + c.queue.map(q => `<tr><td class="rid">${esc(q.request_id)}</td><td>${co(q)}${retryTag(q)}</td><td>${esc(q.target_title)}</td><td>${esc(q.requested_by)}</td><td>${esc(q.path_type)}${q.contact ? ` <span class="foot">via ${esc(q.contact)}</span>` : ''}</td><td class="num">${esc(q.route_score)}</td><td>${esc(q.value_fmt)}</td><td>${esc(q.urgency)}</td></tr>`).join('') + `</tbody></table>` : `<p class="empty">nothing allocated to ${esc(c.connector)} this cycle</p>`)
        + `<h3>already sitting on</h3>` + sittingTable(c, X, state))
      + `</details></section>`;

    // requests the allocator could not place this cycle, by reason
    const EXCEPTION_TITLE = { 'no path to this company in the network': 'no direct path to this company in the network', 'already introduced': 'already introduced — extend the intro' };
    const EXCEPTION_NOTE = { 'no path to this company in the network': 'Not routable this cycle (sourcing issue vs. allocation)' };
    const parked = A.exceptions.find(e => e.reason === 'already introduced');
    sec.exceptions = `<section id="exceptions">${fold(`Unrouted Exceptions <span class="foot">${plural(A.exception_count, 'request')} not allocated in cycle ${esc(A.cycle)}: ${A.exceptions.map(e => `${e.count} ${esc((EXCEPTION_TITLE[e.reason] || e.reason).replace(' to this company in the network', ''))}`).join(', ')} · from <code>golden_allocation.csv</code></span>`)}`
      + (parked ? `<p class="lede">${plural(parked.count, 'request')} · ${esc(parked.value_fmt)} parked behind a live intro → <a href="#introduced">Already Introduced</a>, not repeated here</p>` : '');
    const cover = sc => !sc ? '' : sc.connectors.length
      ? sc.connectors.map(c => `<b>${esc(c.connector)}</b> <span class="foot">${c.asked ? `asked ${esc(c.asked)}` : 'never asked'}</span>`).join('<br>')
      : `<span class="foot">${esc(sc.note)}</span>`;
    for (const e of A.exceptions) {
      if (e === parked) continue;
      const withStage = !e.reason.startsWith('company'), noPath = e.reason.startsWith('no path'), blocked = e.rows.some(r => r.blocked_reason);
      sec.exceptions += `<h3>${esc(EXCEPTION_TITLE[e.reason] || e.reason)} <span class="foot">${e.count} · ${esc(e.value_fmt)}</span></h3>${EXCEPTION_NOTE[e.reason] ? `<p class="foot">${esc(EXCEPTION_NOTE[e.reason])}</p>` : ''}<table><thead><tr><th>request</th><th>company</th>${withStage ? '<th>CRM stage</th>' : ''}<th>wanted</th><th>who</th><th>value</th><th>urgency</th><th>status</th>${blocked ? '<th>blocked on</th>' : ''}${noPath ? '<th>who covers this sector</th>' : ''}<th>${e.reason.startsWith('capacity') ? 'best path (no slot)' : e.reason.startsWith('company') ? 'as written' : 'note'}</th></tr></thead><tbody>`
        + e.rows.map(r => `<tr><td class="rid">${esc(r.request_id)}</td><td>${co(r)}</td>${withStage ? `<td>${esc(r.crm_stage)}</td>` : ''}<td>${esc(r.target_title)}</td><td>${esc(r.requested_by)}</td><td>${esc(r.value_fmt)}</td><td>${esc(r.urgency)}</td><td>${esc(r.status)}</td>${blocked ? `<td>${esc(r.blocked_reason)}</td>` : ''}${noPath ? `<td>${cover(r.sector_cover)}</td>` : ''}<td class="foot">${esc(r.detail || r.best_path || (e.reason.startsWith('company') ? r.company_as_written || '(nothing parseable)' : 'nobody in the network reaches them'))}</td></tr>`).join('')
        + `</tbody></table>`;
    }
    sec.exceptions += `</details></section>`;

    // still in the cycle band: nothing here is a decision to make on this page, each row says where its action lives
    const U = D.unrouted, F = U.finding;
    sec.unrouted = `<section id="unrouted">${fold(`Suggested Unrouted Company Connectors <span class="foot">${U.unrouted_companies} companies with live requests nobody is allocated to, matched to each connector's stated focus areas</span>`)}
      <p class="lede">In-focus asks convert at <b>${esc(F.in_focus_pct)}</b> versus ${esc(F.out_focus_pct)} outside, yet only ${F.in_focus_asks} of ${F.total_asks} asks landed in focus. These are the names that finding points at. Nothing here is ticked. A company with a path moves on the connector's page; one without moves in sourcing, from its trace.</p>`;
    for (const c of U.per_connector) {
      sec.unrouted += `<h3>${esc(c.connector)} <span class="foot">${c.focus.map(esc).join(', ')} · ${plural(c.count, 'company')} · ${esc(c.value_fmt)} · ${c.idle} idle slots · <a href="${esc(c.page)}">their page</a></span></h3>`;
      sec.unrouted += c.companies.length ? `<table><thead><tr><th>company</th><th>industry</th><th>wanted</th><th>waiting</th><th>value</th><th>why unrouted</th><th>their way in</th><th>action lives</th></tr></thead><tbody>`
        + c.companies.map(x => `<tr><td>${co(x)}<br><span class="foot">${x.request_ids.map(esc).join(', ')}</span></td><td>${esc(x.industry)}</td><td>${x.wanted.map(esc).join('<br>')}</td><td>${x.waiting.map(esc).join('<br>')}</td><td>${esc(x.value_fmt)}</td><td class="foot">${x.reasons.map(esc).join('; ')}</td><td class="${x.has_path ? '' : 'foot'}">${esc(x.path)}</td><td class="foot">${x.has_path ? `<a href="${esc(c.page)}">${esc(c.connector)}'s page</a>` : x.href ? `sourcing · <a href="${esc(x.href)}">trace</a>` : 'sourcing'}</td></tr>`).join('') + `</tbody></table>`
        : `<p class="empty">no unrouted company in ${esc(c.connector)}'s focus areas</p>`;
    }
    sec.unrouted += `</details></section>`;

    // no slot spent: a nudge the connector owes, not a fresh ask
    const B = D.bottlenecks;
    sec.bottlenecks = `<section id="bottlenecks">${fold(`Core Introduction Bottlenecks <span class="foot">${plural(B.count, 'ask')} where the connector said yes and never sent the intro · <code>intro_outcomes.csv</code></span>`)}
      <p class="lede">Each of these wants a <b>nudge</b>. Asking again would spend a fresh slot for an answer you already have. Tick the row once you have nudged; it comes back after ${B.quiet_days} quiet days.</p>`
      + tabs('bottlenecks', [{ label: 'All connectors', n: B.count, rows: B.rows, note: `${plural(B.count, 'ask')} · oldest agreement first` }]
          .concat(B.by_connector.map(c => ({ label: c.connector, n: c.count, rows: B.rows.filter(r => r.connector === c.connector), note: `${plural(c.count, 'ask')}${c.on_roster ? '' : ' · off roster'}` }))),
        t => `<p class="foot">${t.note}</p><table class="top"><thead><tr><th></th><th>action</th><th>request</th><th>company</th><th>value</th><th>connector</th><th>asked</th><th>agreed</th><th class="num">days since they agreed</th><th>wanted</th><th>for</th></tr></thead><tbody>`
          + t.rows.map(r => { const k = nudgeTick(X, r); return `<tr class="${doneClass(state, k)}">${tick(state, k)}<td><b>${esc(r.action)}</b></td><td class="rid">${esc(r.request_id)}<br><span class="foot">${esc(r.status)}</span></td><td>${co(r)}</td><td>${esc(r.value_fmt)}${r.value_source === 'crm' ? ' <span class="foot">CRM</span>' : r.value_source === 'deal' ? ' <span class="foot">latest ask</span>' : ''}</td><td>${esc(r.connector)}${r.on_roster ? '' : ' <span class="foot">off roster</span>'}</td><td class="date">${esc(r.asked_date)}</td><td class="date">${esc(r.agreed_date)}</td><td class="num"><b>${r.days_since_agreed}</b></td><td>${esc(r.target_title)}</td><td>${esc(r.requested_by)}</td></tr>`; }).join('')
          + `</tbody></table>`)
      + (B.nudged.length ? `<p class="foot">Nudged in the last ${B.quiet_days} days, off the list until then: ${B.nudged.map(r => `${co(r)} (${esc(r.connector)}, ${esc(r.nudged_on)}, ${r.days_since_nudged}d ago)`).join(' · ')}.</p>` : '')
      + `</details></section>`;

    // ---- assemble: five labelled bands, each carrying its membership test
    let out = `<p class="stamp" id="lp-stamp">as of <b>${esc(D.as_of)}</b></p>`;
    D.bands.forEach((b, i) => {
      out += `<div class="band" id="band-${esc(b.id)}"><div class="band-h"><span class="k">Band ${i + 1}</span><span class="t">${esc(b.title)}</span><span class="foot">${esc(b.test)}</span></div>`
        + b.sections.map(id => sec[id]).join('') + `</div>`;
    });

    root.innerHTML = out + submitBar(X);
    openFoldAt(root);
    window.addEventListener('hashchange', () => openFoldAt(root));

    // wiring: ticks + Submit, build stamp, connector tabs, downloads, upload
    wireCompletions(root, X, state);
    buildStamp(D, root.querySelector('#lp-stamp'));
    wireTabs(root);
    root.querySelector('#lp-dl-import').onclick = () => download(C.import.filename, C.import.csv);
    root.querySelector('#lp-dl-review').onclick = () => download(C.review.filename, C.review.csv);

    const drop = root.querySelector('#lp-drop'), file = root.querySelector('#lp-file'), prev = root.querySelector('#lp-preview');
    const handle = f => {
      if (!f) return;
      f.text().then(text => renderPreview(previewThreads(text, P), f.name, P, prev));
    };
    drop.addEventListener('click', e => { if (e.target !== file) file.click(); });
    file.addEventListener('change', () => handle(file.files[0]));
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', e => handle(e.dataTransfer.files[0]));

    const ta = root.querySelector('#lp-route-text'), rout = root.querySelector('#lp-route-out');
    const go = () => { rout.innerHTML = ta.value.trim() ? renderRoute(route(ta.value, P), P) : ''; };
    root.querySelector('#lp-route-go').onclick = go;
    ta.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) go(); });
    root.querySelectorAll('#route .presets button').forEach(b => b.onclick = () => { ta.value = P.route_presets[+b.dataset.i].text; go(); });
  }

  function renderRoute(x, P) {
    const T = x.target, C = x.company;
    const hover = (o, keys) => keys.map(k => `${k.replace(/_/g, ' ')} ${o[k]}`).join(' × ');
    const cue = m => `<span class="cue">“${esc(m.cue)}” ${m.score > 0 ? '+' : ''}${m.score}</span>`;
    const row = (dt, dd, cls) => `<dt>${dt}</dt><dd${cls ? ` class="${cls}"` : ''}>${dd}</dd>`;
    let target, account, priority;
    if (!T) target = `<i>none</i> <span class="foot">${esc(x.note)}</span>`;
    else if (x.status === 'refused') target = `<i>refused</i>: “${esc(T.text)}” ${cue(T)}<br><span class="foot">${x.candidates.map(c => c.kind === 'company' && c.ref ? `${co(c.ref)} <span class="foot">(customer, ${esc(c.id)})</span>` : `${esc(c.name)} <span class="foot">(${esc(c.kind)}, ${esc(c.id)})</span>`).join(' · or · ')}</span>`;
    else if (x.status === 'fund') target = `${esc(T.name)} <span class="foot">(an investor fund rather than a customer)</span> ${cue(T)}`;
    else if (!C) target = `${esc(T.text)} <span class="foot">(new to the build)</span> ${cue(T)}`;
    else if (C.network) target = `${esc(C.company_name)} <span class="foot">not on file, known to the network${T.is_domain || T.text !== C.company_name ? ` from “${esc(T.text)}”` : ''}</span> ${cue(T)}`;
    else target = `${co(C)} <span class="foot">${esc(C.company_id)} · ${C.crm ? `${esc(T.method)} ${T.confidence.toFixed(2)}` : 'on file, no CRM account'}${T.is_domain || T.text !== C.company_name ? ` from “${esc(T.text)}”` : ''}</span> ${cue(T)}`;
    if (!C) account = x.status === 'refused' ? `<i>${x.candidates.filter(c => c.kind === 'company').length ? 'two records answer to this name' : 'none'}</i>` : `<b class="warn">no CRM record</b>`;
    else if (C.network) account = `<b class="warn">no CRM record</b> <span class="foot">the company is in the network's connections but on nobody's file; create the account (see CRM Updates)</span>`;
    else if (!C.crm) account = `<b class="warn">no CRM record</b> <span class="foot">the company is on file from earlier asks; create the account (see CRM Updates)</span>`;
    else account = `${esc(C.stage)} · ${esc(C.industry || 'no industry')} · ${esc(C.owner || 'nobody')} · ${C.arr_fmt ? esc(C.arr_fmt) + ' ARR potential' : 'no ARR potential on file'}${C.stage === 'Closed Lost' ? ' · <b class="warn">Closed Lost: reopen it or close the request</b>' : ''}`;
    const others = x.others.length
      ? x.others.map(o => `<b>${esc(o.text)}</b> <span class="foot">${o.name && o.name !== o.text ? `(${esc(o.name)}) ` : ''}${esc(o.why)}</span>`).join('<br>')
      : `<span class="foot">no other company is named</span>`;
    if (x.priority) {
      const p = x.priority;
      const req = `<span class="c" title="${esc(hover(p.components, ['deal_value_musd', 'stage_weight', 'age', 'reps_waiting']))}; deal value is ${esc(p.deal_source)}; age 1.0 = posted today">request priority ${p.request_priority.toFixed(3)}</span>`;
      if (!x.top) priority = `${req} <span class="foot">× no connector score: nobody reaches ${esc(C.company_name)}, so nothing to rank</span>`;
      else priority = `<span class="ev" title="expected value = request priority × connector score">${p.expected_value.toFixed(3)}</span> = ${req} × <span class="c" title="${esc(hover(p.connector_components, ['path_strength', 'focus_fit', 'delivery_rate', 'capacity_left']))}">connector score ${p.connector_score.toFixed(3)}</span>${x.top.capacity_left <= 0 ? ` <span class="foot"><b class="warn">zero: ${esc(x.top.connector)} has no slot left this cycle</b>; ${(p.request_priority * x.top.score).toFixed(3)} the moment one frees</span>` : ''}`;
    } else priority = `<span class="foot">not scored${x.status === 'no-target' || x.status === 'refused' ? '' : ': nothing to route'}</span>`;
    let out = `<dl class="route parts">${row('target', target, 'key')}${row('account', account)}${row('title', x.title ? esc(x.title) : '<span class="foot">none named</span>')}${row('not the target', others)}${row('priority', priority)}</dl>`;
    if (x.note) out += `<div class="route-note${x.status === 'routed' ? ' ok' : ''}">${esc(x.note)}</div>`;
    if (x.paths.length) {
      const shown = C && C.path_count > x.paths.length ? ` · the best ${x.paths.length} of ${C.path_count}` : '';
      out += `<h3>Ranked connectors <span class="foot">best first: path strength × focus fit × delivery rate, as <code>build_golden.py</code> scores them${shown}</span></h3>
        <table><thead><tr><th>#</th><th>connector</th><th>path</th><th class="num">score</th><th>why</th></tr></thead><tbody>`
        + x.paths.map((p, i) => `<tr class="${p.score > 0 ? '' : 'foot'}"><td class="order">${i + 1}</td><td><b>${esc(p.connector)}</b>${p.on_roster ? '' : '<br><span class="foot">not on the roster</span>'}</td><td class="path">${esc(p.reach_type)}${p.contact ? `<br><span class="foot">${esc(p.contact)}</span>` : ''}</td><td class="num"><span class="c" title="${p.strength} strength × ${p.fit} fit × ${p.rate} delivery rate">${p.score.toFixed(3)}</span></td><td class="foot">${esc(p.reason)}${p.score > 0 ? '' : '; <b>would not be routed</b>'}</td></tr>`).join('')
        + `</tbody></table>`;
    } else if (C) out += `<p class="empty">no path on the roster</p>`;
    return out;
  }

  function renderPreview(pv, filename, P, el) {
    const flagged = pv.rows.filter(r => r.flags.length).length, offers = pv.rows.filter(r => r.offers.length).length;
    const name = (filename || 'threads.jsonl').replace(/\.[^.]+$/, '');
    let out = `<div class="kpis"><div class="kpi"><div class="v">${pv.count}</div><div class="l">threads</div><div class="s">${pv.rows.filter(r => r.filed).length} already filed</div></div>
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
              r.cands.length > 1 ? `ranked by path × fit × rate: ${r.cands.map(x => `${x.who} ${f3(x.score)}`).join(' > ')}` : ''].filter(Boolean).join('\n');
    };
    const named = (r, who) => `<b class="c" title="${esc(workings(r, who))}">${esc(who)}</b>`;
    if (pv.errors.length) out += `<div class="finding warn"><b>${plural(pv.errors.length, 'line')} skipped</b>${pv.errors.slice(0, 5).map(esc).join('<br>')}</div>`;
    out += `<div class="dl"><button id="lp-dl-preview">Export preview CSV</button><span>Nothing has been written. To apply it for real, from the repo root:<br><code>${esc(P.command.replace('{file}', filename || 'threads.jsonl'))}</code></span></div>`;
    out += `<table class="preview"><thead><tr><th>request</th><th>posted · by</th><th>resolved company</th><th>offer in replies</th><th>would route to<br><span class="fm">hover a name for the arithmetic</span></th><th>needs a human</th></tr></thead><tbody>`
      + pv.rows.map(r => `<tr class="${r.flags.length ? 'flag' : ''}"><td class="rid">${esc(r.request_id)}${r.filed ? '<br><span class="foot">filed</span>' : ''}</td><td class="date">${esc(r.posted)}<br><span class="foot">${esc(r.requested_by)}</span></td><td>${r.company_id ? `${co(r)} <span class="foot">${esc(r.company_id)}</span>` : `<i>${esc(r.company_name || 'none')}</i>`}<br><span class="foot">${esc(r.company_as_written ? `"${r.company_as_written}" · ` : '')}${esc(r.resolved_by)}</span></td><td>${r.offers.length ? r.offers.map(o => `${named(r, o.who)} <span class="foot">${esc(o.date)}</span><br><q>${esc(o.text)}</q>`).join('<br>') : '<span class="foot">none</span>'}</td><td>${r.route_to ? `${named(r, r.route_to)}<br><span class="foot">${esc(r.path)} · expected value ${esc(r.expected_value)}</span>` : `<span class="foot">${esc(r.path || 'none')}</span>`}</td><td class="foot">${r.flags.length ? r.flags.map(esc).join('<br>') : 'nothing'}</td></tr>`).join('')
      + `</tbody></table>`;
    el.innerHTML = out;
    el.querySelector('#lp-dl-preview').onclick = () => download(`${name}_preview.csv`, toCsv(P.preview_columns, pv.rows));
  }

  return { boot, bootConnector, bootBatch, extract, makeResolver, previewThreads, parseJsonl, route, normStrict, toCsv, completionRows, completionId, tickKey, postCompletions };
})();
if (typeof module !== 'undefined') module.exports = LP;
