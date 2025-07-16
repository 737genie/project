import os
import math
import asyncio
import uuid
from typing import Annotated, List, Set, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, Query, status, UploadFile, File
from fastapi.staticfiles import StaticFiles
from sqlmodel import select, func, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
import httpx


from models import ArticleImage, BlogArticle, ArticleCreate, ArticleUpdate, PaginatedResponse
from database import init_db, get_session

app = FastAPI(title="Blog Service")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL")

STATIC_DIR = "/app/static"
IMAGE_DIR = f"{STATIC_DIR}/images"
os.makedirs(IMAGE_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
async def on_startup():
    await init_db()


@app.post("/api/blog/articles", response_model=BlogArticle, status_code=status.HTTP_201_CREATED)
async def create_article(
    article_data: ArticleCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")]
):
    """새로운 블로그 게시글을 생성합니다."""
    new_article = BlogArticle.model_validate(article_data, update={"owner_id": x_user_id})
    session.add(new_article)
    await session.commit()
    await session.refresh(new_article)
    return new_article


@app.post("/api/blog/articles/{article_id}/upload-images", response_model=List[str])
async def upload_article_images(
    article_id: int,
    files: List[UploadFile],
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")]
):
    db_article = await session.get(BlogArticle, article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    if db_article.owner_id != x_user_id:
        raise HTTPException(status_code=403, detail="Not Authorized")
    
    saved_filenames=[]
    for file in files:
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(IMAGE_DIR, unique_filename)

        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        new_image = ArticleImage(image_filename=unique_filename, article_id=article_id)
        session.add(new_image)
        saved_filenames.append(unique_filename)

    await session.commit()
    return saved_filenames

# 게시물 리스트 만들기

@app.get("/api/blog/articles/{article_id}")
async def get_article(article_id: int, session: Annotated[AsyncSession, Depends(get_session)]):
    #게시글 정보 가져오기
    article = await session.get(BlogArticle, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    # 조회수 증가 로직 추가!
    article.views += 1 # 조회수 1 증가
    session.add(article) # 변경 사항을 세션에 추가
    await session.commit() # 데이터베이스에 커밋
    await session.refresh(article) # 업데이트된 데이터로 article 객체 새로고침

    author_info = {}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{USER_SERVICE_URL}/api/users/{article.owner_id}")
            if resp.status_code == 200:
                author_info = resp.json()
    except Exception:
        author_info = {"username": "Unknown"}

    #별도의 쿼리) 불러온 게시글에 속한 이미지 파일명 가져오기
    image_query = select(ArticleImage.image_filename).where(ArticleImage.article_id == article_id)
    image_results = await session.exec(image_query)
    image_filenames = image_results.all()

    #가져온 파일명으로 전체 이미지 url 목록 생성 
    image_urls = [f"/static/images/{filename}" for filename in image_filenames]

    return {"article": article, "author": author_info, "image_urls": image_urls}

@app.get("/api/blog/articles", response_model=PaginatedResponse)
async def list_articles(
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(1, ge=1),
    size: int = Query(4, ge=1, le=100),
    owner_id: Optional[int] = None
):
    """블로그 게시글 목록을 페이지네이션하여 반환합니다."""
    offset = (page - 1) * size
    
    # 기본 쿼리
    count_query = select(func.count(BlogArticle.id))
    articles_query = select(BlogArticle).order_by(BlogArticle.id.desc())

    # owner_id가 주어지면 해당 사용자의 글만 필터링합니다.
    if owner_id:
        count_query = count_query.where(BlogArticle.owner_id == owner_id)
        articles_query = articles_query.where(BlogArticle.owner_id == owner_id)

    total_result = await session.exec(count_query)
    total = total_result.one()

    paginated_query = articles_query.offset(offset).limit(size)
    articles_result = await session.exec(paginated_query)
    articles = articles_result.all()

    # --- 작성자 및 썸네일 정보 가져오기 ---
    author_ids = {p.owner_id for p in articles}
    authors = {}
    if author_ids:
        try:
            async with httpx.AsyncClient() as client:
                tasks = [client.get(f"{USER_SERVICE_URL}/api/users/{uid}") for uid in author_ids]
                results = await asyncio.gather(*tasks)
                for resp in results:
                    if resp.status_code == 200:
                        data = resp.json()
                        authors[data['id']] = data.get('username', 'Unknown')
        except Exception as e:
            print(f"Error fetching authors: {e}")

    article_ids = [a.id for a in articles]
    thumbnails = {}
    if article_ids:
        image_query = select(ArticleImage).where(ArticleImage.article_id.in_(article_ids))
        image_results = await session.exec(image_query)
        for img in image_results.all():
            if img.article_id not in thumbnails:
                thumbnails[img.article_id] = f"/static/images/{img.image_filename}"

    # --- 최종 응답 데이터 조립 ---
    items_with_details = []
    for article in articles:
        article_dict = article.model_dump()
        article_dict["author_username"] = authors.get(article.owner_id, "Unknown")
        article_dict["image_url"] = thumbnails.get(article.id) # 썸네일 URL 추가
        items_with_details.append(article_dict)
        
    return PaginatedResponse(
        total=total, page=page, size=size,
        pages=math.ceil(total / size), items=items_with_details
    )
#--------------------------------------------------------
@app.get("/api/blog/tags", response_model=List[str])
async def get_all_tags(session: Annotated[AsyncSession, Depends(get_session)]):
    #모든 게시물의 태그를 수집하여 중복 없이 반환
    query = select(BlogArticle.tags).where(BlogArticle.tags != None)
    results = await session.exec(query)
    all_tags: Set[str] = set() #중복 제외
    for tags_str in results.all():
        tags=[tag.strip() for tag in tags_str.split(',') if tag.strip()] #공백제거 공백은 태그에 포함 안 시킴
        all_tags.update(tags)
    return sorted(list(all_tags))
#--------------------------------------------------------
@app.patch("/api/blog/articles/{article_id}", response_model = BlogArticle)
async def update_article(
    article_id: int,
    article_data: ArticleUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")]
):
    db_article = await session.get(BlogArticle, article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    if db_article.owner_id != x_user_id:
        raise HTTPException(status_code=403, detial="Not authorized")
    
    update_data = article_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_article, key, value)

    await session.commit()
    await session.refresh(db_article)
    return db_article


@app.delete("/api/blog/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(
    article_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[int, Header(alias="X-User-Id")],
):
    db_article = await session.get(BlogArticle, article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    if db_article.owner_id != x_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    image_query = select(ArticleImage).where(ArticleImage.article_id == article_id)
    images_to_delete = (await session.exec(image_query)).all()
    for image in images_to_delete:
        file_path = os.path.join(IMAGE_DIR, image.image_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        await session.delete(image)

    await session.delete(db_article)
    await session.commit()
    return


#--------------------------------------------------------
@app.get("/api/blog/popular-articles", response_model=List[dict])
async def get_popular_articles(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(5, ge=1, le=10) # 기본 5개, 최대 10개까지 가져올 수 있도록 제한
):
    """
    조회수가 높은 순서대로 인기 게시글을 반환합니다.
    """
    articles_query = select(BlogArticle).order_by(BlogArticle.views.desc()).limit(limit)
    articles_result = await session.exec(articles_query)
    articles = articles_result.all()

    # 작성자 정보 가져오기 (기존 list_articles 로직과 유사)
    author_ids = {p.owner_id for p in articles}
    authors = {}
    if author_ids:
        try:
            async with httpx.AsyncClient() as client:
                tasks = [client.get(f"{USER_SERVICE_URL}/api/users/{uid}") for uid in author_ids]
                results = await asyncio.gather(*tasks)
                for resp in results:
                    if resp.status_code == 200:
                        data = resp.json()
                        authors[data['id']] = data.get('username', 'Unknown')
        except Exception as e:
            print(f"Error fetching authors for popular posts: {e}")

    popular_items = []
    for article in articles:
        popular_items.append({
            "id": article.id,
            "title": article.title,
            "owner_id": article.owner_id,
            "author_username": authors.get(article.owner_id, "Unknown"),
            "views": article.views
        })
    
    return popular_items



#--------------------------------------------------------
# --- 모든 블로그 게시글 가져오기 (GET) 엔드포인트 추가 ---
# @app.get("/api/blog/articles", response_model=List[BlogArticle])
# async def get_all_blog_articles(
#     session: Annotated[AsyncSession, Depends(get_session)]
# ):
#     """
#     모든 블로그 게시글 목록을 조회합니다.
#     """
#     result = await session.execute(select(BlogArticle))
#     articles = result.scalars().all()
#     return articles