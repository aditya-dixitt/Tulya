#!/usr/bin/env python3
"""
TULYA — build the offline console from the SAMANVAY prototype.

This is an UPGRADE, not a rewrite. It takes the original steward-console
template (api/_samanvay_template.orig.html), applies the TULYA rebrand, the
evidence-based workflow, the Material Passport, the Standards Knowledge Graph
and the four modules (Analytics, Collaboration, Impact Simulator, Procurement
Intelligence), and dresses the whole thing as an enterprise operations console:
fixed navigation rail, slim app bar, dense tables, restrained colour.

Writes:
    api/tulya_template.html      the TULYA template, __DATA_JSON__ placeholder
    reports/tulya_console.html   that template with the real data snapshot in it

Every existing panel, renderer and behaviour of the prototype is preserved.

Run:  python3 tulya/build.py
"""
import base64
import csv
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_TEMPLATE = ROOT / "api" / "_samanvay_template.orig.html"
SNAPSHOT = ROOT / "reports" / "steward_console_demo.html"
OUT_TEMPLATE = ROOT / "api" / "tulya_template.html"
OUT_CONSOLE = ROOT / "reports" / "tulya_console.html"
# Vercel deploys public/ as a plain static site. Emitting the console there
# too keeps the deployed page and reports/ from drifting apart -- there is no
# build step on Vercel to regenerate it, so whatever is committed is what
# ships.
OUT_PUBLIC = ROOT / "public" / "index.html"

MISSES = []


def sub(html, old, new, count=1, label=""):
    """Replace, and complain loudly if the anchor moved."""
    if old not in html:
        MISSES.append(label or old[:70])
        return html
    return html.replace(old, new, count)


def cut(html, start, end, new, label):
    """Replace everything between two anchors (end anchor is kept)."""
    i = html.find(start)
    j = html.find(end, i + 1) if i >= 0 else -1
    if i < 0 or j < 0:
        MISSES.append(label)
        return html
    return html[:i] + new + html[j:]


# ===========================================================================
# 1 · brand and type
# ===========================================================================
def rebrand(h):
    h = sub(h, "<title>Samanvay Console</title>",
            "<title>TULYA — Material Intelligence &amp; Governance</title>", label="title")
    h = h.replace("%3ES%3C/text%3E", "%3ET%3C/text%3E")

    # Inter for UI, IBM Plex Mono for anything read aloud as a code or measurement
    h = sub(h,
        '<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700'
        '&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">',
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;550;600'
        '&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">',
        label="font link")

    for a, b in [
        ("Test SAMANVAY", "Test TULYA"),
        ("Why did SAMANVAY match these?", "View evidence"),
        ("Why SAMANVAY refused this match", "Merge refused — evidence"),
        ("Why SAMANVAY matched these", "Match evidence"),
        ("SAMANVAY scores", "TULYA scores"),
        ("Rejected by SAMANVAY", "Rejected by TULYA"),
        ("SAMANVAY says", "TULYA says"),
        ("samanvay_demo_state_v2", "tulya_demo_state_v1"),
    ]:
        h = h.replace(a, b)

    h = sub(h, "<td>${esc(name)}</td><td class=\"mono\">${m.t.toFixed(2)}</td>",
            "<td>${esc(name.replace(/SAMANVAY/g,'TULYA'))}</td><td class=\"mono\">${m.t.toFixed(2)}</td>",
            label="baseline display name")
    return h


# ===========================================================================
# 2 · shell — navigation rail, app bar, compact provenance strip
# ===========================================================================
ICONS = {
    "overview":    "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
    "challenge":   "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
    "queue":       "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    "auto":        "M12 2 2 7l10 5 10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
    "passport":    "M3 5h18v14H3zM8 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM6 16c.5-1.5 2-2 2.5-2s2 .5 2.5 2M14 10h4M14 14h4",
    "analytics":   "M4 20V11M10 20V4M16 20V14M22 20V8",
    "simulator":   "M4 6h16M4 12h16M4 18h16M9 4v4M15 10v4M7 16v4",
    "procurement": "M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v10",
    "collab":      "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2 20c0-3.3 3-5.5 7-5.5s7 2.2 7 5.5M17 5a3.5 3.5 0 0 1 0 7M18 20c0-2-.6-3.6-1.6-4.7",
    "groups":      "M12 3 4 6v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6zM9 12l2.2 2.2L15.5 10",
    "vetoed":      "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM5.6 5.6l12.8 12.8",
    "standards":   "M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8.6 10.5l6.8-4M8.6 13.5l6.8 4",
    "audit":       "M6 2h9l5 5v15H6zM15 2v5h5M9 13h7M9 17h5",
    "performance": "M22 12h-4l-3 8L9 4l-3 8H2",
    "search":      "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20.5 20.5 16 16",
}

NAV_ITEMS = [
    ("WORKSPACE", [
        ("overview", "Overview", None),
        ("challenge", "Test TULYA", None),
        ("queue", "Review Queue", "nQueue"),
        ("auto", "Auto-Suggest", "nAuto"),
    ]),
    ("MATERIAL INTELLIGENCE", [
        ("passport", "Material Passport", None),
        ("analytics", "Analytics", None),
        ("simulator", "Impact Simulator", None),
    ]),
    ("OPERATIONS", [
        ("procurement", "Procurement Intelligence", None),
        ("collab", "Collaboration", None),
    ]),
    ("GOVERNANCE", [
        ("groups", "Golden Records", "nGroups"),
        ("vetoed", "Hard-Key Vetoes", None),
        ("standards", "Standards Knowledge Graph", None),
        ("audit", "Audit Log", None),
    ]),
    ("SYSTEM", [
        ("performance", "Performance", None),
        ("search", "Search", None),
    ]),
]


