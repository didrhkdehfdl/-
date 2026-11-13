"""새 메시지에서 A/S 접수 건을 뽑아 엑셀 한 줄(dict)로 만든다.

- AI 모드(use_ai=true, ANTHROPIC_API_KEY 필요): Claude 가 자유 형식 글도 읽고 정리한다.
- 규칙 모드: '이름: / 휴대전화: / 집:' 처럼 정해진 형식(에이닷 연락처 공유 등)만 처리한다.
"""
import json
import os
import re

PHONE_RE = re.compile(r"(0\d{1,2})[-. ]?(\d{3,4})[-. ]?(\d{4})")
FIELD_RE = re.compile(r"^\s*(이름|성명|고객명|휴대전화|휴대폰|전화|연락처|집|주소|회사|직장)\s*[:：]\s*(.+)$")
FOLLOW_UP_HINTS = ("접수되었는지", "확인부탁", "확인 부탁", "답장")


def format_phone(raw):
    m = PHONE_RE.search(raw or "")
    return f"{m[1]}-{m[2]}-{m[3]}" if m else (raw or "")


def _requester(sender, config):
    mapping = config.get("sender_to_requester", {})
    if sender in mapping:
        return mapping[sender]
    # "이천지사 임범동 부장" → "임범동"
    parts = sender.split()
    return parts[1] if len(parts) >= 3 else sender


def _base_row(msg, config):
    d = config.get("defaults", {})
    return {
        "분류": d.get("분류", "A/S"),
        "접수일자": msg.sent_at.date(),
        "요청부서": d.get("요청부서", ""),
        "요청자": _requester(msg.sender, config),
        "_source": f"{msg.sent_at:%Y-%m-%d %H:%M} {msg.sender}",
    }


# ---------------------------------------------------------------- 규칙 모드
def extract_rule_based(messages, config):
    rows = []
    for i, msg in enumerate(messages):
        if not PHONE_RE.search(msg.text):
            continue
        # 앞선 접수 글을 인용한 답장/재확인 글은 건너뛴다
        if any(h in msg.text for h in FOLLOW_UP_HINTS):
            continue
        fields = {}
        for line in msg.text.split("\n"):
            m = FIELD_RE.match(line)
            if m:
                fields.setdefault(m[1], m[2].strip())
        name_line = fields.get("이름") or fields.get("성명") or fields.get("고객명") or ""
        name, _, memo = name_line.partition(" ")
        row = _base_row(msg, config)
        row["고객명"] = name
        row["연락처"] = format_phone(
            fields.get("휴대전화") or fields.get("휴대폰") or fields.get("연락처")
            or fields.get("전화") or msg.text)
        row["주소"] = fields.get("집") or fields.get("주소") or fields.get("회사") or fields.get("직장") or ""
        notes = [memo] if memo else []
        # 바로 앞뒤의 같은 사람 글(사진/설명)을 접수 내역에 붙인다
        for j in (i - 1, i + 1):
            if 0 <= j < len(messages) and messages[j].sender == msg.sender:
                t = messages[j].text
                if t in ("사진", "동영상") or t.startswith("사진 "):
                    notes.append("사진 첨부(카톡 확인)")
                elif not PHONE_RE.search(t) and len(t) < 200:
                    notes.append(t.replace("\n", " "))
        row["접수 내역"] = " / ".join(n for n in notes if n)
        rows.append(row)
    return rows


# ---------------------------------------------------------------- AI 모드
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["records"],
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["message_index", "분류", "고객명", "연락처", "주소", "발전소명", "접수 내역"],
                "properties": {
                    "message_index": {"type": "integer"},
                    "분류": {"type": "string", "enum": [
                        "A/S", "모니터링 설치", "드론촬영", "KDN 연동시험", "유지관리", "사검/설치확인", "기타 업무"]},
                    "고객명": {"type": "string"},
                    "연락처": {"type": "string"},
                    "주소": {"type": "string"},
                    "발전소명": {"type": "string"},
                    "접수 내역": {"type": "string"},
                },
            },
        }
    },
}

SYSTEM_PROMPT = """너는 태양광 발전설비 회사의 현장대응(A/S) 접수 담당자다.
카카오톡 단체방 메시지 목록을 받으면, 새로 접수된 현장대응 요청 건만 골라 엑셀 한 줄씩으로 정리한다.

규칙:
- 고객 연락처나 주소가 담긴 '새 접수 글'만 기록한다. 같은 건을 인용한 답장, "접수됐는지 확인 부탁" 같은 재확인, 인사, 잡담은 기록하지 않는다.
- message_index 는 접수 내용이 담긴 메시지의 번호다.
- 고객명은 사람 이름만 적는다 (예: "지완종 의왕시 유영경건물주 ..." → "지완종"). 이름 뒤의 메모는 접수 내역에 넣는다.
- 연락처는 010-1234-5678 형식으로 적는다.
- 주소는 메시지에 적힌 그대로 적는다.
- 발전소명이 언급되지 않았으면 빈 문자열로 둔다.
- 접수 내역에는 고장 증상·요청 사항을 짧게 적는다 (예: "인버터 오류17 태양전지(DC) 절연저항 감지"). 주변 메시지(같은 사람이 보낸 사진·설명)를 참고하되, 사진만 있고 내용을 알 수 없으면 "사진 첨부(카톡 확인)" 라고 적는다.
- 분류는 보통 A/S 이고, 모니터링 설치·드론촬영·사용전검사 등이 분명할 때만 다른 값을 쓴다.
- 지어내지 말고, 없는 정보는 빈 문자열로 둔다."""


def extract_with_ai(messages, config):
    import anthropic

    client = anthropic.Anthropic()
    listing = "\n\n".join(
        f"#{i} [{m.sent_at:%Y-%m-%d %H:%M}] {m.sender}:\n{m.text}" for i, m in enumerate(messages))
    response = client.beta.messages.create(
        model=config.get("ai_model", "claude-opus-5-5"),
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": f"새 메시지 목록:\n\n{listing}"}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("AI 가 이 요청을 처리하지 않았습니다. 규칙 모드로 처리합니다.")
    text = next(b.text for b in response.content if b.type == "text")
    rows = []
    for rec in json.loads(text)["records"]:
        idx = rec.pop("message_index")
        if not 0 <= idx < len(messages):
            continue
        row = _base_row(messages[idx], config)
        row.update(rec)
        row["연락처"] = format_phone(row["연락처"])
        rows.append(row)
    return rows


def extract(messages, config, log=print):
    if not messages:
        return []
    if config.get("use_ai") and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return extract_with_ai(messages, config)
        except Exception as e:  # 네트워크 오류 등 → 규칙 모드로 대체
            log(f"[경고] AI 정리 실패, 규칙 모드로 처리: {e}")
    return extract_rule_based(messages, config)
