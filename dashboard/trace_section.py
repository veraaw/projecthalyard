"""The "Company Trace" tab, docs/companytrace.html (built by dashboard/build_dashboard.py).

    from dashboard.trace_section import fragment, sidebar
    aside = sidebar()          # search box + the company list, for the page's left rail
    html = fragment()          # the five trace sections, rendered client-side

Every company trace (analysis/trace.py, `Trace.as_dict()`) is embedded as JSON;
the search box filters the company list on id, name, alias, or CRM account id and
clicking a company swaps the rendered trace in place. Opens on the most-requested company.
"""
import json

from analysis.trace import all_traces
from golden.build_golden import INVESTOR_NETWORK, NETWORK_HAIRCUT

MARK_LABEL = {"<-": "missed", "++": "worked", "**": "offer", "!!": "warning", "  ": ""}


def sidebar() -> str:
    """The left rail's contents: the search box and the company list the script fills in."""
    return ('<input id="trace-q" type="search" placeholder="Search: name, alias, C018, A1050" autocomplete="off" spellcheck="false" aria-label="Search companies">'
            '<nav class="toc" id="trace-matches"></nav>')


def fragment() -> str:
    traces = all_traces()
    payload = json.dumps(traces, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<style>
#trace h2.co{{font-size:26px;margin:0 0 2px}}
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
#trace .empty{{color:var(--mute);font-style:italic}}
#trace .bar.raw{{background:var(--mute);opacity:.55}}
#trace td.score,#trace td.raw{{white-space:nowrap;font-variant-numeric:tabular-nums}}
#trace tr.bypass td{{color:var(--mute);font-size:13px;border-top:none;padding-top:0}}
#trace tr.bypass b{{color:var(--ink);font-weight:600}}
#trace tr.cold td{{color:var(--mute)}}
#trace tr.cold td.route{{font-style:italic}}
#trace td.seat{{font-family:var(--mono);font-weight:600;white-space:nowrap}}
@media(max-width:720px){{#trace h2.co{{font-size:22px}}}}
</style>
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

  function kpi(v, l, s, title) {{ return `<div class="kpi"${{title ? ` title="${{esc(title)}}"` : ''}}><div class="v">${{esc(v)}}</div><div class="l">${{esc(l)}}</div>${{s ? `<div class="s">${{esc(s)}}</div>` : ''}}</div>`; }}

  function render(t) {{
    current = t.company_id;
    const h = t.header;
    const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
    // hover detail behind a header count: one line per request with its dates along the way
    const journey = rows => rows.map(q => [`${{q.request_id}} filed ${{q.date}} (${{q.target_title || '?'}}, ${{q.requested_by || 'unattributed'}})`,
      q.routed_to ? `routed to ${{q.routed_to}}${{q.routed_on ? ' ' + q.routed_on : ''}}` : '', q.asked_date ? `asked ${{q.asked_date}}` : '',
      q.response_date ? `replied ${{q.response_date}}` : '', q.intro_date ? `intro ${{q.intro_date}}` : '', q.meeting_booked ? 'meeting booked' : '',
      q.status ? `filed "${{q.status}}"` : ''].filter(Boolean).join(' → ')).join('\n');
    const people = rows => {{
      const by = new Map();
      for (const q of rows) {{ const k = q.requested_by || 'unattributed'; if (!by.has(k)) by.set(k, []); by.get(k).push(q); }}
      return [...by].map(([who, qs]) => `${{who}}: ${{qs.map(q => `${{q.request_id}} ${{q.date}} ${{q.target_title || '?'}}`).join(', ')}}`).join('\n');
    }};
    let out = `<h2 class="co">${{esc(t.company_name)}} <span class="foot">${{esc(t.company_id)}}${{h.crm_account_ids ? ' · ' + esc(h.crm_account_ids) : ''}}${{h.domain ? ' · ' + esc(h.domain) : ''}}</span></h2>`;
    out += `<p class="aka">${{h.also_known_as.length ? 'also goes by ' + h.also_known_as.map(esc).join(' · ') : 'no other spellings on file'}}${{h.duplicate_accounts && h.duplicate_accounts !== 'no' ? ' · duplicate accounts: ' + esc(h.duplicate_accounts) : ''}}</p>`;
    const rt = h.routing;
    out += `<div class="kpis">${{kpi(rt.furthest, 'routing stage', [rt.booked ? `intro ${{rt.booked.intro_date || 'undated'}} · ${{rt.booked.request_id}} · ${{rt.booked.connector}}` : '', rt.latest && rt.latest !== rt.furthest ? 'latest ask: ' + rt.latest : ''].filter(Boolean).join(' · '))}}${{kpi(h.stage || '?', 'CRM stage', h.industry)}}${{kpi(h.owner || 'none', 'CRM owner')}}${{kpi(h.value.value_usd, 'deal value', h.value.source, h.value.by_request.filter(q => q.value_usd).map(q => `${{q.request_id}} ${{q.date}} ${{q.target_title || '?'}}: ${{q.value_usd}}`).join('\n') || 'no request carries a deal value')}}${{kpi(h.requests, 'requests', '', h.request_rows.map(q => `${{q.request_id}} ${{q.date}} ${{q.target_title || '?'}} · ${{q.requested_by || 'unattributed'}} · ${{q.stage}} (filed "${{q.status}}")`).join('\n'))}}${{kpi(h.people, 'people asking', '', people(h.request_rows))}}${{kpi(rt.counts.routed || 0, 'routed', 'awaiting the ask', journey(h.request_rows.filter(q => q.stage === 'routed')) || 'no request sits at routed')}}${{kpi(rt.counts.closed || 0, 'closed — no path', 'filed closed, not asked', journey(h.request_rows.filter(q => q.stage === 'closed')) || 'no request filed Closed - no path')}}${{kpi(h.titles.length, 'different titles wanted', h.titles.join(' · '))}}</div>`;

    if (t.disagreements.length) {{
      out += `<h3>2. Where the files disagree</h3>` + t.disagreements.map(d => `<div class="finding warn">${{esc(d)}}</div>`).join('');
    }}

    out += `<h3>3. Who can reach them</h3>`;
    if (!t.reach.length) out += `<p class="empty">nobody in the network reaches this company</p>`;
    else {{
      const maxScore = Math.max(...t.reach.map(p => p.route_score)) || 1, maxRaw = Math.max(...t.reach.map(p => p.strength)) || 1;
      const haircut = t.reach.some(p => p.reach_type.startsWith('{INVESTOR_NETWORK}')) ? `; {INVESTOR_NETWORK} rows (our network, not our roster) rank below every roster path and take a {round((1 - NETWORK_HAIRCUT) * 100)}% haircut on route score` : '';
      out += `<p class="foot">ranked by route score = strength × focus fit × delivery rate, the allocator's sort key${{haircut}}; strength is the raw path alone</p>`;
      out += `<table><thead><tr><th>route score</th><th>strength</th><th>connector</th><th>reach</th><th>contact</th><th>evidence</th></tr></thead><tbody>` +
        t.reach.map(p => `<tr><td class="score"><span class="bar" style="width:${{Math.round(90 * p.route_score / maxScore)}}px"></span>${{p.route_score.toFixed(3)}}</td><td class="raw" title="fit ${{p.fit}} × delivery rate ${{p.rate}}"><span class="bar raw" style="width:${{Math.round(90 * p.strength / maxRaw)}}px"></span>${{p.strength.toFixed(3)}}</td><td>${{esc(p.connector)}} <span class="foot">${{esc(p.connector_type)}}</span></td><td>${{esc(p.reach_type)}}</td><td>${{esc([p.contact_name, p.contact_title].filter(Boolean).join(', ') || '?')}}</td><td class="foot">${{esc(p.evidence)}}</td></tr>`
          + (p.bypass ? `<tr class="bypass"><td colspan="6"><b>strongest path, not where it went:</b> ${{esc(p.bypass)}}</td></tr>` : '')).join('') +
        `</tbody></table>`;
    }}

    const nEv = t.chronology.reduce((a, b) => a + b.length, 0);
    out += `<h3>4. Chronology: ${{plural(nEv, 'event')}}, ${{plural(h.requests, 'request')}}, newest first, as of ${{esc(t.as_of)}}</h3>`;
    out += `<p class="legend">markers <b class="missed">&lt;-</b>missed <b class="worked">++</b>worked <b class="offer">**</b>offer <b class="warning">!!</b>warning${{nEv > 12 ? ' · the table scrolls' : ''}}</p>`;
    out += `<table class="tall nopage"><thead><tr><th></th><th>date</th><th>source</th><th>who</th><th>what happened</th></tr></thead><tbody>`;
    t.chronology.forEach((block, i) => {{
      if (i) out += `<tr class="gap"><td colspan="5"></td></tr>`;
      block.forEach(e => {{
        const cls = MARK[e.mark] || '';
        out += `<tr class="${{cls}}"><td class="mark">${{esc(e.mark.trim())}}</td><td class="date">${{esc(e.date)}}</td><td class="src">${{esc(e.source)}}</td><td>${{esc(e.who)}}</td><td class="what">${{esc(e.what)}}</td></tr>`;
      }});
    }});
    out += `</tbody></table>`;

    if (t.orbit.length) {{
      const cold = t.orbit.filter(r => !r.reachable_via).length, net = t.orbit.filter(r => r.reachable_via === '{INVESTOR_NETWORK}').length;
      out += `<h3>5. Additional Investor and Operator Network</h3>`;
      out += `<p class="foot">${{t.orbit.length}} ${{t.orbit.length === 1 ? 'person' : 'people'}} from investor_network.csv, ${{net}} askable as {INVESTOR_NETWORK} paths, ${{cold}} with no warm path · a view of section 3 and the roster's exports: nothing here is scored or allocated on its own</p>`;
      out += `<table><thead><tr><th>person</th><th>role</th><th>fund</th><th>board seat</th><th>source</th><th>warm path</th></tr></thead><tbody>` +
        t.orbit.map(r => `<tr class="${{r.reachable_via ? '' : 'cold'}}"><td>${{esc(r.person)}}</td><td class="foot">${{esc(r.role)}}</td><td>${{esc(r.fund)}}</td><td class="seat">${{r.board_seat ? 'yes' : ''}}</td><td class="src">${{esc(r.source)}}</td><td class="route">${{esc(r.route)}}</td></tr>`).join('') +
        `</tbody></table>`;
    }}
    body.innerHTML = out;
    mark();
  }}

  function mark() {{
    let on = null;
    matches.querySelectorAll('a').forEach(a => {{ const is = a.dataset.id === current; a.classList.toggle('on', is); if (is) on = a; }});
    const side = matches.closest('.side');
    if (on && side && side.scrollHeight > side.clientHeight) {{
      const top = on.offsetTop - side.offsetTop;
      if (top < side.scrollTop + 20 || top > side.scrollTop + side.clientHeight - 40) side.scrollTop = top - side.clientHeight / 2;
    }}
  }}

  function update() {{
    const hits = filter(q.value);
    if (count) count.textContent = q.value.trim() ? `${{hits.length}} of ${{T.length}}` : `${{T.length}}`;
    matches.innerHTML = hits.map(t => `<a href="#${{esc(t.company_id)}}" data-id="${{esc(t.company_id)}}">${{esc(t.company_name)}}<span class="n">${{t.header.requests}}</span></a>`).join('')
      || `<p class="empty">no company matches</p>`;
    matches.querySelectorAll('a').forEach(a => a.onclick = e => {{ e.preventDefault(); render(T.find(t => t.company_id === a.dataset.id)); }});
    const exact = hits.find(t => norm(t.company_name) === norm(q.value) || t.company_id.toLowerCase() === q.value.trim().toLowerCase());
    if (exact) render(exact);
    else if (hits.length === 1) render(hits[0]);
    else if (!hits.some(t => t.company_id === current) && hits.length) render(hits[0]);
    else mark();
  }}
  q.addEventListener('input', update);
  // #C018 (a link from another tab) opens that company; the hash is kept in step so the view is shareable
  function fromHash() {{
    const id = decodeURIComponent(location.hash.slice(1));
    const t = id && T.find(t => t.company_id === id);
    if (t) {{ q.value = ''; update(); render(t); }}
    else update();
  }}
  window.addEventListener('hashchange', fromHash);
  fromHash();
  const _render = render;
  render = function (t) {{ _render(t); if (t && location.hash !== '#' + t.company_id) history.replaceState(null, '', '#' + t.company_id); }};
}})();
</script>
"""