def icon(key):
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="%s"/></svg>' % ICONS[key])


def build_nav():
    # The brand area is deliberately EMPTY. The existing TULYA mark drops into
    # .brand-slot; nothing is invented to stand in for it, and the slot has a
    # fixed height so adding the logo later does not reflow the navigation.
    out = [  # LOGIN_VIEW removed: the console opens straight into the workspace
           '<div class="nav-scrim" id="navScrim" hidden></div>',
           '<aside class="sidebar" id="appSidebar" aria-label="Main navigation">',
           '  <div class="sb-brand">',
           '    <div class="brand-slot" id="brandSlot" aria-label="Brand"></div>',
           '  </div>',
           '  <nav>']
    first = True
    for group, items in NAV_ITEMS:
        out.append('    <div class="sb-group">%s</div>' % group)
        for key, label, badge in items:
            cls = ' class="active"' if first else ''
            first = False
            b = '<span class="n" id="%s">–</span>' % badge if badge else ''
            out.append('    <button data-p="%s"%s>%s<span>%s</span>%s</button>'
                       % (key, cls, icon(key), label, b))
    out += ['  </nav>', '</aside>']
    return "\n".join(out)


_ICO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="%s"/></svg>')

# crumbGroup / crumbPage stay in the DOM — modules.js writes the current page
# into them on every navigation. They are hidden, not removed.
TOPBAR = """<div class="topbar">
  <button class="tb-burger" id="navToggle" aria-label="Open navigation"
          aria-controls="appSidebar" aria-expanded="false">
    <span></span><span></span><span></span>
  </button>
  <div class="crumb" hidden><span id="crumbGroup">Workspace</span><span class="sep">/</span><b id="crumbPage">Overview</b></div>
  <div class="tb-search">
    %s
    <input id="tbSearch" type="search" autocomplete="off" spellcheck="false"
           role="combobox" aria-expanded="false" aria-controls="gsPanel" aria-autocomplete="list"
           placeholder="Search material, CNMC, CPSE, supplier...">
    <kbd>&#8984;K</kbd>
    <div class="gs-panel" id="gsPanel" role="listbox" aria-label="Search results" hidden></div>
  </div>
  <div class="tb-right">
    <span class="stat"><span class="dot"></span>Offline demo</span>
    <span class="stat">Test split: <b>Locked</b></span>
    <span class="stat">Records: <b id="tbRecords">&#8212;</b></span>
    <span class="tb-sep"></span>
    <div class="tb-pop">
      <button class="tb-ico" id="tbBell" title="Notifications" aria-label="Notifications"
              aria-haspopup="true" aria-expanded="false" aria-controls="notifPanel">%s
        <span class="tb-badge" id="tbBadge" hidden>0</span>
      </button>
      <div class="pop notif" id="notifPanel" role="dialog" aria-label="Notifications" hidden></div>
    </div>
    <div class="tb-pop">
      <button class="tb-avatar" id="tbAvatar" title="Account" aria-haspopup="true"
              aria-expanded="false" aria-controls="acctPanel">A</button>
      <div class="pop acct" id="acctPanel" role="menu" aria-label="Account" hidden></div>
    </div>
  </div>
</div>""" % (
    _ICO % "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20.5 20.5 16 16",
    _ICO % "M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
)

LOGIN_VIEW = """<div class="login" id="loginView" hidden>
  <div class="login-card">
    <div class="login-brand">
      <div class="brand-slot" id="loginBrandSlot"></div>
      <div class="wm">TULYA</div>
      <div class="ws">Material Intelligence &amp; Governance</div>
    </div>
    <form class="login-form" id="loginForm" novalidate>
      <h1>Sign in</h1>
      <p class="sub">Use your work account to open the material governance console.</p>
      <label class="fld"><span>Work email</span>
        <input type="email" id="loginEmail" autocomplete="username" spellcheck="false"
               placeholder="name@organisation.gov.in" required></label>
      <label class="fld"><span>Password</span>
        <input type="password" id="loginPass" autocomplete="current-password" required></label>
      <div class="row">
        <label class="chk"><input type="checkbox" id="loginRemember" checked><span>Remember me</span></label>
        <a href="#" id="loginForgot">Forgot password?</a>
      </div>
      <div class="note" id="loginNote" role="status" aria-live="polite"></div>
      <button type="submit" class="btn primary wide">Sign in</button>
      <div class="demo">
        <b>Offline demo</b>
        This export has no identity provider behind it. Sign in with
        <span class="code">steward@tulya.gov.in</span> / <span class="code">tulya-demo</span>.
        The session is a flag in this browser&#8217;s local storage, nothing more.
      </div>
    </form>
    <div class="login-foot">TULYA &#183; SIH26099 &#183; Team AlgoRythms
      &#183; figures from the locked test-split evaluation</div>
  </div>
</div>

"""

BANNER = """<div class="banner">
  <details>
    <summary><span class="chev">▸</span><span>Data provenance — measured pipeline output, with simulated
      stock and demand quantities. <b>Read this before quoting a figure.</b></span></summary>
    <div class="body">
      Every pair, score, specification and verdict is real output from the matching pipeline on its locked
      test split. Approve / reject / un-merge run in this browser and persist to local storage.
      <b>Stock, demand, coverage and procurement quantities are simulated</b> — derived deterministically
      from these same records so the demo is reproducible, and labelled wherever they appear. They are not a
      measured CPSE result.
    </div>
  </details>
</div>"""


