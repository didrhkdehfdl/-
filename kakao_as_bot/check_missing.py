"""독립채산제 엑셀에서 접수된 건 중 빠진 칸을 찾아 빨간색으로 칠한다.

사용법:
  python check_missing.py              누락 칸을 빨간색으로 칠하고 목록 파일(누락목록_날짜.csv) 저장
  python check_missing.py --no-color   칠하지 않고 목록만 확인
  python check_missing.py --file 경로.xlsx   다른 엑셀 파일 검사

- 다시 실행하면, 예전에 빨간색으로 칠했던 칸 중 이제 채워진 칸은 색을 지운다.
- '-' 처럼 일부러 적어 둔 값은 채워진 것으로 본다.
- 접수한 지 얼마 안 된 건(grace_days 이내)은 처리 관련 칸을 아직 진행 중으로 보고 검사하지 않는다.
"""
import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl.utils import column_index_from_string as col_idx

import excel_writer
from excel_writer import FIELD_COLUMNS, WORKER_COLUMNS
from run import HERE, log, read_text_any

RED = (255, 0, 0)
COLUMNS = dict(FIELD_COLUMNS, 처리자=WORKER_COLUMNS[0])
DEFAULT_CHECK = {
    # 모든 접수 건에 있어야 하는 칸
    "required": ["처리일자", "요청자", "접수 내역", "조치 내역", "처리자"],
    # 처리일자·조치 내역·처리자 등 '처리 후' 칸 (최근 접수 건은 진행 중으로 보고 건너뜀)
    "after_done": ["처리일자", "조치 내역", "처리자", "유/무상", "매출액", "발행", "법인"],
    # 유/무상이 '유상' 이면 추가로 있어야 하는 칸
    "paid_required": ["매출액", "발행", "법인"],
    "grace_days": 7,
    # 유/무상 칸이 이 값이면 처리자(현장 방문자)를 검사하지 않음 (전화로 끝난 건 등)
    "no_worker_when": ["유선대응", "취소"],
    # 유/무상 칸이 이 값이면 처리 후 칸을 검사하지 않음
    "no_done_when": ["취소"],
}
# 이 칸 중 하나라도 있으면 '접수된 줄'로 본다
RECEIPT_MARKERS = ["분류", "접수일자", "발전소명", "고객명", "연락처", "주소", "접수 내역"]


def _empty(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def _as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--file", help="검사할 엑셀 파일 (기본: config.json 의 엑셀)")
    ap.add_argument("--no-color", action="store_true", help="칠하지 않고 목록만 만든다")
    ap.add_argument("--grace-days", type=int, help="최근 며칠 접수 건은 처리 칸 검사 제외 (기본 7)")
    args = ap.parse_args()

    config = json.loads(read_text_any(args.config))
    check = dict(DEFAULT_CHECK, **config.get("missing_check", {}))
    if args.grace_days is not None:
        check["grace_days"] = args.grace_days
    if args.file:
        config["excel_path"] = args.file
    path = excel_writer.resolve_excel_path(config)
    log(f"누락 확인 시작: {path} 「{config['sheet_name']}」")

    sh = excel_writer._Sheet(path, config["sheet_name"], config.get("header_row", 3), log)
    try:
        last = sh.last_used_row()
        first = sh.header_row + 1
        width = col_idx("AI")
        rows = sh.rows(first, last, 1, width)
        cutoff = date.today() - timedelta(days=check["grace_days"])

        def cell(row, field):
            if field == "처리자":  # 처리자 1~4 중 한 명이라도 있으면 채워진 것
                vals = [row[col_idx(x) - 1] for x in WORKER_COLUMNS]
                return next((v for v in vals if not _empty(v)), None)
            return row[col_idx(COLUMNS[field]) - 1]

        problems, red_cells, recolor = [], set(), []
        for i, row in enumerate(rows):
            r = first + i
            if all(_empty(cell(row, f)) for f in RECEIPT_MARKERS):
                continue  # 빈 줄
            received = _as_date(cell(row, "접수일자"))
            in_progress = (received is not None and received > cutoff
                           and _empty(cell(row, "처리일자")))
            paid = str(cell(row, "유/무상") or "").strip()
            need = list(check["required"])
            if paid == "유상":
                need += [f for f in check["paid_required"] if f not in need]
            if paid in check["no_worker_when"]:
                need = [f for f in need if f != "처리자"]
            if paid in check["no_done_when"]:
                need = [f for f in need if f not in check["after_done"]]
            missing = [f for f in need
                       if _empty(cell(row, f)) and not (in_progress and f in check["after_done"])]
            if missing:
                name = cell(row, "고객명") or cell(row, "발전소명") or ""
                problems.append({
                    "행": r,
                    "분류": cell(row, "분류") or "",
                    "접수일자": received.isoformat() if received else str(cell(row, "접수일자") or ""),
                    "요청자": cell(row, "요청자") or "",
                    "고객/발전소": str(name).replace("\n", " "),
                    "누락 항목": ", ".join(missing),
                })
                for f in missing:
                    red_cells.add((r, col_idx(COLUMNS[f])))

        if not args.no_color:
            # 1) 예전에 칠한 빨간 칸 중 이제 채워진 칸은 색 지우기
            check_cols = {col_idx(COLUMNS[f]) for f in
                          set(check["required"]) | set(check["paid_required"])}
            for i, row in enumerate(rows):
                r = first + i
                for c in check_cols:
                    if (r, c) not in red_cells and not _empty(row[c - 1]) and sh.get_color(r, c) == RED:
                        recolor.append((r, c))
            for r, c in recolor:
                sh.set_color(r, c, None)
            # 2) 빠진 칸 빨간색
            for r, c in sorted(red_cells):
                sh.set_color(r, c, RED)
            if red_cells or recolor:
                sh.save()
    finally:
        if sh.mode == "xlwings":
            sh.close()

    out = HERE / f"누락목록_{date.today():%Y%m%d}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["행", "분류", "접수일자", "요청자", "고객/발전소", "누락 항목"])
        w.writeheader()
        w.writerows(problems)

    counts = {}
    for p in problems:
        for m in p["누락 항목"].split(", "):
            counts[m] = counts.get(m, 0) + 1
    log(f"검사한 줄: {first}~{last}행 / 누락 있는 줄: {len(problems)}개")
    for k, v in sorted(counts.items(), key=lambda t: -t[1]):
        log(f"  - {k}: {v}건")
    for p in problems[:30]:
        log(f"  {p['행']}행 {p['접수일자']} {p['고객/발전소']} → {p['누락 항목']}")
    if len(problems) > 30:
        log(f"  ... 외 {len(problems) - 30}건 (전체 목록: {out.name})")
    if not args.no_color:
        log(f"빨간색으로 칠한 칸 {len(red_cells)}개, 채워져서 색을 지운 칸 {len(recolor)}개")
    log(f"누락 목록 파일: {out}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        log(f"[오류] {e}")
        traceback.print_exc()
        raise SystemExit(1)
