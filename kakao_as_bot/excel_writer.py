"""접수/처리 기록을 엑셀 「2026년도 데이터」 시트에 반영한다.

- [접수] → 맨 아래에 새 줄 추가 (노란색 표시)
- [처리] → 연락처/고객명/발전소명으로 아직 처리 안 된 접수 줄을 찾아 처리 칸을 채움 (연두색 표시)
           찾지 못하면 새 줄로 추가, 이미 처리된 건이면 접수 정보를 복사한 새 줄로 추가

Windows 에서는 xlwings(실제 Excel)로 쓴다 → 수식·서식·외부 연결이 그대로 유지되고,
파일이 Excel 에 열려 있어도 그 창에 바로 반영된다. 그 밖의 환경(테스트용)에서는 openpyxl 로 쓴다.
"""
import re
from datetime import date, datetime
from pathlib import Path

from openpyxl.utils import column_index_from_string as col_idx

# 필드 → 열 (「2026년도 데이터」 시트 기준)
FIELD_COLUMNS = {
    "분류": "C", "접수일자": "D", "처리일자": "E", "요청부서": "F", "요청자": "G",
    "사업년도": "H", "사업분류": "I", "발전소명": "J", "고객명": "K", "연락처": "L",
    "주소": "M", "접수 내역": "N", "조치 내역": "O", "유/무상": "P", "매출액": "Q",
    "발행": "R", "발행번호": "S", "발행일자": "T", "입금액": "U", "법인": "V",
    "제품명": "W", "제품단가": "X", "제품수량": "Y",
    "처리시간": "AE", "왕복km": "AF", "외주업체": "AG", "외주비용": "AH", "이동": "AI",
}
WORKER_COLUMNS = ["AA", "AB", "AC", "AD"]  # 처리자 1~4
RECEIPT_COPY = ["분류", "접수일자", "요청부서", "요청자", "사업년도", "사업분류",
                "발전소명", "고객명", "연락처", "주소", "접수 내역"]
# 양식이 바뀌었는지 확인할 머리글
EXPECTED_HEADERS = {"C": "A/S", "D": "접수일자", "E": "처리일자", "K": "고객명", "L": "연락처",
                    "O": "조치 내역", "P": "유/무상", "AA": "처리자", "AE": "처리시간(시간)"}
YELLOW = (255, 242, 204)
GREEN = (226, 239, 218)
SCAN_FIRST, SCAN_LAST = col_idx("C"), col_idx("O")


def resolve_excel_path(config):
    """excel_folder + excel_file. excel_file 이 비어 있으면 폴더에서 자동으로 찾는다."""
    if config.get("excel_path"):
        return Path(config["excel_path"])
    folder = Path(config["excel_folder"])
    name = config.get("excel_file", "").strip()
    if name:
        return folder / name
    keywords = config.get("excel_name_keywords", ["현장대응", "AS", "A_S"])
    cands = [p for p in folder.glob("*.xls*")
             if not p.name.startswith("~$") and any(k in p.name for k in keywords)]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        raise RuntimeError(f"{folder} 에서 엑셀 파일을 찾지 못했습니다. config.json 의 excel_file 에 파일 이름을 적어 주세요.")
    names = ", ".join(p.name for p in cands)
    raise RuntimeError(f"{folder} 에 후보 파일이 여러 개입니다({names}). config.json 의 excel_file 에 정확한 이름을 적어 주세요.")


def _digits(v):
    return re.sub(r"\D", "", str(v or ""))


def _text(v):
    return str(v or "").replace(" ", "").strip()


