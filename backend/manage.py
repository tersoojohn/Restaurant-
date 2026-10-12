"""
Command-line user management (this is the "createsuperuser" of this project).

    python manage.py createowner            full access: dashboard, dishes, customers, staff
    python manage.py createstaff            kitchen access: live orders only
    python manage.py listusers              show everyone (optionally --role owner|staff|customer)
    python manage.py changepassword EMAIL
    python manage.py disable EMAIL          block login immediately
    python manage.py enable EMAIL
    python manage.py setrole EMAIL ROLE     owner | staff | customer

Prompts for anything you do not pass as a flag, and never echoes passwords.
"""
import argparse
import getpass
import re
import sys

from sqlalchemy import select

from auth import hash_password
from models import Base, SessionLocal, User, engine

ROLES = ("owner", "staff", "customer")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CommandError(Exception):
    pass


# ---------------------------------------------------------------- reusable logic (also used by tests)

def create_user(db, *, name, email, phone, password, role):
    email = email.strip().lower()
    if role not in ROLES:
        raise CommandError(f"Role must be one of {', '.join(ROLES)}")
    if not EMAIL_RE.match(email):
        raise CommandError("That email address does not look right")
    if len(password) < 8:
        raise CommandError("Password must be at least 8 characters")
    if len(name.strip()) < 2:
        raise CommandError("Name is too short")
    if db.scalar(select(User).where(User.email == email)):
        raise CommandError(f"{email} already has an account")
    user = User(name=name.strip(), email=email, phone=phone.strip(),
                password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    return user


def get_user(db, email):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user:
        raise CommandError(f"No account with email {email}")
    return user


def change_password(db, email, password):
    if len(password) < 8:
        raise CommandError("Password must be at least 8 characters")
    user = get_user(db, email)
    user.password_hash = hash_password(password)
    db.commit()
    return user


def set_active(db, email, active):
    user = get_user(db, email)
    if not active and user.role == "owner":
        owners = db.scalars(select(User).where(User.role == "owner", User.is_active)).all()
        if len(owners) <= 1:
            raise CommandError("That is the only active owner. Create another owner first.")
    user.is_active = active
    db.commit()
    return user


def set_role(db, email, role):
    if role not in ROLES:
        raise CommandError(f"Role must be one of {', '.join(ROLES)}")
    user = get_user(db, email)
    if user.role == "owner" and role != "owner":
        owners = db.scalars(select(User).where(User.role == "owner", User.is_active)).all()
        if len(owners) <= 1:
            raise CommandError("That is the only active owner. Create another owner first.")
    user.role = role
    db.commit()
    return user


# ---------------------------------------------------------------- prompts

def ask(label, given=None, secret=False):
    if given:
        return given
    if secret:
        return getpass.getpass(f"{label}: ")
    return input(f"{label}: ").strip()


def ask_password(given=None):
    if given:
        return given
    while True:
        first = getpass.getpass("Password: ")
        second = getpass.getpass("Password (again): ")
        if first == second:
            return first
        print("Passwords do not match, try again.")


# ---------------------------------------------------------------- commands

def cmd_create(args, role):
    with SessionLocal() as db:
        user = create_user(
            db,
            name=ask("Full name", args.name),
            email=ask("Email", args.email),
            phone=ask("Phone number", args.phone),
            password=ask_password(args.password),
            role=role,
        )
    print(f"Created {role}: {user.email}")


def cmd_list(args):
    with SessionLocal() as db:
        q = select(User).order_by(User.id)
        if args.role:
            q = q.where(User.role == args.role)
        users = db.scalars(q).all()
    print(f"{'ID':<5}{'ROLE':<10}{'ACTIVE':<8}{'EMAIL':<34}NAME")
    for u in users:
        print(f"{u.id:<5}{u.role:<10}{'yes' if u.is_active else 'NO':<8}{u.email:<34}{u.name}")
    print(f"\n{len(users)} user(s)")


def cmd_password(args):
    with SessionLocal() as db:
        change_password(db, args.email, ask_password(args.password))
    print("Password changed. Existing login tokens stay valid until they expire (12 hours).")


def cmd_toggle(args, active):
    with SessionLocal() as db:
        user = set_active(db, args.email, active)
    print(f"{user.email} is now {'enabled' if active else 'disabled'}")


def cmd_role(args):
    with SessionLocal() as db:
        user = set_role(db, args.email, args.role)
    print(f"{user.email} is now {user.role}")


def build_parser():
    p = argparse.ArgumentParser(description="Manage restaurant users")
    sub = p.add_subparsers(dest="command", required=True)

    for name, helptext in (("createowner", "Create a full-access owner"), ("createstaff", "Create a kitchen staff user")):
        c = sub.add_parser(name, help=helptext)
        for flag in ("name", "email", "phone", "password"):
            c.add_argument(f"--{flag}")

    c = sub.add_parser("listusers", help="List users")
    c.add_argument("--role", choices=ROLES)

    c = sub.add_parser("changepassword", help="Set a new password")
    c.add_argument("email")
    c.add_argument("--password")

    for name in ("disable", "enable"):
        sub.add_parser(name, help=f"{name.capitalize()} an account").add_argument("email")

    c = sub.add_parser("setrole", help="Change someone's role")
    c.add_argument("email")
    c.add_argument("role", choices=ROLES)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    Base.metadata.create_all(engine)
    try:
        {
            "createowner": lambda: cmd_create(args, "owner"),
            "createstaff": lambda: cmd_create(args, "staff"),
            "listusers": lambda: cmd_list(args),
            "changepassword": lambda: cmd_password(args),
            "disable": lambda: cmd_toggle(args, False),
            "enable": lambda: cmd_toggle(args, True),
            "setrole": lambda: cmd_role(args),
        }[args.command]()
    except CommandError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(130)


if __name__ == "__main__":
    main()
