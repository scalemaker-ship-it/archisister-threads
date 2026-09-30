#!/usr/bin/env python3
"""건축언니(@archi.sister) 스레드 자동 게시 — 용도변경·건축 인허가 채널.

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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
POST_WEEKDAYS = {1, 3, 5}  # 월=1 ... 일=7 (datetime.isoweekday 기준). 기본은 월/수/금.
# pinned_post.json 에 날짜가 예약된 글은 요일과 무관하게 그 날 발행한다.

THREADS_API = "https://graph.threads.net/v1.0"

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_QUEUE_PATH = os.path.join(_BASE_DIR, "posts_queue.json")
_PINNED_PATH = os.path.join(_BASE_DIR, "pinned_post.json")
_POSTED_LOG_PATH = os.path.join(_BASE_DIR, "posted_log.json")

# GitHub 크론이 몇 시간씩 밀려 KST 날짜가 넘어가도, 이 시간 안이면
# "그 전날(원래 발행일) 몫"으로 인정해 발행한다.
LATE_RUN_GRACE_HOURS = 12


def load_posted_log() -> list[str]:
    """이미 발행한 날짜(KST, YYYY-MM-DD) 목록. 중복 발행 방지용."""
    if not os.path.exists(_POSTED_LOG_PATH):
        return []
    try:
        with open(_POSTED_LOG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[경고] posted_log.json 을 읽지 못했습니다({exc}). 빈 목록으로 진행합니다.")
        return []
    return data.get("posted_dates", []) if isinstance(data, dict) else []


def load_posted_queue() -> list[int]:
    """이미 발행한 큐 번호(1부터). 한 번 나간 글은 다시 발행하지 않는다(2026-09-30 사용자 지시)."""
    try:
        with open(_POSTED_LOG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return data.get("posted_queue", []) if isinstance(data, dict) else []


def record_posted(date_str: str, queue_no: int | None = None) -> None:
    dates = load_posted_log()
    if date_str not in dates:
        dates.append(date_str)
    done = load_posted_queue()
    if queue_no is not None and queue_no not in done:
        done.append(queue_no)
    with open(_POSTED_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"posted_dates": dates[-60:], "posted_queue": sorted(done)},
                  f, ensure_ascii=False, indent=2)
        f.write("\n")


def resolve_post_date(now: datetime) -> datetime | None:
    """발행 대상 날짜를 정한다.

    크론(11:00 UTC = 20:00 KST)이 밀려 자정을 넘겨 실행되는 일이 잦다.
    오늘이 발행 요일이 아니면, LATE_RUN_GRACE_HOURS 안쪽에서 전날이
    발행 요일이었는지 보고 그 날 몫으로 발행한다.
    """
    if now.isoweekday() in POST_WEEKDAYS:
        return now
    earlier = now - timedelta(hours=LATE_RUN_GRACE_HOURS)
    if earlier.isoweekday() in POST_WEEKDAYS and earlier.date() != now.date():
        print(f"[지연 실행] 크론이 밀려 {now:%Y-%m-%d %H:%M KST} 에 떴습니다. "
              f"{earlier:%Y-%m-%d %A} 몫으로 발행합니다.")
        return earlier
    return None


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


# 오타 차단 목록(틀린 표기 → 맞는 표기). 발행 전 전체 큐·예약글을 검사해
# 하나라도 걸리면 아무것도 게시하지 않고 실패한다(GitHub 실패 메일로 알림).
# 오타가 새로 발견되면 여기에 추가한다. (2026-09-05 "특내" 발행 사고 → 2026-09-30 도입)
KNOWN_TYPOS = {
    "특내": "특례", "특레": "특례", "특려": "특례", "특래": "특례", "틀례": "특례",
    "특혜": "특례",
    "이종근린": "제2종 근린", "일종근린": "제1종 근린",
    "외도미 ": "외도민 ", "외도빈": "외도민", "외도밈": "외도민",
    "용도번경": "용도변경", "용도변견": "용도변경",
    "건축물대창": "건축물대장", "이행강재금": "이행강제금",
    "호스탤": "호스텔",
}


def find_typos(post: dict) -> list[str]:
    text = _all_text(post)
    return [f"'{bad}' → '{good}'" for bad, good in KNOWN_TYPOS.items() if bad in text]


def check_all_typos() -> None:
    """큐 전체 + 예약글 전체를 검사. 오타가 있으면 종료 코드 1로 멈춘다."""
    posts = [("큐", i, p) for i, p in enumerate(load_queue(), start=1)]
    if os.path.exists(_PINNED_PATH):
        with open(_PINNED_PATH, encoding="utf-8") as fp:
            raw = json.load(fp)
        posts += [("예약", p.get("date"), p) for p in (raw if isinstance(raw, list) else [raw])]
    errors = [f"  {kind} {key}: {', '.join(hits)}"
              for kind, key, p in posts if (hits := find_typos(p))]
    if errors:
        sys.exit("[오류] 오타가 발견돼 게시하지 않습니다. 고친 뒤 다시 실행하세요.\n"
                 + "\n".join(errors))
    print(f"[오타 검사] 통과 ({len(posts)}편)")


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


def load_pinned_post(today: str, now: datetime | None = None) -> dict | None:
    """레포 루트의 pinned_post.json 중 date(KST, YYYY-MM-DD)가 오늘과 같은 글이
    있으면 큐 대신 그 글을 그대로 게시한다. 날짜가 지나면 자동으로 큐로 복귀한다.

    파일은 단일 글({...})이거나, 여러 예약 글의 배열([{...}, {...}])일 수 있다.

    항목에 "post_after": "HH:MM" (KST)가 있으면 그 시각 전에는 아직 아닌
    것으로 보고 건너뛴다. 저녁 크론이 자정을 넘겨 다음 날 새벽에 떴을 때
    다음 날 아침 예약 글이 먼저 나가버리는 것을 막는다.
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
        after = data.get("post_after")
        if after and now is not None:
            try:
                hh, mm = (int(x) for x in str(after).split(":"))
            except ValueError:
                print(f"[경고] post_after 값 '{after}' 을 읽지 못해 무시합니다.")
            else:
                if (now.hour, now.minute) < (hh, mm):
                    print(f"[대기] {today} 예약 글은 {after} KST 이후에 발행합니다"
                          f"(현재 {now:%H:%M} KST).")
                    continue
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

    # DELETE_IDS: 오타 등으로 잘못 나간 글 삭제(쉼표 구분 게시물 ID, 본문+본인 답글 모두 적는다).
    # 재발행 기능은 두지 않는다(2026-09-30 사용자 지시: 오타 글은 삭제만).
    delete_ids = [x.strip() for x in (os.environ.get("DELETE_IDS") or "").split(",") if x.strip()]
    if delete_ids:
        tok = require_env("THREADS_ACCESS_TOKEN")
        for mid in delete_ids:
            r = requests.delete(f"{THREADS_API}/{mid}", params={"access_token": tok}, timeout=30)
            print(f"  삭제 {mid}: {r.status_code} {r.text[:200]}")
            if not r.ok:
                sys.exit(f"[오류] {mid} 삭제 실패.")
        return

    # REPORT: 게시하지 않고 최근 글 목록을 JSON 으로 덤프(발행 보고서 작성용).
    if _is_truthy(os.environ.get("REPORT")):
        uid = require_env("THREADS_USER_ID")
        tok = require_env("THREADS_ACCESS_TOKEN")
        fields = "id,permalink,timestamp,text,media_type,media_url,shortcode,is_quote_post"
        url = f"https://graph.threads.net/v1.0/{uid}/threads"
        params = {"fields": fields, "limit": 100, "access_token": tok}
        rows: list[dict] = []
        while url and len(rows) < 300:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            body = r.json()
            rows.extend(body.get("data", []))
            url = (body.get("paging") or {}).get("next")
            params = None
        # 각 글의 인사이트(조회수·좋아요·댓글·리포스트·인용) — 리포스트는 제외.
        for row in rows:
            if row.get("media_type") == "REPOST_FACADE":
                continue
            try:
                ins = requests.get(
                    f"https://graph.threads.net/v1.0/{row['id']}/insights",
                    params={"metric": "views,likes,replies,reposts,quotes", "access_token": tok},
                    timeout=30,
                )
                if ins.ok:
                    row["insights"] = {
                        m.get("name"): (m.get("values") or [{}])[0].get("value")
                        for m in ins.json().get("data", [])
                    }
                else:
                    row["insights_error"] = ins.text[:200]
            except Exception as exc:  # noqa: BLE001
                row["insights_error"] = str(exc)[:200]
            # 이어쓰기·첫 댓글(본인 답글)까지 가져와 오타 검사에 쓴다.
            try:
                conv = requests.get(
                    f"{THREADS_API}/{row['id']}/conversation",
                    params={"fields": "id,text,username,timestamp", "access_token": tok},
                    timeout=30,
                )
                if conv.ok:
                    row["own_replies"] = [c for c in conv.json().get("data", [])
                                          if c.get("username") == "archi.sister"]
                else:
                    row["replies_error"] = conv.text[:200]
            except Exception as exc:  # noqa: BLE001
                row["replies_error"] = str(exc)[:200]
            all_text = "\n".join([row.get("text") or ""]
                                 + [c.get("text") or "" for c in row.get("own_replies", [])])
            if hits := find_typos({"main": all_text}):
                print(f"[발행글 오타] {row.get('permalink')} : {', '.join(hits)}")
        print("REPORT_JSON_BEGIN")
        print(json.dumps(rows, ensure_ascii=False))
        print("REPORT_JSON_END")
        return

    dry_run = _is_truthy(os.environ.get("DRY_RUN"))
    check_all_typos()
    if dry_run:
        user_id = access_token = ""
        print("[DRY_RUN] 게시는 건너뛰고 오늘 나갈 글만 검증합니다.")
    else:
        user_id = require_env("THREADS_USER_ID")
        access_token = require_env("THREADS_ACCESS_TOKEN")

    # pinned_post.json 에 오늘 날짜 글이 예약돼 있으면 요일과 무관하게 발행한다.
    # (월/수/금 외의 날에도 특정 글을 예약 발행하고 싶을 때 쓰는 경로)
    raw_now = datetime.now(KST)
    pinned = load_pinned_post(f"{raw_now:%Y-%m-%d}", raw_now)
    if pinned is not None:
        now = raw_now
    else:
        now = resolve_post_date(raw_now)
        if now is None:
            print(f"오늘({raw_now:%Y-%m-%d %A})은 게시일이 아닙니다"
                  f"(월/수/금 + pinned_post.json 예약일만 게시). 종료합니다.")
            return
        pinned = load_pinned_post(f"{now:%Y-%m-%d}", now)

    today = f"{now:%Y-%m-%d}"
    if not dry_run and today in load_posted_log():
        print(f"{today} 몫은 이미 발행했습니다(posted_log.json). 중복 발행하지 않고 종료합니다.")
        return

    if pinned is not None:
        print(f"[{now:%Y-%m-%d %H:%M KST}] 고정 글(pinned_post.json)을 게시합니다.")
        post = pinned
    else:
        queue = load_queue()
        done = set(load_posted_queue())
        start = now.date().toordinal() % len(queue)
        order = [(start + k) % len(queue) for k in range(len(queue))]
        fresh = [i for i in order if i + 1 not in done]
        if not fresh:
            sys.exit("[오류] 큐의 글이 모두 발행됐습니다. 이미 나간 글은 재발행하지 않으므로 "
                     "posts_queue.json 에 새 글을 추가해야 합니다.")
        idx = fresh[0]
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
    record_posted(today, None if pinned is not None else idx + 1)
    print(f"게시 완료. 메인 Threads 게시물 ID: {main_id}")


if __name__ == "__main__":
    main()
