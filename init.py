# AIOGram imports
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# SQLAlchemy imports
from sqlalchemy import Column
from sqlalchemy import Integer, String, Boolean
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import json

# Config loading
with open('config.json') as f:
    config = json.load(f)

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


class Database:
    engine: AsyncEngine
    session: AsyncSession

    async def init_db(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///db.sqlite", )

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(self.engine, class_=AsyncSession)
        self.session = async_session()
        await self.session.begin()


db = Database()
