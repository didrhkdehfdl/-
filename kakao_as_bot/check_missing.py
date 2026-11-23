"""독립채산제 엑셀에서 접수된 건 중 빠진 칸을 찾아 빨간색으로 칠한다.

사용법:
  python check_missing.py              누락 칸을 빨간색으로 칠하고 목록 파일(누락목록_날짜.xlsx) 저장
  python check_missing.py --no-color   칠하지 않고 목록만 확인
  python check_missing.py --file 경로.xlsx   다른 엑셀 파일 검사

- 다시 실행하면, 예전에 빨간색으로 칠했던 칸 중 이제 채워진 칸은 색을 지운다.
- '-' 처럼 일부러 적어 둔 값은 채워진 것으로 본다.
- 접수한 지 얼마 안 된 건(grace_days 이내)은 처리 관련 칸을 아직 진행 중으로 보고 검사하지 않는다.
"""
import argparse
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


FIELDS = ["행", "분류", "접수일자", "요청자", "고객/발전소", "누락 항목"]


def write_report(problems, counts, check, path, first, last):
    """누락목록_날짜.xlsx : 「요약」 시트(항목별 건수) + 「누락목록」 시트(첫 행 틀 고정)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    head_fill = PatternFill("solid", fgColor="404040")
    head_font = Font(bold=True, color="FFFFFF")
    thin = Side(style="thin", color="BFBFBF")
    border = Border(top=thin, bottom=thin, left=thin, right=thin)
    center = Alignment(horizontal="center", vertical="center")

    wb = Workbook()

    # ---- 요약
    ws = wb.active
    ws.title = "요약"
    ws["B2"] = "누락 확인 요약"
    ws["B2"].font = Font(bold=True, size=14)
    info = [("검사 파일", Path(path).name), ("검사 일시", f"{datetime.now():%Y-%m-%d %H:%M}"),
            ("검사 범위", f"{first}~{last}행"), ("누락 있는 줄", f"{len(problems)}개")]
    for i, (k, v) in enumerate(info):
        ws.cell(4 + i, 2, k).font = Font(bold=True)
        ws.cell(4 + i, 3, v)
    top = 4 + len(info) + 1
    for c, title in ((2, "빠진 항목"), (3, "건수")):
        cell = ws.cell(top, c, title)
        cell.fill, cell.font, cell.border, cell.alignment = head_fill, head_font, border, center
    paid = set(check["paid_required"])
    r = top
    for name, n in sorted(counts.items(), key=lambda t: -t[1]):
        r += 1
        ws.cell(r, 2, f"{name} (유상 건)" if name in paid else name).border = border
        cell = ws.cell(r, 3, n)
        cell.border, cell.alignment = border, center
    r += 1
    for c, v in ((2, "합계"), (3, sum(counts.values()))):
        cell = ws.cell(r, c, v)
        cell.font, cell.border = Font(bold=True), border
        cell.fill = PatternFill("solid", fgColor="F2F2F2")
        if c == 3:
            cell.alignment = center
    ws.cell(r + 2, 2, "※ 한 줄에 여러 항목이 빠졌으면 항목마다 1건씩 셉니다. 자세한 목록은 「누락목록」 시트").font = Font(color="808080")
    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 22

    # ---- 누락목록
    ws = wb.create_sheet("누락목록")
    ws.append(FIELDS)
    for cell in ws[1]:
        cell.fill, cell.font, cell.border, cell.alignment = head_fill, head_font, border, center
    for p in problems:
        ws.append([p[f] for f in FIELDS])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
        row[0].alignment = row[2].alignment = center
        row[5].font = Font(color="C00000")
    for letter, width in zip("ABCDEF", (8, 14, 13, 10, 32, 40)):
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "A2"  # 첫 행 틀 고정
    ws.auto_filter.ref = f"A1:F{max(1, len(problems) + 1)}"

    out = HERE / f"누락목록_{date.today():%Y%m%d}.xlsx"
    try:
        wb.save(out)
    except PermissionError:  # 같은 이름 파일이 열려 있으면 다른 이름으로
        out = HERE / f"누락목록_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        wb.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--file", help="검사할 엑셀 파일 (기본: config.json 의 엑셀)")
    ap.add_argument("--color", action="store_true", help="독립채산제 파일의 누락 칸을 빨간색으로 칠한다")
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

    sh = excel_writer._Sheet(path, config["sheet_name"], config.get("header_row", 3), log,
                             read_only=not args.color)
    if not args.color:
        log("독립채산제 파일은 읽기만 하고 바꾸지 않습니다.")
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

        if args.color:
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

    counts = {}
    for p in problems:
        for m in p["누락 항목"].split(", "):
            counts[m] = counts.get(m, 0) + 1
    out = write_report(problems, counts, check, path, first, last)

    log(f"검사한 줄: {first}~{last}행 / 누락 있는 줄: {len(problems)}개")
    for k, v in sorted(counts.items(), key=lambda t: -t[1]):
        log(f"  - {k}: {v}건")
    for p in problems[:30]:
        log(f"  {p['행']}행 {p['접수일자']} {p['고객/발전소']} → {p['누락 항목']}")
    if len(problems) > 30:
        log(f"  ... 외 {len(problems) - 30}건 (전체 목록: {out.name})")
    if args.color:
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
