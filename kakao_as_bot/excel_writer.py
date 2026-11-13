"""정리된 접수 건을 엑셀 「2026년도 데이터」 시트 맨 아래에 추가한다.

Windows 에서는 xlwings(실제 Excel)로 쓴다 → 수식·서식·외부 연결이 그대로 유지되고,
파일이 Excel 에 열려 있어도 그 창에 바로 추가된다.
그 밖의 환경(테스트용)에서는 openpyxl 로 쓴다.
"""
from datetime import date, datetime

# 시트 3행 머리글 → 우리 필드 이름. 'A/S' 열(C)이 실제로는 '분류' 열이다.
HEADER_ALIASES = {"A/S": "분류", "분류": "분류"}
REQUIRED = ["분류", "접수일자", "요청부서", "요청자", "발전소명", "고객명", "연락처", "주소", "접수 내역"]
YELLOW_RGB = (255, 242, 204)
CHECK_COLS = range(3, 16)  # C~O 열 중 하나라도 값이 있으면 사용 중인 행


def _norm(header):
    h = str(header or "").replace("\n", "").strip()
    return HEADER_ALIASES.get(h, h)


def _same(a, b):
    if isinstance(a, datetime):
        a = a.date()
    if isinstance(b, datetime):
        b = b.date()
    return str(a or "").strip() == str(b or "").strip()


class _Sheet:
    """xlwings / openpyxl 공통 인터페이스 (1부터 시작하는 행·열 번호)."""

    def __init__(self, path, sheet_name, header_row):
        self.path, self.header_row = path, header_row
        try:
            import xlwings as xw
            self.book = xw.Book(path)
            self.ws = self.book.sheets[sheet_name]
            self.mode = "xlwings"
        except Exception:
            import openpyxl
            self.book = openpyxl.load_workbook(path)
            self.ws = self.book[sheet_name]
            self.mode = "openpyxl"

    def get(self, r, c):
        if self.mode == "xlwings":
            return self.ws.range((r, c)).value
        return self.ws.cell(r, c).value

    def set(self, r, c, v):
        if self.mode == "xlwings":
            self.ws.range((r, c)).value = v
        else:
            self.ws.cell(r, c).value = v

    def get_formula(self, r, c):
        if self.mode == "xlwings":
            return self.ws.range((r, c)).formula
        return self.ws.cell(r, c).value

    def highlight(self, r, first_col, last_col):
        if self.mode == "xlwings":
            self.ws.range((r, first_col), (r, last_col)).color = YELLOW_RGB
        else:
            from openpyxl.styles import PatternFill
            fill = PatternFill("solid", fgColor="%02X%02X%02X" % YELLOW_RGB)
            for c in range(first_col, last_col + 1):
                self.ws.cell(r, c).fill = fill

    def _block(self, start, count):
        """C~O 열의 start 행부터 count 행 값을 2차원 리스트로."""
        first, last = CHECK_COLS[0], CHECK_COLS[-1]
        if self.mode == "xlwings":
            vals = self.ws.range((start, first), (start + count - 1, last)).value
            return [v if isinstance(v, list) else [v] for v in vals]
        return [[c.value for c in row] for row in self.ws.iter_rows(
            min_row=start, max_row=start + count - 1, min_col=first, max_col=last)]

    def last_used_row(self, gap=30):
        """위에서부터 내려가며, 빈 행이 gap 개 이어지기 직전의 마지막 데이터 행.
        (시트 아래쪽 멀리 떨어진 엉뚱한 값은 무시한다)"""
        last, empty, start, chunk = self.header_row, 0, self.header_row + 1, 500
        while True:
            for i, row in enumerate(self._block(start, chunk)):
                if any(v not in (None, "") for v in row):
                    last, empty = start + i, 0
                else:
                    empty += 1
                    if empty >= gap:
                        return last
            start += chunk

    def save(self, out_path=None):
        if self.mode == "xlwings":
            self.book.save()
        else:
            self.book.save(out_path or self.path)


def append_rows(rows, config, out_path=None, log=print):
    if not rows:
        return 0
    sh = _Sheet(config["excel_path"], config["sheet_name"], config.get("header_row", 3))
    hr = sh.header_row
    cols = {}
    for c in range(1, 60):
        name = _norm(sh.get(hr, c))
        if name and name not in cols:
            cols[name] = c
    missing = [k for k in REQUIRED if k not in cols]
    if missing:
        raise RuntimeError(f"엑셀 머리글에서 열을 찾지 못했습니다: {missing}")

    last = sh.last_used_row()
    # 중복 방지: 기존 행의 (연락처, 접수일자) 모음
    existing = set()
    for r in range(max(hr + 1, last - 300), last + 1):
        existing.add((str(sh.get(r, cols["연락처"]) or "").strip(), str(sh.get(r, cols["접수일자"]) or "")[:10]))

    # 위쪽 행의 수식(No. = ROW()-3, 자재비합계 = X*Y)을 새 행에 맞춰 복사
    formula_cols = {}
    for c in range(1, 60):
        f = sh.get_formula(last, c)
        if isinstance(f, str) and f.startswith("="):
            formula_cols[c] = f.replace(str(last), "{r}")

    added = 0
    for row in rows:
        key = (row.get("연락처", ""), str(row.get("접수일자", ""))[:10])
        if row.get("연락처") and key in existing:
            log(f"  - 이미 있는 건이라 건너뜀: {row.get('고객명')} {row.get('연락처')}")
            continue
        last += 1
        for c, f in formula_cols.items():
            sh.set(last, c, f.format(r=last))
        for field, value in row.items():
            if field.startswith("_") or field not in cols or value in (None, ""):
                continue
            if isinstance(value, date) and not isinstance(value, datetime):
                value = datetime(value.year, value.month, value.day)
            sh.set(last, cols[field], value)
        if config.get("highlight_new_rows", True):
            sh.highlight(last, cols["분류"], cols["접수 내역"])
        existing.add(key)
        added += 1
        log(f"  + {last}행 추가: {row.get('고객명')} / {row.get('연락처')} / {row.get('주소')}")

    if added:
        sh.save(out_path)
    return added
