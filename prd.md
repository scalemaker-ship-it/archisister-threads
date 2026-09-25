# 건축언니(@archi.sister) 스레드 자동화 — PRD (단일 출처)

> 이 파일이 이 프로젝트의 **단일 출처**다. 규칙이 바뀌면 코드보다 먼저 여기를 고친다.
> 톤·문장 규칙은 `docs/글쓰기_가이드.md`, 저장소 사용법은 `README.md`.

## 1. 개요

| 항목 | 값 |
|---|---|
| 계정 | Threads [@archi.sister](https://www.threads.com/@archi.sister) |
| 인물 | 김유나 대표건축사 (건창건축사무소, 용산구) |
| 소재 원천 | 유튜브 [@archi.sister](https://www.youtube.com/@archi.sister) — 용도변경·건축 인허가 |
| 저장소 | `scalemaker-ship-it/archisister-threads` (public) |
| 로컬 | `~/Desktop/kim/건축언니스레드자동화` |
| 발행 | **월·수·금 20:00 KST**, 하루 1건 |
| 비용 | Claude API 미사용 (미리 작성한 큐에서 발행 → 크레딧 0) |

## 2. 발행 파이프라인

```
GitHub Actions 크론 (0 11 * * 1,3,5 = 20:00 KST)
  └ 0~30분 랜덤 지연 (자정 넘긴 지연 실행이면 생략)
      └ threads_post.py
          ├ 1. 발행일 판정        resolve_post_date()
          ├ 2. 중복 발행 차단      posted_log.json
          ├ 3. 글 선택            pinned_post.json > posts_queue.json
          └ 4. Threads API 게시    본문 → 이어쓰기(자기 답글) → 첫 댓글
              └ posted_log.json 갱신 후 워크플로가 커밋·푸시
```

### 2-1. 발행일 판정 규칙

1. **오늘(KST) 날짜가 `pinned_post.json` 에 예약돼 있으면 요일과 무관하게 발행**한다.
2. 예약이 없으면 월·수·금(`POST_WEEKDAYS = {1,3,5}`)에만 발행한다.
3. GitHub 크론은 몇 시간씩 밀린다. 밀려서 KST 자정을 넘겼어도 **12시간 유예**
   (`LATE_RUN_GRACE_HOURS`) 안이면 **전날(원래 발행일) 몫**으로 발행한다.
   → 2026-08-28(금) 누락이 이 규칙이 없어서 생긴 사고다.
4. `posted_log.json` 에 그 날짜가 이미 있으면 발행하지 않는다(중복 차단).

### 2-2. 글 구조

한 건 = **본문 1 + 이어쓰기 2~3 + 첫 댓글 1**. 이어쓰기는 자기 글에 다는 답글로
스레드를 잇고, 첫 댓글은 CTA(프로필 링크 유도)로 끝낸다.

```json
{
  "date": "2026-09-02",
  "image_url": "https://raw.githubusercontent.com/.../images/<video_id>.jpg",
  "image_note": "영상 내 자료 화면 캡처 (486초 지점)",
  "source_youtube": "https://www.youtube.com/watch?v=<video_id>",
  "main": "본문",
  "thread_chain": ["이어쓰기1", "이어쓰기2", "이어쓰기3"],
  "first_comment": "CTA 댓글"
}
```

`posts_queue.json` 은 같은 구조에서 `date`/이미지 필드가 빠진 형태이고,
`main()` 이 날짜 ordinal 로 순환 선택한다(현재 22편).

## 3. 이미지 규칙 ★

**썸네일을 쓰지 않는다.** 붙이는 이미지는 **영상 안의 자료 화면** —
도면(건축물대장 현황도·평면도), 비용표, 조건 체크리스트, 비교 인포그래픽 —
즉 그 한 장만 봐도 정보가 전달되는 화면이다. 얼굴만 나오는 토킹 컷은 쓰지 않는다.

호스팅은 **레포 `images/` 커밋 → raw.githubusercontent.com URL**.
Threads API 는 공개 접근 가능한 URL 을 요구하고, 레포가 public 이라 이걸로 충분하다.
파일명은 `<youtube_video_id>.jpg` 로 두어 출처를 파일명만으로 되짚을 수 있게 한다.

### 3-1. 캡처 절차 (`tools/capture_frames.py`)

```bash
python tools/capture_frames.py sheet <video_id>            # ① 30컷 컨택트시트
python tools/capture_frames.py peek  <video_id> 468 474 480 486   # ② 후보 좁히기
python tools/capture_frames.py grab  <video_id> 486        # ③ images/ 에 저장
git add images && git commit && git push                    # ④ raw URL 활성화
curl -sI <raw_url> | head -1                                # ⑤ 200 확인
```

②에서 **사람이 눈으로 프레임을 고르는 단계는 생략하지 않는다.** 자동으로 고르면
말하는 장면이나 전환 프레임이 잡힌다. 자막 한 줄이 하단에 걸리는 건 허용
(내용을 보조함). 영상 파일은 `/tmp/archisister-yt/` 에만 두고 레포에 넣지 않는다.

## 4. 예약 발행 작업 순서

1. 유튜브에서 소재 영상을 고르고 `posts_queue.json` 에서 주제가 맞는 글을 찾는다
   (없으면 `docs/글쓰기_가이드.md` §5 대로 새로 쓴다).
2. §3-1 로 자료 화면을 캡처한다.
3. `pinned_post.json` 에 `date` + `image_url` + 본문/이어쓰기/첫 댓글을 넣는다.
   날짜는 **월·수·금**으로 잡는다(예약은 요일을 무시할 수 있지만 기본 리듬을 지킨다).
4. 커밋·푸시. 크론이 그날 20시에 알아서 발행한다.
5. `DRY_RUN=1 python threads_post.py` 로 오늘 나갈 글을 검증할 수 있다.

## 5. 운영·진단

| 명령 | 용도 |
|---|---|
| `gh workflow run threads-weekly.yml --repo scalemaker-ship-it/archisister-threads` | 즉시 발행 |
| `... -f dry_run=true` | 게시 없이 오늘 글만 검증 |
| `... -f check_token=true` | 토큰이 물린 계정·최근 글 8건 확인 |
| `... -f report=true` | 최근 글 전체를 JSON 덤프(발행 보고서용) |
| `gh run list --repo scalemaker-ship-it/archisister-threads` | 실행 이력 |

- **토큰 만료**: `THREADS_ACCESS_TOKEN` 은 약 60일. 2026-08-16 발급 → **2026년 10월 중순 재발급**.
  절차는 오산/빵찌 자동화와 동일(Meta 앱 → 토큰 생성기 → `gh secret set`).
- **발행 보고서**: 노션 「건축언니(@archi.sister) 스레드 발행 보고서」
  (발행 날짜 / 주제 / 이미지 유무 / 링크). `report=true` 덤프로 갱신한다.
- 리포스트(재게시)는 계정 주인이 직접 하는 활동이라 자동화·보고서 집계에서 제외한다.

## 6. 파일 맵

```
threads_post.py                    발행 스크립트 (단일 파일)
posts_queue.json                   상시 큐 22편 (이미지 없음, 날짜 순환)
pinned_post.json                   날짜 예약 글 (이미지 포함, 큐보다 우선)
posted_log.json                    발행한 날짜 기록 (중복 차단, 워크플로가 커밋)
images/<video_id>.jpg              영상 자료 화면 캡처 (raw URL 호스팅)
tools/capture_frames.py            캡처 도구 (sheet / peek / grab)
docs/글쓰기_가이드.md              톤·CTA·새 글 작성 규칙
.github/workflows/threads-weekly.yml  크론 + 수동 실행 입력(dry_run/check_token/report)
```

## 7. 사실 관계 규칙 ★ (글에 틀린 제도 정보를 올리지 않는다)

큐·예약글을 새로 쓰거나 고칠 때 아래를 **먼저 확인**한다. 제도가 바뀌면 이 표를 먼저 고친다.

| 날짜 | 항목 | 현재 사실 | 글에서 지킬 것 |
|---|---|---|---|
| 2026-09-25 | **공유숙박 특례** (외도민이 안 나오는 건물을 특례로 숙박 운영하던 제도) | **신규 접수 막힘.** 김유나 대표 확인. 합법 숙박 루트는 **외국인관광 도시민박업(외도민)** 하나만 남음. 특례는 원래도 1년 내내가 아니라 **일부 기간만**(대표 추정 연중 약 1/3) 운영 가능하던 한시 제도 | 특례를 "1단계"·"시작 루트"·"먼저 연습하는 단계"로 **권하지 않는다.** 언급은 "예전엔 있었지만 지금은 막혔다 → 외도민으로" 로만. 연간 일수 등 **확정 안 된 숫자는 쓰지 않는다** |
| 2026-09-25 | **기존건축물 특례** (건축법, 2007년 이전 사용승인 건물) | 위와 **다른 제도**. 서울시가 각 구에 '적용 안 함' 공문 → 사실상 적용 불가 | 기존 글(큐 13번) 그대로 유효. 두 특례를 한 글에서 섞어 쓰지 않는다 |

- 2026-09-24 예약글(4단계 로드맵)은 "1단계 = 특례 운영"으로 **이미 발행됨** → 파일에는 정정본으로 바꿔 두었고 재사용 시 정정본을 쓴다.
- 대표(김유나) 카톡 확인이 이 표의 근거다. 새 정보가 오면 **큐 전체를 `grep`으로 훑어** 충돌하는 글을 같이 고친다.
