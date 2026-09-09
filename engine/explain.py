"""Turn a scored pair into the structured reason a steward actually signs off on.
Nobody should approve `0.93`; they approve a breakdown they can check."""
from engine.score import W_COS, W_FUZ, W_ATTR, T_DISCARD, T_AUTO


def explain(a_row, b_row, r):
    signals = [dict(name="Semantic similarity", value=round(r["cos"], 4), weight=W_COS),
               dict(name="Token similarity", value=round(r["fuz"], 4), weight=W_FUZ)]
    if r["attr"] is not None:
        signals.append(dict(name="Attribute agreement", value=round(r["attr"], 4),
                            weight=W_ATTR))
    return dict(
        a=dict(cpse=a_row["cpse"], code=a_row["legacy_code"], text=a_row["description"]),
        b=dict(cpse=b_row["cpse"], code=b_row["legacy_code"], text=b_row["description"]),
        signals=signals,
        attributes=[dict(key=k, a=a_row["attrs"].get(k), b=b_row["attrs"].get(k),
                         verdict=v) for k, v in r["verdicts"].items()],
        coverage=r["coverage"], score=round(r["score"], 4),
        decision=r["decision"], vetoed=r["vetoed"], reason=r["reason"],
        thresholds=dict(discard=T_DISCARD, auto_suggest=T_AUTO))


def render(x) -> str:
    """Plain-text rendering - this is the panel shown in the demo."""
    L = [f"{'MATCH REJECTED' if x['vetoed'] else 'MATCH RECOMMENDATION'}",
         f"  A  {x['a']['cpse']}·{x['a']['code']}  {x['a']['text']}",
         f"  B  {x['b']['cpse']}·{x['b']['code']}  {x['b']['text']}", "  " + "-" * 62]
    for s in x["signals"]:
        L.append(f"  {s['name']:<24} {s['value']:.3f}   x{s['weight']:.2f}")
    for at in x["attributes"]:
        mark = {"MATCH": "OK ", "MISMATCH": "XX ", "UNKNOWN": "?  "}[at["verdict"]]
        val = f"{at['a']} vs {at['b']}" if at["verdict"] == "MISMATCH" else (at["a"] or at["b"])
        L.append(f"  {mark}{at['key']:<21} {val}")
    L += [f"  coverage                 {x['coverage']} hard key(s) known on both sides",
          f"  {'FINAL SCORE':<24} {x['score']:.3f}",
          f"  DECISION                 {x['decision']}  -  {x['reason']}"]
    return "\n".join(L)
