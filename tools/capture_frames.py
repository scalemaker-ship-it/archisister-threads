#!/usr/bin/env python3
"""유튜브 영상에서 자료 화면(도면·비용표·비교표 등)을 캡처해 images/ 에 저장한다.

스레드 글에 붙일 이미지는 썸네일이 아니라 **영상 안의 자료 화면**을 쓴다.
(사람이 프레임을 눈으로 고르는 단계가 반드시 들어간다 — 3단계 참고)

사용법:
  # 1) 영상 받기 + 컨택트시트(30컷 그리드) 만들기
  python tools/capture_frames.py sheet <video_id>

  # 2) 그리드를 눈으로 보고 후보 구간을 좁혀 재확인 (초 단위, 여러 개)
  python tools/capture_frames.py peek <video_id> 468 474 480 486

  # 3) 최종 프레임을 images/<video_id>.jpg 로 추출
  python tools/capture_frames.py grab <video_id> 486

받은 영상은 캐시 디렉터리에만 두고 레포에는 커밋하지 않는다(이미지만 커밋).
"""

from __future__ import annotations

import os
import subprocess
import sys
import glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(BASE, "images")
CACHE = os.path.join("/tmp", "archisister-yt")

GRID_COLS, GRID_ROWS = 6, 5  # 컨택트시트 30컷


def _video_path(vid: str) -> str:
    hits = glob.glob(os.path.join(CACHE, f"{vid}.*"))
    hits = [h for h in hits if not h.endswith((".jpg", ".png"))]
    return hits[0] if hits else ""


def download(vid: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    path = _video_path(vid)
    if path:
        return path
    subprocess.run(
        ["yt-dlp", "-q", "-f", "bv*[height<=720]+ba/b[height<=720]",
         "-o", os.path.join(CACHE, f"{vid}.%(ext)s"),
         f"https://www.youtube.com/watch?v={vid}"],
        check=True,
    )
    return _video_path(vid)


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def sheet(vid: str) -> str:
    """영상 전체를 30컷 그리드 한 장으로 만든다. 좌→우, 위→아래 순서."""
    path = download(vid)
    n = GRID_COLS * GRID_ROWS
    interval = _duration(path) / n
    out = os.path.join(CACHE, f"grid_{vid}.jpg")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
         "-vf", f"fps=1/{interval},scale=320:-1,tile={GRID_COLS}x{GRID_ROWS}",
         "-frames:v", "1", out],
        check=True,
    )
    print(f"컨택트시트: {out}")
    print(f"간격 {interval:.1f}초 — n번째 칸(0부터)의 시각 = n × {interval:.1f}초")
    return out


def peek(vid: str, seconds: list[str]) -> str:
    """후보 시각들을 한 장에 모아 비교한다."""
    path = download(vid)
    tmp = []
    for i, sec in enumerate(seconds):
        f = os.path.join(CACHE, f"peek_{i:02d}.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(sec),
                        "-i", path, "-frames:v", "1", "-vf", "scale=480:-1", f],
                       check=True)
        tmp.append(f)
    cols = min(3, len(tmp))
    rows = (len(tmp) + cols - 1) // cols
    out = os.path.join(CACHE, f"peek_{vid}.jpg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-pattern_type", "glob",
                    "-i", os.path.join(CACHE, "peek_*.jpg"),
                    "-vf", f"tile={cols}x{rows}", "-frames:v", "1", out], check=True)
    for f in tmp:
        os.remove(f)
    print(f"후보 비교: {out}  (순서: {', '.join(map(str, seconds))}초)")
    return out


def grab(vid: str, second: str) -> str:
    """최종 프레임을 images/<vid>.jpg 로 저장(원본 해상도)."""
    path = download(vid)
    os.makedirs(IMAGES, exist_ok=True)
    out = os.path.join(IMAGES, f"{vid}.jpg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(second),
                    "-i", path, "-frames:v", "1", "-q:v", "2", out], check=True)
    print(f"저장: {out}  ({second}초 지점)")
    print("raw URL: https://raw.githubusercontent.com/scalemaker-ship-it/"
          f"archisister-threads/main/images/{vid}.jpg")
    print("→ images/ 를 커밋·푸시해야 스레드에서 이미지가 보입니다.")
    return out


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, vid, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    if cmd == "sheet":
        sheet(vid)
    elif cmd == "peek":
        if not rest:
            sys.exit("초 단위 후보 시각을 하나 이상 주세요.")
        peek(vid, rest)
    elif cmd == "grab":
        if not rest:
            sys.exit("추출할 시각(초)을 주세요.")
        grab(vid, rest[0])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
