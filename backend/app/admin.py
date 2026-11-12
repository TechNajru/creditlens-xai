"""Command-line administration:  python -m app.admin <command>   (run from backend/)

  init         create/upgrade the database, register + activate the trained models, create demo staff accounts
  create-user  create a user with a chosen role (prompts for the password)
  bootstrap    production-safe setup: migrate, register+activate the model, create the first admin from environment
               variables (CREDITLENS_BOOTSTRAP_ADMIN_EMAIL / CREDITLENS_BOOTSTRAP_ADMIN_PASSWORD). Idempotent; prints no passwords
  status       show users, model versions and database location
"""
from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from . import config, registry
from .db import get_session_factory
from .models import ModelVersion, User
from .security import EMAIL_RE, hash_password, normalize_email, password_problems

DEMO_USERS = [("reviewer@demo.local", "reviewer"), ("admin@demo.local", "admin")]


def alembic_config() -> Config:
    cfg = Config(str(config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(config.BASE_DIR / "migrations"))
    return cfg


def upgrade_database() -> None:
    command.upgrade(alembic_config(), "head")


def create_user(db, email: str, role: str, password: str) -> User:
    email = normalize_email(email)
    if not EMAIL_RE.match(email):
        raise ValueError("invalid email address")
    problems = password_problems(password, email)
    if problems:
        raise ValueError("Password " + "; ".join(problems))
    u = User(email=email, password_hash=hash_password(password), role=role)
    db.add(u)
    db.flush()
    return u


def cmd_init(_: argparse.Namespace) -> int:
    upgrade_database()
    db = get_session_factory()()
    try:
        for track in ("simulation", "public"):
            try:
                mv, created = registry.register_artifact(db, track)
            except FileNotFoundError:
                print(f"  - {track}: no trained model found (run python -m app.train / app.public_train), skipped")
                continue
            if registry.active_version(db, track) is None:
                registry.activate(db, mv)
            print(f"  - {track}: {mv.version} ({'registered' if created else 'already registered'}, "
                  f"{'ACTIVE' if mv.is_active else 'inactive'})")
        print("\nDemo staff accounts (LOCAL DEMO ONLY - passwords are shown once):")
        for email, role in DEMO_USERS:
            if db.scalar(select(User).where(User.email == email)):
                print(f"  - {email}: already exists (password unchanged)")
                continue
            pw = secrets.token_urlsafe(12)
            create_user(db, email, role, pw)
            print(f"  - {email}  role={role}  password={pw}")
        db.commit()
    finally:
        db.close()
    print(f"\nDatabase: {config.database_url()}")
    return 0


def cmd_bootstrap(_: argparse.Namespace) -> int:
    """Safe to run on every start: it only creates what is missing and never changes or prints an existing password."""
    upgrade_database()
    db = get_session_factory()()
    try:
        try:
            mv, created = registry.register_artifact(db, "simulation")
        except FileNotFoundError as exc:
            print(f"ERROR: {exc} Run: python -m app.train")
            return 1
        if registry.active_version(db, "simulation") is None:
            registry.activate(db, mv)
        print(f"simulation model: {mv.version} ({'registered' if created else 'already registered'})")
        try:
            pub, pub_created = registry.register_artifact(db, "public")
            print(f"public model: {pub.version} ({'registered' if pub_created else 'already registered'})")
        except FileNotFoundError:
            print("public model: not found (optional; needs the UCI dataset), skipped")
        if db.scalar(select(User.id).where(User.role == "admin")) is None:
            email, password = os.getenv("CREDITLENS_BOOTSTRAP_ADMIN_EMAIL"), os.getenv("CREDITLENS_BOOTSTRAP_ADMIN_PASSWORD")
            if not (email and password):
                print("WARNING: no admin account exists. Set CREDITLENS_BOOTSTRAP_ADMIN_EMAIL and "
                      "CREDITLENS_BOOTSTRAP_ADMIN_PASSWORD, then restart.")
            else:
                try:
                    create_user(db, email, "admin", password)
                except ValueError as exc:
                    db.rollback()
                    print(f"ERROR: could not create the bootstrap admin: {exc}")
                    return 1
                print(f"admin account created for {normalize_email(email)}")
        else:
            print("admin account: exists")
        db.commit()
    finally:
        db.close()
    print("bootstrap complete")
    return 0


def cmd_create_user(args: argparse.Namespace) -> int:
    pw = getpass.getpass("Password: ")
    db = get_session_factory()()
    try:
        create_user(db, args.email, args.role, pw)
        db.commit()
    except ValueError as exc:
        print("Error:", exc)
        return 1
    finally:
        db.close()
    print("Created", normalize_email(args.email), "with role", args.role)
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    db = get_session_factory()()
    try:
        print("Database:", config.database_url())
        for u in db.scalars(select(User).order_by(User.id)):
            print(f"  user {u.id}: {u.email} role={u.role} active={u.is_active}")
        for m in db.scalars(select(ModelVersion).order_by(ModelVersion.track, ModelVersion.id)):
            print(f"  model {m.id}: [{m.track}] {m.version} {'ACTIVE' if m.is_active else ''}")
    finally:
        db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.admin")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    cu = sub.add_parser("create-user")
    cu.add_argument("--email", required=True)
    cu.add_argument("--role", required=True, choices=["applicant", "reviewer", "admin"])
    cu.set_defaults(fn=cmd_create_user)
    sub.add_parser("bootstrap").set_defaults(fn=cmd_bootstrap)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
