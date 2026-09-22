"""The National Material Code itself - format, check digit, parsing.

    NMC-10-30-10-00042-7
     |   |  |  |    |    |
     |   |  |  |    |    check character (Damm)
     |   |  |  |    serial, 5 digits, assigned within the class
     |   |  |  class    ...  Ball Valve
     |   |  family      ...  Valves
     |   segment        ...  Piping and Fluid Handling
     prefix

Two decisions in here are worth defending, because both have an obvious
alternative that is wrong:

**Why a serial and not a hash of the specifications.**  A content hash is
tempting - stateless, no central authority, no collisions to manage. It is
also unusable, because a material code is a *permanent identifier* that ends
up on drawings, purchase orders, GRNs and warranty claims. Correct one typo
in a spec and a hashed code changes, silently orphaning every document that
quoted it. Codes must survive corrections to the thing they name, so the
code is assigned once and the record underneath it is edited. Serials are
issued per class, so two CPSEs onboarding different classes never contend.

**Why Damm and not Luhn.**  Both catch every single-digit error. Luhn misses
the transposition 09 <-> 90; Damm, being built on a totally anti-symmetric
quasigroup, catches *all* adjacent transpositions. Material codes are
re-keyed by hand off printed indents more often than anyone would like, and
transposition is the commonest hand-keying error there is. The quasigroup
table below is not taken on trust either - tests/test_codegen.py re-derives
the anti-symmetry property from the table rather than asserting known
outputs, so a single mistyped cell fails the suite.
"""
import re

PREFIX = "NMC"
SERIAL_WIDTH = 5
MAX_SERIAL = 10 ** SERIAL_WIDTH - 1

# Damm's totally anti-symmetric quasigroup of order 10.
_DAMM = (
    (0, 3, 1, 7, 5, 9, 8, 6, 4, 2),
    (7, 0, 9, 2, 1, 5, 4, 8, 6, 3),
    (4, 2, 0, 6, 8, 7, 1, 3, 5, 9),
    (1, 7, 5, 0, 9, 8, 3, 4, 2, 6),
    (6, 1, 2, 3, 0, 4, 5, 9, 7, 8),
    (3, 6, 7, 4, 2, 0, 9, 5, 8, 1),
    (5, 8, 6, 9, 7, 2, 0, 1, 3, 4),
    (8, 9, 4, 5, 3, 6, 2, 0, 1, 7),
    (9, 4, 3, 8, 6, 1, 7, 2, 0, 5),
    (2, 5, 8, 1, 4, 3, 6, 7, 9, 0),
)

_CODE_RE = re.compile(
    rf"^{PREFIX}-(\d{{2}})-(\d{{2}})-(\d{{2}})-(\d{{{SERIAL_WIDTH}}})-(\d)$")


def damm_check(digits: str) -> int:
    """The check digit for a digit string."""
    interim = 0
    for ch in digits:
        if not ch.isdigit():
            raise ValueError(f"non-digit {ch!r} in {digits!r}")
        interim = _DAMM[interim][int(ch)]
    return interim


def damm_valid(digits_with_check: str) -> bool:
    """A Damm-checked string is valid exactly when its own interim digit is 0."""
    try:
        return damm_check(digits_with_check) == 0
    except ValueError:
        return False


def mint_code(class_code: str, serial: int) -> str:
    """Build the code string for a class and an already-assigned serial.

    Pure and total: the registry decides *which* serial, this decides what the
    code for it looks like. Same inputs always give the same code.
    """
    parts = str(class_code).split(".")
    if len(parts) != 3 or not all(p.isdigit() and len(p) == 2 for p in parts):
        raise ValueError(f"class code must be ss.ff.cc, got {class_code!r}")
    if not 0 <= int(serial) <= MAX_SERIAL:
        raise ValueError(f"serial {serial} outside 0..{MAX_SERIAL}")
    body = f"{parts[0]}{parts[1]}{parts[2]}{int(serial):0{SERIAL_WIDTH}d}"
    return f"{PREFIX}-{parts[0]}-{parts[1]}-{parts[2]}-{int(serial):0{SERIAL_WIDTH}d}-{damm_check(body)}"


def parse_code(code: str) -> dict | None:
    """-> {class_code, serial, check, valid} or None if it isn't code-shaped.

    `valid` False means it is shaped like a code but fails its check digit -
    a typo, not a different kind of identifier. The two are reported
    separately because they need different handling on an ERP import: one is
    a rejected row, the other is a row that isn't ours.
    """
    m = _CODE_RE.match(str(code).strip().upper())
    if not m:
        return None
    seg, fam, cls, serial, check = m.groups()
    return dict(class_code=f"{seg}.{fam}.{cls}", serial=int(serial), check=int(check),
                valid=damm_valid(f"{seg}{fam}{cls}{serial}{check}"), code=m.string)


def is_valid_code(code: str) -> bool:
    p = parse_code(code)
    return bool(p and p["valid"])
