#!/usr/bin/env python3
"""
Migrate legacy user data from scripts/user_data.sql into the PostgreSQL user table.

Legacy (MySQL) vs PostgreSQL:
- id: char(36) -> UUID (same format)
- role: enum('admin','treasurer','member','compliance') -> userroleenum (ADMIN, TREASURER, MEMBER, COMPLIANCE)
- approved: tinyint(0/1) -> boolean (false/true)
- All other fields align (first_name, last_name, email, phone_number, bank_*, nrc_number,
  physical_address, password_hash, *_next_of_kin, date_joined).

Also creates MemberProfile records for all users:
- Status: ACTIVE if approved=True, INACTIVE if approved=False/None
- activated_at: Set to date_joined if approved=True

Uses email check to skip users that already exist, but creates MemberProfile if missing.
"""

import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.db.base import SessionLocal
from app.models.user import User, UserRoleEnum
from app.models.member import MemberProfile, MemberStatus


# Legacy column order (from INSERT INTO user VALUES ...)
FIELDS = [
    "id",
    "first_name",
    "last_name",
    "email",
    "phone_number",
    "bank_account",
    "bank_name",
    "bank_branch",
    "nrc_number",
    "physical_address",
    "password_hash",
    "role",
    "approved",
    "first_name_next_of_kin",
    "last_name_next_of_kin",
    "phone_number_next_of_kin",
    "date_joined",
]


def parse_mysql_insert_values(content: str) -> list[dict]:
    """Parse INSERT INTO user VALUES (row1),(row2),... into list of dicts."""
    # Find the INSERT line and extract from "VALUES " to the terminating ";"
    values_blob = None
    for line in content.splitlines():
        if "INSERT INTO" in line and "user" in line and "VALUES" in line:
            start = line.index("VALUES") + len("VALUES")
            end = line.rindex(";")
            values_blob = line[start:end].strip()
            break
    if not values_blob:
        raise ValueError("Could not find INSERT INTO user VALUES in SQL file")

    rows = []
    i = 0
    n = len(values_blob)

    def skip_ws():
        nonlocal i
        while i < n and values_blob[i] in " \t\n\r":
            i += 1

    def parse_value():
        nonlocal i
        skip_ws()
        if i >= n:
            return None
        if values_blob[i] == "(":
            i += 1
            skip_ws()
        if values_blob[i] == "'":
            # Quoted string
            i += 1
            buf = []
            while i < n:
                if values_blob[i] == "'" and i + 1 < n and values_blob[i + 1] == "'":
                    buf.append("'")
                    i += 2
                elif values_blob[i] == "'":
                    i += 1
                    break
                else:
                    buf.append(values_blob[i])
                    i += 1
            return "".join(buf)
        # Unquoted: NULL or 0/1 (approved)
        start = i
        while i < n and values_blob[i] not in ",)":
            i += 1
        tok = values_blob[start:i].strip()
        if tok.upper() == "NULL":
            return None
        return tok

    while i < n:
        skip_ws()
        if i >= n:
            break
        if values_blob[i] == ",":
            i += 1
            continue
        if values_blob[i] == "(":
            i += 1
        row = {}
        for k, f in enumerate(FIELDS):
            v = parse_value()
            row[f] = v
            skip_ws()
            if i < n and values_blob[i] == ",":
                i += 1
        skip_ws()
        if i < n and values_blob[i] == ")":
            i += 1
        rows.append(row)
    return rows


def map_row_to_user(row: dict) -> dict:
    """Map legacy row to User model fields. Align types for PostgreSQL."""
    role_raw = (row.get("role") or "member").strip().lower()
    role_map = {
        "admin": UserRoleEnum.ADMIN,
        "treasurer": UserRoleEnum.TREASURER,
        "member": UserRoleEnum.MEMBER,
        "compliance": UserRoleEnum.COMPLIANCE,
    }
    role = role_map.get(role_raw, UserRoleEnum.MEMBER)

    approved_raw = row.get("approved")
    if approved_raw is None:
        approved = None
    elif isinstance(approved_raw, str):
        approved = approved_raw.strip() in ("1", "true", "yes")
    else:
        approved = bool(approved_raw)

    def str_or_none(s):
        if s is None:
            return None
        t = (s if isinstance(s, str) else str(s)).strip()
        return t if t else None

    raw_date = str_or_none(row.get("date_joined"))
    date_joined = None
    if raw_date:
        try:
            date_joined = datetime.strptime(raw_date.strip(), "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    return {
        "id": row["id"],
        "first_name": str_or_none(row.get("first_name")),
        "last_name": str_or_none(row.get("last_name")),
        "email": (row.get("email") or "").strip() or None,
        "phone_number": str_or_none(row.get("phone_number")),
        "bank_account": str_or_none(row.get("bank_account")),
        "bank_name": str_or_none(row.get("bank_name")),
        "bank_branch": str_or_none(row.get("bank_branch")),
        "nrc_number": str_or_none(row.get("nrc_number")),
        "physical_address": str_or_none(row.get("physical_address")),
        "password_hash": (row.get("password_hash") or "").strip(),
        "role": role,
        "approved": approved,
        "first_name_next_of_kin": str_or_none(row.get("first_name_next_of_kin")),
        "last_name_next_of_kin": str_or_none(row.get("last_name_next_of_kin")),
        "phone_number_next_of_kin": str_or_none(row.get("phone_number_next_of_kin")),
        "date_joined": date_joined,
    }


