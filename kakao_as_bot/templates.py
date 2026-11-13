"""카톡방에 올리는 [접수] / [처리] 양식을 읽는다.

양식 규칙:
  - 첫 줄에 [접수] 또는 [처리]
  - 그 다음 줄부터 '항목: 값'
  - 항목이 없는 줄은 바로 위 항목에 이어 붙는다 (조치내역 여러 줄 작성 가능)
  - 모르는 항목·빈 값은 적지 않아도 된다
"""
import re
from datetime import date, datetime

# 카톡에 쓰는 항목 이름 → 내부 필드 이름 (엑셀 위치는 excel_writer.FIELD_COLUMNS)
KEY_ALIASES = {
    # 접수
    "분류": "분류", "구분": "분류",
    "접수일자": "접수일자", "접수일": "접수일자",
    "요청부서": "요청부서", "부서": "요청부서",
    "요청자": "요청자",
    "사업년도": "사업년도", "사업연도": "사업년도", "설치년도": "사업년도",
    "사업분류": "사업분류", "사업구분": "사업분류",
    "발전소명": "발전소명", "발전소": "발전소명", "현장명": "발전소명",
    "고객명": "고객명", "고객": "고객명", "이름": "고객명", "성명": "고객명",
    "연락처": "연락처", "전화": "연락처", "휴대전화": "연락처", "휴대폰": "연락처", "전화번호": "연락처",
    "주소": "주소", "집": "주소",
    "접수내역": "접수 내역", "접수내용": "접수 내역", "요청내용": "접수 내역", "증상": "접수 내역",
    # 처리
    "처리일자": "처리일자", "처리일": "처리일자", "방문일": "처리일자",
    "처리자": "처리자", "담당자": "처리자", "방문자": "처리자",
    "조치내역": "조치 내역", "조치내용": "조치 내역", "처리내용": "조치 내역",
    "유무상": "유/무상", "유/무상": "유/무상",
    "매출액": "매출액", "금액": "매출액", "청구금액": "매출액",
    "발행": "발행", "증빙": "발행", "결제방법": "발행",
    "발행번호": "발행번호",
    "발행일자": "발행일자", "입금일자": "발행일자",
    "입금액": "입금액",
    "법인": "법인",
    "제품명": "제품명", "자재": "제품명", "교체품": "제품명",
    "제품단가": "제품단가", "단가": "제품단가",
    "제품수량": "제품수량", "수량": "제품수량",
    "처리시간": "처리시간", "작업시간": "처리시간",
    "왕복km": "왕복km", "왕복거리": "왕복km", "거리": "왕복km",
    "외주업체": "외주업체",
    "외주비용": "외주비용", "외주비": "외주비용",
    "이동": "이동", "비고": "이동", "다음일정": "이동",
}
NUMBER_FIELDS = {"사업년도", "매출액", "입금액", "제품단가", "제품수량", "처리시간", "왕복km", "외주비용"}
DATE_FIELDS = {"접수일자", "처리일자", "발행일자"}

HEADER_RE = re.compile(r"^\s*[\[【<(]?\s*(접수|처리|완료)\s*[\]】>)]?\s*$")
LINE_RE = re.compile(r"^\s*[-•*]?\s*([가-힣A-Za-z/ ]{1,10}?)\s*[:：]\s*(.*)$")
PHONE_RE = re.compile(r"(0\d{1,2})[-. ]?(\d{3,4})[-. ]?(\d{4})")


def format_phone(raw):
    m = PHONE_RE.search(raw or "")
    return f"{m[1]}-{m[2]}-{m[3]}" if m else (raw or "").strip()


def parse_date(text, base):
    t = (text or "").strip()
    if not t or t in ("오늘", "금일"):
        return base
    if t in ("어제", "전일"):
        return date.fromordinal(base.toordinal() - 1)
    nums = [int(n) for n in re.findall(r"\d+", t)]
    try:
        if len(nums) >= 3:
            y, m, d = nums[:3]
            return date(y + 2000 if y < 100 else y, m, d)
        if len(nums) == 2:
            return date(base.year, nums[0], nums[1])
    except ValueError:
        pass
    return t  # 해석 못 하면 글자 그대로


def parse_number(text):
    t = (text or "").replace(",", "").replace("원", "").replace("km", "").replace("시간", "").strip()
    try:
        f = float(t)
        return int(f) if f.is_integer() else f
    except ValueError:
        return text.strip()


def parse_template(msg):
    """[접수]/[처리] 양식이면 (종류, 필드 dict) 를, 아니면 None 을 돌려준다."""
    lines = msg.text.split("\n")
    # 첫 몇 줄 안에 [접수]/[처리] 머리말이 있어야 한다 (답장 인용 줄 등은 건너뜀)
    for start, line in enumerate(lines[:4]):
        m = HEADER_RE.match(line)
        if m:
            kind = "접수" if m[1] == "접수" else "처리"
            break
    else:
        return None

    fields, current = {}, None
    for line in lines[start + 1:]:
        m = LINE_RE.match(line)
        key = KEY_ALIASES.get(m[1].replace(" ", "")) if m else None
        if key:
            current = key
            fields[key] = m[2].strip()
        elif current and line.strip():
            fields[current] = (fields[current] + "\n" + line.strip()).strip()

    base = msg.sent_at.date()
    out = {}
    for k, v in fields.items():
        if not v:
            continue
        if k in DATE_FIELDS:
            v = parse_date(v, base)
        elif k in NUMBER_FIELDS:
            v = parse_number(v)
        elif k == "연락처":
            v = format_phone(v)
        elif k == "처리자":
            v = [p for p in re.split(r"[,/、·\s]+", v) if p][:4]
        out[k] = v
    if kind == "접수":
        out.setdefault("접수일자", base)
    else:
        out.setdefault("처리일자", base)
    return kind, out