def shell(h):
    h = cut(h, '<div class="topbar">', '<nav>', TOPBAR + "\n" + BANNER + "\n", "topbar+banner")
    i = h.find("<nav>")
    j = h.find("</nav>", i)
    if i < 0 or j < 0:
        MISSES.append("nav block")
        return h
    return h[:i] + build_nav() + h[j + len("</nav>"):]


# ===========================================================================
# 3 · overview — an operator's first screen, not a brochure
# ===========================================================================
OVERVIEW = """  <div class="panel active" id="p-overview">

    <!-- Control tower header. The background is a flat vector plant silhouette
         drawn for this file, held at watermark contrast — it sits behind the
         type at low opacity and fades out before the text, so it reads as
         stationery rather than a hero image. -->
    <header class="ct-hero">
      <div class="ct-hero-bg" aria-hidden="true"></div>
      <div class="ct-hero-in">
        <div class="ct-hero-t">
          <span class="eyebrow">Control Tower</span>
          <h1>Material Intelligence for a Stronger, Connected India</h1>
          <p>Unifying material identities across 6 CPSEs for efficient procurement, better asset
            utilisation and data-driven governance.</p>
        </div>
        <aside class="ct-quote">
          <span class="rules"><i class="a"></i><i class="b"></i></span>
          <q>&#8220;One Material Identity<br>Six CPSEs<br>Greater Impact&#8221;</q>
          <span class="meta">Last updated <b id="ovUpdated">&#8212;</b></span>
        </aside>
      </div>
    </header>

    <div class="kpis" id="overviewCards"></div>

    <div class="ct-grid">

      <section class="ct-panel" id="ctPerf">
        <header>
          <div>
            <h3>Matching Performance</h3>
            <p id="ctPerfSub">Auto-suggest precision against review share across the threshold sweep</p>
          </div>
          <div class="hx-group">
            <div class="seg" id="ctPerfSeg" role="group" aria-label="Chart view">
              <button type="button" data-view="operating" class="on" aria-pressed="true">Operating point</button>
              <button type="button" data-view="quality" aria-pressed="false">Precision &#183; Recall &#183; F1</button>
            </div>
            <div class="hx" id="ctPerfOp">&#8212;</div>
          </div>
        </header>
        <div class="bd"><div class="ct-chart">
          <div class="ct-plot"><div id="ctPerfChart"></div><div class="ct-legend" id="ctPerfLegend"></div></div>
          <div class="ct-side" id="ctPerfSide"></div>
        </div></div>
        <div class="ct-prov" id="ctPerfProv"></div>
      </section>

      <div class="ct-stack">
        <section class="ct-panel">
          <header>
            <div>
              <h3>Review Queue &#8212; Attention Required</h3>
              <p>Ranked by uncertainty &#215; evidence &#215; value</p>
            </div>
            <button class="hx-link" onclick="switchPanel('queue')">View all &#8594;</button>
          </header>
          <div class="bd"><div class="prio-strip" id="prioStrip"></div></div>
        </section>

        <section class="ct-panel ct-activity">
          <header>
            <div>
              <h3>Recent Activity</h3>
              <p>Steward decisions and system events, append-only</p>
            </div>
            <button class="hx-link" onclick="switchPanel('audit')">View all &#8594;</button>
          </header>
          <div class="bd" style="padding:0"><div id="ovDecisions"></div><div id="ovActivity"></div></div>
        </section>
      </div>

      <section class="ct-panel" id="ctNet">
        <header>
          <div>
            <h3>Cross-CPSE Material Network</h3>
            <p>Which CPSEs share candidate material identities in this export</p>
          </div>
          <div class="hx" id="ctNetHx">&#8212;</div>
        </header>
        <div class="bd">
          <div class="ct-net" id="ctNetGraph"></div>
          <div class="ct-net-detail" id="ctNetDetail"></div>
        </div>
        <div class="ct-prov" id="ctNetProv"></div>
      </section>

      <section class="ct-panel ct-reco" id="ctReco">
        <header>
          <div>
            <h3>Material Recommendation</h3>
            <p>Highest-scoring cross-CPSE candidate in this export</p>
          </div>
        </header>
        <div class="bd" id="ctRecoBody"></div>
        <div class="ct-prov" id="ctRecoProv"></div>
      </section>

    </div>

    <div class="section-title">Cross-CPSE opportunities<span class="rule"></span>
      <span class="side">quantities simulated</span></div>
    <div id="ovOpportunities"></div>

    <details class="pipe" style="margin-top:22px">
      <summary><span class="chev">&#9656;</span>Pipeline detail and backend configuration</summary>
      <div class="pd">
        <div class="proc" id="trustRail"></div>
        <div class="flow" id="flowStrip"></div>
        <div class="section-title" style="margin-top:18px">What produced these numbers<span class="rule"></span></div>
        <div class="twrap"><table id="backendTable"></table></div>
      </div>
    </details>
  </div>

"""

