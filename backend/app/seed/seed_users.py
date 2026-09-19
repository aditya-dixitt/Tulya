"""Create the demo accounts used to exercise the four roles.

Refused outright when ENVIRONMENT=production. The prototype shipped these
credentials in source; here they exist only when SEED_DEMO_USERS is true, and
the production config validator rejects that combination, so a deployed
instance cannot have them by accident.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import Cpse, User
from ..services.auth_service import hash_password

DEMO_USERS = [
    ("viewer",   "V. Iyer (audit)",     "CPCL", "viewer",   "viewer123"),
    ("steward",  "R. Mishra",           "IOCL", "steward",  "steward123"),
    ("steward2", "A. Deshmukh",         "BPCL", "steward",  "steward123"),
    ("approver", "S. Nair (materials)", "IOCL", "approver", "approver123"),
    ("engineer", "K. Menon (rotating)", "ONGC", "approver", "engineer123"),
    ("admin",    "System Administrator", None,  "admin",    "admin123"),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="(ignored in production — demo users are never seeded there)")
    a = ap.parse_args(argv)

    if settings.is_production or not settings.SEED_DEMO_USERS:
        print("refusing to seed demo users: SEED_DEMO_USERS is false or "
              "ENVIRONMENT=production. Create real accounts with "
              "`python -m app.seed.create_user`.", file=sys.stderr)
        return 1

    created = 0
    with SessionLocal() as db:
        for username, full_name, cpse_code, role, password in DEMO_USERS:
            if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
                continue
            cpse_id = None
            if cpse_code:
                c = db.execute(select(Cpse).where(Cpse.code == cpse_code)).scalar_one_or_none()
                cpse_id = c.id if c else None
            db.add(User(username=username, full_name=full_name, cpse_id=cpse_id,
                        role=role, password_hash=hash_password(password),
                        is_active=True))
            created += 1
        db.commit()
    print(f"seeded {created} demo user(s); "
          f"{len(DEMO_USERS) - created} already existed")
    print("DEMO CREDENTIALS — development only, never deployed:")
    for u, _, _, role, pw in DEMO_USERS:
        print(f"  {u:9} / {pw:12} ({role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
