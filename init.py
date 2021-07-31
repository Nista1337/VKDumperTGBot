# AIOGram imports
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# SQLAlchemy imports
from sqlalchemy import Column
from sqlalchemy import Integer, String, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import json

# Config loading
with open('telegram/config.json') as f:
    config = json.load(f)

with open('config.json') as f:
    parser_config = json.load(f)


# AIOGram initialization
storage = MemoryStorage()
bot = Bot(config['token'])
dp = Dispatcher(bot, storage=storage)

# SQLAlchemy initialization
Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    token = Column(String, nullable=False)
    limit = Column(Integer, nullable=False)
    group_attachments = Column(Boolean, nullable=False)
    type_users = Column(Boolean, nullable=False)
    type_chats = Column(Boolean, nullable=False)
    type_groups = Column(Boolean, nullable=False)


async def init_db():
    db_engine = create_async_engine("sqlite+aiosqlite:///db.sqlite", )

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(db_engine, class_=AsyncSession)
    db_session = async_session()
    await db_session.begin()
    return db_session, db_engine
