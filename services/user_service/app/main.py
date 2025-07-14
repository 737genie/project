import os
import uuid
from typing import Annotated, Optional
from fastapi import FastAPI, status, Response, Depends, HTTPException, Cookie, UploadFile, File, Header
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from redis.asyncio import Redis

from database import init_db, get_session
from models import User, UserCreate, UserPublic, Userlogin, UserUpdate, UpdatePassword
from redis_client import get_redis
from auth import get_password_hash, create_session, verify_password, get_user_id_from_session, delete_session

app = FastAPI(title="User Service")

STATIC_DIR = "/app/static"
PROFILE_IMAGE_DIR = f"{STATIC_DIR}/profiles"
os.makedirs(PROFILE_IMAGE_DIR, exist_ok = True) #directory 없으면 만들어 ㅇㅇ
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def create_user_public(user: User) -> UserPublic:
    image_url = f"/static/profiles/{user.profile_image_filename}" if user.profile_image_filename else "https://www.gklibrarykor.com/wp-content/uploads/2024/08/1_%EA%B0%95%EC%95%84%EC%A7%80%EC%9D%98-%EC%8B%A0%EC%B2%B4%EC%A0%81-%ED%8A%B9%EC%A7%95.jpg"
    user_dict = user.model_dump() 
    user_dict["profile_image_url"] = image_url
    return UserPublic.model_validate(user_dict)

async def get_current_user_id(
        session_id: Annotated[str | None, Cookie()] = None,
        redis: Annotated[Redis, Depends(get_redis)] = None,
) -> int:
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id_str = await get_user_id_from_session(redis, session_id)
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Invalid session")
    return int(user_id_str)
    
@app.on_event("startup")
async def on_startup():
    await init_db()

@app.get("/")
def health_check():
    return {"status":"User service running"}


#-------------------------------------------------------------------------------
@app.post('/api/auth/register', response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(
    response: Response,
    user_data: UserCreate,
    session: Annotated[AsyncSession, Depends(get_session)], 
    redis: Annotated[Redis, Depends(get_redis)]
):
    statement = select(User).where(User.email==user_data.email)
    exist_user_result = await session.exec(statement)

    if exist_user_result.one_or_none(): #있거나말거나
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용중인 이메일 입니다.")
    
    hashed_password = get_password_hash(user_data.password)
    new_user = User.model_validate(user_data, update={"hashed_password": hashed_password}) 
    # model이랑 연결 - 입력받은 데이터를 column명대로 넣어줌

    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    session_id = await create_session(redis, new_user.id)
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=3600, path="/") 
    #httponly ... -->  보안
    #httponly :: 브라우저에서 쿠키를 못 건들게 하겠다~ 서버에서만 이용하겠다~~
    #Strict    Lax(도메인에 상관없이 값 전달해줌 근데 get 방식만)    None 

    return create_user_public(new_user)

@app.post("/api/auth/login")
async def login(
    response: Response,
    user_data: Userlogin,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)]
):
    statement = select(User).where(User.email==user_data.email)
    exist_user_result = await session.exec(statement)
    print(exist_user_result)


    user = exist_user_result.one_or_none()
    print(user)
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 맞지 않습니다.")
    
    session_id = await create_session(redis, user.id)
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=3600, path="/")  #쿠키먹이기ㅋㅋ
    return{"message":"log in 성공"}


@app.get("/api/auth/me", response_model=UserPublic)
async def get_current_user(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[Optional[str], Cookie()] = None,
):
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    user_id = await get_user_id_from_session(redis, session_id)

    if not user_id:
        response.delete_cookie("session_id", path="/")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found redis session")
    
    user = await session.get(User, int(user_id))

    if not user:
        response.delete_cookie("session_id", path="/")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    return create_user_public(user)

@app.post("/api/auth/logout")
async def logout(
    response: Response,
    redis: Annotated[Redis, Depends(get_redis)],
    session_id: Annotated[Optional[str], Cookie()] = None,
):
    if session_id:
        await delete_session(redis, session_id)
    response.delete_cookie("session_id", path="/")
    return {"message":"Logout 성공"}

@app.get("/api/users/{user_id}", response_model=UserPublic)
async def get_user_by_id(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)]
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return create_user_public(user)

#-------------------------------------------------------------------------------
@app.patch("/api/users/me", response_model=UserPublic)
async def update_my_profile(
    user_data: UserUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    # user_id: Annotated[int, Header(alias="X-User-ID")]
    user_id: Annotated[int, Depends(get_current_user_id)]
):
    db_user = await session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="There is no user.")
    
    update_data = user_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)

    await session.commit()
    await session.refresh(db_user)
    return create_user_public(db_user)
#-------------------------------------------------------------------------------
    
@app.post("/api/users/me/upload-image", response_model=UserPublic)
async def upload_my_profile_image(
    session: Annotated[AsyncSession, Depends(get_session)],
    # user_id : Annotated[int, Header(alias="X-User-ID")],
    user_id : Annotated[int, Depends(get_current_user_id)],
    file: UploadFile
):
    db_user = await session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="There is no user.")
    
    file_extension = os.path.splitext(file.filename)[1] #파일 이름 읽어오기
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(PROFILE_IMAGE_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    db_user.profile_image_filename = unique_filename
    await session.commit()
    await session.refresh(db_user)
    return create_user_public(db_user)
#-------------------------------------------------------------------------------

@app.post("/api/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    password_data: UpdatePassword,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    user_id: Annotated[int, Depends(get_current_user_id)] = None,
    session_id: Annotated[Optional[str], Cookie()] = None, #로그아웃시 제일 나중에 지워야함 session_id로 서버-브라우저연결
):
    db_user = await session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="There is no User")
    
    #script에 적은 변수명 current_password, new_password를 그대로 받음
    if not verify_password(password_data.current_password, db_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="비밀번호가 다릅니다.")
    
    #get_password_hash > auth에 만든 함수
    db_user.hashed_password = get_password_hash(password_data.new_password)
    await session.commit()

    #
    if session_id:
        await delete_session(redis, session_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
#-------------------------------------------------------------------------------
