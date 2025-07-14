import os
from fastapi import FastAPI
from database import init_db, get_session
from sqlmodel import Field, SQLModel

from models import ArticleImage, BlogArticle

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await init_db()