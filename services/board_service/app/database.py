import os
from dotenv import load_dotenv
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL is None:
    raise ValueError("DATABASE_URL 환경 변수가 일치하지 않습니다.")
engine: AsyncEngine = create_async_engine(DATABASE_URL)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session():
    async with AsyncSession(engine) as session:
        yield session

        