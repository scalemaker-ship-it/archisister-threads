#!/usr/bin/env python3
"""건축언니(@u.nakim) 스레드 자동 게시 — 용도변경·건축 인허가 채널.

김유나 대표건축사(건창건축사무소, 용산구) / 유튜브 @archi.sister 콘텐츠를
스레드용으로 재구성한 글을 게시한다.

AI 자동생성을 쓰지 않는다. 미리 사람이 정리해둔 posts_queue.json에서
날짜(ordinal) 기준으로 순환 선택해 게시하므로 Anthropic API 크레딧이
전혀 들지 않는다. (구조는 0ra_marketing/threads_post.py와 동일)

발행 요일: 월·수·금만 (그 외 요일은 스크립트가 스스로 건너뜀).

흐름:
  월/수/금 확인 → pinned_post.json 오버라이드 확인 → 없으면 posts_queue.json에서
  순환 선택 → main 발행 → thread_chain 순차 이어쓰기(자기 답글) → first_comment 답글

환경변수(= GitHub Secrets):
  THREADS_USER_ID       Threads 사용자 ID
  THREADS_ACCESS_TOKEN  Threads 액세스 토큰
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
POST_WEEKDAYS = {1, 3, 5}  # 월=1 ... 일=7 (datetime.isoweekday 기준). 월/수/금만 게시.

THREADS_API = "https://graph.threads.net/v1.0"

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_QUEUE_PATH = os.path.join(_BASE_DIR, "posts_queue.json")
_PINNED_PATH = os.path.join(_BASE_DIR, "pinned_post.json")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"[오류] 환경변수 {name} 가 설정되지 않았습니다.")
    return value


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _all_text(post: dict) -> str:
    parts = [post.get("main", ""), post.get("first_comment", "")]
    parts.extend(post.get("thread_chain") or [])
    return "\n".join(p for p in parts if p)


def load_queue() -> list[dict]:
    """미리 써둔 글 큐(posts_queue.json)를 읽는다. Claude 호출 없음(크레딧 0)."""
    with open(_QUEUE_PATH, encoding="utf-8") as fp:
        data = json.load(fp)
    posts = data.get("posts", []) if isinstance(data, dict) else data
    if not posts:
        sys.exit("[오류] posts_queue.json 에 게시할 글이 없습니다.")
    for p in posts:
        p.setdefault("thread_chain", [])
        p.setdefault("first_comment", "")
    return posts


def load_pinned_post(today: str) -> dict | None:
    """레포 루트의 pinned_post.json 중 date(KST, YYYY-MM-DD)가 오늘과 같은 글이
    있으면 큐 대신 그 글을 그대로 게시한다. 날짜가 지나면 자동으로 큐로 복귀한다.

    파일은 단일 글({...})이거나, 여러 예약 글의 배열([{...}, {...}])일 수 있다.
    """
    if not os.path.exists(_PINNED_PATH):
        return None
    try:
        with open(_PINNED_PATH, encoding="utf-8") as fp:
            raw = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[경고] pinned_post.json 읽기 실패 → 큐로 진행: {exc}")
        return None
    candidates = raw if isinstance(raw, list) else [raw]
    for data in candidates:
        if data.get("date") != today:
            continue
        if not data.get("main"):
            print("[경고] pinned_post.json 의 오늘자 항목에 main 이 없어 큐로 진행합니다.")
            return None
        data.setdefault("thread_chain", [])
        data.setdefault("first_comment", "")
        return data
    return None


def _create_container(user_id: str, access_token: str, text: str,
                       reply_to_id: str | None = None,
                       image_url: str | None = None) -> str:
    if image_url:
        payload = {"media_type": "IMAGE", "image_url": image_url, "text": text,
                   "access_token": access_token}
    else:
        payload = {"media_type": "TEXT", "text": text, "access_token": access_token}
    if reply_to_id:
        payload["reply_to_id"] = reply_to_id
    resp = requests.post(f"{THREADS_API}/{user_id}/threads", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]


def _publish(user_id: str, access_token: str, creation_id: str) -> str:
    resp = requests.post(
        f"{THREADS_API}/{user_id}/threads_publish",
        json={"creation_id": creation_id, "access_token": access_token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def publish_one(user_id: str, access_token: str, text: str,
                 reply_to_id: str | None = None, wait: int = 30,
                 image_url: str | None = None) -> str:
    """컨테이너 생성 → 대기 → 발행. 게시물 ID 반환."""
    creation_id = _create_container(user_id, access_token, text, reply_to_id, image_url)
    time.sleep(wait)  # Threads 권장 대기
    return _publish(user_id, access_token, creation_id)


def post_to_threads(user_id: str, access_token: str, post: dict) -> str:
    """main → thread_chain(자기 답글 체인) → first_comment(답글) 순으로 게시.

    post에 image_url이 있으면 main 게시물에 이미지를 첨부한다.
    main 게시물 ID를 반환한다.
    """
    main_id = publish_one(user_id, access_token, post["main"],
                           image_url=post.get("image_url"))
    print(f"  main 게시 완료: {main_id}")

    prev_id = main_id
    for i, text in enumerate(post.get("thread_chain") or [], start=1):
        text = (text or "").strip()
        if not text:
            continue
        prev_id = publish_one(user_id, access_token, text, reply_to_id=prev_id)
        print(f"  이어쓰기 {i} 게시 완료: {prev_id}")

    first_comment = (post.get("first_comment") or "").strip()
    if first_comment:
        cid = publish_one(user_id, access_token, first_comment, reply_to_id=main_id)
        print(f"  첫 댓글 게시 완료: {cid}")

    return main_id


def main() -> None:
    # CHECK_TOKEN: 게시하지 않고 THREADS 토큰이 어느 계정에 물렸는지 확인(진단용).
    if _is_truthy(os.environ.get("CHECK_TOKEN")):
        uid = require_env("THREADS_USER_ID")
        tok = require_env("THREADS_ACCESS_TOKEN")
        r = requests.get(
            f"https://graph.threads.net/v1.0/{uid}",
            params={"fields": "username", "access_token": tok},
            timeout=30,
        )
        print(f"HTTP {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
        print(f"토큰 계정 = @{r.json().get('username')} (USER_ID={uid})")
        lst = requests.get(
            f"https://graph.threads.net/v1.0/{uid}/threads",
            params={"fields": "id,permalink,timestamp,text", "limit": 8, "access_token": tok},
            timeout=30,
        )
        print(f"[최근 글 목록] HTTP {lst.status_code}")
        for t in lst.json().get("data", []):
            print(f"  - {t.get('timestamp')} | {t.get('permalink')} | {(t.get('text') or '')[:30]}")
        return

    dry_run = _is_truthy(os.environ.get("DRY_RUN"))
    if dry_run:
        user_id = access_token = ""
        print("[DRY_RUN] 게시는 건너뛰고 오늘 나갈 글만 검증합니다.")
    else:
        user_id = require_env("THREADS_USER_ID")
        access_token = require_env("THREADS_ACCESS_TOKEN")

    now = datetime.now(KST)
    if now.isoweekday() not in POST_WEEKDAYS:
        print(f"오늘({now:%Y-%m-%d %A})은 게시일이 아닙니다(월/수/금만 게시). 종료합니다.")
        return

    pinned = load_pinned_post(f"{now:%Y-%m-%d}")
    if pinned is not None:
        print(f"[{now:%Y-%m-%d %H:%M KST}] 고정 글(pinned_post.json)을 게시합니다.")
        post = pinned
    else:
        queue = load_queue()
        idx = now.date().toordinal() % len(queue)
        post = queue[idx]
        print(f"[{now:%Y-%m-%d %H:%M KST}] 큐 글 {idx + 1}/{len(queue)} 게시(크레딧 미사용).")

    print("=== 게시될 글 ===")
    print(post["main"])
    if post.get("thread_chain"):
        for i, t in enumerate(post["thread_chain"], start=1):
            print(f"--- 이어쓰기 {i} ---\n{t}")
    if post.get("first_comment"):
        print(f"--- 첫 댓글 ---\n{post['first_comment']}")
    print("=================")

    if dry_run:
        print(f"[DRY_RUN] 본문 길이: {len(post['main'])}자")
        print("[DRY_RUN] 게시하지 않고 종료합니다.")
        return

    main_id = post_to_threads(user_id, access_token, post)
    print(f"게시 완료. 메인 Threads 게시물 ID: {main_id}")


if __name__ == "__main__":
    main()
