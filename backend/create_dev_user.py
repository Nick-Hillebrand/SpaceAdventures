#!/usr/bin/env python3
"""Create a pre-verified dev test user in the local SQLite database.

Usage (from the backend/ directory with venv active):
    python create_dev_user.py
    python create_dev_user.py --email dev@local.test --password changeme
"""
import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.user import User
from app.services.auth_service import hash_password

DATABASE_URL = "sqlite+aiosqlite:///./data/app.db"

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def main(email: str, password: str, first: str, last: str) -> None:
    async with SessionLocal() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing:
            print(f"User {email!r} already exists (id={existing.id}). Nothing created.")
            return

        user = User(
            first_name=first,
            last_name=last,
            email=email,
            password_hash=hash_password(password),
            email_verified=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    print(f"Created dev user (id={user.id}):")
    print(f"  Email:    {email}")
    print(f"  Password: {password}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a dev test user")
    parser.add_argument("--email", default="dev@local.test")
    parser.add_argument("--password", default="devpassword123")
    parser.add_argument("--first", default="Dev")
    parser.add_argument("--last", default="User")
    args = parser.parse_args()

    asyncio.run(main(args.email, args.password, args.first, args.last))
    sys.exit(0)
