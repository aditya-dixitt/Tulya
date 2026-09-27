/* ===========================================================================
   TULYA — modules layer
   ---------------------------------------------------------------------------
   Material Passport · Engineering Evidence · Standards Knowledge Graph ·
   Analytics · Collaboration · Cross-CPSE Impact Simulator · Procurement
   Intelligence, plus the operational tables on the overview.

   Every one of these reads TULYA.materials — the single derived model built
   from the material records the console already ships. There is no second
   dataset and no page-local fixture.
   =========================================================================== */

/* ---------- shared vocabulary ------------------------------------------- */
const VERDICT_GLYPH = { IDENTICAL: '=', EQUIVALENT: '≈', CONDITIONAL: '~',
                        DIFFERENT: '≠', CONFLICT: '✕', UNRESOLVED: '?' };

const VERDICT_SHORT = { IDENTICAL: 'IDENTICAL', EQUIVALENT: 'EQUIVALENT',
  CONDITIONAL: 'CONDITIONAL', DIFFERENT: 'DIFFERENT', CONFLICT: 'CONFLICT', UNRESOLVED: 'UNRESOLVED' };

/* compact: the short label, for a table cell. The full wording stays on hover. */
function verdictBadge(key, withNext, compact) {
  const v = TULYA.VERDICTS[key]; if (!v) return '';
  const label = compact ? VERDICT_SHORT[key] : v.label;
  return `<span class="vb ${v.cls}" title="${v.label} \u2014 ${v.next}"><span class="g">${VERDICT_GLYPH[key]}</span>${label}</span>` +
         (withNext ? `<span class="vb-next">${v.next}</span>` : '');
}
const qty = n => Number(n || 0).toLocaleString('en-US');
const el = id => document.getElementById(id);
const clock = ts => new Date(ts * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

/* the trust model, as a process rail rather than six billboards */
function procRailHTML() {
  return [
    ['ai',   'Candidate',  'semantic retrieval proposes',   'The engine retrieves candidates on meaning and text. It never merges anything.'],
    ['ev',   'Evidence',   'attributes and standards read', 'Specifications are recovered from both descriptions and compared one by one.'],
    ['veto', 'Validation', 'conflicts block the merge',     'A specification known on both sides and disagreeing forces the score to zero.'],
    ['gov',  'Steward',    'a named person decides',        'Nothing maps until a steward signs it, and the decision carries their name.'],
    ['cnmc', 'CNMC',       'legacy codes retained',         'A Common National Material Code maps the legacy ERP codes; it does not replace them.'],
    ['',     'Audit',      'traceable and actionable',      'Every decision is appended to the audit log and becomes visible to procurement.']
  ].map(([cls, t, d, tip]) =>
    `<div class="s ${cls}" title="${tip}"><div class="t"><i></i>${t}</div><div class="d">${d}</div></div>`
  ).join('');
}

/* app-bar breadcrumb, driven by the panel the rail switches to */
const PAGE_MAP = {
  overview: ['Workspace', 'Overview'], challenge: ['Workspace', 'Test TULYA'],
  queue: ['Workspace', 'Review Queue'], auto: ['Workspace', 'Auto-Suggest'],
  passport: ['Material Intelligence', 'Material Passport'],
  analytics: ['Material Intelligence', 'Analytics'],
  simulator: ['Material Intelligence', 'Impact Simulator'],
  procurement: ['Operations', 'Procurement Intelligence'],
  collab: ['Operations', 'Collaboration'],
  groups: ['Governance', 'Golden Records'], vetoed: ['Governance', 'Hard-Key Vetoes'],
  standards: ['Governance', 'Standards Knowledge Graph'], audit: ['Governance', 'Audit Log'],
  performance: ['System', 'Performance'], search: ['System', 'Search']
};
function installChrome() {
  const base = switchPanel;
  switchPanel = function (name) {
    base(name);
    const p = PAGE_MAP[name] || ['Workspace', name];
    if (el('crumbGroup')) el('crumbGroup').textContent = p[0];
    if (el('crumbPage')) el('crumbPage').textContent = p[1];
  };
}

/* ---------- small table helpers ----------------------------------------- */
function tableHTML(cols, rows, opts) {
  opts = opts || {};
  if (!rows.length) return `<div class="empty">${opts.empty || 'Nothing to show.'}</div>`;
  return `<div class="twrap"><table><thead><tr>${
    cols.map(c => `<th${c.num ? ' class="num"' : ''}>${c.h}</th>`).join('')
  }</tr></thead><tbody>${rows.join('')}</tbody></table></div>` +
  (opts.foot ? `<div class="tfoot">${opts.foot}</div>` : '');
}
function showing(n, total, label) {
  return `<span class="count">Showing <b>${qty(n)}</b> of <b>${qty(total)}</b> ${label || 'rows'}</span>`;
}

/* ===========================================================================
   ENGINEERING EVIDENCE — a comparison table
   =========================================================================== */
function evidenceTableHTML(it) {
  const rows = TULYA.evidenceRows(it);
  const a = it.record_a, b = it.record_b;
  const mism = rows.filter(r => r.verdict === 'MISMATCH');
  const scope = rows.filter(r => r.verdict === 'REVIEW SCOPE');
  const agree = rows.filter(r => r.verdict === 'MATCH');

  const line = r => {
    const cls = r.verdict === 'MATCH' ? 'match' : r.verdict === 'MISMATCH' ? 'mismatch'
              : r.verdict === 'REVIEW SCOPE' ? 'scope' : 'unknown';
    const res = r.verdict === 'MATCH' ? '✓ MATCH' : r.verdict === 'MISMATCH' ? '✕ CONFLICT'
              : r.verdict === 'REVIEW SCOPE' ? 'REVIEW SCOPE' : 'NOT READABLE';
    const dim = v => v == null ? '<span style="color:var(--n-300)">—</span>' : esc(v);
    return `<div class="ev-line ${cls}">
      <div class="k">${esc(r.label)}${r.hard ? '<span class="hard">HARD KEY</span>' : ''}</div>
      <div class="val">${dim(r.a)}</div><div class="val">${dim(r.b)}</div>
      <div class="res">${res}</div></div>`;
  };

  let foot;
  if (mism.length) {
    foot = `<b>Hard specification conflict.</b> ${mism.map(r => esc(r.label) + ' reads ' + esc(r.a) +
      ' against ' + esc(r.b)).join('; ')}. A specification known on both sides and disagreeing forces the
      score to zero however similar the text is — the merge is refused, not averaged away.`;
  } else if (scope.length) {
    foot = `<b>Standards scope differs.</b> The attributes agree, but the records cite different
      designations. A scoped cross-reference is not an assertion of equivalence, so this routes to
      engineering review rather than straight to a steward.`;
  } else {
    foot = `<b>${agree.length} specification${agree.length === 1 ? '' : 's'} agree, none in conflict.</b>
      Attribute agreement is what supports this proposal; the text similarity on its own would not.`;
  }

  return `<div class="ev-table">
    <div class="ev-head">
      <div>Attribute</div>
      <div class="src">Record A<b>${esc(a.cpse)} · ${esc(a.legacy_code)}</b></div>
      <div class="src">Record B<b>${esc(b.cpse)} · ${esc(b.legacy_code)}</b></div>
      <div>Result</div>
    </div>
    ${rows.map(line).join('') || '<div class="ev-line unknown"><div class="k">specifications</div><div class="val" style="grid-column:2/5;color:var(--n-400)">No specification was readable on both sides.</div></div>'}
    <div class="ev-foot">${foot}</div>
  </div>
  <div class="notequal"><b>SIMILARITY ≠ EQUIVALENCE</b>
    <span>Text similarity is ${(it.cos * 100).toFixed(1)}% on this pair. The result column above decides
    whether it may be mapped — not the score.</span></div>`;
}

/* ===========================================================================
   OVERVIEW — operational tables
   =========================================================================== */
const ACTION_LABEL = { approve: 'Approved', reject: 'Rejected', unmerge: 'Split out',
                       conditional: 'Marked conditional', verify: 'Verification requested',
                       assign: 'Assignment', comment: 'Comment', engineering: 'Engineering review',
                       escalate: 'Escalated' };

function renderOverviewOps() {
  if (el('ovUpdated')) el('ovUpdated').textContent = new Date().toLocaleString('en-GB',
    { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

  /* cross-CPSE opportunities */
  const rows = TULYA.procurementRows().filter(r => r.material.cross_cpse).slice(0, 6);
  el('ovOpportunities').innerHTML = crossTable(rows, 'ovOpportunities');

  /* Recent activity.
     This column is a third of the page: two stacked tables were squeezing
     material descriptions into seven-line columns. The same append-only audit
     entries are rendered as a feed instead — one line of event, one of
     context — which is what the width can carry honestly. Nothing is added:
     every row is an entry STATE.audit already holds. */
  el('ovDecisions').innerHTML = '';
  const act = STATE.audit.slice(0, 7);
  el('ovActivity').innerHTML = !act.length
    ? `<div class="feed-empty">No activity in this browser yet. Approve or reject a pair in the
         review queue and it is recorded here, and in the audit log, as it happens.</div>`
    : `<div class="feed-list">` + act.map(r => {
        const rec = RECORDS[r.record_a] || {};
        const kind = ['approve','reject','unmerge','conditional'].includes(r.action) ? r.action : 'event';
        const when = new Date(r.ts * 1000);
        return `<div class="fd" title="${esc(when.toLocaleString('en-GB'))}">`
          + `<span class="fd-dot ${kind}"></span>`
          + `<div class="fd-b">`
          +   `<div class="fd-t"><b>${esc(ACTION_LABEL[r.action] || r.action)}</b>`
          +     (rec.description ? ` <span class="fd-mat">${esc(rec.description)}</span>` : '')
          +   `</div>`
          +   `<div class="fd-m">`
          +     (rec.cpse ? cpseMark(rec.cpse, 20) : '')
          +     `<span class="mono">${r.record_a}${r.record_b != null ? ' &#8596; ' + r.record_b : ''}</span>`
          +     (r.score != null ? ` <span class="sep">&#183;</span> ${(r.score*100).toFixed(1)}%` : '')
          +     ` <span class="sep">&#183;</span> ${esc(r.steward || '—')}`
          +   `</div>`
          + `</div>`
          + `<time class="fd-ts">${clock(r.ts)}</time>`
          + `</div>`;
      }).join('')
      + `<div class="feed-foot">${showing(act.length, STATE.audit.length, 'entries')}`
      + `<button class="jump" onclick="switchPanel('audit')">Full audit log</button></div></div>`;

  ctRenderPanels();
}

function crossTable(rows, tag) {
  return tableHTML(
    [{ h: 'Material' }, { h: 'CNMC' }, { h: 'CPSEs' }, { h: 'Stock', num: 1 },
     { h: 'Demand', num: 1 }, { h: 'Coverage' }, { h: 'Status' }, { h: '' }],
    rows.map(r => `<tr>
      <td>${esc(r.material.description.slice(0, 44))}<div class="site">${esc(r.material.category_label)}</div></td>
      <td class="mono">${esc(r.material.cnmc)}</td>
      <td><div class="cpse-stack">${r.material.cpses.map(c=>cpseTag(c, '', 20)).join('')}</div></td>
      <td class="num mono">${qty(r.available)}</td>
      <td class="num mono">${qty(r.required)}</td>
      <td><div class="cov-mini"><span class="t"><i class="${r.coverage >= 1 ? '' : 'part'}" style="width:${(r.coverage * 100).toFixed(0)}%"></i></span>
        <span class="mono">${(r.coverage * 100).toFixed(0)}%</span></div></td>
      <td><span class="sig ${SIGCLS[r.signal]}" title="${r.signal}">${SIG_SHORT[r.signal] || r.signal}</span></td>
      <td><div class="rowacts"><button onclick="gotoProcurement('${r.material.id}')">Open</button></div></td>
    </tr>`),
    { empty: 'No cross-CPSE opportunity in the current model.',
      foot: rows.length ? `<span class="count">Quantities <b>simulated</b></span>
        <button class="jump" onclick="switchPanel('procurement')">All procurement opportunities</button>` : '' });
}

/* ===========================================================================
   MATERIAL PASSPORT
   =========================================================================== */
let PASSPORT_ID = null, PASSPORT_FILTER = '';

/* Which CPSEs hold this identity, and on how many of their own legacy codes.
   The per-identity count is read off this material's source records; the split
   total beside it is the tally in DATA.cpse_records. Neither is estimated. */
function cpsePartRows(m){
  const by = {};
  (m.legacy_identities || []).forEach(l=>{
    const c = l.cpse; if (!c) return;
    by[c] = by[c] || {n:0, plants:new Set()};
    by[c].n++; if (l.plant) by[c].plants.add(l.plant);
  });
  const names = Object.keys(by).sort((a,b)=>by[b].n-by[a].n || a.localeCompare(b));
  if (!names.length) return '<div class="hint">No source record names a CPSE for this identity.</div>';
  return names.map(c=>{
    const d = by[c], total = cpseRecordCount(c);
    return `<div class="cp-row">${cpseMark(c,24)}`
      + `<span class="cp-n"><b>${esc(c)}</b>`
      + `<span>${d.n} legacy code${d.n===1?'':'s'}`
      + (d.plants.size ? ` &#183; ${d.plants.size} plant${d.plants.size===1?'':'s'}` : '') + `</span></span>`
      + `<span class="cp-t">${total!=null ? total.toLocaleString()+'<span>materials in split</span>' : '<span class="none">count unavailable</span>'}</span>`
      + `</div>`;
  }).join('');
}

function bestCaseFor(m) {
  if (!m.cases.length) return null;
  const order = { CONFLICT: 0, CONDITIONAL: 1, UNRESOLVED: 2, EQUIVALENT: 3, IDENTICAL: 4, DIFFERENT: 5 };
  return m.cases.slice().sort((x, y) =>
    order[TULYA.verdictOf(x).key] - order[TULYA.verdictOf(y).key] || y.score - x.score)[0];
}
function openPassport(matId) { PASSPORT_ID = matId; switchPanel('passport'); renderPassport(); }
function passportForRecord(rid) {
  const m = TULYA.byRecord[rid];
  if (m) openPassport(m.id); else toast('No material identity for that record');
}

function renderPassport() {
  const list = TULYA.materials;
  if (!PASSPORT_ID || !TULYA.byId[PASSPORT_ID]) PASSPORT_ID = (list[0] || {}).id;
  const q = PASSPORT_FILTER.toLowerCase();
  const shown = list.filter(x => !q || (x.description + ' ' + x.cnmc + ' ' + x.cpses.join(' ') + ' ' +
                 x.legacy_identities.map(l => l.legacy_code).join(' ')).toLowerCase().includes(q));

  if (el('ppCount')) el('ppCount').textContent = qty(list.length);
  el('ppListCount').innerHTML = showing(Math.min(60, shown.length), shown.length, 'materials') +
    (q ? ` <button class="jump" onclick="clearPassportFilter()">Clear</button>` : '');

  el('passportList').innerHTML = shown.slice(0, 60).map(x =>
    `<button class="r${x.id === PASSPORT_ID ? ' on' : ''}" onclick="openPassport('${x.id}')">
       <div class="d">${esc(x.description)}</div>
       <div class="m"><span>${x.records.length} legacy</span><span class="cpse-stack">${x.cpses.map(c=>cpseMark(c,20)).join('')}</span></div>
     </button>`).join('') || '<div class="empty">No material matches that filter.</div>';

  const m = TULYA.byId[PASSPORT_ID];
  el('passportDetail').innerHTML = m ? passportHTML(m) : '<div class="empty">No material selected.</div>';
}
function clearPassportFilter() { PASSPORT_FILTER = ''; el('passportSearch').value = ''; renderPassport(); }

function passportHTML(m) {
  const c = bestCaseFor(m);
  const v = c ? TULYA.verdictOf(c) : { key: m.equivalence_status, reason: 'no candidate pair shipped for this record' };
  const fam = TULYA.STANDARDS[m.family] || { nodes: [], edges: [] };
  const approved = c && STATE.reviews[pkey(c.a, c.b)] && STATE.reviews[pkey(c.a, c.b)].action === 'approve';

  const analysis = c ? [
    ['Semantic similarity', (c.cos * 100).toFixed(1) + '%', 'measured'],
    ['Token similarity', (c.fuz * 100).toFixed(1) + '%', 'measured'],
    ['Attribute agreement', (c.explain.attributes || []).filter(a => a.verdict === 'MATCH').length + ' of ' +
                            (c.explain.attributes || []).length + ' readable', 'measured'],
    ['Fused score', (c.score * 100).toFixed(1) + '%', 'measured'],
    ['Engineering validation', v.key === 'CONFLICT' ? 'Refused — hard key conflict'
                              : (c.coverage >= 2 ? 'Passed' : 'Thin evidence — capped at review'), 'measured'],
    ['Standards relationship', fam.nodes.length ? (fam.nodes[0].verified ? 'Scoped cross-reference on file'
                              : 'Prototype — requires verification') : 'None on file', 'derived'],
    ['Conflict detection', v.key === 'CONFLICT' ? 'Conflict raised' : 'None', 'measured']
  ] : [];

  return `<div class="pp">
    <div class="pp-head">
      <div class="eyebrow">Material passport</div>
      <div class="t">${esc(m.description)}</div>
      <div class="row">
        <div class="f"><span class="k">CNMC</span><span class="v">${esc(m.cnmc)}</span></div>
        <div class="f"><span class="k">Status</span><span class="v">${verdictBadge(v.key)}</span></div>
        <div class="f"><span class="k">Category</span><span class="v">${esc(m.category_label)}</span></div>
        <div class="f"><span class="k">CPSEs</span><span class="v"><span class="cpse-stack">${m.cpses.map(c=>cpseMark(c,20)).join('')}</span>${esc(m.cpses.join(' · '))}</span></div>
        <div class="f"><span class="k">Issuance</span><span class="v">${approved ? 'ISSUED' : 'PROPOSED'}</span></div>
      </div>
    </div>

    <div class="pp-grid">
      <div>
        <div class="kicker">Identity</div>
        <div class="attrgrid">
          <div class="k">Normalised description</div><div class="v" style="text-align:left">${esc(m.description)}</div>
          <div class="k">Material family</div><div class="v">${esc(m.family_name)}</div>
          <div class="k">Source records</div><div class="v">${m.records.length}</div>
          <div class="k">Plants</div><div class="v">${m.plants.length}</div>
        </div>

        <div class="kicker">CPSE participation <span class="prov">source records</span></div>
        <div class="cpse-part">${cpsePartRows(m)}</div>

        <div class="kicker">Legacy codes <span class="prov">source records</span></div>
        ${m.legacy_identities.map(l => `<div class="idrow">
          <span><b>${esc(l.cpse)}</b></span>
          <span class="site">${esc(l.plant || '')}</span>
          <span class="mono">${esc(l.legacy_code)}</span></div>`).join('')}
        <div class="hint" style="margin:7px 0 0;font-size:11px">Legacy codes are retained, never overwritten.
          Each CPSE keeps addressing the item by its own ERP code.</div>

        <div class="kicker">Normalized attributes <span class="prov">pipeline output</span></div>
        <div class="attrgrid">
          ${Object.entries(m.attrs).map(([k, val]) =>
            `<div class="k">${esc(TULYA.attrLabel(k))}</div><div class="v">${esc(TULYA.attrValue(k, val))}</div>`).join('')
            || '<div class="k" style="grid-column:1/3">No specification was recovered from these descriptions.</div>'}
        </div>
      </div>

      <div>
        <div class="kicker">Engineering validation</div>
        ${c ? evidenceTableHTML(c) : '<div class="hint">No candidate pair was shipped for this record.</div>'}

        <div class="kicker">Standards evidence
          <span class="prov ${m.family === 'PIP' ? '' : 'sim'}">${m.family === 'PIP' ? 'source-backed' : 'prototype'}</span></div>
        ${fam.nodes.map(n => `<button class="stdchip${n.verified ? ' verified' : ''}"
           onclick="openStandard('${m.family}','${esc(n.id)}')">${esc(n.id)}</button>`).join('')
           || '<span class="hint">None on file.</span>'}

        <div class="kicker">Match analysis</div>
        ${c ? `<div class="twrap"><table><thead><tr><th>Signal</th><th class="num">Result</th><th>Source</th></tr></thead>
          <tbody>${analysis.map(([k, val, prov]) =>
            `<tr><td>${k}</td><td class="num mono">${esc(val)}</td>
              <td><span class="prov">${prov}</span></td></tr>`).join('')}</tbody></table></div>`
          : '<div class="hint">—</div>'}

        <div class="kicker">Decision</div>
        <div class="verdict ${v.key === 'CONFLICT' ? 'stop' : (v.key === 'IDENTICAL' || v.key === 'EQUIVALENT' ? 'merge' : 'hold')}">
          <b>${TULYA.VERDICTS[v.key].label} · ${TULYA.VERDICTS[v.key].next}</b>${esc(v.reason)}.
        </div>
        ${c && !approved ? `<div class="actbar">
          ${v.key === 'CONFLICT'
            ? '<span class="sig sig-unres">MERGE BLOCKED · HARD SPECIFICATION CONFLICT</span>'
            : `<button class="btn approve small" onclick="decide(${c.a},${c.b},'approve');renderPassport()">Approve</button>
               <button class="btn reject small" onclick="decide(${c.a},${c.b},'reject');renderPassport()">Reject</button>
               <button class="btn ghost small" onclick="conditionalHold(${c.a},${c.b})">Conditional</button>
               <button class="btn ghost small" onclick="requestVerification(${c.a},${c.b})">Request verification</button>`}
        </div>` : ''}
        ${approved ? `<div class="chain">
          <div class="c-step"><span class="m">✓</span><span><b>${esc(m.cnmc)}</b> issued</span></div>
          <div class="c-step"><span class="m">✓</span><span>Legacy mapping preserved — ${m.legacy_identities.map(l => esc(l.cpse) + ' ' + esc(l.legacy_code)).join(', ')}</span></div>
          <div class="c-step"><span class="m">✓</span><span>Cross-CPSE visibility enabled across ${esc(m.cpses.join(', '))}</span></div>
          <div class="c-step"><span class="m">✓</span><span>Demand aggregation enabled <span class="prov sim">simulated</span></span></div>
          <div class="c-step"><span class="m">✓</span><span>Audit entry created</span></div>
        </div>` : ''}

        <div class="actbar">
          <button class="jump" onclick="gotoProcurement('${m.id}')">Procurement</button>
          <button class="jump" onclick="gotoSimulator('${m.id}')">Simulate impact</button>
          <button class="jump" onclick="gotoCollab('${m.id}')">Collaboration case</button>
          <button class="jump" onclick="switchPanel('audit')">Audit log</button>
        </div>
      </div>
    </div></div>`;
}

function conditionalHold(a, b) {
  STATE.audit.unshift({ ts: Date.now() / 1000, action: 'conditional', record_a: a, record_b: b,
    steward: steward(), score: (ITEM_BY_KEY[pkey(a, b)] || {}).score || null,
    before: 'proposed', after: 'held as conditional equivalence',
    detail: 'engineering review required before mapping' });
  saveState(); toast('Marked conditional — routed to engineering review'); renderAll();
}
function requestVerification(a, b) {
  STATE.audit.unshift({ ts: Date.now() / 1000, action: 'verify', record_a: a, record_b: b,
    steward: steward(), score: (ITEM_BY_KEY[pkey(a, b)] || {}).score || null,
    before: 'proposed', after: 'standards verification requested',
    detail: 'verification of the standards cross-reference against the standard texts' });
  saveState(); toast('Standards verification requested'); renderAll();
}

/* ===========================================================================
   STANDARDS KNOWLEDGE GRAPH
   =========================================================================== */
let KG_FAMILY = 'PIP', KG_NODE = null;
function openStandard(fam, id) { KG_FAMILY = fam; KG_NODE = id; switchPanel('standards'); renderStandards(); }
function setKgFamily(f) { KG_FAMILY = f; KG_NODE = null; renderStandards(); }
function selectStandard(id) { KG_NODE = id; renderStandards(); }

const RELCLS = { EQUIVALENT: 'rel-equivalent', SUPERSET: 'rel-superset', SUBSTITUTE: 'rel-substitute',
                 CONFLICT: 'rel-conflict', 'REQUIRES VERIFICATION': 'rel-requires' };

function renderStandards() {
  const set = TULYA.STANDARDS[KG_FAMILY];
  el('kgFamilies').innerHTML = Object.keys(TULYA.STANDARDS).map(f =>
    `<button class="${f === KG_FAMILY ? 'on' : ''}" onclick="setKgFamily('${f}')">${esc(TULYA.FAMILY_NAME[f])}</button>`).join('');

  const root = set.nodes[0], others = set.nodes.slice(1);
  el('kgTree').innerHTML = `
    <button class="kg-root" onclick="selectStandard('${esc(root.id)}')">${esc(root.id)}</button>
    <div class="kg-branch">
      ${others.map(n => {
        const e = set.edges.find(x => (x.a === root.id && x.b === n.id) || (x.b === root.id && x.a === n.id));
        const rel = e ? e.rel : 'RELATED', st = e ? e.state : 'REQUIRES REVIEW';
        return `<div class="kg-edge"><span class="stem"></span>
          <span class="rel ${RELCLS[rel] || 'rel-requires'}">${rel}</span>
          <button class="kg-node ${KG_NODE === n.id ? 'on' : ''}" onclick="selectStandard('${esc(n.id)}')">${esc(n.id)}</button>
          <span class="state-chip ${st === 'SCOPED' ? 'state-scoped' : 'state-review'}">${st}</span></div>`;
      }).join('')}
    </div>
    <div class="hint" style="margin-top:16px;font-size:11.5px">Relationship types: EQUIVALENT · SUPERSET ·
      SUBSTITUTE · CONFLICT · REQUIRES VERIFICATION. No edge is drawn as unconditional.</div>
    <div class="serieskey">
      <span><span class="state-chip state-verified">VERIFIED</span> stated in the TULYA reference set</span>
      <span><span class="state-chip state-scoped">SCOPED</span> holds within a stated range</span>
      <span><span class="state-chip state-review">REQUIRES REVIEW</span> prototype, unverified</span>
    </div>`;

  const nodeId = KG_NODE || root.id;
  const n = set.nodes.find(x => x.id === nodeId) || root;
  const edges = set.edges.filter(e => e.a === nodeId || e.b === nodeId);
  const usedBy = TULYA.materials.filter(m => m.family === KG_FAMILY);

  el('kgPanel').innerHTML = `
    <div style="display:flex;align-items:center;gap:9px;flex-wrap:wrap;padding-bottom:11px;
                border-bottom:1px solid var(--line);margin-bottom:12px">
      <span class="mono" style="font-size:14px;font-weight:600;color:var(--n-900)">${esc(n.id)}</span>
      <span class="state-chip ${n.verified ? 'state-verified' : 'state-review'}">${n.verified ? 'VERIFIED' : 'PROTOTYPE — REQUIRES REVIEW'}</span>
    </div>
    <dl>
      <dt>Issuing body</dt><dd>${esc(n.body)}</dd>
      <dt>Scope</dt><dd>${esc(n.scope)}</dd>
      <dt>Relevant attributes</dt>
      <dd class="mono" style="font-size:11.5px">${[...new Set(usedBy.flatMap(m => Object.keys(m.attrs)))]
          .map(k => esc(TULYA.attrLabel(k))).join(' · ') || 'none recovered'}</dd>
      <dt>Relationships</dt>
      <dd>${edges.length ? edges.map(e => {
        const other = e.a === nodeId ? e.b : e.a;
        return `<div style="margin:6px 0"><span class="rel ${RELCLS[e.rel] || 'rel-requires'}">${e.rel}</span>
          <span class="mono" style="font-size:11.5px">${esc(other)}</span>
          <span class="state-chip ${e.state === 'SCOPED' ? 'state-scoped' : 'state-review'}">${e.state}</span>
          <div style="font-size:11.5px;color:var(--n-500);margin-top:3px">${esc(e.evidence)}</div></div>`;
      }).join('') : 'No relationship on file.'}</dd>
      <dt>Verification state</dt>
      <dd>${n.verified
        ? 'Source-backed. The cross-reference appears in the TULYA reference set and is scoped to the stated range — not a blanket equivalence.'
        : 'Prototype relationship. Shipped so the graph is walkable; not verified against the standard texts, and treated as REQUIRES VERIFICATION.'}</dd>
      <dt>Evidence reference</dt>
      <dd style="font-size:11.5px">${n.note ? esc(n.note) + '<br>' : ''}${n.verified
        ? 'TULYA reference set — standards section (BIS / BSI / ASTM / JIS designations).'
        : 'No published cross-reference cited. Steward action: request standards verification.'}</dd>
      <dt>Materials using this family</dt>
      <dd>${usedBy.length} identit${usedBy.length === 1 ? 'y' : 'ies'} ·
        ${usedBy.reduce((s, m) => s + m.records.length, 0)} source records
        ${usedBy.length ? `<br><button class="jump" style="margin-top:5px" onclick="openPassport('${usedBy[0].id}')">Open a material passport</button>` : ''}</dd>
    </dl>`;
}

/* ===========================================================================
   ANALYTICS
   =========================================================================== */
const STATUS_COLOR = { IDENTICAL: '#1F6B4A', EQUIVALENT: '#4E9873', CONDITIONAL: '#B98B34',
                       DIFFERENT: '#B9C3CC', CONFLICT: '#A3392C', UNRESOLVED: '#8C99A5' };
const SERIES_COLOR = { records: '#12283F', matched: '#1F6FB2', duplicates: '#B98B34',
                       reviews: '#A3392C', harmonised: '#1F6B4A' };

function hbar(label, value, max, cls, display) {
  const w = max ? Math.max(1, (value / max) * 100) : 1;
  return `<div class="hbar ${cls || ''}"><span class="lbl" title="${esc(label)}">${esc(label)}</span>
    <span class="track"><i style="width:${w.toFixed(1)}%"></i></span>
    <span class="num">${display != null ? display : qty(value)}</span></div>`;
}

function renderAnalytics() {
  const A = TULYA.analytics(STATE.reviews), t = A.totals;

  el('anKpis').style.gridTemplateColumns = 'repeat(auto-fit,minmax(196px,1fr))';
  el('anKpis').innerHTML = [
    ['Material identities', qty(t.materials), 'after harmonisation', 'passport'],
    ['Harmonized', qty(t.harmonised), 'identical or equivalent', null],
    ['Pending review', qty(t.pending), 'conditional equivalence', 'collab'],
    ['Conflicts', qty(t.conflicts), 'merge blocked by veto', 'vetoed'],
    ['Cross-CPSE', qty(t.cross_cpse), 'identities in 2+ CPSEs', 'procurement']
  ].map(([k, v, s, go]) => go
    ? `<button onclick="switchPanel('${go}')"><span class="k">${k}</span><span class="v">${v}</span><span class="s">${s}</span></button>`
    : `<div><span class="k">${k}</span><span class="v">${v}</span><span class="s">${s}</span></div>`).join('');

  /* 1 — harmonisation overview, the large chart */
  const stTotal = Object.values(A.byStatus).reduce((s, x) => s + x, 0) || 1;
  el('anStatus').innerHTML = `
    <h4>Material harmonization overview</h4>
    <div class="cap">Governed verdict across every derived material identity. Derived from pipeline output.</div>
    <div class="body">
      <div class="stackbar">${Object.entries(A.byStatus).filter(([, n]) => n).map(([k, n]) =>
        `<i style="width:${(n / stTotal * 100).toFixed(2)}%;background:${STATUS_COLOR[k]}" title="${k}: ${n}"></i>`).join('')}</div>
      ${Object.entries(A.byStatus).map(([k, n]) =>
        `<div class="hbar wide"><span class="lbl">${verdictBadge(k)}</span>
          <span class="track"><i style="width:${(n / stTotal * 100).toFixed(1)}%;background:${STATUS_COLOR[k]}"></i></span>
          <span class="num">${qty(n)}</span></div>`).join('')}
    </div>`;

  /* 2 — CPSE distribution */
  const maxRec = Math.max(1, ...A.byCpse.flatMap(c => [c.records, c.matched, c.duplicates, c.reviews, c.harmonised]));
  el('anCpse').innerHTML = `
    <h4>CPSE distribution</h4>
    <div class="cap">Records, matched, duplicates, open reviews and harmonised records per CPSE.</div>
    <div class="body">
      ${A.byCpse.map(c => `<div class="grouped">
        <div class="lbl">${cpseMark(c.cpse, 20)}<span>${esc(c.cpse)}</span></div>
        <div class="series">${['records', 'matched', 'duplicates', 'reviews', 'harmonised'].map(k =>
          `<div class="srow"><span class="t"><i style="width:${(c[k] / maxRec * 100).toFixed(1)}%;background:${SERIES_COLOR[k]}"></i></span>
            <span class="n">${qty(c[k])}</span></div>`).join('')}</div></div>`).join('')}
      <div class="serieskey">${Object.entries(SERIES_COLOR).map(([k, v]) =>
        `<span><i style="background:${v}"></i>${k}</span>`).join('')}</div>
    </div>`;

  /* 3 — material category distribution */
  const maxFam = Math.max(...A.byFamily.map(f => f.records), 1);
  el('anCategory').innerHTML = `
    <h4>Material category distribution</h4>
    <div class="cap">Source records by material family; conflicts shown alongside.</div>
    <div class="body">${A.byFamily.map(f => hbar(f.name, f.records, maxFam, f.conflicts ? 'amber' : '',
      qty(f.records) + (f.conflicts ? ' · ' + f.conflicts + '✕' : ''))).join('')}</div>`;

  /* 4 — review status */
  const maxBand = Math.max(...Object.values(A.bands), 1);
  el('anBands').innerHTML = `
    <h4>Review status</h4>
    <div class="cap">Steward priority bands across the shipped cases. Pipeline priority ranking.</div>
    <div class="body">
      ${[['Critical', A.bands.CRITICAL, 'bad'], ['High', A.bands.HIGH, 'amber'],
         ['Medium', A.bands.MEDIUM, ''], ['Low', A.bands.LOW, 'dim']]
        .map(([l, n, c]) => hbar(l, n, maxBand, c)).join('')}
      <div class="actbar" style="margin-top:10px">
        <button class="jump" onclick="switchPanel('queue')">Open the review queue</button></div>
    </div>`;

  /* 5 — cross-CPSE opportunities, as a table */
  el('anOpportunities').innerHTML = crossTable(A.aggregation.slice(0, 10), 'an');
}

/* ===========================================================================
   COLLABORATION
   =========================================================================== */
let COLLAB_ID = null, COLLAB_STAGE = 'ALL';

function gotoCollab(matId) {
  const m = TULYA.byId[matId], c = m ? bestCaseFor(m) : null;
  if (c) { COLLAB_ID = pkey(c.a, c.b); COLLAB_STAGE = 'ALL'; }
  switchPanel('collab'); renderCollab();
}
function openCase(a, b) { COLLAB_ID = pkey(a, b); COLLAB_STAGE = 'ALL'; switchPanel('collab'); renderCollab(); }
function setCollabStage(s) { COLLAB_STAGE = s; renderCollab(); }

function collabCases() {
  const seen = {};
  return TULYA.cases.filter(it => { const k = pkey(it.a, it.b); if (seen[k]) return false; seen[k] = 1; return true; })
    .map(TULYA.caseOf)
    .filter(c => COLLAB_STAGE === 'ALL' || TULYA.STAGES[c.stage] === COLLAB_STAGE);
}

function renderCollab() {
  const cases = collabCases();
  el('collabStages').innerHTML = ['ALL'].concat(TULYA.STAGES).map(s =>
    `<button class="${COLLAB_STAGE === s ? 'on' : ''}" onclick="setCollabStage('${s}')">${s === 'ALL' ? 'All' : s}</button>`).join('');
  if (el('collabCount')) el('collabCount').textContent = qty(cases.length);
  el('collabListCount').innerHTML = showing(Math.min(50, cases.length), cases.length, 'cases');

  el('collabList').innerHTML = cases.slice(0, 50).map(c => {
    const on = pkey(c.pair.a, c.pair.b) === COLLAB_ID;
    return `<button class="r${on ? ' on' : ''}" onclick="openCase(${c.pair.a},${c.pair.b})">
      <div class="d">${esc(c.pair.record_a.description)}</div>
      <div class="m"><span>${esc(c.case_id)}</span><span>${esc(c.stage_name)}</span></div>
      <div style="margin-top:4px">${verdictBadge(c.verdict.key)}</div>
    </button>`;
  }).join('') || '<div class="empty">No case at this stage.</div>';

  const chosen = cases.find(c => pkey(c.pair.a, c.pair.b) === COLLAB_ID) || cases[0];
  if (!chosen) { el('collabDetail').innerHTML = '<div class="empty">No case selected.</div>'; return; }
  COLLAB_ID = pkey(chosen.pair.a, chosen.pair.b);
  el('collabDetail').innerHTML = caseHTML(chosen);
}

function caseHTML(c) {
  const it = c.pair, m = c.material;
  const reviewed = STATE.reviews[pkey(it.a, it.b)];
  const st = TULYA.standardsEvidence(it);
  return `<div class="panel-box">
    <div class="ph"><span>${esc(c.case_id)}</span>
      <span class="side">${verdictBadge(c.verdict.key, true)}</span></div>
    <div class="pb">
      <div style="font-size:14.5px;font-weight:600;color:var(--n-900)">${esc(it.record_a.description)}</div>
      <div class="wf-rail">${TULYA.STAGES.map((s, i) =>
        `<span class="n ${i < c.stage ? 'done' : (i === c.stage ? 'now' : '')}">${s}</span>`).join('')}</div>

      <div class="twrap" style="margin-top:12px"><table><tbody>
        <tr><td style="width:180px;color:var(--n-500)">Material</td><td>${esc(it.record_a.description)}</td></tr>
        <tr><td style="color:var(--n-500)">Legacy code · CPSE</td>
            <td class="mono">${esc(it.record_a.legacy_code)} (${esc(it.record_a.cpse)}) · ${esc(it.record_b.legacy_code)} (${esc(it.record_b.cpse)})</td></tr>
        <tr><td style="color:var(--n-500)">Candidate match</td><td>${esc(it.record_b.description)}</td></tr>
        <tr><td style="color:var(--n-500)">Confidence</td><td class="mono">${(it.score * 100).toFixed(1)}%</td></tr>
        <tr><td style="color:var(--n-500)">Attributes</td><td class="mono" style="font-size:11.5px">${
          (it.explain.attributes || []).map(a => esc(TULYA.attrLabel(a.key)) + ' ' +
            (a.verdict === 'MATCH' ? '✓' : a.verdict === 'MISMATCH' ? '✕' : '?')).join(' · ') || 'none readable'}</td></tr>
        <tr><td style="color:var(--n-500)">Standards evidence</td><td class="mono" style="font-size:11.5px">${
          st ? esc(st.a) + ' vs ' + esc(st.b) + ' — ' + st.rel : 'none on file'}
          ${st ? `<span class="state-chip ${st.verified ? 'state-verified' : 'state-review'}">${st.verified ? 'VERIFIED' : 'REQUIRES REVIEW'}</span>` : ''}</td></tr>
        <tr><td style="color:var(--n-500)">Conflict status</td><td>${c.verdict.key === 'CONFLICT'
          ? '<span class="sig sig-unres">HARD CONFLICT · MERGE BLOCKED</span>' : '<span class="sig sig-stock">NONE DETECTED</span>'}</td></tr>
        <tr><td style="color:var(--n-500)">Procurement status</td><td>${esc(c.procurement)} <span class="prov sim">simulated</span></td></tr>
        <tr><td style="color:var(--n-500)">Decision</td><td>${reviewed
          ? '<span class="pill ' + esc(reviewed.action) + '">' + esc(reviewed.action) + '</span> by ' + esc(reviewed.steward)
          : '<span class="pill review">PENDING</span>'}</td></tr>
      </tbody></table></div>

      <div class="assign">
        <div><label>Assigned steward</label>
          <select onchange="assignRole(${it.a},${it.b},'steward',this.value)">
            ${['R. Nair', 'A. Deshmukh', 'P. Iyer', 'S. Banerjee', 'M. Qureshi'].map(s =>
              `<option ${s === c.steward ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
        <div><label>Assigned engineer</label>
          <select onchange="assignRole(${it.a},${it.b},'engineer',this.value)">
            <option ${!c.engineer ? 'selected' : ''}>— not assigned —</option>
            ${['V. Rao (Static)', 'K. Menon (Rotating)', 'T. Ghosh (Piping)', 'D. Shah (Electrical)'].map(s =>
              `<option ${s === c.engineer ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      </div>

      <div class="actbar">
        ${c.verdict.key === 'CONFLICT' ? '' :
          `<button class="btn approve small" onclick="decide(${it.a},${it.b},'approve');renderCollab()">Approve</button>`}
        <button class="btn ghost small" onclick="caseAction(${it.a},${it.b},'engineering')">Request review</button>
        <button class="btn ghost small" onclick="requestVerification(${it.a},${it.b})">Standards verification</button>
        ${c.verdict.key === 'CONFLICT' ? '' :
          `<button class="btn ghost small" onclick="conditionalHold(${it.a},${it.b})">Conditional</button>`}
        <button class="btn ghost small" onclick="caseAction(${it.a},${it.b},'comment')">Comment</button>
        <button class="btn ghost small" onclick="caseAction(${it.a},${it.b},'escalate')">Escalate</button>
        ${c.verdict.key === 'CONFLICT' ? '' :
          `<button class="btn reject small" onclick="decide(${it.a},${it.b},'reject');renderCollab()">Reject</button>`}
      </div>

      <div class="case-grid" style="margin-top:18px">
        <div>
          <div class="kicker">Engineering evidence</div>
          ${evidenceTableHTML(it)}
        </div>
        <div>
          <div class="kicker">Decision timeline</div>
          <div class="tline">${TULYA.timelineOf(c).map(s =>
            `<div class="tl-i ${s.state}"><div class="h">${esc(s.head)}</div>
              <div class="d">${esc(s.detail)}</div></div>`).join('')}</div>
          <div class="kicker">Activity</div>
          <div class="feed">${TULYA.activityOf(c).map(f =>
            `<div class="f"><span class="t">${f.at}</span><span>${esc(f.text)}</span></div>`).join('')}</div>
          ${m ? `<div class="actbar">
            <button class="jump" onclick="openPassport('${m.id}')">Passport</button>
            <button class="jump" onclick="gotoProcurement('${m.id}')">Procurement</button>
            <button class="jump" onclick="gotoSimulator('${m.id}')">Simulate impact</button></div>` : ''}
        </div>
      </div>
    </div></div>`;
}

function assignRole(a, b, role, who) {
  STATE.audit.unshift({ ts: Date.now() / 1000, action: 'assign', record_a: a, record_b: b,
    steward: steward(), score: null, before: null, after: null, detail: role + ' assigned: ' + who });
  saveState(); toast(role === 'steward' ? 'Steward assigned' : 'Engineer assigned'); renderAudit();
}
function caseAction(a, b, kind) {
  const labels = { comment: 'Comment added', engineering: 'Engineering review requested',
                   escalate: 'Escalated to final governance' };
  let note = '';
  if (kind === 'comment') { note = prompt('Comment on this case:') || ''; if (!note) return; }
  STATE.audit.unshift({ ts: Date.now() / 1000,
    action: kind === 'comment' ? 'comment' : (kind === 'escalate' ? 'escalate' : 'engineering'),
    record_a: a, record_b: b, steward: steward(), score: null, before: null, after: null,
    detail: note || labels[kind] });
  saveState(); toast(labels[kind]); renderCollab(); renderAudit();
}

/* ===========================================================================
   CROSS-CPSE IMPACT SIMULATOR
   =========================================================================== */
let SIM_MAT = null, SIM_CPSES = null, SIM_SCENARIO = 0, SIM_REQUIRED = null;

function gotoSimulator(matId) { SIM_MAT = matId; SIM_CPSES = null; SIM_REQUIRED = null; switchPanel('simulator'); renderSimulator(); }
function setSimMat(id) { SIM_MAT = id; SIM_CPSES = null; SIM_REQUIRED = null; renderSimulator(); }
function toggleSimCpse(c) {
  SIM_CPSES = SIM_CPSES || [];
  SIM_CPSES = SIM_CPSES.includes(c) ? SIM_CPSES.filter(x => x !== c) : SIM_CPSES.concat(c);
  renderSimulator();
}
function setScenario(i) { SIM_SCENARIO = i; renderSimulator(); }
function setRequired(v) { SIM_REQUIRED = Math.max(0, +v || 0); renderSimulator(); }

function renderSimulator() {
  const candidates = TULYA.materials.filter(m => m.cross_cpse).slice(0, 40);
  if (!SIM_MAT || !TULYA.byId[SIM_MAT]) SIM_MAT = (candidates[0] || TULYA.materials[0] || {}).id;
  const m = TULYA.byId[SIM_MAT];
  if (!m) { el('simBody').innerHTML = '<div class="empty">No material available.</div>'; return; }
  if (!SIM_CPSES) SIM_CPSES = m.cpses.slice();

  el('simPicker').innerHTML = candidates.map(x =>
    `<option value="${x.id}" ${x.id === SIM_MAT ? 'selected' : ''}>${esc(x.description.slice(0, 54))}</option>`).join('');

  const scenarios = [['Current', 1], ['+10%', 1.1], ['+25%', 1.25], ['+50%', 1.5]];
  const baseReq = SIM_REQUIRED != null ? SIM_REQUIRED : (m.demand ? m.demand.qty : Math.round(m.stock_total * 0.55));
  const required = Math.round(baseReq * scenarios[SIM_SCENARIO][1]);
  const participating = m.stock.filter(s => SIM_CPSES.includes(s.cpse));
  const combined = participating.reduce((s, x) => s + x.qty, 0);
  const coverage = required ? Math.min(1, combined / required) : 0;
  const surplus = Math.max(0, combined - required);
  const shortfall = Math.max(0, required - combined);
  const legacyConsolidated = m.legacy_identities.filter(l => SIM_CPSES.includes(l.cpse)).length;
  const simMax = Math.max(20, Math.round(Math.max(m.stock_total, baseReq) * 2));
  const simStep = Math.max(1, Math.round(simMax / 200));
  const perCpse = {};
  m.stock.forEach(s => { perCpse[s.cpse] = (perCpse[s.cpse] || 0) + s.qty; });

  el('simControls').innerHTML = `
    <div class="sim-row"><label>CPSE participation</label>
      <div class="cpse-toggles">${m.cpses.map(c =>
        `<button class="${SIM_CPSES.includes(c) ? 'on' : ''}" onclick="toggleSimCpse('${c}')">
          <span class="bx">${SIM_CPSES.includes(c) ? '■' : '□'}</span>${esc(c)}
          <span class="q">${qty(perCpse[c])}</span></button>`).join('')}</div></div>
    <div class="sim-row"><label>Demand scenario</label>
      <div class="scenario">${scenarios.map(([l], i) =>
        `<button class="${SIM_SCENARIO === i ? 'on' : ''}" onclick="setScenario(${i})">${l}</button>`).join('')}</div></div>
    <div class="sim-row"><label>Required quantity</label>
      <div class="reqrow">
        <input type="range" min="0" max="${simMax}" step="${simStep}"
               value="${Math.min(baseReq, simMax)}" oninput="setRequired(this.value)">
        <span class="q">${qty(required)} ${esc(m.unit)}</span>
      </div></div>`;

  el('simBody').innerHTML = `
    <div class="ba">
      <div class="side">
        <h5>Before — separate identities</h5>
        ${m.stock.map(s => `<div class="silo">
          <span>${esc(s.cpse)} <span class="mono" style="color:var(--n-400)">${esc(s.legacy_code)}</span></span>
          <span class="q">${qty(s.qty)}</span></div>`).join('')}
        <div class="hint" style="margin:9px 0 0;font-size:11px">${m.legacy_identities.length} separate legacy
          codes. No stock position here is visible to the others.</div>
      </div>
      <div class="mid">→</div>
      <div class="side after">
        <h5>After proposed harmonisation</h5>
        <div class="mono" style="font-size:11.5px;color:var(--n-900);font-weight:600;word-break:break-all">${esc(m.cnmc)}</div>
        <div class="hint" style="margin:3px 0 10px;font-size:10.5px">common material identity</div>
        <div style="font-size:9.5px;color:var(--n-500);text-transform:uppercase;letter-spacing:.7px;font-weight:600">Visible combined stock</div>
        <div class="bigqty">${qty(combined)} <span style="font-size:13px;font-weight:500;color:var(--n-500)">${esc(m.unit)}</span></div>
        <div class="hint" style="margin:6px 0 0;font-size:11px">${SIM_CPSES.length} participating
          CPSE${SIM_CPSES.length === 1 ? '' : 's'} · ${legacyConsolidated} legacy identities consolidated</div>
      </div>
    </div>

    <div class="chart" style="margin-top:14px">
      <h4>Impact results</h4>
      <div class="body" style="padding:0">
        <div class="simout">
          <div class="o"><div class="v">${qty(required)}</div><div class="k">Current demand</div></div>
          <div class="o good"><div class="v">${qty(combined)}</div><div class="k">Available stock</div></div>
          <div class="o ${coverage >= 0.6 ? 'good' : 'amber'}"><div class="v">${(coverage * 100).toFixed(0)}%</div><div class="k">Projected coverage</div></div>
          <div class="o ${shortfall ? 'amber' : 'good'}"><div class="v">${qty(shortfall)}</div><div class="k">Procurement requirement</div></div>
          <div class="o"><div class="v">${qty(surplus)}</div><div class="k">Potential surplus</div></div>
          <div class="o"><div class="v">${SIM_CPSES.length > 1 ? 'Yes' : 'No'}</div><div class="k">Aggregation opportunity</div></div>
          <div class="o"><div class="v">${legacyConsolidated}</div><div class="k">Legacy codes consolidated</div></div>
          <div class="o"><div class="v">${m.cpses.length}</div><div class="k">CPSEs in identity</div></div>
        </div>
        <div style="padding:13px 14px">
          <div style="font-size:10px;color:var(--n-500);text-transform:uppercase;letter-spacing:.6px;font-weight:600">
            Coverage of required quantity</div>
          <div class="covermeter"><i class="${coverage >= 1 ? '' : 'part'}" style="width:${(coverage * 100).toFixed(1)}%"></i></div>
        </div>
      </div>
    </div>

    <div class="chart" style="margin-top:14px">
      <h4>Stock contribution by CPSE</h4>
      <div class="cap">Only selected CPSEs contribute to the combined figure.</div>
      <div class="body">
        ${m.stock.map(s => {
          const on = SIM_CPSES.includes(s.cpse);
          const max = Math.max(...m.stock.map(x => x.qty), 1);
          return `<div class="hbar ${on ? '' : 'dim'}">
            <span class="lbl">${on ? '■' : '□'} ${esc(s.cpse)} · ${esc(s.plant || '')}</span>
            <span class="track"><i style="width:${(s.qty / max * 100).toFixed(1)}%"></i></span>
            <span class="num">${qty(s.qty)}</span></div>`;
        }).join('')}
      </div>
    </div>

    <div class="actbar">
      <button class="jump" onclick="openPassport('${m.id}')">Material passport</button>
      <button class="jump" onclick="gotoProcurement('${m.id}')">Procurement intelligence</button>
      <button class="jump" onclick="gotoCollab('${m.id}')">Request review</button>
    </div>`;
}

/* ===========================================================================
   PROCUREMENT INTELLIGENCE
   =========================================================================== */
const SIG_SHORT = { 'CROSS-CPSE STOCK FOUND': 'STOCK FOUND',
  'DEMAND AGGREGATION CANDIDATE': 'AGGREGATION', 'OPPORTUNITY DETECTED': 'OPPORTUNITY',
  'NO CROSS-CPSE STOCK': 'NO STOCK', 'UNRESOLVED CASE': 'UNRESOLVED' };
const SIGCLS = { 'CROSS-CPSE STOCK FOUND': 'sig-stock', 'DEMAND AGGREGATION CANDIDATE': 'sig-agg',
                 'OPPORTUNITY DETECTED': 'sig-opp', 'NO CROSS-CPSE STOCK': 'sig-none',
                 'UNRESOLVED CASE': 'sig-unres' };
const PROC = { cpse: 'ALL', family: 'ALL', signal: 'ALL', stock: 'ALL', review: 'ALL',
               q: '', sort: 'coverage', dir: -1, page: 0, size: 25, focus: null };

function gotoProcurement(matId) {
  Object.assign(PROC, { cpse: 'ALL', family: 'ALL', signal: 'ALL', stock: 'ALL', review: 'ALL',
                        q: '', page: 0, focus: matId });
  switchPanel('procurement'); renderProcurement();
}
function setProc(k, v) { PROC[k] = v; PROC.page = 0; PROC.focus = null; renderProcurement(); }
function clearProc() {
  Object.assign(PROC, { cpse: 'ALL', family: 'ALL', signal: 'ALL', stock: 'ALL', review: 'ALL',
                        q: '', page: 0, focus: null });
  renderProcurement();
}
function sortProc(k) { if (PROC.sort === k) PROC.dir *= -1; else { PROC.sort = k; PROC.dir = -1; } renderProcurement(); }
function pageProc(d) { PROC.page = Math.max(0, PROC.page + d); renderProcurement(); }

function procFiltered() {
  let rows = TULYA.procurementRows();
  if (PROC.focus) return rows.filter(r => r.material.id === PROC.focus);
  if (PROC.cpse !== 'ALL') rows = rows.filter(r => r.material.cpses.includes(PROC.cpse));
  if (PROC.family !== 'ALL') rows = rows.filter(r => r.material.family === PROC.family);
  if (PROC.signal !== 'ALL') rows = rows.filter(r => r.signal === PROC.signal);
  if (PROC.stock === 'AVAILABLE') rows = rows.filter(r => r.available > 0);
  if (PROC.stock === 'NONE') rows = rows.filter(r => !r.available);
  if (PROC.review !== 'ALL') rows = rows.filter(r => r.review_status === PROC.review);
  if (PROC.q) {
    const q = PROC.q.toLowerCase();
    rows = rows.filter(r => (r.material.description + ' ' + r.material.cnmc + ' ' +
      r.material.cpses.join(' ')).toLowerCase().includes(q));
  }
  const key = { coverage: r => r.coverage, required: r => r.required, available: r => r.available,
                material: r => r.material.description.toLowerCase() }[PROC.sort] || (r => r.coverage);
  return rows.sort((a, b) => { const x = key(a), y = key(b);
    return (x < y ? -1 : x > y ? 1 : 0) * PROC.dir; });
}

function renderProcurement() {
  const all = TULYA.procurementRows();
  const counts = {
    open: all.length,
    stock: all.filter(r => r.signal === 'CROSS-CPSE STOCK FOUND').length,
    dup: all.filter(r => r.material.cross_cpse && r.coverage > 0).length,
    agg: all.filter(r => r.signal === 'CROSS-CPSE STOCK FOUND' || r.signal === 'DEMAND AGGREGATION CANDIDATE').length,
    unres: all.filter(r => r.signal === 'UNRESOLVED CASE' || r.review_status === 'UNRESOLVED').length
  };
  if (el('procTotal')) el('procTotal').textContent = qty(counts.open);
  el('procKpis').style.gridTemplateColumns = 'repeat(auto-fit,minmax(196px,1fr))';
  el('procKpis').innerHTML = [
    ['Open material demand', counts.open, () => clearProc()],
    ['Cross-CPSE stock found', counts.stock, () => setProc('signal', 'CROSS-CPSE STOCK FOUND')],
    ['Duplicate procurement candidates', counts.dup, () => setProc('stock', 'AVAILABLE')],
    ['Demand aggregation opportunities', counts.agg, () => setProc('signal', 'DEMAND AGGREGATION CANDIDATE')],
    ['Unresolved procurement cases', counts.unres, () => setProc('review', 'UNRESOLVED')]
  ].map(([k, v], i) => `<button onclick="PROC_KPI[${i}]()"><span class="k">${k}</span>
      <span class="v">${qty(v)}</span><span class="s">Filter</span></button>`).join('');
  window.PROC_KPI = [() => clearProc(), () => setProc('signal', 'CROSS-CPSE STOCK FOUND'),
    () => setProc('stock', 'AVAILABLE'), () => setProc('signal', 'DEMAND AGGREGATION CANDIDATE'),
    () => setProc('review', 'UNRESOLVED')];

  const cpses = [...new Set(all.flatMap(r => r.material.cpses))].sort();
  const fams = [...new Set(all.map(r => r.material.family))];
  const opt = (v, cur, label) => `<option value="${v}" ${v === cur ? 'selected' : ''}>${label}</option>`;
  el('procFilters').innerHTML = `
    <div class="f"><label>CPSE</label><select onchange="setProc('cpse',this.value)">
      ${opt('ALL', PROC.cpse, 'All CPSEs')}${cpses.map(c => opt(c, PROC.cpse, c)).join('')}</select></div>
    <div class="f"><label>Material category</label><select onchange="setProc('family',this.value)">
      ${opt('ALL', PROC.family, 'All categories')}${fams.map(f => opt(f, PROC.family, TULYA.FAMILY_NAME[f])).join('')}</select></div>
    <div class="f"><label>Demand status</label><select onchange="setProc('signal',this.value)">
      ${opt('ALL', PROC.signal, 'All')}${Object.keys(SIGCLS).map(s => opt(s, PROC.signal, s)).join('')}</select></div>
    <div class="f"><label>Stock availability</label><select onchange="setProc('stock',this.value)">
      ${opt('ALL', PROC.stock, 'Any')}${opt('AVAILABLE', PROC.stock, 'Stock elsewhere')}${opt('NONE', PROC.stock, 'None found')}</select></div>
    <div class="f"><label>Review status</label><select onchange="setProc('review',this.value)">
      ${opt('ALL', PROC.review, 'All')}${Object.keys(TULYA.VERDICTS).map(k => opt(k, PROC.review, TULYA.VERDICTS[k].label)).join('')}</select></div>
    <div class="f" style="min-width:180px"><label>Search</label>
      <input value="${esc(PROC.q)}" placeholder="Material, CNMC, CPSE"
             oninput="PROC.q=this.value;PROC.page=0;PROC.focus=null;renderProcurement();document.querySelector('#procFilters input').focus()"></div>
    <div class="spacer"></div>
    <button class="btn ghost" onclick="clearProc()">Clear filters</button>
    <button class="btn ghost" onclick="exportProc()">Export CSV</button>`;

  const rows = procFiltered();
  const from = PROC.page * PROC.size, page = rows.slice(from, from + PROC.size);
  const arrow = k => PROC.sort === k ? `<span class="sort">${PROC.dir > 0 ? '▲' : '▼'}</span>` : '<span class="sort">▾</span>';
  const th = (k, label, num) => `<th${num ? ' class="num' : ' class="'}${PROC.sort === k ? ' on' : ''}" data-sort="${k}" onclick="sortProc('${k}')">${label}${arrow(k)}</th>`;

  el('procTable').innerHTML = !rows.length
    ? '<div class="empty">No procurement case matches these filters.</div>'
    : `<div class="twrap"><table>
      <thead><tr>
        ${th('material', 'Material')}<th>CNMC</th><th>Req. CPSE</th>
        ${th('required', 'Demand', 1)}${th('available', 'Stock avail.', 1)}<th>Stock CPSE</th>
        ${th('coverage', 'Coverage')}<th>Std.</th><th>Status</th><th>Action</th>
      </tr></thead><tbody>
      ${page.map(r => `<tr>
        <td>${esc(r.material.description)}<div class="site">${esc(r.material.category_label)}</div></td>
        <td class="mono cnmc" title="${esc(r.material.cnmc)}">${esc(r.material.cnmc)}</td>
        <td>${cpseTag(r.requesting_cpse, '', 20)}</td>
        <td class="num mono">${qty(r.required)}</td>
        <td class="num mono">${qty(r.available)}</td>
        <td>${r.best_source ? cpseTag(r.best_source.cpse, '', 20) + '<div class="site">' + esc(r.best_source.plant || '') + '</div>' : '—'}</td>
        <td><div class="cov-mini"><span class="t"><i class="${r.coverage >= 1 ? '' : 'part'}" style="width:${(r.coverage * 100).toFixed(0)}%"></i></span>
          <span class="mono">${(r.coverage * 100).toFixed(0)}%</span></div>
          <span class="sig ${SIGCLS[r.signal]}" style="margin-top:3px" title="${r.signal}">${SIG_SHORT[r.signal] || r.signal}</span></td>
        <td><span class="state-chip ${r.standards_status === 'VERIFIED CROSS-REFERENCE' ? 'state-verified' : 'state-review'}" title="${r.standards_status}">${r.standards_status === 'VERIFIED CROSS-REFERENCE' ? 'VERIFIED' : (r.standards_status === 'NONE ON FILE' ? 'NONE' : 'REVIEW')}</span></td>
        <td>${verdictBadge(r.review_status, false, true)}</td>
        <td><div class="rowacts">
          <button onclick="openPassport('${r.material.id}')">Material</button>
          <button onclick="gotoSimulator('${r.material.id}')">Simulate</button>
          <button onclick="gotoCollab('${r.material.id}')">Review</button>
        </div></td></tr>`).join('')}
      </tbody></table></div>
      <div class="tfoot">
        ${showing(Math.min(PROC.size, rows.length - from), rows.length, 'procurement cases')}
        <span class="pg">
          <button class="btn ghost small" ${from === 0 ? 'disabled' : ''} onclick="pageProc(-1)">Previous</button>
          <span style="padding:0 6px">Page ${PROC.page + 1} of ${Math.max(1, Math.ceil(rows.length / PROC.size))}</span>
          <button class="btn ghost small" ${from + PROC.size >= rows.length ? 'disabled' : ''} onclick="pageProc(1)">Next</button>
        </span>
      </div>`;
}

function exportProc() {
  const rows = procFiltered();
  const head = ['Material', 'CNMC', 'Requesting CPSE', 'Demand', 'Available stock', 'Stock CPSE',
                'Coverage %', 'Standards status', 'Review status', 'Signal'];
  const body = rows.map(r => [r.material.description, r.material.cnmc, r.requesting_cpse, r.required,
    r.available, r.best_source ? r.best_source.cpse : '', (r.coverage * 100).toFixed(0),
    r.standards_status, r.review_status, r.signal]);
  const csv = [head].concat(body).map(l => l.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = 'tulya_procurement_opportunities.csv';
  a.click(); URL.revokeObjectURL(a.href);
  toast(rows.length + ' rows exported — simulated quantities');
}

/* ===========================================================================
   panel dispatch
   =========================================================================== */
function renderTulyaPanels() {
  const safe = (n, f) => { try { f(); } catch (e) { console.error(n, e); } };
  safe('passport', renderPassport);
  safe('standards', renderStandards);
  safe('analytics', renderAnalytics);
  safe('collab', renderCollab);
  safe('simulator', renderSimulator);
  safe('procurement', renderProcurement);
}


/* ===========================================================================
   NO SIGN-IN GATE
   This console is an offline static export: there is no identity provider to
   talk to and no server to hold a session, so a sign-in screen whose password
   is printed beneath the form would have been theatre. It was removed. The
   steward identity written into the audit log is the name in the footer, and
   decisions persist in this browser's local storage exactly as before.
   =========================================================================== */
const AUTH_KEY = 'tulya_demo_session_v1';
function sessionClear(){ try { localStorage.removeItem(AUTH_KEY); } catch(e){} }

function installAuth(){
  // No sign-in gate. This is an offline export with no identity provider behind
  // it, so a credential printed on the page bought nothing and cost the reviewer
  // a click. The console opens directly on the workspace.
  sessionClear();
  document.body.classList.remove('signed-out');
  const g = el('loginView'); if (g) g.remove();
}

/* ===========================================================================
   APP-BAR POPOVERS — notifications and account
   The bell had no handler. It now reads the same demo state the rest of the
   console reads: STATE.audit (append-only, written by real steward actions in
   this browser) and the live review backlog from DATA. Nothing is invented —
   if no decision has been taken yet the panel says so rather than showing
   manufactured operational events, because this build is an offline export,
   not a live notification service.
   =========================================================================== */
const POPS = ['notifPanel', 'acctPanel'];

function popClose(all){
  POPS.forEach(id=>{
    if (all && id !== all) { /* fall through: close everything but `all` */ }
    const pan = el(id); if (!pan || (all && id === all)) return;
    pan.hidden = true;
    const btn = el(id === 'notifPanel' ? 'tbBell' : 'tbAvatar');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  });
}
function popToggle(id){
  const pan = el(id); if (!pan) return;
  const show = pan.hidden;
  popClose(show ? id : null);
  pan.hidden = !show;
  const btn = el(id === 'notifPanel' ? 'tbBell' : 'tbAvatar');
  if (btn) btn.setAttribute('aria-expanded', show ? 'true' : 'false');
  if (show){
    const first = pan.querySelector('button'); first && first.focus();
  } else if (btn) btn.focus();
}

/* What the console can honestly tell a steward they have not seen. */
function notifItems(){
  const out = [];

  /* 1 — the real backlog, straight off DATA and this browser's decisions */
  const pend = (DATA.queue || []).filter(it => !STATE.reviews[pkey(it.a, it.b)]);
  if (pend.length){
    const crit = pend.filter(it => it.priority === 'CRITICAL').length;
    out.push({ kind:'warn', t:`${pend.length.toLocaleString()} pairs awaiting a steward`,
      s: crit ? `${crit} in the critical band — open these first`
              : 'Ranked by uncertainty × evidence × value',
      m:'Review queue', go:()=>switchPanel('queue') });
  }
  const auto = (DATA.auto_suggest || []).filter(it => !STATE.reviews[pkey(it.a, it.b)]);
  if (auto.length){
    out.push({ kind:'info', t:`${auto.length.toLocaleString()} pairs above the auto-suggest threshold`,
      s:`Scored at or above t = ${DATA.holdout.threshold} and not yet confirmed`,
      m:'Auto-suggest', go:()=>switchPanel('auto') });
  }
  const veto = DATA.decision_counts && DATA.decision_counts.REJECTED_VETO;
  if (veto) out.push({ kind:'bad', t:`${veto.toLocaleString()} pairs blocked by a specification conflict`,
    s:'A hard-key veto stopped these from being proposed at all',
    m:'Hard-key vetoes', go:()=>switchPanel('vetoed') });

  /* 2 — cross-CPSE stock the model actually found */
  try {
    const opp = TULYA.procurementRows().filter(r => r.signal === 'CROSS-CPSE STOCK FOUND');
    if (opp.length) out.push({ kind:'ok',
      t:`${opp.length} cross-CPSE sourcing opportunities`,
      s:`Open demand that another CPSE already holds · quantities simulated`,
      m:'Procurement intelligence', go:()=>switchPanel('procurement') });
  } catch(e){ /* procurement model unavailable in this export */ }

  /* 3 — this browser's own steward decisions, newest first */
  (STATE.audit || []).slice(0, 5).forEach(r => {
    const rec = RECORDS[r.record_a] || {};
    const kind = r.action === 'approve' ? 'ok'
               : r.action === 'reject' ? 'bad'
               : ['conditional','unmerge','verify'].includes(r.action) ? 'warn' : 'info';
    out.push({ kind, t:`${ACTION_LABEL[r.action] || r.action}${rec.cpse ? ' · ' + rec.cpse : ''}`,
      s: rec.description || `Records ${r.record_a}${r.record_b != null ? ' ↔ ' + r.record_b : ''}`,
      m: new Date(r.ts * 1000).toLocaleString('en-GB'),
      go: r.record_b != null ? ()=>openCase(r.record_a, r.record_b) : ()=>switchPanel('audit') });
  });
  return out;
}

function renderNotifs(){
  const pan = el('notifPanel'); if (!pan) return;
  const items = notifItems();
  const acted = (STATE.audit || []).length;
  const badge = el('tbBadge');
  if (badge){
    const n = items.filter(i => i.m !== undefined && ['Review queue','Auto-suggest','Hard-key vetoes',
      'Procurement intelligence'].includes(i.m)).length;
    badge.hidden = n === 0; badge.textContent = n;
    const bell = el('tbBell');
    if (bell) bell.setAttribute('aria-label', n ? `Notifications, ${n} items needing attention` : 'Notifications');
  }
  pan.innerHTML =
    `<div class="hd"><h4>Notifications</h4><span>${items.length} item${items.length===1?'':'s'}</span></div>`
  + (items.length
      ? items.map((it,i)=>`<button type="button" class="nt" data-i="${i}">`
          + `<span class="dot ${it.kind}"></span><span>`
          + `<span class="t">${esc(it.t)}</span>`
          + (it.s ? `<span class="s">${esc(it.s)}</span>` : '')
          + (it.m ? `<span class="m">${esc(it.m)}</span>` : '')
          + `</span></button>`).join('')
      : `<div class="empty">Nothing to report. Every pair in this export has been decided in this
           browser, and no backlog remains.</div>`)
  + `<div class="ft">Offline demo — these are the live counts in this export plus the decisions you
       have taken in this browser. Nothing here comes from a notification service, and no event is
       generated for appearance.</div>`;
  pan.querySelectorAll('.nt').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      const it = items[+btn.dataset.i]; popClose();
      if (it && it.go) try { it.go(); } catch(e){ if (window.console) console.warn('notification:', e); }
    });
  });
}

function renderAcct(){
  const pan = el('acctPanel'); if (!pan) return;
  const who = (el('stewardName') && el('stewardName').value) || 'steward_demo';
  pan.innerHTML =
    `<div class="who"><b>${esc(who)}</b><span>Data steward · offline demo</span></div>`
  + `<button type="button" role="menuitem" data-go="passport">Profile</button>`
  + `<button type="button" role="menuitem" data-go="performance">Settings</button>`
  + `<div class="note">This export has no sign-in. The steward name in the footer is the
       identity written into the audit log, and your decisions stay in this browser's
       local storage.</div>`;
  pan.querySelectorAll('button').forEach(b=>{
    b.addEventListener('click', ()=>{
      popClose();
      if (b.dataset.go) switchPanel(b.dataset.go);
    });
  });
}

function installPopovers(){
  const bell = el('tbBell'), av = el('tbAvatar');
  if (bell && !bell.dataset.wired){
    bell.dataset.wired = '1';
    bell.addEventListener('click', e=>{ e.stopPropagation(); renderNotifs(); popToggle('notifPanel'); });
  }
  if (av && !av.dataset.wired){
    av.dataset.wired = '1';
    av.addEventListener('click', e=>{ e.stopPropagation(); renderAcct(); popToggle('acctPanel'); });
  }
  document.addEventListener('click', e=>{ if (!e.target.closest('.tb-pop')) popClose(); });
  document.addEventListener('keydown', e=>{
    if (e.key !== 'Escape') return;
    if (POPS.some(id => el(id) && !el(id).hidden)){ e.preventDefault(); popClose(); }
  });
  renderNotifs();
}

/* ===========================================================================
   NAVIGATION DRAWER
   One control, one state class, and the existing navigation underneath it.
   No second routing implementation: the drawer only shows and hides the same
   <nav> the application has always used, and switchPanel() is untouched.
   =========================================================================== */
function navOpen(on){
  document.body.classList.toggle('nav-open', !!on);
  const btn = el('navToggle'), scrim = el('navScrim'), rail = el('appSidebar');
  if (btn){ btn.setAttribute('aria-expanded', on ? 'true' : 'false');
            btn.setAttribute('aria-label', on ? 'Close navigation' : 'Open navigation'); }
  if (scrim) scrim.hidden = !on;
  if (on && rail){ const first = rail.querySelector('nav button'); first && first.focus(); }
  else if (!on && btn && document.activeElement && rail && rail.contains(document.activeElement)) btn.focus();
}
function navToggle(){ navOpen(!document.body.classList.contains('nav-open')); }

function installNavDrawer(){
  const btn = el('navToggle'); if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = '1';
  btn.addEventListener('click', e=>{ e.stopPropagation(); navToggle(); });
  const scrim = el('navScrim'); if (scrim) scrim.addEventListener('click', ()=>navOpen(false));
  // choosing a destination closes the drawer; the button's own handler still runs
  const rail = el('appSidebar');
  if (rail) rail.addEventListener('click', e=>{ if (e.target.closest('nav button')) navOpen(false); });
  document.addEventListener('keydown', e=>{
    if (e.key === 'Escape' && document.body.classList.contains('nav-open')){
      e.preventDefault(); navOpen(false);
    }
  });
  navOpen(false);
}

/* ===========================================================================
   HASH ROUTING
   switchPanel() showed and hid panels without recording anything, so the
   browser Back button left the console instead of stepping back through it.
   The panel name is written to location.hash — not history.pushState, which a
   browser refuses on a file:// page, and this console is opened as a file.
   Every existing caller of switchPanel keeps working untouched.
   =========================================================================== */
const ROUTE_PANELS = ['overview','challenge','queue','auto','passport','analytics','simulator',
  'procurement','collab','groups','vetoed','standards','audit','performance','search'];
let ROUTE_SILENT = false;

(function installRouter(){
  if (typeof switchPanel !== 'function') return;
  const base = switchPanel;
  switchPanel = function(name){
    base(name);
    if (!ROUTE_SILENT && ROUTE_PANELS.indexOf(name) >= 0 &&
        location.hash.slice(1) !== name){
      try { location.hash = name; } catch(e){ /* nothing to record; carry on */ }
    }
  };
  window.addEventListener('hashchange', ()=>{
    const name = location.hash.slice(1);
    if (ROUTE_PANELS.indexOf(name) < 0) return;
    const open = document.querySelector('.panel.active');
    if (open && open.id === 'p-' + name) return;
    ROUTE_SILENT = true; try { switchPanel(name); } finally { ROUTE_SILENT = false; }
  });
})();

/* restore the panel named in the address on load, so a refresh stays put */
function routeBoot(){
  const name = location.hash.slice(1);
  if (ROUTE_PANELS.indexOf(name) < 0) return;
  ROUTE_SILENT = true; try { switchPanel(name); } finally { ROUTE_SILENT = false; }
}

/* ===========================================================================
   GLOBAL SEARCH
   The topbar field had no handler at all — it was markup. This wires it to the
   models the rest of the console already renders from: TULYA.materials for
   identities and CNMC codes, DATA.cpse_records for CPSEs, DATA.queue and
   DATA.auto_suggest for pending pairs. Nothing here builds an index of its own
   and nothing is invented: every hit navigates to a route that already exists.
   =========================================================================== */
const GS = { open:false, idx:-1, rows:[], q:'' };

function gsNorm(s){ return String(s || '').toLowerCase(); }

/* Rank: a prefix hit beats a word-boundary hit beats a loose substring. */
function gsScore(hay, q){
  const h = gsNorm(hay); if (!h) return -1;
  const i = h.indexOf(q); if (i < 0) return -1;
  if (i === 0) return 100 - Math.min(40, h.length / 4);
  if (/[\s\-_/.]/.test(h.charAt(i-1))) return 70 - Math.min(30, h.length / 6);
  return 40 - Math.min(20, h.length / 8);
}

function gsHighlight(text, q){
  const s = String(text == null ? '' : text);
  const i = gsNorm(s).indexOf(q);
  if (i < 0 || !q) return esc(s);
  return esc(s.slice(0,i)) + '<mark>' + esc(s.slice(i, i+q.length)) + '</mark>' + esc(s.slice(i+q.length));
}

function gsSearch(raw){
  const q = gsNorm(raw).trim();
  if (q.length < 2) return [];
  const out = [];

  /* A field only contributes when it actually matched: gsScore returns -1 for
     a miss, so the field bonus is applied to the hit, never to the -1. Adding
     it first is what made every record match every query. */
  const bump = (hay, q, bonus) => { const sc = gsScore(hay, q); return sc < 0 ? -1 : sc + bonus; };

  /* materials — description, CNMC, category, legacy codes, CPSE */
  (TULYA.materials || []).forEach(m => {
    let best = -1, via = null, legacy = null;
    const take = (sc, tag) => { if (sc > best){ best = sc; via = tag; } };
    take(bump(m.description, q, 0), 'description');
    take(bump(m.cnmc, q, 5), 'cnmc');
    take(bump(m.category_label, q, -15), 'category');
    (m.legacy_identities || []).forEach(l => {
      const sc = bump(l.legacy_code, q, 3);
      if (sc > best){ best = sc; via = 'legacy'; legacy = l; }
    });
    // a CPSE name finds that CPSE's identities, but ranks below a name match
    (m.cpses || []).forEach(c => take(bump(c, q, -22), 'cpse'));
    if (best > 0) out.push({
      group:'Materials', score:best, via, legacy,
      title:m.description, sub:m.cnmc,
      meta:`${m.cpses.length} CPSE${m.cpses.length===1?'':'s'} · ${m.records.length} legacy code${m.records.length===1?'':'s'}`,
      cpses:m.cpses,
      go:()=>openPassport(m.id)
    });
  });

  /* CPSEs — only those the data actually names */
  const counts = (DATA.cpse_records && DATA.cpse_records.counts) || {};
  const cpseNames = [...new Set([].concat(
    Object.keys(counts),
    (TULYA.materials || []).flatMap(m => m.cpses)))].filter(Boolean);
  cpseNames.forEach(c => {
    const sc = gsScore(c, q);
    if (sc > 0) out.push({
      group:'CPSE', score:sc + 20, via:'cpse', cpse:c,
      title:c, sub: counts[c] != null
        ? counts[c].toLocaleString() + ' material records in the locked test split'
        : 'named on material identities in this export',
      meta: (TULYA.materials || []).filter(m => m.cpses.includes(c)).length + ' identities',
      go:()=>{ setProc('cpse', c); switchPanel('procurement'); }
    });
  });

  /* pending review pairs, by either side's description or legacy code */
  const pairs = (DATA.queue || []).concat(DATA.auto_suggest || []);
  pairs.forEach(p => {
    const a = p.record_a || {}, b = p.record_b || {};
    const sc = Math.max(gsScore(a.description, q), gsScore(b.description, q),
                        bump(a.legacy_code, q, 3), bump(b.legacy_code, q, 3),
                        bump(a.cpse, q, -26), bump(b.cpse, q, -26));
    if (sc > 0) out.push({
      group:'Review items', score:sc - 8, via:'pair',
      title:a.description || b.description || 'Candidate pair',
      sub:`${a.legacy_code || '—'} ↔ ${b.legacy_code || '—'}`,
      meta:`${a.cpse || '—'} ↔ ${b.cpse || '—'} · score ${p.score != null ? p.score.toFixed(3) : '—'}`,
      cpses:[a.cpse, b.cpse].filter(Boolean),
      go:()=>openCase(p.a, p.b)
    });
  });

  /* the destinations a person types a page name to reach */
  const ACTIONS = [
    ['Material Passport','Every legacy code behind one identity','passport'],
    ['Review Queue','Pairs waiting on a steward','queue'],
    ['Auto-Suggest','Pairs above the auto-suggest threshold','auto'],
    ['Procurement Intelligence','Cross-CPSE stock against open demand','procurement'],
    ['Cross-CPSE Analytics','Scope, distribution and backend comparison','analytics'],
    ['Audit Log','Every steward decision, append-only','audit'],
    ['Hard-Key Vetoes','Pairs a specification conflict blocked','vetoed'],
    ['Standards Knowledge Graph','Designations and scoped cross-references','standards'],
    ['Golden Records','Identities that have been issued a CNMC','groups'],
    ['Impact Simulator','Model pooling across participating CPSEs','simulator'],
  ];
  ACTIONS.forEach(([name, sub, panel]) => {
    const sc = gsScore(name, q);
    if (sc > 0) out.push({ group:'Actions', score:sc - 25, via:'action',
      title:name, sub, meta:'', go:()=>switchPanel(panel) });
  });

  /* keep the list short enough to scan, and grouped in a fixed order */
  const ORDER = { 'Materials':0, 'CPSE':1, 'Review items':2, 'Actions':3 };
  const CAP   = { 'Materials':6, 'CPSE':4, 'Review items':4, 'Actions':3 };
  const taken = {};
  return out.sort((x,y)=>y.score-x.score)
    .filter(r => { taken[r.group] = (taken[r.group]||0)+1; return taken[r.group] <= CAP[r.group]; })
    .sort((x,y)=>ORDER[x.group]-ORDER[y.group] || y.score-x.score);
}

function gsRender(){
  const box = el('gsPanel'); if (!box) return;
  const q = GS.q;
  if (!GS.open || q.trim().length < 2){ box.hidden = true; box.innerHTML = ''; return; }
  box.hidden = false;
  if (!GS.rows.length){
    box.innerHTML = `<div class="gs-none">No matching records found<span>Nothing in this export matches `
      + `“${esc(q)}”. Try a material word, a CNMC or legacy code, or a CPSE.</span></div>`;
    return;
  }
  const nq = gsNorm(q).trim();
  let html = '', last = null;
  GS.rows.forEach((r,i)=>{
    if (r.group !== last){ html += `<div class="gs-grp">${esc(r.group)}</div>`; last = r.group; }
    html += `<button type="button" class="gs-row${i===GS.idx?' on':''}" data-i="${i}">`
      + (r.cpse ? cpseMark(r.cpse, 24)
                : (r.cpses && r.cpses.length ? cpseMark(r.cpses[0], 24) : `<span class="gs-ico">${esc((r.group||'?').charAt(0))}</span>`))
      + `<span class="gs-b"><span class="gs-t">${gsHighlight(r.title, nq)}</span>`
      +   (r.sub ? `<span class="gs-s">${gsHighlight(r.sub, nq)}</span>` : '')
      + `</span>`
      + (r.meta ? `<span class="gs-m">${esc(r.meta)}</span>` : '')
      + `</button>`;
  });
  box.innerHTML = html;
  box.querySelectorAll('.gs-row').forEach(btn=>{
    btn.addEventListener('mousedown', e=>{ e.preventDefault(); gsGo(+btn.dataset.i); });
    btn.addEventListener('mouseenter', ()=>{ GS.idx = +btn.dataset.i;
      box.querySelectorAll('.gs-row').forEach((b,j)=>b.classList.toggle('on', j===GS.idx)); });
  });
}

function gsGo(i){
  const r = GS.rows[i]; if (!r) return;
  gsClose();
  const input = el('tbSearch'); if (input) input.blur();
  try { r.go(); } catch(e){ if (window.console) console.warn('search navigation:', e); }
}

function gsClose(){ GS.open = false; GS.idx = -1; gsRender(); }

function gsInput(v){
  GS.q = v; GS.open = true;
  GS.rows = gsSearch(v);
  GS.idx = GS.rows.length ? 0 : -1;
  gsRender();
}

function gsMove(d){
  if (!GS.rows.length) return;
  GS.idx = (GS.idx + d + GS.rows.length) % GS.rows.length;
  gsRender();
  const on = el('gsPanel') && el('gsPanel').querySelector('.gs-row.on');
  if (on && on.scrollIntoView) on.scrollIntoView({ block:'nearest' });
}

function gsWire(){
  const input = el('tbSearch'); if (!input || input.dataset.wired) return;
  input.dataset.wired = '1';
  input.addEventListener('input', e=>gsInput(e.target.value));
  input.addEventListener('focus', ()=>{ if (input.value.trim().length >= 2) gsInput(input.value); });
  input.addEventListener('keydown', e=>{
    if (e.key === 'ArrowDown'){ e.preventDefault(); gsMove(1); }
    else if (e.key === 'ArrowUp'){ e.preventDefault(); gsMove(-1); }
    else if (e.key === 'Enter'){
      if (GS.open && GS.idx >= 0){ e.preventDefault(); gsGo(GS.idx); }
    }
    else if (e.key === 'Escape'){
      e.preventDefault();
      if (GS.open && GS.q) gsClose(); else { input.value = ''; GS.q = ''; gsClose(); input.blur(); }
    }
  });
  document.addEventListener('click', e=>{ if (!e.target.closest('.tb-search')) gsClose(); });
  document.addEventListener('keydown', e=>{
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k'){
      e.preventDefault(); input.focus(); input.select();
    }
  });
}

/* ===========================================================================
   CONTROL TOWER PANELS
   Every figure below is read from DATA or from TULYA.procurementRows(). Where a
   field does not exist in this export, the panel says so rather than deriving a
   plausible value — an invented number here would be the only unsourced thing
   on the page.
   =========================================================================== */
const CT_NAVY = '#17324D', CT_BLUE = '#3D6B8C', CT_LINE = '#D9DEE5', CT_DIM = '#8D99A7';

/* --- CPSE marks -----------------------------------------------------------
   DATA.cpse_marks holds a data URI per CPSE, populated by build.py from the
   authorised files in tulya/assets/cpse/. Nothing here draws or approximates a
   logo: a CPSE with no asset gets a monogram container, which is a placeholder
   for a file that has not been supplied. Sizes are fixed so a mark can never
   grow into decoration. */
function cpseMark(code, size){
  const c = String(code || '').toUpperCase();
  const cls = size && size !== 24 ? ' cm-' + size : '';
  const src = (DATA.cpse_marks || {})[c];
  return src
    ? `<span class="cm${cls}" title="${esc(c)}"><img src="${src}" alt="${esc(c)} logo"></span>`
    : `<span class="cm ph${cls}" title="${esc(c)} — official logo asset not supplied" `
      + `aria-label="${esc(c)}">${esc(size === 32 && c.length <= 4 ? c : c.slice(0,2))}</span>`;
}
/* mark + code, the form used in tables and lists */
function cpseTag(code, sub, size){
  return `<span class="cpse-tag">${cpseMark(code, size)}<b>${esc(String(code||'').toUpperCase())}</b>`
       + (sub ? `<span class="sub">${sub}</span>` : '') + `</span>`;
}
/* material records held by a CPSE in the locked test split, or null */
function cpseRecordCount(code){
  const t = DATA.cpse_records && DATA.cpse_records.counts;
  return t && t[code] != null ? t[code] : null;
}

function ctRenderPanels(){
  try { ctPerformance(); } catch(e){ ctFail('ctPerfChart', e); }
  try { ctNetwork();     } catch(e){ ctFail('ctNetGraph', e); }
  try { ctRecommend();   } catch(e){ ctFail('ctRecoBody', e); }
}
function ctFail(id, e){
  const n = el(id); if (n) n.innerHTML =
    '<div class="ct-net-detail none">This panel could not be built from the data in this export.</div>';
  if (window.console) console.warn('control tower panel:', id, e);
}

/* --- 1 · Matching Performance ---------------------------------------------
   DATA.sweep is the threshold sweep from threshold_selection.json: 20 real
   points of (threshold, auto_precision, coverage, auto_pairs, false_merges).
   It is NOT a time series, so this is plotted as what it is — a trade-off
   curve against the threshold, with the chosen operating point marked. */
function ctPerfOperating(){
  const sweep = (DATA.sweep || []).slice().sort((a,b)=>a.threshold-b.threshold);
  if (!sweep.length) throw new Error('no sweep');
  const chosen = DATA.threshold ? DATA.threshold.chosen : null;
  const lc = DATA.holdout.layer_c;

  const W = 520, H = 210, L = 38, R = 12, T = 12, B = 30;
  const xs = sweep.map(d=>d.threshold);
  const x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
  const px = t => L + (t - x0) / ((x1 - x0) || 1) * (W - L - R);
  // Both series live in a narrow high band (precision ~0.90-1.0, coverage
  // ~0.75-0.95). Plotted 0-100% the trade-off — precision rising as coverage
  // falls — reads as two flat lines. The axis is floored to the data instead,
  // and the provenance note says where it starts so the zoom is declared
  // rather than hidden.
  // NOTE: sweep[].coverage is identical at every threshold (0.9118) — it is set
  // by blocking and retrieval, upstream of the decision band, so it does not
  // belong on a threshold axis. Plotting it as a line would imply a
  // relationship the data does not contain. It is reported as a static figure
  // in the side column instead. What genuinely trades against precision is
  // pct_review: the share of candidates pushed to a person.
  const vals = sweep.flatMap(d => [d.auto_precision, d.pct_review]).filter(v => v != null);
  const yMin = Math.max(0, Math.floor(Math.min.apply(null, vals) * 20 - 1) / 20);
  const py = v => T + (1 - (v - yMin) / ((1 - yMin) || 1)) * (H - T - B);
  const maxPairs = Math.max.apply(null, sweep.map(d=>d.auto_pairs || 0)) || 1;
  const bw = Math.max(3, (W - L - R) / sweep.length - 3);

  let g = '';
  // horizontal rules at 0/25/50/75/100%
  for (let i=0;i<=4;i++){
    const v = yMin + (i/4) * (1 - yMin), y = py(v);
    g += `<line x1="${L}" y1="${y.toFixed(1)}" x2="${W-R}" y2="${y.toFixed(1)}" stroke="${CT_LINE}" stroke-width="1"/>`
      +  `<text x="${L-7}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-size="9.5" fill="${CT_DIM}">${(v*100).toFixed(0)}%</text>`;
  }
  // bars — pairs the engine would auto-suggest at that threshold
  sweep.forEach(d=>{
    const h = (d.auto_pairs||0)/maxPairs * (H-T-B) * 0.78;
    g += `<rect x="${(px(d.threshold)-bw/2).toFixed(1)}" y="${(H-B-h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" fill="${CT_BLUE}" opacity=".13"/>`;
  });
  // lines
  const line = (key, colour, dash) => {
    const pts = sweep.filter(d=>d[key]!=null).map(d=>`${px(d.threshold).toFixed(1)},${py(d[key]).toFixed(1)}`).join(' ');
    return `<polyline points="${pts}" fill="none" stroke="${colour}" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"${dash?` stroke-dasharray="${dash}"`:''}/>`;
  };
  g += line('pct_review', CT_BLUE, '4 3') + line('auto_precision', CT_NAVY, '');
  // chosen operating point
  if (chosen != null){
    const cx = px(chosen), pt = sweep.reduce((b,d)=>Math.abs(d.threshold-chosen)<Math.abs(b.threshold-chosen)?d:b, sweep[0]);
    g += `<line x1="${cx.toFixed(1)}" y1="${T}" x2="${cx.toFixed(1)}" y2="${H-B}" stroke="${CT_NAVY}" stroke-width="1" stroke-dasharray="3 3" opacity=".55"/>`
      +  `<circle cx="${cx.toFixed(1)}" cy="${py(pt.auto_precision).toFixed(1)}" r="3.6" fill="#fff" stroke="${CT_NAVY}" stroke-width="2"/>`
      +  `<text x="${cx.toFixed(1)}" y="${H-B-6}" text-anchor="middle" font-size="9.5" fill="${CT_NAVY}" font-weight="600">t = ${chosen}</text>`;
  }
  // x axis
  g += `<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="${CT_LINE}" stroke-width="1"/>`;
  sweep.forEach((d,i)=>{ if (i % 4) return;
    g += `<text x="${px(d.threshold).toFixed(1)}" y="${H-B+14}" text-anchor="middle" font-size="9.5" fill="${CT_DIM}">${d.threshold.toFixed(2)}</text>`; });
  g += `<text x="${((L+W-R)/2).toFixed(0)}" y="${H-2}" text-anchor="middle" font-size="9.5" fill="${CT_DIM}">Auto-suggest threshold</text>`;

  el('ctPerfChart').innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Auto-suggest precision and the share of candidates sent to review, plotted against the matching threshold, from the validation sweep">${g}</svg>`;
  el('ctPerfLegend').innerHTML =
    `<span><i style="background:${CT_NAVY}"></i>Auto-suggest precision</span>`
  + `<span style="color:${CT_BLUE}"><i class="sw-dash"></i><span style="color:var(--n-500)">Share sent to steward review</span></span>`
  + `<span><i class="sw-bar" style="background:${CT_BLUE};opacity:.35"></i>Pairs auto-suggested</span>`;

  const opPt = el('ctPerfOp');
  if (opPt) opPt.innerHTML = `Operating point<br><b style="color:var(--navy);font-size:13px">t = ${DATA.holdout.threshold}</b>`;

  el('ctPerfSide').innerHTML = [
    ['hero', pct(lc.auto_suggest_precision), 'Auto-suggest precision at the locked operating point'],
    ['', lc.false_merges_proposed.toLocaleString(), 'Potential mismatches proposed'],
    ['', lc.auto_suggest_pairs.toLocaleString(), 'Pairs auto-suggested'],
    ['', DATA.pairs_scored.toLocaleString(), 'Candidate pairs evaluated'],
    ['', DATA.records.toLocaleString(), 'Material records processed'],
    ['', pct(sweep[0].coverage), 'Coverage of true duplicates \u2014 fixed by blocking, identical at every threshold'],
  ].map(([c,v,k])=>`<div class="m ${c}"><b>${v}</b><span>${k}</span></div>`).join('');

  el('ctPerfProv').innerHTML =
    `<b>Data provenance</b> — curve from <span class="mono">threshold_selection.json</span>, a 20-point `
  + `sweep measured on the <b>validation</b> split. The side figures are from `
  + `<span class="mono">holdout_run.json</span>, the locked <b>test</b> split at t = ${DATA.holdout.threshold}. `
  + `The x-axis is the threshold, not time — this export contains a single run, so there is no time series to plot. `
  + `The y-axis starts at <b>${(yMin*100).toFixed(0)}%</b>, not zero, because both series sit in a narrow high band. `
  + `Coverage of true duplicates is <b>not</b> plotted: it is identical at all 20 thresholds because blocking and `
  + `retrieval decide it upstream of the decision band, so it is shown as a fixed figure instead of a flat line.`;
}

/* --- 1b · Precision / recall / F1 -------------------------------------------
   DATA.curves is recorded in holdout_run.json: for each matching backend, 101
   threshold points carrying the measured precision, recall and F1 on the
   locked test split. These are real evaluation curves, so they are plotted as
   curves. Nothing is smoothed, interpolated or extended beyond the 101 points
   the run actually wrote. */
const CT_HYBRID = 'TULYA hybrid';

function ctPerfQuality(){
  const curves = DATA.curves || {};
  const hy = curves[CT_HYBRID];
  if (!hy || !hy.length) throw new Error('no curves');
  const pts = hy.slice().sort((a,b)=>a.t-b.t);
  const op  = DATA.holdout.threshold;
  const at  = t => pts.reduce((b,d)=>Math.abs(d.t-t)<Math.abs(b.t-t)?d:b, pts[0]);
  const best = pts.reduce((b,d)=>d.f1>b.f1?d:b, pts[0]);
  const here = at(op);

  const W = 520, H = 210, L = 38, R = 12, T = 12, B = 30;
  const px = t => L + t * (W - L - R);
  const py = v => T + (1 - v) * (H - T - B);   // full 0-100%: the three series
                                               // span the whole range honestly

  let g = '';
  for (let i=0;i<=4;i++){
    const y = py(i/4);
    g += `<line x1="${L}" y1="${y.toFixed(1)}" x2="${W-R}" y2="${y.toFixed(1)}" stroke="${CT_LINE}" stroke-width="1"/>`
      +  `<text x="${L-7}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-size="9.5" fill="${CT_DIM}">${(i*25)}%</text>`;
  }
  const line = (key, colour, dash, w) => {
    const d = pts.filter(p=>p[key]!=null).map(p=>`${px(p.t).toFixed(1)},${py(p[key]).toFixed(1)}`).join(' ');
    return `<polyline points="${d}" fill="none" stroke="${colour}" stroke-width="${w||1.9}" `
         + `stroke-linejoin="round" stroke-linecap="round"${dash?` stroke-dasharray="${dash}"`:''}/>`;
  };
  g += line('recall', CT_BLUE, '4 3') + line('f1', CT_DIM, '1.5 2.5', 1.6) + line('precision', CT_NAVY, '');

  // the deployed operating point, and the threshold that would maximise F1
  g += `<line x1="${px(best.t).toFixed(1)}" y1="${T}" x2="${px(best.t).toFixed(1)}" y2="${H-B}" `
    +  `stroke="${CT_DIM}" stroke-width="1" stroke-dasharray="2 3" opacity=".7"/>`
    +  `<text x="${px(best.t).toFixed(1)}" y="${T+10}" text-anchor="middle" font-size="9" fill="${CT_DIM}">peak F1</text>`;
  g += `<line x1="${px(op).toFixed(1)}" y1="${T}" x2="${px(op).toFixed(1)}" y2="${H-B}" `
    +  `stroke="${CT_NAVY}" stroke-width="1" stroke-dasharray="3 3" opacity=".6"/>`
    +  `<circle cx="${px(op).toFixed(1)}" cy="${py(here.precision).toFixed(1)}" r="3.6" fill="#fff" stroke="${CT_NAVY}" stroke-width="2"/>`
    +  `<circle cx="${px(op).toFixed(1)}" cy="${py(here.recall).toFixed(1)}" r="3.2" fill="#fff" stroke="${CT_BLUE}" stroke-width="1.8"/>`
    +  `<text x="${px(op).toFixed(1)}" y="${H-B-6}" text-anchor="middle" font-size="9.5" fill="${CT_NAVY}" font-weight="600">t = ${op}</text>`;

  g += `<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="${CT_LINE}" stroke-width="1"/>`;
  [0,0.2,0.4,0.6,0.8,1].forEach(t=>{
    g += `<text x="${px(t).toFixed(1)}" y="${H-B+14}" text-anchor="middle" font-size="9.5" fill="${CT_DIM}">${t.toFixed(1)}</text>`; });
  g += `<text x="${((L+W-R)/2).toFixed(0)}" y="${H-2}" text-anchor="middle" font-size="9.5" fill="${CT_DIM}">Fused score threshold</text>`;

  el('ctPerfChart').innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Precision, recall and F1 of the TULYA hybrid matcher plotted against the fused score threshold, measured on the locked test split">${g}</svg>`;
  el('ctPerfLegend').innerHTML =
    `<span><i style="background:${CT_NAVY}"></i>Precision</span>`
  + `<span style="color:${CT_BLUE}"><i class="sw-dash"></i><span style="color:var(--n-500)">Recall</span></span>`
  + `<span style="color:${CT_DIM}"><i class="sw-dash"></i><span style="color:var(--n-500)">F1</span></span>`;

  const opPt = el('ctPerfOp');
  if (opPt) opPt.innerHTML = `Operating point<br><b style="color:var(--navy);font-size:13px">t = ${op}</b>`;

  /* side column: how every backend in the run compares at its own best F1 */
  const order = Object.keys(curves).map(k=>{
    const c = curves[k].slice().sort((a,b)=>b.f1-a.f1)[0];
    return {k, f1:c.f1, t:c.t, p:c.precision, r:c.recall};
  }).sort((a,b)=>b.f1-a.f1);
  const top = order[0].f1 || 1;

  el('ctPerfSide').innerHTML =
    `<div class="m hero"><b>${(here.precision*100).toFixed(1)}%</b>`
  + `<span>Precision at the deployed threshold &#183; recall ${(here.recall*100).toFixed(1)}%</span></div>`
  + `<div class="ct-cmp"><div class="hd">Best F1 by matcher<span>locked test split</span></div>`
  + order.map(o=>`<div class="row${o.k===CT_HYBRID?' me':''}">`
      + `<span class="nm">${esc(o.k)}</span>`
      + `<span class="bar"><i style="width:${(o.f1/top*100).toFixed(1)}%"></i></span>`
      + `<span class="v">${o.f1.toFixed(3)}</span></div>`).join('')
  + `</div>`;

  el('ctPerfProv').innerHTML =
    `<b>Data provenance</b> — all three curves are read from <span class="mono">holdout_run.json</span>, `
  + `101 threshold points per matcher measured on the locked <b>test</b> split `
  + `(${DATA.records.toLocaleString()} records, ${DATA.pairs_scored.toLocaleString()} scored pairs). `
  + `The x-axis is the fused score, not time. The marked point is the deployed threshold `
  + `<b>t = ${op}</b>, chosen on the validation split against a precision floor — not the threshold that `
  + `maximises F1, which is <b>t = ${best.t.toFixed(2)}</b> (F1 ${best.f1.toFixed(3)}). The system gives up `
  + `recall on purpose: at t = ${op} it keeps precision at ${(here.precision*100).toFixed(1)}% and sends the `
  + `rest to a steward rather than merging it. The side comparison reads each matcher at <b>its own</b> best `
  + `threshold, which is the most favourable reading of each and is a ceiling, not an operating point.`;
}

/* --- 1 · Matching Performance ---------------------------------------------
   Two measured views over one panel. They come from different artefacts and
   different splits, so they are never drawn on the same axes; the toggle
   switches between them and each carries its own provenance line. */
let CT_PERF_VIEW = 'operating';

function ctPerformance(){
  const seg = el('ctPerfSeg');
  if (seg && !seg.dataset.wired){
    seg.dataset.wired = '1';
    seg.addEventListener('click', e=>{
      const btn = e.target.closest('button[data-view]'); if (!btn) return;
      CT_PERF_VIEW = btn.getAttribute('data-view');
      try { ctPerformance(); } catch(err){ ctFail('ctPerfChart', err); }
    });
  }
  if (seg) seg.querySelectorAll('button[data-view]').forEach(b=>{
    const on = b.getAttribute('data-view') === CT_PERF_VIEW;
    b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  const sub = el('ctPerfSub');

  if (CT_PERF_VIEW === 'quality' && (DATA.curves || {})[CT_HYBRID]){
    if (sub) sub.textContent = 'Precision, recall and F1 against the fused score threshold';
    ctPerfQuality();
  } else {
    if (sub) sub.textContent = 'Auto-suggest precision against review share across the threshold sweep';
    ctPerfOperating();
  }
}

/* --- 2 · Cross-CPSE Material Network --------------------------------------
   Built by counting the CPSEs actually named on the pairs in this export
   (DATA.queue + DATA.auto_suggest). Spoke weight is that real count. No edge
   is drawn for a relationship the export does not contain. */
function ctNetwork(){
  const pairs = (DATA.queue||[]).concat(DATA.auto_suggest||[]);
  const byCpse = {}, partners = {};
  pairs.forEach(p=>{
    const a = p.record_a && p.record_a.cpse, b = p.record_b && p.record_b.cpse;
    if (!a || !b) return;
    [a,b].forEach(c=>{ byCpse[c] = byCpse[c] || {n:0, items:[], cross:0}; byCpse[c].n++; });
    byCpse[a].items.push(p); if (b!==a) byCpse[b].items.push(p);
    if (a!==b){
      byCpse[a].cross++; byCpse[b].cross++;
      const k=[a,b].sort().join('|'); partners[k]=(partners[k]||0)+1;
    }
  });
  const names = Object.keys(byCpse).sort((x,y)=>byCpse[y].n-byCpse[x].n);
  if (!names.length) throw new Error('no cpse pairs');
  const maxN = byCpse[names[0]].n;

  /* Geometry. Nodes sit on a ring around the identity hub; the hub-to-node
     line is weighted by that CPSE's candidate-pair count. Chords between two
     CPSEs are drawn only where DATA actually contains pairs spanning them. */
  // NR is the node radius: a 36px container for every CPSE, identical
  // across all of them. LOGO_BOX is the square inscribed in that circle.
  const W=560, H=372, cx=W/2, cy=176, rad=116, NR=18;
  const LOGO_BOX = NR * 2 - 9;   // 4.5px of padding on every side
  const pos = names.map((c,i)=>{
    const ang = -Math.PI/2 + i * (2*Math.PI/names.length);
    return {c, ang, x: cx+Math.cos(ang)*rad, y: cy+Math.sin(ang)*rad,
            ux: Math.cos(ang), uy: Math.sin(ang)};
  });
  const at = {}; pos.forEach(n=>at[n.c]=n);

  let g='';
  /* CPSE-to-CPSE chords, behind everything */
  Object.keys(partners).forEach(k=>{
    const [a,b] = k.split('|'); if (!at[a] || !at[b]) return;
    const A = at[a], B = at[b];
    // bow the chord sideways, away from the hub, by enough that a pair of
    // opposite nodes still clears the identity circle
    const mx=(A.x+B.x)/2, my=(A.y+B.y)/2;
    const vx=B.x-A.x, vy=B.y-A.y, L=Math.hypot(vx,vy)||1;
    let px=-vy/L, py=vx/L;
    if ((px*(mx-cx) + py*(my-cy)) < 0){ px=-px; py=-py; }
    const bow = 30 + 40*(1 - Math.min(1, Math.hypot(mx-cx,my-cy)/rad));
    const w = 0.7 + (partners[k]/maxN)*1.5;
    g += `<path class="ch" data-a="${esc(a)}" data-b="${esc(b)}" `
      +  `d="M${A.x.toFixed(1)} ${A.y.toFixed(1)} Q${(mx+px*bow).toFixed(1)} ${(my+py*bow).toFixed(1)} `
      +  `${B.x.toFixed(1)} ${B.y.toFixed(1)}" `
      +  `fill="none" stroke="${CT_BLUE}" stroke-width="${w.toFixed(2)}"/>`;
  });
  /* hub spokes */
  pos.forEach(n=>{
    const w = 0.8 + (byCpse[n.c].n/maxN)*2.0;
    g += `<line class="sp" data-c="${esc(n.c)}" x1="${cx}" y1="${cy}" `
      +  `x2="${n.x.toFixed(1)}" y2="${n.y.toFixed(1)}" stroke="${CT_BLUE}" `
      +  `stroke-width="${w.toFixed(2)}" opacity=".4"/>`;
  });
  /* hub */
  g += `<circle cx="${cx}" cy="${cy}" r="37" fill="#fff" stroke="${CT_NAVY}" stroke-width="1.6"/>`
    +  `<text x="${cx}" y="${cy-3}" text-anchor="middle" font-size="9" font-weight="700" `
    +  `letter-spacing=".4" fill="${CT_NAVY}">MATERIAL</text>`
    +  `<text x="${cx}" y="${cy+8}" text-anchor="middle" font-size="9" font-weight="700" `
    +  `letter-spacing=".4" fill="${CT_NAVY}">IDENTITY</text>`;

  /* nodes: an authorised logo when one is present, a monogram container when not */
  const marks = DATA.cpse_marks || {};
  pos.forEach(n=>{
    const held = cpseRecordCount(n.c);
    // a label on a side node is anchored at the circle edge and runs outward,
    // so a long count never reaches back across the node it belongs to
    const side = Math.abs(n.ux) > 0.3;
    const anc  = side ? (n.ux > 0 ? 'start' : 'end') : 'middle';
    const lx = n.x + n.ux*(NR + (side ? 18 : 16));
    const ly = n.y + n.uy*(NR + (side ? 18 : 16));
    // one place decides both label baselines, so the code and the count can
    // never end up drawn 3px apart on top of each other
    const top = n.uy < -0.3;
    const yCode  = ly + (side ? -2 : (top ? -4 : 12));
    const yCount = yCode + 12;
    const logo = marks[n.c];
    g += `<g class="nd" data-cpse="${esc(n.c)}" tabindex="0" role="button" `
      +  `aria-label="${esc(n.c)}${held!=null?', '+held+' material records':''}, `
      +  `${byCpse[n.c].n} candidate pairs">`
      +  `<rect x="${(n.x-NR).toFixed(1)}" y="${(n.y-NR).toFixed(1)}" `
      +  `width="${NR*2}" height="${NR*2}" rx="10" fill="#fff" `
      +  `stroke="${CT_BLUE}" stroke-width="1.5"/>`
      // The mark sits inside the container with even padding and
      // preserveAspectRatio="meet": never cropped, stretched, recoloured or
      // restyled, and LOGO_BOX is identical for every CPSE. With no asset the
      // same container carries the code instead, and then the code is not
      // repeated outside the node.
      +  (logo
          ? `<image href="${logo}" x="${(n.x-LOGO_BOX/2).toFixed(1)}" y="${(n.y-LOGO_BOX/2).toFixed(1)}" `
            + `width="${LOGO_BOX.toFixed(1)}" height="${LOGO_BOX.toFixed(1)}" `
            + `preserveAspectRatio="xMidYMid meet"/>`
            + `<text x="${lx.toFixed(1)}" y="${yCode.toFixed(1)}" text-anchor="${anc}" `
            + `font-size="10.5" font-weight="600" fill="${CT_NAVY}">${esc(n.c)}</text>`
          : `<text x="${n.x.toFixed(1)}" y="${(n.y+4).toFixed(1)}" text-anchor="middle" `
            + `font-size="10.5" font-weight="700" fill="${CT_NAVY}">${esc(n.c)}</text>`)
      +  `<text x="${lx.toFixed(1)}" y="${(logo ? yCount : yCode).toFixed(1)}" text-anchor="${anc}" `
      +  `font-size="9" fill="${CT_DIM}">${held!=null ? held.toLocaleString()+' materials' : byCpse[n.c].n+' pairs'}</text>`
      +  `</g>`;
  });
  el('ctNetGraph').innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Candidate material identities shared between CPSEs in this export">${g}</svg>`;

  const hx = el('ctNetHx');
  if (hx) hx.innerHTML = `${names.length} CPSEs<br><b style="color:var(--navy);font-size:13px">${pairs.length} pairs</b>`;

  const detail = el('ctNetDetail');
  const svg = el('ctNetGraph').querySelector('svg');
  const rest = () => {
    svg.classList.remove('focus');
    svg.querySelectorAll('.nd').forEach(o=>o.classList.remove('on','dim'));
    svg.querySelectorAll('.ch,.sp').forEach(o=>o.classList.remove('hot','dim'));
    detail.innerHTML =
      `Select a CPSE to see the candidate identities it shares. `
    + `Across this export, <b>${DATA.scope.inter.toLocaleString()}</b> candidate pairs cross CPSE boundaries and `
    + `<b>${DATA.scope.intra.toLocaleString()}</b> sit inside a single CPSE across its ${DATA.scope.plants} plants.`;
  };
  rest();

  svg.querySelectorAll('.nd').forEach(node=>{
    const c = node.getAttribute('data-cpse');
    const show = () => {
      /* highlight this CPSE's identities: its own node, its hub spoke and every
         chord it participates in; everything else recedes. */
      svg.classList.add('focus');
      svg.querySelectorAll('.nd').forEach(o=>{
        const oc = o.getAttribute('data-cpse');
        const linked = oc===c || partners[[c,oc].sort().join('|')];
        o.classList.toggle('on', oc===c);
        o.classList.toggle('dim', !linked);
      });
      svg.querySelectorAll('.ch').forEach(o=>{
        const hot = o.getAttribute('data-a')===c || o.getAttribute('data-b')===c;
        o.classList.toggle('hot', !!hot); o.classList.toggle('dim', !hot);
      });
      svg.querySelectorAll('.sp').forEach(o=>o.classList.toggle('dim', o.getAttribute('data-c')!==c));

      const d = byCpse[c];
      const top = d.items.slice().sort((a,b)=>b.score-a.score)[0];
      const held = cpseRecordCount(c);
      const plants = DATA.cpse_records && DATA.cpse_records.plants && DATA.cpse_records.plants[c];
      const linkedNames = Object.keys(partners).filter(k=>k.split('|').includes(c))
        .map(k=>k.split('|').find(x=>x!==c));

      let html = `<div class="nd-head">${cpseMark(c,28)}<div><b>${esc(c)}</b>`
        + `<span>${held!=null ? held.toLocaleString()+' material records'
              + (plants ? ' across '+plants+' plants' : '') : 'record count unavailable'}`
        + ` &#183; ${d.n} candidate pair${d.n===1?'':'s'} &#183; ${d.cross} crossing a CPSE boundary</span></div></div>`;
      if (linkedNames.length)
        html += `<div class="nd-links">Shares candidate identities with `
              + linkedNames.map(x=>cpseTag(x, partners[[c,x].sort().join('|')]+' pairs', 20)).join(' ')
              + `</div>`;
      if (top){
        const mine  = top.record_a.cpse === c ? top.record_a : top.record_b;
        const other = top.record_a.cpse === c ? top.record_b : top.record_a;
        html += `<div class="nd-top">Highest-scoring: <b>${esc(mine.description)}</b><br>`
          + `<span class="mono">${esc(mine.legacy_code)}</span> at ${esc(mine.plant||'—')} `
          + `&#8596; <span class="mono">${esc(other.legacy_code)}</span> at ${esc(other.cpse)} `
          + `&#183; score <b>${top.score.toFixed(3)}</b> &#183; ${top.coverage} spec${top.coverage===1?'':'s'} readable on both sides</div>`;
      } else {
        html += `<div class="nd-top none">No candidate pair detail for this CPSE in this export.</div>`;
      }
      detail.innerHTML = html;
    };
    node.addEventListener('click', show);
    node.addEventListener('mouseenter', show);
    node.addEventListener('focus', show);
    node.addEventListener('keydown', e=>{ if (e.key==='Enter'||e.key===' '){ e.preventDefault(); show(); } });
  });
  el('ctNetGraph').addEventListener('mouseleave', ()=>{
    if (!svg.querySelector('.nd.pinned')) rest();
  });

  el('ctNetProv').innerHTML =
    `<b>Data provenance</b> — spokes and chords are counted from the <b>${pairs.length}</b> candidate pairs carried in this `
  + `static export (${(DATA.queue||[]).length} review-band, ${(DATA.auto_suggest||[]).length} auto-suggest), not from all `
  + `${DATA.pairs_scored.toLocaleString()} scored pairs. Spoke weight is that count, and a chord is drawn only between `
  + `two CPSEs the export actually pairs. Material records per CPSE are a tally of the locked <b>test</b> split `
  + `(${DATA.records.toLocaleString()} records). `
  + (Object.keys(DATA.cpse_marks||{}).length
      ? `CPSE marks are the logo files supplied in <span class="code">tulya/assets/cpse/</span>.`
      : `CPSE marks show a monogram placeholder: no official logo assets have been supplied in `
        + `<span class="code">tulya/assets/cpse/</span> yet.`)
  + ` No relationship is drawn that the export does not contain.`;
}

/* --- 3 · Material Recommendation ------------------------------------------
   The highest-scoring auto-suggest pair. Confidence is the fused score that
   produced it; evidence is the signal breakdown the engine recorded. Stock and
   demand are only shown when a procurement row exists for the same material —
   otherwise the field reads unavailable. */
function ctRecommend(){
  const list = (DATA.auto_suggest||[]).slice().sort((a,b)=>b.score-a.score);
  const top = list[0];
  if (!top) throw new Error('no auto-suggest pairs');
  const a = top.record_a, b = top.record_b;

  let proc = null;
  try {
    proc = TULYA.procurementRows().find(r =>
      r.material && r.material.description &&
      r.material.description.toLowerCase() === a.description.toLowerCase()) || null;
  } catch(e){ proc = null; }

  const sig = (top.explain && top.explain.signals) || [];
  const evRows = sig.length
    ? sig.map(x=>`<div class="r"><span>${esc(x.name)}<span style="color:var(--n-400);font-weight:400"> &#183; weight ${Number(x.weight).toFixed(2)}</span></span><b class="mono">${Number(x.value).toFixed(3)}</b></div>`).join('')
    : '<div class="r"><span class="unavailable">Evidence unavailable for this pair.</span></div>';

  const cnmc = proc && proc.material.cnmc
    ? `<div class="cnmc"><span class="code">${esc(proc.material.cnmc)}</span> <span style="color:var(--n-400)">&#183; candidate code, not yet minted</span></div>`
    : `<div class="cnmc"><span class="unavailable">Canonical CNMC unavailable &#8212; no national code has been minted for this identity.</span></div>`;

  const facts = [
    [pct(top.score), 'Confidence'],
    [proc ? qty(proc.available) : '&#8212;', 'Units available'],
    [proc ? qty(proc.required)  : '&#8212;', 'Units required'],
  ];

  el('ctRecoBody').innerHTML =
    `<div class="lede">${esc(a.description)}</div>${cnmc}`
  + `<div style="margin-top:9px;font-size:11.5px;color:var(--n-500);line-height:1.5">`
  +   `${top.coverage} specification${top.coverage===1?'':'s'} readable on both sides`
  +   ` &#183; <span class="mono">${esc(a.legacy_code)}</span> &#8596; <span class="mono">${esc(b.legacy_code)}</span></div>`
  + `<div class="reco-cpses"><span class="k">Matched CPSEs</span>`
  +   `<span class="cpse-stack">${[a.cpse,b.cpse].map(c=>cpseTag(c,'',20)).join('')}</span></div>`
  + `<div class="facts">${facts.map(([v,k])=>`<div class="f"><b>${v}</b><span>${k}</span></div>`).join('')}</div>`
  + (proc ? `<div style="margin-top:9px;font-size:11.5px;color:var(--n-500)">Coverage `
      + `<b style="color:var(--n-800)">${(proc.coverage*100).toFixed(0)}%</b> of the requirement `
      + `&#183; quantities <b>simulated</b></div>`
    : `<div style="margin-top:9px;font-size:11.5px" class="unavailable">Stock and demand unavailable &#8212; no procurement row for this material in this export.</div>`)
  + `<div class="ev"><div class="r" style="color:var(--n-500);font-weight:600;text-transform:uppercase;letter-spacing:.4px;font-size:10px"><span>Evidence</span><span></span></div>${evRows}</div>`
  + `<div class="acts">`
  +   `<button class="btn primary" onclick="openCase(${top.a},${top.b})">Review evidence</button>`
  +   `<button class="btn" onclick="switchPanel('passport')">View material</button>`
  + `</div>`;

  el('ctRecoProv').innerHTML =
    `<b>Data provenance</b> — highest-scoring pair of the <b>${list.length}</b> auto-suggest pairs in this export. `
  + `Confidence is the fused score recorded by the engine, not a separate estimate. `
  + `Stock, demand and coverage are <b>simulated</b> quantities, labelled as such wherever they appear.`;
}
