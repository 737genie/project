import asyncio
import os
import sys
import logging
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
import redis.asyncio as redis

from models import Post

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='--- [Worker] %(message)s')

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_async_engine(DATABASE_URL)
REDIS_URL = os.getenv("REDIS_URL")

async def sync_redis_to_mysql():
  logging.info("조회수 동기화 작업 시작")

  redis_client = None
  try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    logging.info("Redis 클라이언트 생성 완료")
    
    post_ids_to_sync = await redis_client.zrange("view_sync_queue", 0, -1)
    if not post_ids_to_sync:
      logging.info("동기화할 게시물이 없습니다.")
      return
    
    logging.info(f"{len(post_ids_to_sync)}개의 동기화 대상 발견: {post_ids_to_sync}")

    updates_to_commit = []
    for post_id_str in post_ids_to_sync:
      post_id = int(post_id_str)
      redis_key = f"views:post:{post_id}"
      view_count_str = await redis_client.get(redis_key)

      if view_count_str:
        updates_to_commit.append({"id": post_id, "views": int(view_count_str)})
        logging.info(f"Post ID {post_id}의 조회수 {view_count_str}를 업데이트 목록에 추가")

    if updates_to_commit:
      async with AsyncSession(engine) as session:
        logging.info("DB 세션 시작")
        for update in updates_to_commit:
          db_post = await session.get(Post, update["id"])
          if db_post:
            db_post.views = update["views"]

        logging.info(f"{len(updates_to_commit)}개의 업데이트를 DB에 커밋합니다...")
        await session.commit()
        logging.info("DB 커밋 완료.")

    await redis_client.zrem("view_sync_queue", *post_ids_to_sync)
    logging.info(f"{len(post_ids_to_sync)}개 작업 큐에서 제거 완료")

  except Exception as e:
    logging.error(f"동기화 중 심각한 오류 발생: {e}", exc_info=True)
  
  finally:
    if redis_client:
      await redis_client.aclose()
      logging.info("Redis 연결 종료")

async def main():
  scheduler = AsyncIOScheduler()
  scheduler.add_job(sync_redis_to_mysql, 'interval', minutes=1, id="sync_job", misfire_grace_time=10, coalesce=True, max_instances=1)
  scheduler.start()
  logging.info("백그라운드 워커 시작. 1분마다 조회수를 동기화합니다. (Ctrl+C로 종료)")

  try:
    while True:
      await asyncio.sleep(1)
  except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()

if __name__ == "__main__":
  asyncio.run(main())
  