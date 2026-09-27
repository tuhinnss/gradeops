"""Provision a user account (the only way to create a professor).

Usage:
    python -m scripts.create_user --email prof@uni.edu --name "Dr. Sharma" --role professor
    python -m scripts.create_user --email ta@uni.edu --role ta --password '…'
    python -m scripts.create_user --email prof@uni.edu --reset-password
    python -m scripts.create_user --email ta@uni.edu --deactivate

The password is prompted for when not given. Run against the database in
DATABASE_URL (after `alembic upgrade head`).
"""

import argparse
import asyncio
import getpass
import sys

from app.core.security import hash_password
from app.db import crud
from app.db.models import UserRole
from app.db.session import async_session_factory, engine


def _password(given: str | None) -> str:
    if given:
        pw = given
    else:
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match")
    if len(pw) < 8:
        sys.exit("Password must be at least 8 characters")
    return pw


async def main(args: argparse.Namespace) -> None:
    async with async_session_factory() as session:
        user = await crud.get_user_by_email(session, args.email)
        if args.deactivate or args.reset_password:
            if not user:
                sys.exit(f"No user {args.email}")
            if args.deactivate:
                user.is_active = False
            if args.reset_password:
                user.hashed_password = hash_password(_password(args.password))
            await session.commit()
            print(f"Updated {user.email}")
            return
        if user:
            sys.exit(f"{args.email} already exists (role {user.role.value}); use --reset-password")
        user = await crud.create_user(
            session,
            email=args.email,
            hashed_password=hash_password(_password(args.password)),
            full_name=args.name or args.email.split("@")[0],
            role=UserRole(args.role),
        )
        await session.commit()
        print(f"Created {user.role.value} {user.email} ({user.id})")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name")
    parser.add_argument("--role", choices=[r.value for r in UserRole], default="professor")
    parser.add_argument("--password", help="Prompted if omitted (preferred: keeps it out of shell history)")
    parser.add_argument("--reset-password", action="store_true")
    parser.add_argument("--deactivate", action="store_true")
    asyncio.run(main(parser.parse_args()))
