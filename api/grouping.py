"""Union-find over steward-approved pairs, turned into golden records.

A group only exists because a human approved every edge that connects it —
the engine never merges anything on its own (see engine/score.py). This
module just answers "given the approvals so far, what does the world look
like": which records are now one golden item, which legacy code from which
CPSE maps to it, and what the group should be called.
"""
import json


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


def compute_components(edges):
    """edges: list of (a,b) approved pairs -> dict record_id -> group_root (min id in group)."""
    uf = UnionFind()
    for a, b in edges:
        uf.union(int(a), int(b))
    members = {}
    for a, b in edges:
        for x in (int(a), int(b)):
            root = uf.find(x)
            members.setdefault(root, set()).add(x)
    return {root: sorted(ids) for root, ids in members.items()}


def _canonical(member_ids, recs, prep):
    """Pick the member with the most hard-key attributes resolved (most
    complete record) as the display-canonical description; ties broken by
    longer description text."""
    best, best_key = member_ids[0], (-1, -1)
    for rid in member_ids:
        try:
            n_attrs = len(json.loads(prep.at[rid, "attrs"]))
        except Exception:
            n_attrs = 0
        desc_len = len(str(recs.at[rid, "description"]))
        key = (n_attrs, desc_len)
        if key > best_key:
            best_key, best = key, rid
    return best


def build_golden_records(edges, recs, prep):
    """recs: DataFrame indexed by record_id (cpse, legacy_code, description, category_true).
    prep: DataFrame indexed by record_id (norm, attrs json, category, bucket).
    Returns a list of group dicts, largest first. Edges referencing a record
    id outside `recs` (shouldn't happen once the API validates input, but
    kept defensive so one bad row can never take the whole console down)
    are silently dropped."""
    valid_ids = set(recs.index)
    edges = [(a, b) for a, b in edges if int(a) in valid_ids and int(b) in valid_ids]
    comps = compute_components(edges)
    groups = []
    for root, member_ids in comps.items():
        canon_id = _canonical(member_ids, recs, prep)
        canon = recs.loc[canon_id]
        members = []
        for rid in member_ids:
            r = recs.loc[rid]
            members.append(dict(record_id=int(rid), cpse=r.cpse, legacy_code=str(r.legacy_code),
                                 description=r.description, is_canonical=(rid == canon_id)))
        category = prep.at[canon_id, "category"] if canon_id in prep.index else canon.get("category_true", "")
        groups.append(dict(
            group_id=f"G{root}",
            root_record_id=int(root),
            category=category,
            canonical=dict(record_id=int(canon_id), cpse=canon.cpse,
                            legacy_code=str(canon.legacy_code), description=canon.description),
            members=members,
            size=len(member_ids),
            cpses=sorted({m["cpse"] for m in members}),
        ))
    groups.sort(key=lambda g: (-g["size"], g["group_id"]))
    return groups


def find_group_for_record(groups, record_id):
    record_id = int(record_id)
    for g in groups:
        if any(m["record_id"] == record_id for m in g["members"]):
            return g
    return None
