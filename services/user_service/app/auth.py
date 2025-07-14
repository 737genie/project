import secrets
from typing import Optional
from passlib.context import CryptContext
from redis.asyncio import Redis

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SESSION_TTL_SECONDS = 3600 #세션 지속시간 (초 단위)

def verify_password(plain_password:str, hashed_password:str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password:str) -> str:
    return pwd_context.hash(password) #hash를 넣으면 객체를 알수없는 수로 바꿔줌(보안)

#로그아웃
async def delete_session(redis: Redis, session_id: str):
    await redis.delete(f"session:{session_id}")

#session은 redis로 다룸
#로그인 유지시간
async def create_session(redis: Redis, user_id: int) -> str: #user_id는 정해진 값 아님 아무렇게나 써도 ok
    session_id = secrets.token_hex(16) #16자리 난수 만들기 == 이걸 세션 id로 받겠다
    await redis.setex(f"session:{session_id}", SESSION_TTL_SECONDS, user_id) 
    #세션 아이디, 지속시간, 유저아이디를 redis에 저장 
    #> 지속시간 끝나면 데이터 사라짐
    return session_id

#redis에서 session id 조회
async def get_user_id_from_session(redis:Redis, session_id:str) -> Optional[int]:
    user_id = await redis.get(f"session:{session_id}")
    return user_id if user_id else None