KPI_BLOCK = """  const lc = DATA.holdout.layer_c, la = DATA.holdout.layer_a;
  const _A = TULYA.analytics(STATE.reviews);
  const cards = [
    ['Material records', DATA.records.toLocaleString(), 'locked test split'],
    ['Duplicate candidates', (DATA.decision_counts.REVIEW + DATA.decision_counts.AUTO_SUGGEST).toLocaleString(),
     'pairs the engine proposed'],
    ['Auto-suggest precision', pct(lc.auto_suggest_precision),
     lc.false_merges_proposed + ' wrong of ' + lc.auto_suggest_pairs.toLocaleString()],
    ['Pending reviews', reviewRemaining.toLocaleString(), 'awaiting a steward'],
    ['Golden records / CNMC', groups.length.toLocaleString(),
     groups.reduce((s,g)=>s+g.size,0) + ' legacy codes mapped'],
    ['Cross-CPSE matches', _A.totals.cross_cpse.toLocaleString(), 'identities in two or more CPSEs'],
  ];
  // One outline icon per metric, same stroke weight as the navigation. No trend
  // arrows and no sparklines: this split is a single locked run, so there is no
  // time series to draw and an invented one would be the only unsourced number
  // on the page.
  const _kpiIcon = [
    'M12 7c4.4 0 8-1.1 8-2.5S16.4 2 12 2 4 3.1 4 4.5 7.6 7 12 7zM4 4.5v15C4 20.9 7.6 22 12 22s8-1.1 8-2.5v-15M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5',
    'M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8.6 13.5l6.8 4M15.4 6.5l-6.8 4',
    'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
    'M9 3h6v3H9zM8 4H6v17h12V4h-2M9 11h6M9 16h4',
    'M12 3 4 6v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6zM9 12l2.2 2.2L15.5 10',
    'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 1 0-5.7-5.7l-1.7 1.7M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 1 0 5.7 5.7l1.7-1.7',
  ].map(d=>'<span class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    +'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    +'<path d="'+d+'"/></svg></span>');
  document.getElementById('overviewCards').innerHTML = cards.map(([k,v,sub],i)=>
    `<div>${_kpiIcon[i]||''}<span class="k">${k}</span><span class="v">${v}</span><span class="s">${sub}</span></div>`).join('');
  const _tb = document.getElementById('tbRecords'); if(_tb) _tb.textContent = DATA.records.toLocaleString();

"""


def overview(h):
    h = cut(h, '  <div class="panel active" id="p-overview">',
            "  <!-- ================= CHALLENGE", OVERVIEW, "overview panel")
    h = cut(h, "  const lc = DATA.holdout.layer_c, la = DATA.holdout.layer_a;",
            "  const c = bandCounts();", KPI_BLOCK, "overview KPI block")
    return h


# ===========================================================================
# 4 · new panels
# ===========================================================================
PANELS = """
  <!-- ================= MATERIAL PASSPORT ================= -->
  <div class="panel" id="p-passport">
    <div class="page-head">
      <div><h1>Material passport</h1>
        <p>The engineering record for a material identity: every legacy code that means it, the
          specifications recovered from those descriptions, the standards on file, the match analysis and
          the steward decision that issues — or refuses — a Common National Material Code.</p></div>
      <div class="meta">Material identities<b id="ppCount">—</b></div>
    </div>
    <div class="split">
      <div>
        <input class="steward-input" id="passportSearch" style="width:100%;margin-bottom:8px"
               placeholder="Filter description, CNMC, CPSE, legacy code">
        <div class="tbar"><span class="count" id="ppListCount"></span></div>
        <div class="reclist" id="passportList" style="max-height:720px;overflow-y:auto"></div>
      </div>
      <div id="passportDetail"></div>
    </div>
  </div>

  <!-- ================= ANALYTICS ================= -->
  <div class="panel" id="p-analytics">
    <div class="page-head">
      <div><h1>Analytics</h1>
        <p>Harmonisation state across the material records this console works through. Counts, verdicts and
          priorities are pipeline output; stock and demand figures are simulated and labelled.</p></div>
      <div class="meta">Scope<b>Locked test split</b></div>
    </div>
    <div class="kpis" id="anKpis"></div>
    <div class="chart" id="anStatus" style="margin-bottom:14px"></div>
    <div class="chart-grid">
      <div class="chart" id="anCpse"></div>
      <div class="chart" id="anCategory"></div>
    </div>
    <div class="chart" id="anBands" style="margin-top:14px"></div>
    <div class="section-title" style="margin-top:22px">Cross-CPSE opportunities<span class="rule"></span>
      <span class="side">quantities simulated</span></div>
    <div id="anOpportunities"></div>
  </div>

  <!-- ================= IMPACT SIMULATOR ================= -->
  <div class="panel" id="p-simulator">
    <div class="page-head">
      <div><h1>Cross-CPSE impact simulator</h1>
        <p>What could follow if these material identities are harmonised. Select a material, choose which
          CPSEs participate, set the demand scenario.</p></div>
      <div class="meta">Mode<b>Simulation</b></div>
    </div>
    <div class="simbar"><span class="lbl">SIMULATED</span>
      <span>Illustrative, derived from prototype data — <b>not a measured CPSE result</b>. Stock and demand
      quantities are generated deterministically from the prototype's own records. The material identity,
      the legacy codes, the CPSEs and the evidence linking the records are real pipeline output.</span></div>
    <div class="sim-grid">
      <div class="sim-controls">
        <div class="sc-head">Scenario controls</div>
        <div class="sc-body">
          <div class="sim-row"><label>Material</label>
            <select id="simPicker" onchange="setSimMat(this.value)" class="field" style="width:100%"></select></div>
          <div id="simControls"></div>
        </div>
      </div>
      <div id="simBody"></div>
    </div>
  </div>

  <!-- ================= PROCUREMENT INTELLIGENCE ================= -->
  <div class="panel" id="p-procurement">
    <div class="page-head">
      <div><h1>Procurement intelligence</h1>
        <p>Decision support. Nothing here approves a purchase or moves stock — it surfaces where an open
          demand could already be met from a material another CPSE holds under a different code, and routes
          the case to review.</p></div>
      <div class="meta">Open demand<b id="procTotal">—</b></div>
    </div>
    <div class="simbar"><span class="lbl">SIMULATED</span>
      <span>Required and available quantities are derived from prototype data for demonstration. Materials,
      legacy codes, CPSEs, plants and equivalence verdicts are real pipeline output.</span></div>
    <div class="kpis" id="procKpis"></div>
    <div class="filters" id="procFilters"></div>
    <div id="procTable"></div>
  </div>

  <!-- ================= COLLABORATION ================= -->
  <div class="panel" id="p-collab">
    <div class="page-head">
      <div><h1>Collaboration</h1>
        <p>A material case moves AI → data steward → engineering → procurement → final governance.
          Each stage leaves a record, and every action is written to the audit log.</p></div>
      <div class="meta">Open cases<b id="collabCount">—</b></div>
    </div>
    <div class="split">
      <div>
        <div class="subnav" id="collabStages"></div>
        <div class="tbar"><span class="count" id="collabListCount"></span></div>
        <div class="reclist" id="collabList" style="max-height:720px;overflow-y:auto"></div>
      </div>
      <div id="collabDetail"></div>
    </div>
  </div>

  <!-- ================= STANDARDS KNOWLEDGE GRAPH ================= -->
  <div class="panel" id="p-standards">
    <div class="page-head">
      <div><h1>Standards knowledge graph</h1>
        <p>How the designations these records cite relate to each other. Every edge carries a relationship
          type and a verification state — an unverified relationship is shown as REQUIRES REVIEW, never
          presented as fact.</p></div>
      <div class="meta">Families<b>6</b></div>
    </div>
    <div class="subnav" id="kgFamilies"></div>
    <div class="kg-wrap">
      <div class="kg" id="kgTree"></div>
      <div class="kg-panel" id="kgPanel"></div>
    </div>
  </div>
"""


