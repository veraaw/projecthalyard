// node tests/lp_parity.js  <  {"parser": ..., "texts": [...], "threads": "<jsonl text>"}
// Prints JSON: per text the target the JS parser picks and how it resolves, plus
// the preview rows for the jsonl — tests/test_live_priorities.py compares it
// with golden/parse.py + golden/resolver.py + golden/build_golden.py.
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
  const preview = LP.previewThreads(threads, parser).rows.map(r => ({
    request_id: r.request_id, company_id: r.company_id, offer_by: r.offer_by, route_to: r.route_to, flags: r.flags,
  }));
  process.stdout.write(JSON.stringify({ extracted, preview }));
});
