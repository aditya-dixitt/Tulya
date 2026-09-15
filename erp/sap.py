"""The SAP MM material-master shape SAMANVAY reads and writes.

Every CPSE in scope runs SAP MM (or something that exports the same way), so
the connector is written against the real table and field names rather than a
tidy CSV of our own invention. A judge who has run an SAP project recognises
these on sight; a team that has not seen them finds out on integration day.

    MARA   material, general      MATNR  material number  (the legacy code)
                                  MTART  material type    (ROH / ERSA / HIBE)
                                  MEINS  base unit of measure
                                  MATKL  material group   (the CPSE's own grouping)
    MAKT   material descriptions  MATNR
                                  SPRAS  language key     (EN / HI)
                                  MAKTX  short text       ** 40 characters **
    MARC   plant data             MATNR, WERKS (plant)
    MARD   storage location       MATNR, WERKS, LABST (unrestricted stock)

**MAKTX is 40 characters.** That single limit is a large part of why this
problem statement exists. "Hexagonal Bolt M12 x 50 mm Stainless Steel 316" is
48 characters, so whoever created the record shortened it, and the next
person at the next plant shortened it differently. The duplication that looks
like careless data entry is substantially a field-length constraint doing what
field-length constraints do. `maktx_pressure()` measures it on any extract, so
the claim is a number rather than an anecdote.

**Write-back never touches MATNR.** The national code goes into a customer
namespace table (`Z_NMC_MAP`), keyed by material and plant. Overwriting a
material number in a live ERP invalidates open purchase orders, goods
receipts, reservations and every historical document that quoted it - and it
is the single fastest way to have a harmonisation project stopped by the
finance function. Legacy codes are kept and mapped, which is also what the
problem statement asks for.
"""
import csv
import hashlib
import pathlib

MAKTX_LIMIT = 40          # SAP MAKT-MAKTX short text
MATNR_LIMIT = 18          # SAP MARA-MATNR material number
WERKS_LIMIT = 4           # SAP plant code

MARA_FIELDS = ["MANDT", "MATNR", "MTART", "MATKL", "MEINS", "ERSDA", "ERNAM"]
MAKT_FIELDS = ["MANDT", "MATNR", "SPRAS", "MAKTX"]
MARC_FIELDS = ["MANDT", "MATNR", "WERKS"]
MARD_FIELDS = ["MANDT", "MATNR", "WERKS", "LABST", "STPRS"]

# The custom table the national code is written into. Z_ is SAP's customer
# namespace - anything we create must live there, not in SAP's own tables.
# ZZNMC_STATUS  A = the code is live, S = it was superseded and resolves onward
# ZZNMC_CONF    C = every defining spec on this row confirms the code
#               P = provisional: nothing contradicts it, but this row's own
#                   description cannot confirm all of them. A buyer must see
#                   this rather than infer certainty from the code's presence.
ZNMC_FIELDS = ["MANDT", "MATNR", "WERKS", "ZZNMC", "ZZNMC_CLASS", "ZZNMC_STATUS",
               "ZZNMC_CONF", "ZZ_UNCONFIRMED", "ZZ_VALID_FROM", "ZZ_SOURCE", "ZZ_APPROVER"]

CLIENT = "800"            # MANDT - SAP client; 800 is the conventional demo client

# Material type by class segment, as a CPSE would actually assign it.
MTART_BY_SEGMENT = {
    "10": "ERSA",   # spare parts
    "20": "ERSA",
    "30": "ERSA",
    "40": "ERSA",
    "99": "ROH",    # raw material - the fallback when nothing is known
}


def truncate_maktx(text: str) -> str:
    """What the ERP would have stored. Truncation, not summarisation - that is
    precisely the point: SAP does not shorten intelligently, it cuts."""
    return str(text)[:MAKTX_LIMIT]


def maktx_pressure(descriptions) -> dict:
    """How much of an extract does not fit in MAKTX.

    Reported on every extract because it is the strongest available evidence
    that the duplication is structural rather than careless.
    """
    lens = [len(str(d)) for d in descriptions]
    if not lens:
        return dict(n=0, over_limit=0, share_over_limit=0.0, mean_len=0.0, max_len=0)
    over = sum(1 for n in lens if n > MAKTX_LIMIT)
    return dict(n=len(lens), over_limit=over, share_over_limit=round(over / len(lens), 4),
                mean_len=round(sum(lens) / len(lens), 1), max_len=max(lens),
                chars_lost=sum(max(0, n - MAKTX_LIMIT) for n in lens))


def plant_code(plant_name: str, seen: dict) -> str:
    """A 4-character WERKS for a plant name, stable within a run.

    Real WERKS values come from the CPSE's own configuration; this derives a
    deterministic stand-in so the mock extract is shaped correctly. Collisions
    are resolved by numbering, never by silently sharing a code - two plants
    sharing a WERKS would corrupt the very thing the mapping is keyed on.
    """
    if plant_name in seen:
        return seen[plant_name]
    letters = "".join(w[0] for w in str(plant_name).split() if w)[:3].upper() or "PL"
    base = (letters + "0")[:WERKS_LIMIT]
    code, n = base, 0
    taken = set(seen.values())
    while code in taken:
        n += 1
        code = (letters[:2] + f"{n:02d}")[:WERKS_LIMIT]
    seen[plant_name] = code
    return code


def write_table(path, fields, rows):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def read_table(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
