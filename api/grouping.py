"""Approved pairs -> golden records, with the veto enforced at group level too.

A group only exists because a human approved every edge that connects it - the
engine never merges anything on its own (see engine/score.py). This module
answers "given the approvals so far, what does the world look like": which
records are now one golden item, which legacy code from which CPSE maps to it,
and what the group's consolidated specification is.

---------------------------------------------------------------------------
Why this is not just a union-find
---------------------------------------------------------------------------
It was, and the ERP round trip caught it: **transitive closure defeats a
pairwise veto.**

The hard-key veto compares two records. Union-find joins whole components. A
record whose specification was destroyed - a description truncated at SAP's
40-character MAKTX limit, say - conflicts with nobody, because an unreadable
key is UNKNOWN and UNKNOWN never vetoes. It can therefore pair legitimately
with a 1-inch gasket and, separately, with an 18-inch gasket. Neither pair is
wrong. The union of the two is very wrong, and no pairwise check anywhere in
the system is looking at it.

Measured on the IOCL round trip before the fix: 21 of 516 golden records
(4.1%) contained at least one pair of members that directly contradicted each
other on a hard key - bores of 1", 2.5", 5" and 18" inside a single national
code. That is a catalogue-corrupting defect, and it is invisible at pair level
because every individual pair passed.

So grouping now carries a **consolidated specification profile** per group and
refuses any edge that would merge two profiles disagreeing on a hard key. The
approval is not discarded - it is returned as a *blocked* edge with the
conflict named, and the console shows it to the steward who made it. The
system declining to carry out an instruction it can prove is unsafe, and
saying exactly why, is better behaviour than either silently obeying or
silently dropping it.

Edges are applied strongest-evidence-first (by score where known, then by a
stable id order) so that when two approvals cannot both hold, the one that is
refused is the weaker one, deterministically.
"""
import json

from engine.attributes import HARD_KEYS


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)
            return True
        return False


def _attrs_of(rid, prep):
    if rid not in prep.index:
        return {}
    try:
        return json.loads(prep.at[rid, "attrs"]) or {}
    except Exception:
        return {}


def _conflicts(pa, pb):
    """Hard keys known in both profiles that disagree."""
    return [k for k in HARD_KEYS if k in pa and k in pb and pa[k] != pb[k]]


def compute_components(edges, recs=None, prep=None, scores=None, enforce=True):
    """-> (components, blocked)

    components: {root -> sorted member ids}
    blocked:    edges refused because applying them would have produced a group
                whose members contradict each other, each with the conflict.

    With enforce=False this degrades to a plain union-find, which is what the
    ablation in the tests uses to demonstrate what the check is worth.
    """
    edges = [(int(a), int(b)) for a, b in edges]
    if prep is not None:
        valid = set(prep.index)
        if recs is not None:
            valid &= set(recs.index)
        edges = [(a, b) for a, b in edges if a in valid and b in valid]
    elif recs is not None:
        valid = set(recs.index)
        edges = [(a, b) for a, b in edges if a in valid and b in valid]

    # strongest evidence first, deterministic tie-break
    scores = scores or {}
    def _rank(e):
        a, b = e
        s = scores.get((a, b), scores.get((b, a)))
        return (-(s if s is not None else 0.0), a, b)
    edges = sorted(set(edges), key=_rank)

    uf = UnionFind()
    profiles, blocked = {}, []
    for a, b in edges:
        ra, rb = uf.find(a), uf.find(b)
        pa = profiles.get(ra) or (_attrs_of(a, prep) if prep is not None else {})
        pb = profiles.get(rb) or (_attrs_of(b, prep) if prep is not None else {})
        if ra != rb and enforce and prep is not None:
            bad = _conflicts(pa, pb)
            if bad:
                blocked.append(dict(
                    a=a, b=b, conflicts=bad,
                    detail={k: [pa.get(k), pb.get(k)] for k in bad},
                    reason=("approving this would merge two groups that disagree on "
                            + ", ".join(bad))))
                continue
        merged = dict(pa)
        merged.update({k: v for k, v in pb.items() if k not in merged})
        if uf.union(a, b):
            root = uf.find(a)
            profiles[root] = merged
        else:
            profiles[uf.find(a)] = merged

    blocked_keys = {(x["a"], x["b"]) for x in blocked}
    members = {}
    for a, b in edges:
        if (a, b) in blocked_keys:
            continue
        for x in (a, b):
            members.setdefault(uf.find(x), set()).add(x)
    return {root: sorted(ids) for root, ids in members.items()}, blocked


