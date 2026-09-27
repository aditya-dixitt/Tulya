/* ===========================================================================
   TULYA — derived material model
   ---------------------------------------------------------------------------
   ONE connected data model. Everything below is derived from the material
   records the existing prototype already ships (DATA.queue, DATA.auto_suggest,
   DATA.vetoed_examples, DATA.challenge) — the same real records the Review
   Queue, Golden Records, Vetoes and Audit Log already use.

   Three kinds of value live here, and they are labelled differently on screen:

     MEASURED    produced by the matching pipeline on the locked test split
                 (scores, attributes, verdicts, coverage, veto outcomes).
     DERIVED     computed deterministically from those records by this file
                 (material identities, CNMC, equivalence state, case routing).
     SIMULATED   stock, demand and procurement quantities. These do not exist
                 in the source records. They are generated from a fixed hash of
                 the record id so the demo is reproducible, and every screen
                 that shows them says SIMULATED · ILLUSTRATIVE. They are not a
                 measured CPSE result and must never be quoted as one.
   =========================================================================== */
const TULYA = (function () {

  /* ---------- deterministic pseudo-randomness, seeded by record id -------- */
  function h32(n, salt) {
    let x = (n | 0) ^ 0x9e3779b9;
    for (let i = 0; i < (salt || '').length; i++) x = Math.imul(x ^ salt.charCodeAt(i), 0x85ebca6b);
    x ^= x >>> 15; x = Math.imul(x, 0x2545f491); x ^= x >>> 13;
    return (x >>> 0);
  }
  const rnd = (id, salt) => h32(id, salt) / 4294967296;
  const pick = (id, salt, arr) => arr[Math.floor(rnd(id, salt) * arr.length) % arr.length];
  const between = (id, salt, lo, hi) => Math.round(lo + rnd(id, salt) * (hi - lo));

  /* ---------- category → family, standards, unit economics ---------------- */
  /* VERIFIED marks a standard whose cross-reference is stated in the TULYA
     reference set (IS 1239 Part 1 / BS EN 10255 / ASTM A53 / JIS G3452 — the
     pipe family). Everything else is a PROTOTYPE relationship shipped so the
     graph is walkable, and is shown as REQUIRES VERIFICATION. */
  const FAMILY = {
    stud_bolt:       'FST', hex_nut:      'FST', plain_washer: 'FST', spring_washer: 'FST',
    seamless_pipe:   'PIP', elbow_90:     'PIP', wnrf_flange:  'PIP',
    ball_valve:      'VLV', gate_valve:   'VLV', globe_valve:  'VLV', check_valve:   'VLV',
    centrifugal_pump:'ROT', induction_motor:'ROT', roller_bearing:'ROT',
    o_ring:          'SEL', spiral_gasket:'SEL', caf_gasket:   'SEL',
    xlpe_cable:      'ELE'
  };
  const FAMILY_NAME = {
    FST: 'Fasteners', PIP: 'Piping & fittings', VLV: 'Valves',
    ROT: 'Rotating equipment', SEL: 'Sealing', ELE: 'Electrical'
  };
  const CATEGORY_LABEL = {
    stud_bolt: 'Stud / hex bolt', hex_nut: 'Hex nut', plain_washer: 'Plain washer',
    spring_washer: 'Spring washer', seamless_pipe: 'Seamless pipe', elbow_90: '90° elbow',
    wnrf_flange: 'WNRF flange', ball_valve: 'Ball valve', gate_valve: 'Gate valve',
    globe_valve: 'Globe valve', check_valve: 'Check valve', centrifugal_pump: 'Centrifugal pump',
    induction_motor: 'Induction motor', roller_bearing: 'Roller bearing', o_ring: 'O-ring',
    spiral_gasket: 'Spiral wound gasket', caf_gasket: 'CAF gasket', xlpe_cable: 'XLPE cable'
  };

  /* standard → {scope, verified} ; edges carry the relationship type */
  const STANDARDS = {
    PIP: {
      nodes: [
        { id: 'IS 1239 Part 1', body: 'BIS',  scope: 'Steel tubes — mild steel, welded and seamless, up to DN150', verified: true,  note: 'The Indian designation carried by most CPSE pipe records.' },
        { id: 'BS EN 10255',    body: 'BSI',  scope: 'Non-alloy steel tubes suitable for welding and threading',    verified: true,  note: 'Replaced BS 1387, which is withdrawn. Cross-reference is scoped, not blanket.' },
        { id: 'ASTM A53',       body: 'ASTM', scope: 'Pipe, steel, black and hot-dipped, zinc-coated, welded and seamless', verified: true, note: 'Related — wall class must be checked before substitution.' },
        { id: 'JIS G3452',      body: 'JIS',  scope: 'Carbon steel pipes for ordinary piping',                      verified: true,  note: 'Related designation, different wall schedule table.' }
      ],
      edges: [
        { a: 'IS 1239 Part 1', b: 'BS EN 10255', rel: 'EQUIVALENT',           state: 'SCOPED',   evidence: 'Scoped equivalence for dimensions and threading within the overlapping bore range. Outside that range the standards do not correspond.' },
        { a: 'IS 1239 Part 1', b: 'ASTM A53',    rel: 'SUBSTITUTE',           state: 'REQUIRES REVIEW', evidence: 'Substitution is possible on chemistry and pressure duty, but the wall-class designations differ. Confirm SCH against the drawing before treating as equivalent.' },
        { a: 'IS 1239 Part 1', b: 'JIS G3452',   rel: 'REQUIRES VERIFICATION', state: 'REQUIRES REVIEW', evidence: 'Related family. The JIS schedule table is not a one-to-one map to the IS light/medium/heavy classes.' },
        { a: 'BS EN 10255',    b: 'ASTM A53',    rel: 'SUBSTITUTE',           state: 'REQUIRES REVIEW', evidence: 'Both cover welded and seamless non-alloy tube; tolerance classes differ.' }
      ]
    },
    FST: {
      nodes: [
        { id: 'IS 1367',   body: 'BIS',  scope: 'Technical supply conditions for threaded steel fasteners', verified: false },
        { id: 'ISO 898-1', body: 'ISO',  scope: 'Mechanical properties of fasteners — bolts, screws and studs', verified: false },
        { id: 'ASTM A193', body: 'ASTM', scope: 'Alloy and stainless steel bolting for high-temperature service', verified: false },
        { id: 'IS 1364',   body: 'BIS',  scope: 'Hexagon head bolts, screws and nuts — product grades A and B', verified: false }
      ],
      edges: [
        { a: 'IS 1367',   b: 'ISO 898-1', rel: 'EQUIVALENT', state: 'REQUIRES REVIEW', evidence: 'Property classes correspond. Prototype relationship — not verified against the standard texts.' },
        { a: 'IS 1364',   b: 'ISO 898-1', rel: 'SUPERSET',   state: 'REQUIRES REVIEW', evidence: 'Dimensional standard against a mechanical-property standard; they govern different attributes.' },
        { a: 'ASTM A193', b: 'ISO 898-1', rel: 'CONFLICT',   state: 'REQUIRES REVIEW', evidence: 'Grade systems are not interchangeable. B7 is not an ISO property class and must not be mapped onto one.' }
      ]
    },
    VLV: {
      nodes: [
        { id: 'API 6D',    body: 'API', scope: 'Pipeline and piping valves',                    verified: false },
        { id: 'API 600',   body: 'API', scope: 'Bolted bonnet steel gate valves for petroleum and gas', verified: false },
        { id: 'IS 14846',  body: 'BIS', scope: 'Sluice valves for water works purposes',        verified: false },
        { id: 'ASME B16.34', body: 'ASME', scope: 'Valves — flanged, threaded and welding end', verified: false }
      ],
      edges: [
        { a: 'API 600',  b: 'ASME B16.34', rel: 'SUPERSET',   state: 'REQUIRES REVIEW', evidence: 'B16.34 sets the pressure-temperature ratings API 600 valves are built to. Prototype relationship.' },
        { a: 'API 6D',   b: 'API 600',     rel: 'SUBSTITUTE', state: 'REQUIRES REVIEW', evidence: 'Overlapping scope for gate valves in pipeline duty only. Prototype relationship.' },
        { a: 'IS 14846', b: 'API 600',     rel: 'CONFLICT',   state: 'REQUIRES REVIEW', evidence: 'Water-works duty against hydrocarbon duty. Not a substitution path.' }
      ]
    },
    ROT: {
      nodes: [
        { id: 'API 610',     body: 'API', scope: 'Centrifugal pumps for petroleum, petrochemical and natural gas', verified: false },
        { id: 'IS 5120',     body: 'BIS', scope: 'Technical requirements — rotodynamic special purpose pumps',     verified: false },
        { id: 'IEC 60034-1', body: 'IEC', scope: 'Rotating electrical machines — rating and performance',          verified: false },
        { id: 'IS 12615',    body: 'BIS', scope: 'Line operated three-phase AC motors — efficiency classes',        verified: false },
        { id: 'ISO 15',      body: 'ISO', scope: 'Rolling bearings — radial bearings, boundary dimensions',         verified: false }
      ],
      edges: [
        { a: 'API 610',     b: 'IS 5120',  rel: 'SUBSTITUTE', state: 'REQUIRES REVIEW', evidence: 'Both govern process pumps; API 610 is the stricter hydrocarbon-duty specification. Prototype relationship.' },
        { a: 'IEC 60034-1', b: 'IS 12615', rel: 'EQUIVALENT', state: 'REQUIRES REVIEW', evidence: 'IE efficiency classes correspond. Prototype relationship — not verified against the standard texts.' }
      ]
    },
    SEL: {
      nodes: [
        { id: 'ASME B16.20', body: 'ASME', scope: 'Metallic gaskets for pipe flanges — ring joint, spiral wound', verified: false },
        { id: 'IS 2712',     body: 'BIS',  scope: 'Compressed asbestos fibre jointing',                            verified: false },
        { id: 'ISO 3601',    body: 'ISO',  scope: 'Fluid power systems — O-rings, inside diameters and sections',  verified: false }
      ],
      edges: [
        { a: 'ASME B16.20', b: 'IS 2712', rel: 'CONFLICT', state: 'REQUIRES REVIEW', evidence: 'Different gasket construction entirely — spiral wound metallic against compressed fibre. Not substitutable.' }
      ]
    },
    ELE: {
      nodes: [
        { id: 'IS 7098 Part 2', body: 'BIS', scope: 'XLPE insulated cables for working voltages 3.3 kV to 33 kV', verified: false },
        { id: 'IEC 60502-1',    body: 'IEC', scope: 'Power cables with extruded insulation, 1 kV to 30 kV',        verified: false }
      ],
      edges: [
        { a: 'IS 7098 Part 2', b: 'IEC 60502-1', rel: 'EQUIVALENT', state: 'REQUIRES REVIEW', evidence: 'Overlapping voltage range and construction. Prototype relationship — not verified against the standard texts.' }
      ]
    }
  };

  /* indicative unit value per family, in rupees. SIMULATED. */
  const UNIT_VALUE = { FST: 180, PIP: 2400, VLV: 48000, ROT: 165000, SEL: 640, ELE: 1250 };
  const UNIT_OF    = { FST: 'nos', PIP: 'm',  VLV: 'nos', ROT: 'nos',  SEL: 'nos', ELE: 'm' };

  const familyOf   = c => FAMILY[c] || 'FST';
  const catLabel   = c => CATEGORY_LABEL[c] || String(c || 'unclassified').replace(/_/g, ' ');

  /* ---------- CNMC minting ------------------------------------------------ */
  const ORDER = ['thread', 'bore_in', 'schedule', 'pressure_class', 'length_mm', 'id_mm',
                 'section_mm', 'dim_mm', 'cap_m3hr', 'head_m', 'power_kw', 'rpm',
                 'cores', 'csa_sqmm', 'voltage_kv', 'bearing_desig', 'material_grade'];
  const SUFFIX = { bore_in: 'IN', schedule: 'SCH', pressure_class: 'CL', length_mm: 'L',
                   id_mm: 'ID', section_mm: 'W', dim_mm: 'D', cap_m3hr: 'Q', head_m: 'H',
                   power_kw: 'KW', rpm: 'RPM', cores: 'C', csa_sqmm: 'SQ', voltage_kv: 'KV' };

  function tokenise(key, val) {
    const v = String(val).toUpperCase().replace(/[^A-Z0-9.]/g, '');
    if (key === 'thread' || key === 'material_grade' || key === 'bearing_desig') return v;
    const s = SUFFIX[key] || '';
    return (key === 'schedule' || key === 'pressure_class') ? s + v : v + s;
  }

  function cnmcFor(category, attrs) {
    const fam = familyOf(category);
    const base = String(category || 'ITEM').toUpperCase().replace(/[^A-Z0-9]/g, '');
    const parts = ORDER.filter(k => attrs && attrs[k] != null && attrs[k] !== '')
                       .map(k => tokenise(k, attrs[k]));
    return ['NMC', fam, base].concat(parts.slice(0, 3)).join('-');
  }

  /* ---------- governed verdict states ------------------------------------- */
  /* Derived strictly from what the pipeline measured on the pair: the veto
     outcome, the attribute verdicts, the coverage and the fused score. The
     engine never asserts a merge — these are proposals with a named reason. */
  const VERDICTS = {
    IDENTICAL:   { label: 'IDENTICAL',              cls: 'v-identical',   next: 'Ready for governed mapping',   tone: 'good' },
    EQUIVALENT:  { label: 'EQUIVALENT',             cls: 'v-equivalent',  next: 'Steward approval',             tone: 'good' },
    CONDITIONAL: { label: 'CONDITIONAL EQUIVALENCE',cls: 'v-conditional', next: 'Engineering / steward review',  tone: 'amber' },
    DIFFERENT:   { label: 'DIFFERENT',              cls: 'v-different',   next: 'No mapping proposed',          tone: 'dim' },
    CONFLICT:    { label: 'CONFLICT',               cls: 'v-conflict',    next: 'Merge blocked',                tone: 'bad' },
    UNRESOLVED:  { label: 'UNRESOLVED',             cls: 'v-unresolved',  next: 'More evidence required',       tone: 'dim' }
  };

  function verdictOf(it) {
    const x = it.explain || {};
    const attrs = x.attributes || [];
    const mism = attrs.filter(a => a.verdict === 'MISMATCH');
    const unk = attrs.filter(a => a.verdict === 'UNKNOWN');
    const agree = attrs.filter(a => a.verdict === 'MATCH');
    const cov = it.coverage || 0;
    const tAuto = 0.92, tDiscard = 0.75;

    if (x.vetoed || mism.length) {
      return { key: 'CONFLICT', reason: mism.length
        ? mism.map(a => a.key + ' ' + (a.a ?? '—') + ' ≠ ' + (a.b ?? '—')).join(', ')
        : 'a specification known on both sides disagreed' };
    }
    if (cov === 0 || unk.length > agree.length) {
      return { key: 'UNRESOLVED', reason: cov === 0
        ? 'no specification could be read on both sides \u2014 nothing confirms and nothing contradicts'
        : unk.length + ' of ' + attrs.length + ' specifications could not be read on one side, against ' +
          agree.length + ' that agree \u2014 the evidence base is mostly missing' };
    }
    if (it.score < tDiscard) {
      return { key: 'DIFFERENT', reason: 'fused score ' + it.score.toFixed(3) + ' sits below the discard threshold' };
    }
    /* IDENTICAL and EQUIVALENT are not degrees of confidence. IDENTICAL means
       the two records state the item the same way once normalised; EQUIVALENT
       means they state it differently and the specifications still agree \u2014
       and that second case is what this whole system exists to find. */
    if (it.score >= tAuto && cov >= 2 && !unk.length) {
      const flat = s => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      const same = flat(it.record_a.description) === flat(it.record_b.description);
      return same
        ? { key: 'IDENTICAL', reason: 'the normalised descriptions are indistinguishable and every readable specification agrees' }
        : { key: 'EQUIVALENT', reason: 'the descriptions differ in wording, but all ' + agree.length +
            ' readable specification' + (agree.length === 1 ? '' : 's') + ' agree and none conflict' };
    }
    if (it.score >= tAuto && cov < 2) {
      return { key: 'CONDITIONAL', reason: 'clears ' + tAuto + ' but rests on ' + cov + ' readable specification' + (cov === 1 ? '' : 's') + ' — the coverage floor caps it at review' };
    }
    return { key: 'CONDITIONAL', reason: unk.length
      ? agree.length + ' specification' + (agree.length === 1 ? '' : 's') + ' agree, ' + unk.length + ' could not be read on one side'
      : 'score sits in the steward review band — the call is genuinely marginal' };
  }

  /* ---------- engineering evidence ---------------------------------------- */
  const ATTR_LABEL = {
    thread: 'Thread / nominal diameter', material_grade: 'Grade', length_mm: 'Length',
    bore_in: 'Nominal bore', schedule: 'Wall class / schedule', pressure_class: 'Pressure class',
    id_mm: 'Inside diameter', section_mm: 'Section', dim_mm: 'Dimension',
    cap_m3hr: 'Capacity', head_m: 'Head', power_kw: 'Rated power', rpm: 'Speed',
    cores: 'Cores', csa_sqmm: 'Conductor CSA', voltage_kv: 'Voltage grade',
    bearing_desig: 'Bearing designation'
  };
  const ATTR_UNIT = { length_mm: 'mm', id_mm: 'mm', section_mm: 'mm', dim_mm: 'mm',
                      bore_in: 'in', cap_m3hr: 'm³/hr', head_m: 'm', power_kw: 'kW',
                      rpm: 'rpm', csa_sqmm: 'sq mm', voltage_kv: 'kV' };
  const attrLabel = k => ATTR_LABEL[k] || String(k).replace(/_/g, ' ');
  const attrValue = (k, v) => v == null || v === '' ? null : (String(v) + (ATTR_UNIT[k] ? ' ' + ATTR_UNIT[k] : ''));

  /* Standards row sits alongside the measured attribute rows. Its verdict is
     REVIEW SCOPE whenever the two sides carry different designations — a
     scoped cross-reference is not an assertion of equivalence. */
  function standardsEvidence(it) {
    const fam = familyOf(it.record_a.category);
    const set = STANDARDS[fam];
    if (!set) return null;
    const a = set.nodes[0], b = set.nodes[Math.min(1, set.nodes.length - 1)];
    const sameCpse = it.record_a.cpse === it.record_b.cpse;
    const designations = sameCpse ? [a.id, a.id] : [a.id, b.id];
    const differ = designations[0] !== designations[1];
    const edge = differ ? (set.edges.find(e => (e.a === designations[0] && e.b === designations[1]) ||
                                               (e.b === designations[0] && e.a === designations[1])) || set.edges[0]) : null;
    return {
      family: fam, a: designations[0], b: designations[1], differ,
      rel: edge ? edge.rel : 'SAME DESIGNATION',
      state: edge ? edge.state : 'SCOPED',
      verified: a.verified && b.verified,
      evidence: edge ? edge.evidence : 'Both records carry the same designation, so no cross-reference is needed.',
      verdict: differ ? 'REVIEW SCOPE' : 'MATCH'
    };
  }

  function evidenceRows(it) {
    const x = it.explain || {};
    const rows = (x.attributes || []).map(at => ({
      key: at.key, label: attrLabel(at.key),
      a: attrValue(at.key, at.a), b: attrValue(at.key, at.b),
      verdict: at.verdict,
      hard: at.key === 'thread' || at.key === 'bore_in' || at.key === 'pressure_class' ||
            at.key === 'schedule' || at.key === 'material_grade' || at.key === 'bearing_desig'
    }));
    const st = standardsEvidence(it);
    if (st) rows.push({ key: 'standard', label: 'Standard', a: st.a, b: st.b,
                        verdict: st.verdict, standards: st, hard: false });
    return rows;
  }

  /* ---------- material identities: connected components over pair edges --- */
  /* A material identity is a cluster of source records the pipeline proposed
     as the same item. This is the object Analytics, Procurement, the Simulator
     and the Passport all read — there is no second dataset. */
  let MATERIALS = [], BY_RECORD = {}, BY_ID = {}, ALL_CASES = [];

  function build(DATA, RECORDS) {
    ALL_CASES = [].concat(DATA.queue || [], DATA.auto_suggest || [],
                          DATA.vetoed_examples || [], DATA.challenge || []);

    const parent = {};
    const find = x => { if (!(x in parent)) parent[x] = x; let r = x;
      while (parent[r] !== r) r = parent[r];
      while (parent[x] !== r) { const n = parent[x]; parent[x] = r; x = n; } return r; };
    const union = (a, b) => { const ra = find(a), rb = find(b); if (ra !== rb) parent[Math.max(ra, rb)] = Math.min(ra, rb); };

    /* CONFLICT edges do not join a cluster — a vetoed pair is evidence that two
       records are NOT the same item, so merging them into one identity would
       contradict the veto that produced it. */
    ALL_CASES.forEach(it => {
      const v = verdictOf(it);
      if (v.key === 'CONFLICT' || v.key === 'DIFFERENT') { find(it.a); find(it.b); return; }
      union(it.a, it.b);
    });

    const buckets = {};
    Object.keys(RECORDS).forEach(rid => {
      const r = find(+rid); (buckets[r] = buckets[r] || []).push(+rid);
    });

    MATERIALS = Object.entries(buckets).map(([root, ids]) => {
      ids.sort((a, b) => a - b);
      const recs = ids.map(id => RECORDS[id]).filter(Boolean);
      if (!recs.length) return null;
      /* canonical = the member with the most specifications resolved */
      let canon = recs[0];
      recs.forEach(r => {
        const n = Object.keys(r.attrs || {}).length, c = Object.keys(canon.attrs || {}).length;
        if (n > c || (n === c && (r.description || '').length > (canon.description || '').length)) canon = r;
      });
      const merged = {};
      recs.forEach(r => Object.entries(r.attrs || {}).forEach(([k, v]) => { if (merged[k] == null) merged[k] = v; }));

      const cases = ALL_CASES.filter(it => ids.includes(it.a) || ids.includes(it.b));
      const verdicts = cases.map(it => verdictOf(it).key);
      const rank = ['CONFLICT', 'UNRESOLVED', 'CONDITIONAL', 'EQUIVALENT', 'IDENTICAL', 'DIFFERENT'];
      const status = rank.find(k => verdicts.includes(k)) || 'UNRESOLVED';

      const fam = familyOf(canon.category);
      const cpses = [...new Set(recs.map(r => r.cpse))].sort();
      const id = 'MAT-' + String(root).padStart(6, '0');

      /* ---- SIMULATED from here down --------------------------------------- */
      const unitValue = Math.round(UNIT_VALUE[fam] * (0.7 + rnd(+root, 'uv') * 0.6));
      const stock = recs.map(r => ({
        record_id: r.record_id, cpse: r.cpse, plant: r.plant, legacy_code: r.legacy_code,
        qty: between(r.record_id, 'stk', fam === 'ROT' ? 2 : 120, fam === 'ROT' ? 40 : 5200)
      }));
      const hasDemand = rnd(+root, 'dm') > 0.55;
      const demandCpse = pick(+root, 'dc', cpses);
      const demand = hasDemand ? {
        cpse: demandCpse,
        qty: between(+root, 'dq', fam === 'ROT' ? 3 : 400, fam === 'ROT' ? 25 : 6000),
        raised: 'indent ' + ['REQ', 'IND', 'PR'][Math.floor(rnd(+root, 'dt') * 3) % 3] + '-' +
                between(+root, 'dn', 10000, 99999)
      } : null;

      return {
        id, root: +root, record_ids: ids, records: recs, canonical: canon,
        description: canon.description, category: canon.category,
        category_label: catLabel(canon.category), family: fam, family_name: FAMILY_NAME[fam],
        attrs: merged, cpses, plants: [...new Set(recs.map(r => r.plant).filter(Boolean))],
        cnmc: cnmcFor(canon.category, merged),
        equivalence_status: status, cases,
        legacy_identities: recs.map(r => ({ cpse: r.cpse, plant: r.plant, legacy_code: r.legacy_code, record_id: r.record_id })),
        standards: (STANDARDS[fam] || { nodes: [] }).nodes.map(n => n.id),
        unit_value: unitValue,
        unit: UNIT_OF[fam],
        stock, stock_total: stock.reduce((s, x) => s + x.qty, 0),
        demand,
        cross_cpse: cpses.length > 1
      };
    }).filter(Boolean);

    MATERIALS.sort((a, b) => b.records.length - a.records.length || a.id.localeCompare(b.id));
    BY_ID = {}; BY_RECORD = {};
    MATERIALS.forEach(m => { BY_ID[m.id] = m; m.record_ids.forEach(r => BY_RECORD[r] = m); });
    return MATERIALS;
  }

  /* ---------- procurement view over the same materials -------------------- */
  function procurementRows() {
    return MATERIALS.filter(m => m.demand).map(m => {
      const reqCpse = m.demand.cpse;
      const elsewhere = m.stock.filter(s => s.cpse !== reqCpse);
      const available = elsewhere.reduce((s, x) => s + x.qty, 0);
      const best = elsewhere.slice().sort((a, b) => b.qty - a.qty)[0] || null;
      const coverage = m.demand.qty ? Math.min(1, available / m.demand.qty) : 0;
      let signal;
      if (m.equivalence_status === 'CONFLICT') signal = 'UNRESOLVED CASE';
      else if (!elsewhere.length) signal = 'NO CROSS-CPSE STOCK';
      else if (coverage >= 0.6) signal = 'CROSS-CPSE STOCK FOUND';
      else if (m.cross_cpse) signal = 'DEMAND AGGREGATION CANDIDATE';
      else signal = 'OPPORTUNITY DETECTED';
      return { material: m, requesting_cpse: reqCpse, required: m.demand.qty,
               available, best_source: best, coverage, signal,
               standards_status: m.standards.length ? (m.family === 'PIP' ? 'VERIFIED CROSS-REFERENCE' : 'REQUIRES VERIFICATION') : 'NONE ON FILE',
               review_status: m.equivalence_status };
    }).sort((a, b) => b.coverage - a.coverage || b.required - a.required);
  }

  /* ---------- collaboration cases ----------------------------------------- */
  const STAGES = ['AI', 'DATA STEWARD', 'ENGINEERING', 'PROCUREMENT', 'FINAL GOVERNANCE'];
  const STEWARDS  = ['R. Nair', 'A. Deshmukh', 'P. Iyer', 'S. Banerjee', 'M. Qureshi'];
  const ENGINEERS = ['V. Rao (Static)', 'K. Menon (Rotating)', 'T. Ghosh (Piping)', 'D. Shah (Electrical)'];

  function caseOf(it) {
    const v = verdictOf(it);
    const seed = it.a * 31 + it.b;
    let stage;
    if (v.key === 'CONFLICT') stage = 2;
    else if (v.key === 'UNRESOLVED') stage = 1;
    else if (v.key === 'CONDITIONAL') stage = 2;
    else if (v.key === 'IDENTICAL') stage = 3;
    else stage = 1 + (h32(seed, 'st') % 2);
    return {
      case_id: 'CASE-' + String(it.a).padStart(5, '0') + '-' + String(it.b).padStart(5, '0'),
      pair: it, verdict: v, stage, stage_name: STAGES[stage],
      steward: pick(seed, 'sw', STEWARDS),
      engineer: v.key === 'CONDITIONAL' || v.key === 'CONFLICT' ? pick(seed, 'en', ENGINEERS) : null,
      procurement: stage >= 3 ? 'Linked to open demand' : 'Not yet routed',
      material: BY_RECORD[it.a] || BY_RECORD[it.b] || null
    };
  }

  function timelineOf(c) {
    const done = i => i < c.stage + 2;
    const steps = [
      ['AI proposal generated', 'semantic retrieval returned this pair as a candidate'],
      ['Attributes extracted', (c.pair.coverage || 0) + ' specification(s) readable on both sides'],
      ['Standards evidence retrieved', (c.material && c.material.standards[0]) || 'none on file'],
      ['Engineering validation', c.engineer ? 'assigned to ' + c.engineer : 'not required at this verdict'],
      ['Steward approval', c.steward],
      ['CNMC creation', c.material ? c.material.cnmc : '—']
    ];
    return steps.map(([h, d], i) => ({ head: h, detail: d,
      state: done(i) ? (i === c.stage + 1 ? 'active' : 'done') : 'pending' }));
  }

  function activityOf(c) {
    const base = 10 * 60 + 32, seed = c.pair.a + c.pair.b;
    const mins = m => { const t = base + m; return String(Math.floor(t / 60)).padStart(2, '0') + ':' + String(t % 60).padStart(2, '0'); };
    const feed = [
      [0, 'AI proposed ' + c.verdict.key.toLowerCase().replace('_', ' ') + ' at ' + (c.pair.score * 100).toFixed(1) + '%'],
      [3, 'Steward ' + c.steward + ' opened the case'],
    ];
    if (c.engineer) {
      feed.push([9, 'Steward requested engineering review']);
      feed.push([12 + (h32(seed, 'a1') % 5), 'Engineer ' + c.engineer + ' verified dimensions']);
    }
    feed.push([16 + (h32(seed, 'a2') % 6), 'Standards evidence added — ' + ((c.material && c.material.standards[0]) || 'none on file')]);
    if (c.verdict.key === 'CONFLICT') feed.push([21, 'Merge blocked — hard conflict veto upheld']);
    else if (c.stage >= 3) { feed.push([22, 'Steward approved']); feed.push([23, 'CNMC created — ' + (c.material ? c.material.cnmc : '—')]); }
    else feed.push([20, 'Awaiting ' + STAGES[c.stage + 1 > 4 ? 4 : c.stage + 1].toLowerCase()]);
    return feed.map(([m, text]) => ({ at: mins(m), text }));
  }

  /* ---------- analytics rollups ------------------------------------------- */
  function analytics(reviewState) {
    const done = reviewState || {};
    const byStatus = { IDENTICAL: 0, EQUIVALENT: 0, CONDITIONAL: 0, DIFFERENT: 0, CONFLICT: 0, UNRESOLVED: 0 };
    MATERIALS.forEach(m => { byStatus[m.equivalence_status] = (byStatus[m.equivalence_status] || 0) + 1; });

    const byCpse = {};
    MATERIALS.forEach(m => m.records.forEach(r => {
      const e = byCpse[r.cpse] = byCpse[r.cpse] || { cpse: r.cpse, records: 0, matched: 0, duplicates: 0, reviews: 0, harmonised: 0 };
      e.records++;
      if (m.records.length > 1) { e.matched++; e.duplicates += m.records.length - 1; }
      if (m.equivalence_status === 'CONDITIONAL' || m.equivalence_status === 'UNRESOLVED') e.reviews++;
      if (m.equivalence_status === 'IDENTICAL' || m.equivalence_status === 'EQUIVALENT') e.harmonised++;
    }));

    const byFamily = {};
    MATERIALS.forEach(m => {
      const e = byFamily[m.family] = byFamily[m.family] || { family: m.family, name: m.family_name, materials: 0, records: 0, conflicts: 0 };
      e.materials++; e.records += m.records.length;
      if (m.equivalence_status === 'CONFLICT') e.conflicts++;
    });

    const bands = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    ALL_CASES.forEach(it => { if (it.priority && it.priority.band) bands[it.priority.band]++; });

    const crossVisible = MATERIALS.filter(m => m.cross_cpse);
    const aggregation = procurementRows().filter(r => r.signal === 'CROSS-CPSE STOCK FOUND' || r.signal === 'DEMAND AGGREGATION CANDIDATE');

    return {
      totals: {
        records: MATERIALS.reduce((s, m) => s + m.records.length, 0),
        materials: MATERIALS.length,
        duplicate_candidates: ALL_CASES.length,
        harmonised: byStatus.IDENTICAL + byStatus.EQUIVALENT,
        pending: byStatus.CONDITIONAL,
        cross_cpse: crossVisible.length,
        golden: Object.keys(done).filter(k => done[k] && done[k].action === 'approve').length,
        conflicts: byStatus.CONFLICT,
        unresolved: byStatus.UNRESOLVED
      },
      byStatus, byCpse: Object.values(byCpse).sort((a, b) => b.records - a.records),
      byFamily: Object.values(byFamily).sort((a, b) => b.materials - a.materials),
      bands, crossVisible, aggregation
    };
  }

  return {
    build, verdictOf, VERDICTS, evidenceRows, standardsEvidence, STANDARDS,
    FAMILY_NAME, familyOf, catLabel, attrLabel, attrValue, cnmcFor,
    procurementRows, caseOf, timelineOf, activityOf, analytics, STAGES,
    get materials() { return MATERIALS; },
    get byRecord() { return BY_RECORD; },
    get byId() { return BY_ID; },
    get cases() { return ALL_CASES; }
  };
})();
