from datetime import datetime
from typing import Optional, List
from zoneinfo import ZoneInfo
from sqlmodel import Field, SQLModel

class PostImage(SQLModel, table=True):
  id: Optional[int] = Field(default=None, primary_key=True)
  image_filename: str
  post_id: Optional[int]=Field(default=None, index=True)
  
class Post(SQLModel, table=True):
  id: Optional[int] = Field(default=None, primary_key=True)
  title: str = Field(index=True)
  content: str
  create_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Seoul")))
  #timezone.utc
  owner_id: int
  tags: Optional[str] = Field(default=None)
  views: int = Field(default=0) # 조회수 필드 추가, 기본값은 0
  

class PostCreate(SQLModel):
    title: str
    content: str
    tags: Optional[str] = Field(default=None)

class PostUpdate(SQLModel):
    title: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    tags: Optional[str] = Field(default=None)

class PaginatedResponse(SQLModel):
  total: int
  page: int
  size: int
  pages: int
  items: List[dict] = []