def _canonical(member_ids, recs, prep):
    """The member with the most hard keys resolved is the display canonical -
    the most completely described row, not the longest or the first."""
    best, best_key = member_ids[0], (-1, -1)
    for rid in member_ids:
        n_attrs = len(_attrs_of(rid, prep))
        desc_len = len(str(recs.at[rid, "description"]))
        key = (n_attrs, desc_len)
        if key > best_key:
            best_key, best = key, rid
    return best


def _group_profile(member_ids, prep):
    """Consolidated specification: every hard key any member could read.

    This is the golden record's actual content - one item, described by the
    union of what its members knew, which is strictly more than any single
    legacy row knew. Recovering a spec that no individual CPSE row still
    carried is the clearest single answer to "what did harmonisation buy us".
    """
    prof, sources = {}, {}
    for rid in member_ids:
        for k, v in _attrs_of(rid, prep).items():
            if k not in prof:
                prof[k], sources[k] = v, rid
    return prof, sources


def build_golden_records(edges, recs, prep, scores=None, enforce=True):
    """Backwards-compatible entry point: returns the list of groups only."""
    return resolve(edges, recs, prep, scores=scores, enforce=enforce)["groups"]


def resolve(edges, recs, prep, scores=None, enforce=True):
    """-> {'groups': [...], 'blocked': [...]}"""
    comps, blocked = compute_components(edges, recs, prep, scores=scores, enforce=enforce)
    groups = []
    for root, member_ids in comps.items():
        canon_id = _canonical(member_ids, recs, prep)
        canon = recs.loc[canon_id]
        members = []
        for rid in member_ids:
            r = recs.loc[rid]
            members.append(dict(record_id=int(rid), cpse=r.cpse,
                                plant=(r.plant if "plant" in recs.columns else ""),
                                legacy_code=str(r.legacy_code),
                                description=r.description, is_canonical=(rid == canon_id)))
        profile, sources = _group_profile(member_ids, prep)
        category = prep.at[canon_id, "category"] if canon_id in prep.index else \
            canon.get("category_true", "")
        canon_attrs = _attrs_of(canon_id, prep)
        groups.append(dict(
            group_id=f"G{root}",
            root_record_id=int(root),
            category=category,
            canonical=dict(record_id=int(canon_id), cpse=canon.cpse,
                           legacy_code=str(canon.legacy_code), description=canon.description),
            members=members,
            size=len(member_ids),
            cpses=sorted({m["cpse"] for m in members}),
            plants=sorted({m["plant"] for m in members if m["plant"]}),
            specs=profile,
            specs_recovered=sorted(k for k in profile if k not in canon_attrs),
        ))
    groups.sort(key=lambda g: (-g["size"], g["group_id"]))
    return dict(groups=groups, blocked=blocked)


def audit_consistency(groups, prep):
    """Independent re-check: does any finished group contain two members that
    contradict each other? Should always be zero once `enforce` is on, and the
    tests assert exactly that. Kept as a separate function deliberately - a
    guarantee the same code path produces and verifies is not a guarantee."""
    bad = []
    for g in groups:
        ids = [m["record_id"] for m in g["members"]]
        attrs = {i: _attrs_of(i, prep) for i in ids}
        conf = {}
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                for k in _conflicts(attrs[ids[i]], attrs[ids[j]]):
                    conf.setdefault(k, set()).add((attrs[ids[i]][k], attrs[ids[j]][k]))
        if conf:
            bad.append(dict(group_id=g["group_id"], size=g["size"],
                            conflicts={k: sorted(v) for k, v in conf.items()}))
    return bad


def find_group_for_record(groups, record_id):
    record_id = int(record_id)
    for g in groups:
        if any(m["record_id"] == record_id for m in g["members"]):
            return g
    return None
