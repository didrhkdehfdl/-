"""카카오톡 방 → 엑셀 자동 정리. 작업 스케줄러가 1시간마다 이 파일을 실행한다.

사용법:
  python run.py                      지정한 카톡방 하나만 읽어 새 접수/처리 건을 엑셀에 반영
  python run.py --file 대화.txt       '대화 내보내기' txt 파일로 처리
  python run.py --file 대화.txt --dry-run   엑셀에 쓰지 않고 결과만 출력
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

VERSION = "2026-11-23"
HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "state.json"
LOG_FILE = HERE / "run.log"


def log(msg):
    """화면과 run.log 에 함께 기록."""
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"seen": []}


def save_state(state):
    state["seen"] = state["seen"][-5000:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    log(f"프로그램 시작 (버전 {VERSION}, 폴더 {HERE})")
    import chat_parser
    import excel_writer
    import extractor

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--file", help="카톡 '대화 내보내기' txt 파일")
    ap.add_argument("--dry-run", action="store_true", help="엑셀에 쓰지 않고 결과만 출력")
    ap.add_argument("--out", help="(테스트용) 결과를 다른 엑셀 파일로 저장")
    ap.add_argument("--reset", action="store_true", help="처리 기록을 지우고 처음부터 다시 처리")
    args = ap.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    state = {"seen": []} if args.reset else load_state()
    state.setdefault("rooms", [])
    seen = set(state["seen"])

    # 읽을 방 목록: room_names(여러 개) 또는 예전 설정 room_name(한 개)
    rooms = config.get("room_names") or [config["room_name"]]
    since = config.get("process_since")
    cutoff = datetime.fromisoformat(since) if since else None

    new, read_keys = [], []
    if args.file:
        sources = [("파일", lambda: Path(args.file).read_text(encoding="utf-8-sig"))]
    else:
        import kakao_reader
        sources = [(room, lambda room=room: kakao_reader.read_room_text(room)) for room in rooms]

    for room, read in sources:
        try:
            messages = chat_parser.parse(read())
        except Exception as e:  # 한 방이 안 열려도 다른 방은 계속 처리
            log(f"[오류] '{room}' 방 읽기 실패: {e}")
            continue
        room_new = [m for m in messages if m.key not in seen]
        log(f"'{room}': 메시지 {len(messages)}개 중 새 메시지 {len(room_new)}개")

        # 처음 읽는 방은 쌓여 있던 예전 글을 넣지 않고 '처리됨'으로만 기록
        known = (room in state["rooms"] or len(room_new) < len(messages)
                 or (state["seen"] and not state["rooms"] and room == config.get("room_name")))
        if not args.file and room not in state["rooms"]:
            state["rooms"].append(room)
        if cutoff:
            room_new = [m for m in room_new if m.sent_at >= cutoff]
        elif not known and not args.file:
            log(f"'{room}' 첫 실행: 지금까지의 글은 '처리됨'으로 기록만 하고, 다음 실행부터 새 글을 정리합니다.")
            state["seen"] += [m.key for m in messages]
            seen.update(m.key for m in messages)
            continue
        new += room_new
        read_keys += [m.key for m in room_new]
        seen.update(m.key for m in room_new)  # 두 방에 같은 글이 있으면 한 번만

    new.sort(key=lambda m: m.sent_at)
    records = extractor.extract(new, config, log=log)
    n_recv = sum(r["kind"] == "접수" for r in records)
    log(f"접수 {n_recv}건, 처리 {len(records) - n_recv}건 발견")

    if args.dry_run:
        for r in records:
            fields = {k: (v if isinstance(v, list) else str(v)) for k, v in r["fields"].items()}
            print(json.dumps({"종류": r["kind"], "보낸글": r["_source"], **fields}, ensure_ascii=False, indent=1))
        return

    changed = excel_writer.apply_records(records, config, out_path=args.out, log=log)
    log(f"엑셀 반영 완료 ({changed}건)")
    state["seen"] += read_keys
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        log(f"[오류] {e}")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
        sys.exit(1)