def panels(h):
    return sub(h, "  <div class=\"footnote\">", PANELS + "\n  <div class=\"footnote\">", label="panel insert")


# ===========================================================================
# 5 · page heads on the panels the original template shipped
# ===========================================================================
HEADS = [
    ("challenge",
     '    <div class="section-title">Test TULYA — three real pairs from the locked test split</div>',
     '<h1>Test TULYA</h1><p>Three real pairs from the locked test split. Decide before the system tells '
     'you — the answer shown afterwards is the planted ground truth, not the engine’s opinion of '
     'itself.</p>', 'Cases<b>3</b>'),
    ("queue",
     '    <div class="section-title">Steward review queue — score 0.75 – 0.92</div>',
     '<h1>Review queue</h1><p>Pairs the engine will not decide alone. Priority is uncertainty × thin '
     'evidence × value at stake, and each row shows all three so the ranking can be argued with rather '
     'than trusted.</p>', 'Score band<b>0.75 – 0.92</b>'),
    ("auto",
     '    <div class="section-title">Auto-suggested pairs — score ≥ 0.92</div>',
     '<h1>Auto-suggest</h1><p>Pre-ranked by the engine as high confidence. Still needs a steward’s '
     'sign-off — nothing here has merged itself.</p>', 'Score band<b>≥ 0.92</b>'),
    ("groups",
     '    <div class="section-title">Golden records formed so far</div>',
     '<h1>Golden records</h1><p>A golden record carries a Common National Material Code. Every CPSE keeps '
     'its own legacy ERP code — the CNMC maps them, it does not replace them. A group exists only '
     'because a steward approved every edge connecting it.</p>', 'Issued<b id="grCount">—</b>'),
    ("vetoed",
     '    <div class="section-title">Hard-key vetoes — text says yes, the specification says no</div>',
     '<h1>Hard-key vetoes</h1><p>The highest text-similarity pairs the engine rejected outright, because a '
     'specification known on both sides disagreed. Each one is a false positive a fuzzy matcher hands over '
     'as a confident match.</p>', 'Rejected on conflict<b id="vetoCount">—</b>'),
    ("performance",
     '    <div class="section-title">Where the threshold comes from</div>',
     '<h1>Performance</h1><p>Nothing on this page is computed for display. Every figure is a measured point '
     'from the validation sweep and the locked holdout run.</p>', 'Holdout<b>Opened once</b>'),
    ("search",
     '    <div class="section-title">Search — same fusion scorer, an arbitrary query</div>',
     '<h1>Search</h1><p>The same normaliser, attribute extraction and fusion scorer the pipeline runs, '
     'against a query. This offline page ships eight precomputed queries.</p>', 'Queries<b>8</b>'),
    ("audit",
     '    <div class="section-title">Audit log</div>',
     '<h1>Audit log</h1><p>Append-only, this browser only. Every entry records what changed, the confidence '
     'at the moment of the decision, and who made it — so a merge can always be traced back and undone.</p>',
     'Events<b id="auditCount">—</b>'),
]


