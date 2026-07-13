import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    user = User(**payload.model_dump())
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # SQLAlchemy's asyncpg dialect wraps the real driver exception and only
        # copies pgcode/sqlstate onto it; the original (with .constraint_name,
        # .message) is chained as __cause__.
        cause = exc.orig.__cause__ if exc.orig is not None else None
        constraint = getattr(cause, "constraint_name", None)
        if constraint == "users_email_key":
            raise HTTPException(status_code=409, detail="email already registered")
        detail = getattr(cause, "message", None) or str(exc.orig)
        raise HTTPException(status_code=422, detail=detail)
    await db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.get("", response_model=list[UserOut])
async def list_users(
    limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)
) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at).limit(limit).offset(offset))
    return list(result.scalars().all())


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, payload: UserUpdate, db: AsyncSession = Depends(get_db)
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user
