from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from sqlmodel import Field, SQLModel

class ArticleImage(SQLModel, table=True):
  id: Optional[int] = Field(default=None, primary_key=True)
  image_filename: str
  article_id: Optional[int] = Field(default=None, index=True)


class BlogArticle(SQLModel, table=True):
  id: Optional[int] = Field(default=None, primary_key=True)
  title: str = Field(index=True)
  content: str
  create_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Seoul")))
  owner_id: int
  tags: Optional[str] = Field(default=None)