"""카카오톡 텍스트(창 복사본 또는 '대화 내보내기' txt)를 메시지 목록으로 바꾼다."""
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime

DATE_RE = re.compile(r"^-*\s*(\d{4})년 (\d{1,2})월 (\d{1,2})일 \S+요일\s*-*$")
MSG_RE = re.compile(r"^\[(.+?)\] \[(오전|오후) (\d{1,2}):(\d{2})\] ?(.*)$")


@dataclass
class Message:
    sent_at: datetime
    sender: str
    text: str

    @property
    def key(self):
        raw = f"{self.sent_at:%Y%m%d%H%M}|{self.sender}|{self.text}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _to_datetime(day, ampm, hour, minute):
    hour = int(hour) % 12
    if ampm == "오후":
        hour += 12
    return datetime(day.year, day.month, day.day, hour, int(minute))


def parse(text, today=None):
    day = today or date.today()
    messages = []
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        m = DATE_RE.match(stripped)
        if m:
            day = date(int(m[1]), int(m[2]), int(m[3]))
            continue
        m = MSG_RE.match(line)
        if m:
            messages.append(Message(_to_datetime(day, m[2], m[3], m[4]), m[1].strip(), m[5]))
            continue
        if messages:  # 여러 줄 메시지의 이어지는 줄
            messages[-1].text += "\n" + line
    for msg in messages:
        msg.text = msg.text.strip()
    return messages