def heads(h):
    for key, anchor, body, meta in HEADS:
        h = sub(h, anchor,
                '    <div class="page-head"><div>%s</div><div class="meta">%s</div></div>' % (body, meta),
                label="page head " + key)
    # the veto count sentence moved into the page head
    h = sub(h,
        "      Across the whole split the veto rejected <b id=\"vetoCount\">\u2013</b> pairs.</div>",
        "</div>", label="veto count sentence")
    # the veto page head now says this; the old hint below it is a duplicate
    h = sub(h, '<div class="hint">The highest text-similarity pairs the engine still rejected outright',
            '<div class="hint" style="display:none">The highest text-similarity pairs the engine still rejected outright',
            label="veto hint dedupe")
    h = sub(h, '<div class="hint">The production console takes free text; this static page ships 8 precomputed queries\n'
               '      so the demo works with no backend at all.</div>', '', label="search hint")
    return h


# ===========================================================================
# CPSE marks
# ---------------------------------------------------------------------------
# CPSE logos are registered trademarks. This build does not draw them and does
# not fetch them. It reads whatever the operator has placed in tulya/assets/cpse/
# and inlines it, so an authorised asset appears everywhere at once. When a file
# is absent the UI renders a neutral monogram container of the same size, which
# is a placeholder, not a substitute mark.
# ===========================================================================
CPSE_DIR = ROOT / "tulya" / "assets" / "cpse"
_MIME = {".svg": "image/svg+xml", ".png": "image/png",
         ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def cpse_marks():
    """{'BPCL': 'data:image/svg+xml;base64,...'} for each asset actually present."""
    out = {}
    if not CPSE_DIR.is_dir():
        return out
    for f in sorted(CPSE_DIR.iterdir()):
        if not f.is_file() or f.suffix.lower() not in _MIME:
            continue
        if f.stat().st_size > 512 * 1024:
            print("  skipped %s — over the 512 KB inline budget" % f.name)
            continue
        blob = base64.b64encode(f.read_bytes()).decode("ascii")
        out[f.stem.upper()] = "data:%s;base64,%s" % (_MIME[f.suffix.lower()], blob)
    return out


def measured_extras():
    """Real series read from the evaluation artefacts, for the analytics panels.

    Nothing here is computed for presentation: curves are the recorded
    precision/recall/F1 of each backend on the locked test split, and the CPSE
    counts are a straight tally of the same split's records.
    """
    extra = {}

    run = ROOT / "data" / "out" / "holdout_run.json"
    if run.exists():
        curves = json.loads(run.read_text(encoding="utf-8"))["result"].get("curves") or {}
        extra["curves"] = {("TULYA hybrid" if "SAMANVAY" in k.upper() else k): v
                           for k, v in curves.items()}

    recs = ROOT / "data" / "out" / "records.csv"
    if recs.exists():
        tally, plants = {}, {}
        with recs.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("split") != "test":
                    continue
                c = row.get("cpse")
                if not c:
                    continue
                tally[c] = tally.get(c, 0) + 1
                plants.setdefault(c, set()).add(row.get("plant"))
        extra["cpse_records"] = {"split": "test", "counts": tally,
                                 "plants": {k: len(v) for k, v in plants.items()}}
    return extra


# ===========================================================================
# 6 · assets
# ===========================================================================
def assets(h):
    css = (ROOT / "tulya" / "modules.css").read_text(encoding="utf-8")
    # The control-tower header image, inlined so the console stays one file.
    # The supplied panorama is used when it is present; the flat vector
    # silhouette is the fallback so the header never renders as a bare band.
    hero = None
    for name, mime in (("industrial/refinery-banner.jpg",  "image/jpeg"),
                       ("industrial/refinery-banner.webp", "image/webp"),
                       ("industrial/refinery-banner.png",  "image/png"),
                       ("hero-refinery.webp", "image/webp"),
                       ("hero-refinery.jpg",  "image/jpeg"),
                       ("plant-silhouette.svg", "image/svg+xml")):
        f = ROOT / "tulya" / "assets" / name
        if f.exists():
            hero = (name, mime, f)
            break
    if hero:
        name, mime, f = hero
        css = css.replace("__HERO_IMAGE__", "data:%s;base64,%s"
                          % (mime, base64.b64encode(f.read_bytes()).decode("ascii")))
        print("control-tower header image: %s (%.0f KB)" % (name, f.stat().st_size / 1024))
    else:
        css = css.replace("__HERO_IMAGE__", "")
        print("control-tower header image: none found in tulya/assets/")
    model = (ROOT / "tulya" / "model.js").read_text(encoding="utf-8")
    mods = (ROOT / "tulya" / "modules.js").read_text(encoding="utf-8")

    h = sub(h, "</style>\n</head>", "\n/* ===== TULYA design system ===== */\n" + css + "\n</style>\n</head>",
            label="css insert")
    h = sub(h, "<script id=\"data\" type=\"application/json\">__DATA_JSON__</script>",
            "<script id=\"data\" type=\"application/json\">__DATA_JSON__</script>\n<script>\n" + model + "\n</script>",
            label="model insert")
    h = sub(h, "function renderAll(){", mods + "\n\nfunction renderAll(){", label="modules insert")
    return h


# ===========================================================================
# 7 · wire the new layer into the existing renderers
# ===========================================================================
def wire(h):
    h = sub(h,
        "function pkey(a,b){ return a<b ? a+'_'+b : b+'_'+a; }",
        "function pkey(a,b){ return a<b ? a+'_'+b : b+'_'+a; }\nTULYA.build(DATA, RECORDS);",
        label="TULYA.build")

    # overview: process rail + operational tables
    h = sub(h,
        "  const steps = [\n    ['Raw records','6 CPSEs, 20 categories']",
        """  document.getElementById('trustRail').innerHTML = procRailHTML();
  renderOverviewOps();

  const steps = [
    ['Raw records','6 CPSEs, 20 categories']""",
        label="overview ops wiring")

    # pair cards: governed verdict + passport route
    h = sub(h,
        "      <span>${prioPill}<span class=\"pill ${kind==='auto'?'auto':'review'}\">${esc(it.decision)}</span>${scopeChip(it)}</span>",
        "      <span>${prioPill}${verdictBadge(TULYA.verdictOf(it).key)} "
        "<span class=\"pill ${kind==='auto'?'auto':'review'}\">${esc(it.decision)}</span>${scopeChip(it)}</span>",
        label="pair card verdict")

    h = sub(h,
        "      <button class=\"btn ghost small\" onclick=\"openExplain(${it.a},${it.b})\">View evidence</button>",
        "      <button class=\"btn ghost small\" onclick=\"openExplain(${it.a},${it.b})\">View evidence</button>\n"
        "      <button class=\"btn ghost small\" onclick=\"passportForRecord(${it.a})\">Passport</button>",
        label="pair card passport")

    # explain modal
    h = sub(h, "<div class=\"modal\">\n    <button class=\"close\" id=\"modalClose\">",
            "<div class=\"modal wide\">\n    <button class=\"close\" id=\"modalClose\">", label="modal wide")

    h = sub(h,
        "  html += `<div class=\"kicker\">Specifications read from both descriptions</div>`;",
        """  if(it){
    html += `<div class="kicker">Governed verdict</div>
      <div>${verdictBadge(TULYA.verdictOf(it).key, true)}
        <div class="hint" style="margin:5px 0 0">${esc(TULYA.verdictOf(it).reason)}.</div></div>
      <div class="kicker">Engineering evidence \\u2014 attribute comparison</div>
      ${evidenceTableHTML(it)}`;
  }
  html += `<div class="kicker">Specifications read from both descriptions</div>`;""",
        label="explain evidence")

    h = sub(h,
        "  document.getElementById('modalBody').innerHTML = html;\n  document.getElementById('modalBg').classList.add('open');",
        """  html += `<div class="actbar"><button class="jump" onclick="closeModal();passportForRecord(${a})">Material passport</button>
    <button class="jump" onclick="closeModal();openCase(${a},${b})">Collaboration case</button>
    <button class="jump" onclick="closeModal();switchPanel('standards')">Standards graph</button></div>`;
  document.getElementById('modalBody').innerHTML = html;
  document.getElementById('modalBg').classList.add('open');""",
        label="explain footer links")

    # golden records / CNMC
    h = sub(h,
        "    <div class=\"hint\">Each group exists only because you approved every edge connecting it.",
        "    <div class=\"hint\" style=\"display:none\">Each group exists only because you approved every edge connecting it.",
        label="groups hint hide")
    h = sub(h,
        "        <div><span class=\"pill auto\">${g.group_id}</span> <b style=\"margin-left:8px\">${esc(g.category)}</b>",
        "        <div><span class=\"pill auto\">${g.group_id}</span> <b style=\"margin-left:8px\">${esc(TULYA.catLabel(g.category))}</b>",
        label="groups category label")
    h = sub(h,
        "        <div class=\"gold\"><b>Canonical record</b>${esc(g.canonical.description)}",
        """        <div class="gold"><b>CNMC issued \\u00b7 legacy codes retained</b>
          <div class="mono" style="font-size:12px;font-weight:600;color:var(--n-900);margin-bottom:5px;word-break:break-all">${esc(TULYA.cnmcFor(g.canonical.category, g.canonical.attrs||{}))}</div>
          ${esc(g.canonical.description)}""",
        label="groups cnmc")
    h = sub(h,
        "        <td style=\"text-align:right\"><button class=\"btn ghost small\" onclick=\"unmerge('${g.group_id}',${m.record_id})\">split out</button></td>",
        "        <td style=\"text-align:right\"><div class=\"rowacts\" style=\"justify-content:flex-end\">"
        "<button onclick=\"passportForRecord(${m.record_id})\">Passport</button>"
        "<button onclick=\"unmerge('${g.group_id}',${m.record_id})\">Split out</button></div></td>",
        label="groups passport button")
    h = sub(h,
        "    el.innerHTML = `<div class=\"empty\">No golden records yet — approve a pair in the Review Queue or",
        "    el.innerHTML = `<div class=\"empty\">No CNMC issued yet — approve a pair in the Review Queue or",
        label="groups empty")
    h = sub(h, "  const el = document.getElementById('groupsList');",
            "  const el = document.getElementById('groupsList');\n"
            "  { const _gc=document.getElementById('grCount'); if(_gc) _gc.textContent=groups.length; }",
            label="groups count")

    # hard-key veto
    h = sub(h,
        "        <span class=\"pill vetoed\">REJECTED — HARD-KEY CONFLICT</span>",
        "        <span>${verdictBadge('CONFLICT', true)}</span>",
        label="veto badge")
    h = sub(h, "${esc(cf.key)} disagrees", "${esc(TULYA.attrLabel(cf.key))} disagrees",
            label="veto attr label")
    h = sub(h,
        "      <button class=\"btn ghost small\" style=\"margin-top:10px\" onclick=\"openExplain(${it.a},${it.b})\">full breakdown</button>",
        """      <div class="verdict stop"><b>Merge blocked \\u2014 hard specification conflict</b>
        Semantic similarity ${(it.cos*100).toFixed(1)}%. Attribute validation:
        ${conflict.map(cf=>esc(TULYA.attrLabel(cf.key))+' '+esc(cf.a ?? '\\u2014')+' \\u2260 '+esc(cf.b ?? '\\u2014')).join('; ')}.
        Named reason: ${conflict.map(cf=>esc(TULYA.attrLabel(cf.key))+' mismatch').join(', ')}.</div>
      <div class="notequal"><b>SIMILARITY \\u2260 EQUIVALENCE</b>
        <span>A fuzzy matcher hands this over as a confident match. TULYA refuses it, and names the
        specification it refused on.</span></div>
      <div class="actbar">
        <button class="btn ghost small" onclick="openExplain(${it.a},${it.b})">View evidence</button>
        <button class="btn ghost small" onclick="openCase(${it.a},${it.b})">Open case</button>
        <button class="btn ghost small" onclick="passportForRecord(${it.a})">Passport</button>
      </div>""",
        label="veto verdict block")

    # audit
    h = sub(h,
        "      <td><span class=\"pill ${r.action}\">${esc(r.action)}</span></td>",
        "      <td><span class=\"pill ${['approve','reject','unmerge'].includes(r.action)?r.action:'review'}\">${esc(r.action)}</span></td>",
        label="audit pill")
    h = sub(h, "  el.innerHTML = `<div class=\"twrap\"><table><thead><tr><th>When</th><th>Action</th><th>Confidence</th>",
            "  { const _ac=document.getElementById('auditCount'); if(_ac) _ac.textContent=STATE.audit.length; }\n"
            "  el.innerHTML = `<div class=\"twrap\"><table><thead><tr><th>When</th><th>Action</th><th>Confidence</th>",
            label="audit count")

    # render the new panels alongside the existing ones
    h = sub(h,
        "  renderVetoed(); renderChallenge(); renderAudit();\n}",
        "  renderVetoed(); renderChallenge(); renderAudit();\n  renderTulyaPanels();\n}",
        label="renderAll")

    h = sub(h,
        "renderAll();\nrenderPerformance();\nrenderSearch();",
        """document.getElementById('passportSearch').addEventListener('input', e=>{
  PASSPORT_FILTER = e.target.value; renderPassport(); });
installChrome();
installNavDrawer();
installPopovers();
installAuth();
gsWire();
renderAll();
renderPerformance();
renderSearch();
routeBoot();""",
        label="boot")

    # footnote, compact
    h = cut(h, '  <div class="footnote">', "</main>",
        """  <div class="footnote">
    Steward for this session <input class="steward-input" id="stewardName" value="steward_demo"
      style="width:140px;height:28px">
    &nbsp;·&nbsp; TULYA — Material Intelligence &amp; Governance · SIH26099 · Team AlgoRythms
    &nbsp;·&nbsp; figures from the locked test-split evaluation on the TF-IDF-SVD encoder backend; see
    RESULTS.md for the reproducible run.
  </div>
""", "footnote")
    return h


# ===========================================================================
def main():
    if not SRC_TEMPLATE.exists():
        sys.exit("missing %s — the original template this build upgrades" % SRC_TEMPLATE)
    h = SRC_TEMPLATE.read_text(encoding="utf-8")

    for step in (rebrand, shell, overview, panels, heads, assets, wire):
        h = step(h)

    if MISSES:
        sys.exit("build anchors not found:\n  - " + "\n  - ".join(MISSES))

    OUT_TEMPLATE.write_text(h, encoding="utf-8")

    snap = SNAPSHOT.read_text(encoding="utf-8")
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', snap, re.S)
    if not m:
        sys.exit("could not read the data snapshot out of %s" % SNAPSHOT)
    data = json.loads(m.group(1))
    data.update(measured_extras())

    marks = cpse_marks()
    data["cpse_marks"] = marks
    expected = ["BPCL", "HPCL", "ONGC", "IOCL", "GAIL", "CPCL"]
    missing = [c for c in expected if c not in marks]
    if marks:
        print("CPSE logo assets inlined: %s" % ", ".join(sorted(marks)))
    if missing:
        print("CPSE logo assets still missing: %s" % ", ".join(missing))
        print("  drop each one at tulya/assets/cpse/<code>.svg (or .png/.jpg/.webp),")
        print("  taken from that CPSE's own website or brand page, then rebuild;")
        print("  until then those CPSEs render a monogram placeholder.")

    OUT_CONSOLE.write_text(h.replace("__DATA_JSON__", json.dumps(data, separators=(",", ":"))),
                           encoding="utf-8")

    OUT_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    OUT_PUBLIC.write_bytes(OUT_CONSOLE.read_bytes())

    leftover = len(re.findall(r"SAMANVAY|Samanvay|samanvay", OUT_CONSOLE.read_text(encoding="utf-8")))
    print("wrote %s" % OUT_TEMPLATE.relative_to(ROOT))
    print("wrote %s  (%.0f KB)" % (OUT_CONSOLE.relative_to(ROOT), OUT_CONSOLE.stat().st_size / 1024))
    print("wrote %s  (served at / by Vercel)" % OUT_PUBLIC.relative_to(ROOT))
    print("residual SAMANVAY strings (data keys only, renamed on display): %d" % leftover)


if __name__ == "__main__":
    main()
