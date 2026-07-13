import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Address, User
from app.schemas import AddressCreate, AddressOut

router = APIRouter(prefix="/users/{user_id}/addresses", tags=["addresses"])


async def _get_user_or_404(user_id: uuid.UUID, db: AsyncSession) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.post("", response_model=AddressOut, status_code=201)
async def create_address(
    user_id: uuid.UUID, payload: AddressCreate, db: AsyncSession = Depends(get_db)
) -> Address:
    await _get_user_or_404(user_id, db)

    if payload.is_default:
        await db.execute(
            update(Address).where(Address.user_id == user_id, Address.is_default.is_(True)).values(is_default=False)
        )

    address = Address(user_id=user_id, **payload.model_dump())
    db.add(address)
    await db.flush()

    if payload.is_default:
        user = await db.get(User, user_id)
        user.default_shipping_address_id = address.id

    await db.commit()
    await db.refresh(address)
    return address


@router.get("", response_model=list[AddressOut])
async def list_addresses(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[Address]:
    await _get_user_or_404(user_id, db)
    result = await db.execute(
        select(Address).where(Address.user_id == user_id).order_by(Address.created_at)
    )
    return list(result.scalars().all())


@router.post("/{address_id}/set-default", response_model=AddressOut)
async def set_default_address(
    user_id: uuid.UUID, address_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Address:
    await _get_user_or_404(user_id, db)
    address = await db.get(Address, address_id)
    if address is None or address.user_id != user_id:
        raise HTTPException(status_code=404, detail="address not found")

    await db.execute(
        update(Address).where(Address.user_id == user_id, Address.is_default.is_(True)).values(is_default=False)
    )
    address.is_default = True

    user = await db.get(User, user_id)
    user.default_shipping_address_id = address.id

    await db.commit()
    await db.refresh(address)
    return address
