"""The "Company Trace" tab, docs/companytrace.html (built by dashboard/build_dashboard.py).

    from dashboard.trace_section import fragment
    html = fragment()          # <div> with a search box + the five trace sections, rendered client-side

Every company trace (analysis/trace.py, `Trace.as_dict()`) is embedded as JSON;
a search box matches on id, name, alias, or CRM account id and swaps the
rendered trace in place. Opens on the most-requested company.
"""
import json

from analysis.trace import all_traces

MARK_LABEL = {"<-": "missed", "++": "worked", "**": "offer", "!!": "warning", "  ": ""}


def fragment() -> str:
    traces = all_traces()
    payload = json.dumps(traces, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<style>
#trace .search{{display:flex;gap:12px;align-items:center;margin:12px 0 4px}}
#trace .search input{{flex:1;max-width:460px;font:15px var(--sans);padding:9px 12px;border:1px solid var(--ink);background:var(--surface);color:var(--ink);outline:none}}
#trace .search input:focus{{border-color:var(--blue)}}
#trace .matches{{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 18px;min-height:30px}}
#trace .matches button{{font:13px var(--sans);padding:5px 10px;border:1px solid var(--line);background:var(--surface);color:var(--ink);cursor:pointer}}
#trace .matches button:hover,#trace .matches button.on{{border-color:var(--blue);color:var(--blue)}}
#trace .matches .n{{color:var(--mute);margin-left:5px}}
#trace h2.co{{font-size:26px;margin:18px 0 2px}}
#trace .aka{{color:var(--mute);font-size:14px;margin:0 0 10px}}
#trace table td.mark{{font-family:var(--mono);font-weight:600;width:28px;white-space:nowrap}}
#trace tr.missed td.mark,#trace tr.missed td.what{{color:var(--warn)}}
#trace tr.worked td.mark{{color:#1d6b2a}} #trace tr.worked td.what{{color:#1d6b2a}}
#trace tr.offer td.mark,#trace tr.offer td.what{{color:var(--blue)}}
#trace tr.warning td.mark{{color:var(--warn)}}
#trace tr.gap td{{border-bottom:none;padding:9px 0 0;background:var(--bg)}}
#trace td.src,#trace td.rid{{font-family:var(--mono);font-size:12px;color:var(--mute);white-space:nowrap}}
#trace td.date{{white-space:nowrap;font-variant-numeric:tabular-nums}}
#trace .bar{{display:inline-block;height:9px;background:var(--blue);vertical-align:middle;margin-right:8px}}
#trace .legend{{color:var(--mute);font-size:13px;font-family:var(--sans);margin:0 0 8px}}
#trace .legend b{{font-family:var(--mono);font-weight:600;margin:0 4px 0 12px}}
#trace .legend b.missed{{color:var(--warn)}} #trace .legend b.worked{{color:#1d6b2a}} #trace .legend b.offer{{color:var(--blue)}} #trace .legend b.warning{{color:var(--warn)}}
#trace td.order{{font-family:var(--mono);color:var(--mute)}}
#trace .empty{{color:var(--mute);font-style:italic}}
</style>
<div class="search">
  <input id="trace-q" type="search" placeholder="Search a company — name, alias, C018, A1050…" autocomplete="off" spellcheck="false">
  <span class="foot" id="trace-count"></span>
</div>
<div class="matches" id="trace-matches"></div>
<div id="trace-body"></div>
<script id="trace-data" type="application/json">{payload}</script>
<script>
(function(){{
  const T = JSON.parse(document.getElementById('trace-data').textContent);
  const q = document.getElementById('trace-q'), matches = document.getElementById('trace-matches'),
        body = document.getElementById('trace-body'), count = document.getElementById('trace-count');
  const MARK = {json.dumps(MARK_LABEL)};
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
  const norm = s => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  let current = null;

  function filter(text) {{
    const n = norm(text);
    if (!n) return T;
    const words = n.split(' ');
    return T.filter(t => {{ const s = norm(t.search); return words.every(w => s.includes(w)); }});
  }}

  function kpi(v, l, s) {{ return `<div class="kpi"><div class="v">${{esc(v)}}</div><div class="l">${{esc(l)}}</div>${{s ? `<div class="s">${{esc(s)}}</div>` : ''}}</div>`; }}

  function render(t) {{
    current = t.company_id;
    const h = t.header;
    const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
    let out = `<h2 class="co">${{esc(t.company_name)}} <span class="foot">${{esc(t.company_id)}}${{h.crm_account_ids ? ' · ' + esc(h.crm_account_ids) : ''}}${{h.domain ? ' · ' + esc(h.domain) : ''}}</span></h2>`;
    out += `<p class="aka">${{h.also_known_as.length ? 'also goes by ' + h.also_known_as.map(esc).join(' · ') : 'no other spellings on file'}}${{h.duplicate_accounts && h.duplicate_accounts !== 'no' ? ' · duplicate accounts: ' + esc(h.duplicate_accounts) : ''}}</p>`;
    out += `<div class="kpis">${{kpi(h.stage || '?', 'stage', h.industry)}}${{kpi(h.owner || 'none', 'CRM owner')}}${{kpi(h.value_usd, 'deal value', h.largest_request_usd ? 'largest request ' + h.largest_request_usd : '')}}${{kpi(h.requests, 'requests')}}${{kpi(h.people, 'people asking')}}${{kpi(h.titles.length, 'different titles wanted', h.titles.join(' · '))}}</div>`;

    if (t.disagreements.length) {{
      out += `<h3>2. Where the files disagree</h3>` + t.disagreements.map(d => `<div class="finding warn">${{esc(d)}}</div>`).join('');
    }}

    out += `<h3>3. Who can reach them</h3>`;
    if (!t.reach.length) out += `<p class="empty">nobody in the network reaches this company</p>`;
    else {{
      const max = t.reach[0].strength || 1;
      out += `<table><thead><tr><th>strength</th><th>connector</th><th>reach</th><th>contact</th><th>evidence</th></tr></thead><tbody>` +
        t.reach.map(p => `<tr><td><span class="bar" style="width:${{Math.round(90 * p.strength / max)}}px"></span>${{p.strength.toFixed(3)}}</td><td>${{esc(p.connector)}} <span class="foot">${{esc(p.connector_type)}}</span></td><td>${{esc(p.reach_type)}}</td><td>${{esc([p.contact_name, p.contact_title].filter(Boolean).join(' — ') || '?')}}</td><td class="foot">${{esc(p.evidence)}}</td></tr>`).join('') +
        `</tbody></table>`;
    }}

    const nEv = t.chronology.reduce((a, b) => a + b.length, 0);
    out += `<h3>4. Chronology — ${{plural(nEv, 'event')}}, ${{plural(h.requests, 'request')}}, oldest first, as of ${{esc(t.as_of)}}</h3>`;
    out += `<p class="legend">markers <b class="missed">&lt;-</b>missed <b class="worked">++</b>worked <b class="offer">**</b>offer <b class="warning">!!</b>warning</p>`;
    out += `<table><thead><tr><th></th><th>date</th><th>source</th><th>who</th><th>what happened</th></tr></thead><tbody>`;
    t.chronology.forEach((block, i) => {{
      if (i) out += `<tr class="gap"><td colspan="5"></td></tr>`;
      block.forEach(e => {{
        const cls = MARK[e.mark] || '';
        out += `<tr class="${{cls}}"><td class="mark">${{esc(e.mark.trim())}}</td><td class="date">${{esc(e.date)}}</td><td class="src">${{esc(e.source)}}</td><td>${{esc(e.who)}}</td><td class="what">${{esc(e.what)}}</td></tr>`;
      }});
    }});
    out += `</tbody></table>`;

    out += `<h3>5. Next steps, by person, cheapest first</h3>`;
    if (!t.next_steps.length) out += `<p class="empty">nobody needs to do anything</p>`;
    else out += `<table><thead><tr><th>#</th><th>who</th><th>role</th><th>action</th><th>why</th><th>requests</th></tr></thead><tbody>` +
      t.next_steps.map((s, i) => `<tr><td class="order">${{i + 1}}</td><td>${{esc(s.who)}}</td><td class="foot">${{esc(s.role)}}</td><td><b>${{esc(s.action)}}</b></td><td>${{esc(s.why)}}</td><td class="rid">${{esc(s.request_ids.join(', ') || '—')}}</td></tr>`).join('') +
      `</tbody></table>`;
    body.innerHTML = out;
    matches.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.id === current));
  }}

  function update() {{
    const hits = filter(q.value);
    count.textContent = `${{hits.length}} of ${{T.length}} companies`;
    matches.innerHTML = hits.slice(0, 12).map(t => `<button data-id="${{esc(t.company_id)}}">${{esc(t.company_name)}}<span class="n">${{t.header.requests}}</span></button>`).join('')
      + (hits.length > 12 ? `<span class="foot" style="align-self:center">+${{hits.length - 12}} more — keep typing</span>` : '');
    matches.querySelectorAll('button').forEach(b => b.onclick = () => render(T.find(t => t.company_id === b.dataset.id)));
    const exact = hits.find(t => norm(t.company_name) === norm(q.value) || t.company_id.toLowerCase() === q.value.trim().toLowerCase());
    if (exact) render(exact);
    else if (hits.length === 1) render(hits[0]);
    else if (!hits.some(t => t.company_id === current) && hits.length) render(hits[0]);
    else matches.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.id === current));
  }}
  q.addEventListener('input', update);
  // #C018 (a link from another tab) opens that company; the hash is kept in step so the view is shareable
  function fromHash() {{
    const id = decodeURIComponent(location.hash.slice(1));
    const t = id && T.find(t => t.company_id === id);
    if (t) q.value = t.company_id;
    update();
  }}
  window.addEventListener('hashchange', fromHash);
  fromHash();
  const _render = render;
  render = function (t) {{ _render(t); if (t && location.hash !== '#' + t.company_id) history.replaceState(null, '', '#' + t.company_id); }};
}})();
</script>
"""
