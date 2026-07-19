import aiogram
from sqlalchemy import select, insert
from models.users import Users

async def check_exists(session, user: aiogram.types.User | None) -> Users:
    user_id = user.id
    data = (await session.execute(
        select(Users).where(Users.user_id == user_id)
    )).scalar_one_or_none()

    if not data:
        await session.execute(insert(Users).values(user_id=user_id, lang=user.language_code))
        await session.commit()
        data = (await session.execute(
            select(Users).where(Users.user_id == user_id)
        )).scalar_one()

    return data