def _to_cell(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return datetime(v.year, v.month, v.day)
    return v


class _Sheet:
    """xlwings / openpyxl 공통 인터페이스 (1부터 시작하는 행·열 번호)."""

    def __init__(self, path, sheet_name, header_row):
        self.path, self.header_row = str(path), header_row
        try:
            import xlwings as xw
            self.book = xw.Book(self.path)
            if self.book.api.ReadOnly:
                raise RuntimeError("엑셀 파일이 읽기 전용으로 열렸습니다(다른 사람이 사용 중). 다음 실행 때 다시 시도합니다.")
            self.ws = self.book.sheets[sheet_name]
            self.mode = "xlwings"
        except ImportError:
            import openpyxl
            self.book = openpyxl.load_workbook(self.path)
            self.ws = self.book[sheet_name]
            self.mode = "openpyxl"

    def get(self, r, c):
        if self.mode == "xlwings":
            return self.ws.range((r, c)).value
        return self.ws.cell(r, c).value

    def set(self, r, c, v, color=None):
        v = _to_cell(v)
        if self.mode == "xlwings":
            cell = self.ws.range((r, c))
            cell.value = v
            if color:
                cell.color = color
        else:
            cell = self.ws.cell(r, c)
            cell.value = v
            if color:
                from openpyxl.styles import PatternFill
                cell.fill = PatternFill("solid", fgColor="%02X%02X%02X" % color)

    def get_formula(self, r, c):
        if self.mode == "xlwings":
            return self.ws.range((r, c)).formula
        return self.ws.cell(r, c).value

    def rows(self, start, end, first, last):
        """start~end 행, first~last 열 값 2차원 리스트."""
        if self.mode == "xlwings":
            vals = self.ws.range((start, first), (end, last)).value
            if start == end:
                vals = [vals]
            return [v if isinstance(v, list) else [v] for v in vals]
        return [[c.value for c in row] for row in self.ws.iter_rows(
            min_row=start, max_row=end, min_col=first, max_col=last)]

    def last_used_row(self, gap=30):
        """위에서부터 내려가며 빈 행이 gap 개 이어지기 직전의 마지막 데이터 행
        (시트 아래쪽 멀리 떨어진 엉뚱한 값은 무시)."""
        last, empty, start, chunk = self.header_row, 0, self.header_row + 1, 500
        while True:
            for i, row in enumerate(self.rows(start, start + chunk - 1, SCAN_FIRST, SCAN_LAST)):
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


class Writer:
    def __init__(self, config, log=print):
        self.config, self.log = config, log
        self.path = resolve_excel_path(config)
        self.sh = _Sheet(self.path, config["sheet_name"], config.get("header_row", 3))
        self._check_headers()
        self.last = self.sh.last_used_row()
        self.template_row = self.last
        self.formulas = {}
        for c in range(1, col_idx("AK")):
            f = self.sh.get_formula(self.template_row, c)
            if isinstance(f, str) and f.startswith("="):
                self.formulas[c] = f
        self.changed = 0

    def _check_headers(self):
        hr = self.sh.header_row
        for letter, expected in EXPECTED_HEADERS.items():
            got = str(self.sh.get(hr, col_idx(letter)) or "").replace("\n", "")
            if got.replace(" ", "") != expected.replace(" ", ""):
                raise RuntimeError(f"엑셀 {letter}{hr} 머리글이 '{expected}' 이(가) 아니라 '{got}' 입니다. 양식이 바뀌었는지 확인하세요.")

    # ------------------------------------------------------------ 공통
    def _new_row(self):
        self.last += 1
        r = self.last
        for c, f in self.formulas.items():  # No.(=ROW()-3), 자재비합계(=X*Y) 등
            self.sh.set(r, c, re.sub(rf"(?<=[A-Z]){self.template_row}(?!\d)", str(r), f))
        return r

    def _write(self, r, fields, color, append_text=False):
        for field, value in fields.items():
            if field.startswith("_") or value in (None, "", []):
                continue
            if field == "처리자":
                names = value if isinstance(value, list) else [value]
                for letter, name in zip(WORKER_COLUMNS, names):
                    self.sh.set(r, col_idx(letter), name, color)
                continue
            if field not in FIELD_COLUMNS:
                continue
            c = col_idx(FIELD_COLUMNS[field])
            if append_text and field == "조치 내역":
                old = str(self.sh.get(r, c) or "").strip()
                if old and str(value) not in old:
                    value = f"{old}\n\n{value}"
            self.sh.set(r, c, value, color)
        self.changed += 1

    def _recent_rows(self, n=1500):
        start = max(self.sh.header_row + 1, self.last - n)
        vals = self.sh.rows(start, self.last, 1, col_idx("O"))
        return [(start + i, row) for i, row in enumerate(vals)]

    # ------------------------------------------------------------ 접수
    def add_receipt(self, fields, source):
        phone, day = _digits(fields.get("연락처")), str(_to_cell(fields.get("접수일자")))[:10]
        if phone:
            L, D = col_idx("L") - 1, col_idx("D") - 1
            for r, row in self._recent_rows(300):
                if _digits(row[L]) == phone and str(row[D])[:10] == day:
                    self.log(f"  - 이미 접수된 건이라 건너뜀({r}행): {fields.get('고객명')} {fields.get('연락처')}")
                    return
        r = self._new_row()
        self._write(r, fields, YELLOW)
        self.log(f"  + [접수] {r}행 추가: {fields.get('고객명') or fields.get('발전소명')} / "
                 f"{fields.get('연락처', '')} / {fields.get('접수 내역', '')}  ({source})")

    # ------------------------------------------------------------ 처리
    def _find_receipt(self, fields):
        phone = _digits(fields.get("연락처"))
        name, plant = _text(fields.get("고객명")), _text(fields.get("발전소명"))
        if not (phone or name or plant):
            return None, None
        J, K, L, E = (col_idx(x) - 1 for x in "JKLE")
        open_match = done_match = None
        for r, row in reversed(self._recent_rows()):
            if phone:
                hit = _digits(row[L]) == phone
            elif name:
                hit = _text(row[K]) == name
            else:
                hit = _text(row[J]) == plant
            if not hit:
                continue
            if row[E] in (None, ""):
                open_match = open_match or r
            else:
                done_match = done_match or r
            if open_match:
                break
        return open_match, done_match

    def apply_done(self, fields, source):
        open_row, done_row = self._find_receipt(fields)
        label = fields.get("고객명") or fields.get("발전소명") or fields.get("연락처") or "?"
        if open_row:
            self._write(open_row, fields, GREEN, append_text=True)
            self.log(f"  * [처리] {open_row}행에 처리 내용 반영: {label}  ({source})")
            return
        r = self._new_row()
        if done_row:  # 같은 고객의 다음 방문 → 접수 정보 복사
            for f in RECEIPT_COPY:
                v = self.sh.get(done_row, col_idx(FIELD_COLUMNS[f]))
                if v not in (None, ""):
                    self.sh.set(r, col_idx(FIELD_COLUMNS[f]), v)
            self.log(f"  + [처리] 이미 처리된 건({done_row}행)의 추가 방문 → {r}행 새로 추가: {label}  ({source})")
        else:
            self.log(f"  + [처리] 접수 기록을 못 찾아 {r}행에 새로 추가(접수 칸 확인 필요): {label}  ({source})")
            fields = dict(fields)
            fields.setdefault("분류", self.config.get("defaults", {}).get("분류", "A/S"))
        self._write(r, fields, GREEN)

    def apply(self, records):
        for rec in records:
            if rec["kind"] == "접수":
                self.add_receipt(rec["fields"], rec["_source"])
            else:
                self.apply_done(rec["fields"], rec["_source"])
        return self.changed

    def save(self, out_path=None):
        if self.changed:
            self.sh.save(out_path)


def apply_records(records, config, out_path=None, log=print):
    if not records:
        return 0
    w = Writer(config, log)
    n = w.apply(records)
    w.save(out_path)
    return n
