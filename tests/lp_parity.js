// node tests/lp_parity.js  <  {"parser": ..., "texts": [...], "threads": "<jsonl text>"}
// Prints JSON: per text the target the JS parser picks and how it resolves, what
// the route panel would do with it, plus the preview rows for the jsonl —
// tests/test_live_priorities.py and tests/test_parse.py compare it with
// golden/parse.py + golden/resolver.py + golden/build_golden.py.
const path = require('path');
const LP = require(path.join(__dirname, '..', 'dashboard', 'live_priorities.js'));

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  const { parser, texts, threads } = JSON.parse(input);
  const resolver = LP.makeResolver(parser.resolver);
  const extracted = texts.map(text => {
    const ex = LP.extract(text, parser, resolver);
    const t = ex.target;
    return {
      mentions: ex.mentions.map(m => [m.start, m.text, m.cue, m.score, m.is_domain]),
      target: t ? t.text : null,
      target_id: t && t.resolution ? t.resolution.entity_id : '',
      method: t && t.resolution ? t.resolution.method : '',
      candidates: t && t.resolution ? t.resolution.candidates.map(c => c.id) : [],
    };
  });
  const routed = texts.map(text => {
    const x = LP.route(text, parser);
    return {
      status: x.status, title: x.title, target: x.target ? x.target.text : null,
      company_id: x.company ? x.company.company_id : '', company_name: x.company ? x.company.company_name : '',
      crm: x.crm, candidates: x.candidates.map(c => c.id), others: x.others.map(o => o.text),
      top: x.top ? { connector: x.top.connector, reach_type: x.top.reach_type, contact: x.top.contact, score: x.top.score } : null,
      paths: x.paths.map(p => p.connector), expected_value: x.priority ? x.priority.expected_value : null,
    };
  });
  const preview = threads ? LP.previewThreads(threads, parser).rows.map(r => ({
    request_id: r.request_id, company_id: r.company_id, offer_by: r.offer_by, route_to: r.route_to, flags: r.flags,
  })) : [];
  process.stdout.write(JSON.stringify({ extracted, routed, preview }));
});
