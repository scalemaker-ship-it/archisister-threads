# 건축언니(@archi.sister) 스레드 자동화

**용도변경·건축 인허가** 실전 정보를 **존댓말 정보형**으로 **월/수/금** 발행하는 자동화입니다.

> 유튜브 [건축언니(@archi.sister)](https://www.youtube.com/@archi.sister) 와 동일한 인물
> — **김유나 대표건축사, 건창건축사무소(용산구)** — 의 스레드 계정입니다.
> 오산·빵찌·이슬·0ra 자동화와 **완전히 분리된 별도 저장소·Meta 앱·계정**입니다.

> **규격 단일 출처는 [`prd.md`](prd.md)** 입니다. 발행 규칙·이미지 규칙·예약 절차가
> 바뀌면 코드보다 먼저 `prd.md` 를 고칩니다.

## 구조

| 파일 | 역할 |
|---|---|
| `prd.md` | **단일 출처** — 발행 파이프라인·이미지 규칙·예약 절차·운영 명령 |
| `threads_post.py` | 월/수/금 확인 → 날짜 시드로 큐에서 글 순환 선택 → Threads 게시 |
| `posts_queue.json` | **미리 정리해둔 글 21편.** AI 호출 없음 → **Anthropic 크레딧 0원** |
| `pinned_post.json` | 날짜 예약 글. 큐보다 우선하고, **예약일은 요일과 무관하게 발행** |
| `posted_log.json` | 발행한 날짜 기록 → 같은 날 중복 발행 차단 (워크플로가 커밋) |
| `images/<video_id>.jpg` | 영상 **자료 화면** 캡처. raw URL 로 호스팅해 글에 첨부 |
| `tools/capture_frames.py` | 캡처 도구 — `sheet` → `peek` → `grab` 3단계 |
| `.github/workflows/threads-weekly.yml` | 월/수/금 저녁 크론, 랜덤 지연 포함 |
| `docs/글쓰기_가이드.md` | 톤·구조·CTA 규칙, 새 영상 추가하는 법 |
| `requirements.txt` | requests |

### 발행 스케줄 — 월/수/금 (한 달 약 13건 → 목표 "월 10건 이상" 충족)

| 크론(UTC) | 목표 게시(KST) |
|---|---|
| `0 11 * * 1,3,5` | 20:00 + 랜덤 0~30분 → **20:00~20:30** |

크론이 밀려 KST 자정을 넘겨 실행돼도 **12시간 유예** 안이면 전날(원래 발행일) 몫으로
발행합니다. 자세한 판정 규칙은 `prd.md` §2-1.

### 콘텐츠 원천

`docs/글쓰기_가이드.md` 참고. 유튜브 @archi.sister 영상 22편(자막·설명란)을
바탕으로, 표절 없이 새로 재구성한 21편이 `posts_queue.json` 에 채워져 있습니다.
용도변경 비용, 호스텔/외도민/고시원 조건, 위반건축물 양성화 특별법, 주차대수,
창문 차폐, 실제 수익 사례 등 채널의 핵심 소재를 골고루 담았습니다.

**새 영상이 올라오면** → `docs/글쓰기_가이드.md` §5 절차대로 `posts_queue.json`
끝에 새 글을 추가하면 됩니다(Claude 호출 없이 사람이 직접 정리).

### CTA — 프로필 링크 유도만

본문·이어쓰기에는 raw URL이나 카카오톡 링크를 넣지 않고, 첫 댓글에서
**"프로필 링크"로만 담백하게 유도**합니다. 실제 문의 채널(홈페이지 등)은
**@archi.sister 계정 바이오**에 걸어두세요.

## 로컬 미리보기 (게시 없이 글만 확인)

```bash
pip install -r requirements.txt
python threads_post.py --dry-run   # 토큰 불필요. 오늘 요일 기준으로 검증
```

(월/수/금이 아닌 날엔 "게시일이 아닙니다"로 정상 종료됩니다.)

## 현재 상태 — 세팅 진행 중

| 항목 | 상태 |
|---|---|
| 코드·워크플로우·문서 | ✅ |
| 글 큐 21편 (dry-run 검증) | ✅ |
| GitHub 저장소 | ⏳ 이 대화에서 생성 예정 |
| Meta 앱 (Threads API) | ⏳ **미생성 — 아래 절차대로 신규 생성 필요** |
| `THREADS_USER_ID` / `THREADS_ACCESS_TOKEN` 시크릿 | ⏳ 미등록 |
| 실제 첫 발행 | ⏳ 위 항목들 완료 후 다음 월/수/금 크론에 자동, 또는 수동 트리거 |

### 다음에 해야 할 일 — Meta 앱 신규 생성 (사람이 해야 하는 부분)

이 계정은 지금까지 스레드 자동화를 한 적이 없어서, **Meta 개발자 앱을 새로
만들고 Threads API 접근 권한을 받아야** 합니다. (이슬/빵찌 자동화 때와 동일한 절차.)

1. [developers.facebook.com/apps](https://developers.facebook.com/apps) 에서
   새 앱 생성 (예: 앱 이름 `건축언니_자동화`).
2. 앱에 **Threads API** 제품(Use Case) 추가.
3. **Threads 테스터**로 `@archi.sister` 계정을 등록 → 해당 계정으로 로그인해서
   테스터 초대를 **수락**해야 합니다(앱 대시보드 또는 Threads 앱 내 알림).
4. 권한 범위: `threads_basic` + `threads_content_publish`.
5. 앱 설정 → 이용 사례 → Threads API 액세스 → 설정 페이지 맨 아래
   **사용자 토큰 생성기**로 장기 액세스 토큰 발급.
   (팝업이라 브라우저 자동화가 막히면, 팝업 URL을 가로채 같은 탭에서 열고
   콜백 페이지 HTML에서 토큰을 추출하는 방식 — 다른 계정들과 동일한 우회 절차.)
6. USER_ID 확인 후 GitHub Secrets 등록:
   ```bash
   curl -s "https://graph.threads.net/v1.0/me?fields=id,username&access_token=<토큰>"
   gh secret set THREADS_USER_ID --repo scalemaker-ship-it/archisister-threads
   gh secret set THREADS_ACCESS_TOKEN --repo scalemaker-ship-it/archisister-threads
   ```

> ⚠️ Threads 토큰은 발급 후 약 60일 뒤 만료됩니다. 만료되면 5~6단계를 반복하세요.

Meta 앱 생성·테스터 수락은 브라우저에서 `@archi.sister` 계정 로그인 상태가 필요해서
사람이 직접 하거나, 로그인 세션이 준비되면 브라우저 자동화로 도와드릴 수 있습니다.