def run(dry_run: bool = False, verbose: bool = False):
    sql_path = Path(__file__).resolve().parent / "user_data.sql"
    if not sql_path.exists():
        print(f"❌ Not found: {sql_path}")
        return 1

    content = sql_path.read_text(encoding="utf-8", errors="replace")
    rows = parse_mysql_insert_values(content)
    print(f"Parsed {len(rows)} user rows from {sql_path.name}")

    if dry_run:
        print("\n📋 Sample parsed data (showing first user):")
        if rows:
            r = rows[0]
            print(f"  ID: {r.get('id')}")
            print(f"  Name: {r.get('first_name')} {r.get('last_name')}")
            print(f"  Email: {r.get('email')}")
            print(f"  Phone: {r.get('phone_number')}")
            print(f"  NRC: {r.get('nrc_number')}")
            print(f"  Address: {r.get('physical_address')}")
            print(f"  Bank: {r.get('bank_name')} - {r.get('bank_branch')} (Account: {r.get('bank_account')})")
            print(f"  Password Hash: {r.get('password_hash')[:50]}..." if r.get('password_hash') else "  Password Hash: None")
            print(f"  Role: {r.get('role')}")
            print(f"  Approved: {r.get('approved')}")
            print(f"  Next of Kin: {r.get('first_name_next_of_kin')} {r.get('last_name_next_of_kin')} ({r.get('phone_number_next_of_kin')})")
            print(f"  Date Joined: {r.get('date_joined')}")
        print(f"\n✅ Total: {len(rows)} users parsed. All fields will be migrated.")
        print("Dry run complete. No DB changes.")
        return 0

    db = SessionLocal()
    inserted_users = 0
    created_profiles = 0
    skipped = 0
    errors = 0

    try:
        for row in rows:
            try:
                mapped = map_row_to_user(row)
                if not mapped["email"]:
                    print(f"  ⚠ Skip (no email): id={mapped['id']}")
                    skipped += 1
                    continue
                if not mapped["password_hash"]:
                    print(f"  ⚠ Skip (no password_hash): email={mapped['email']}")
                    skipped += 1
                    continue

                existing = db.query(User).filter(User.email == mapped["email"]).first()
                if existing:
                    # Check if member profile exists
                    existing_profile = db.query(MemberProfile).filter(MemberProfile.user_id == existing.id).first()
                    if not existing_profile:
                        # Create member profile for existing user (use existing user's approved status)
                        member_status = MemberStatus.ACTIVE if existing.approved else MemberStatus.INACTIVE
                        member_profile = MemberProfile(
                            user_id=existing.id,
                            status=member_status,
                            activated_at=existing.date_joined if existing.approved else None,
                            activated_by=None,
                        )
                        db.add(member_profile)
                        if verbose:
                            print(f"  ✓ Created MemberProfile for existing user: {mapped['email']} (status: {member_status.value})")
                        created_profiles += 1
                    else:
                        if verbose:
                            print(f"  ⚠ Skip (already exists): {mapped['email']} (existing ID: {existing.id}, profile exists)")
                        skipped += 1
                    continue

                user = User(
                    id=mapped["id"],
                    first_name=mapped["first_name"],
                    last_name=mapped["last_name"],
                    email=mapped["email"],
                    phone_number=mapped["phone_number"],
                    bank_account=mapped["bank_account"],
                    bank_name=mapped["bank_name"],
                    bank_branch=mapped["bank_branch"],
                    nrc_number=mapped["nrc_number"],
                    physical_address=mapped["physical_address"],
                    password_hash=mapped["password_hash"],
                    role=mapped["role"],
                    approved=mapped["approved"],
                    first_name_next_of_kin=mapped["first_name_next_of_kin"],
                    last_name_next_of_kin=mapped["last_name_next_of_kin"],
                    phone_number_next_of_kin=mapped["phone_number_next_of_kin"],
                    date_joined=mapped["date_joined"],
                )
                db.add(user)
                db.flush()  # Get user.id
                
                # Create member profile
                member_status = MemberStatus.ACTIVE if mapped["approved"] else MemberStatus.INACTIVE
                member_profile = MemberProfile(
                    user_id=user.id,
                    status=member_status,
                    activated_at=mapped["date_joined"] if mapped["approved"] else None,
                    activated_by=None,  # Could set to admin user ID if needed
                )
                db.add(member_profile)
                
                if verbose:
                    print(f"  ✓ Insert: {mapped['email']} ({mapped['first_name']} {mapped['last_name']}) - MemberProfile: {member_status.value}")
                inserted_users += 1
            except Exception as e:
                errors += 1
                print(f"  ❌ Error for email={row.get('email')}: {e}")

        db.commit()
        print(f"✅ Inserted {inserted_users} users, created {created_profiles} member profiles, skipped {skipped}, errors {errors}")
        return 0 if not errors else 1
    except Exception as e:
        db.rollback()
        print(f"❌ Fatal: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Migrate legacy user data from user_data.sql into PostgreSQL")
    ap.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    ap.add_argument("--verbose", "-v", action="store_true", help="Show detailed output for each user")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run, verbose=args.verbose))
