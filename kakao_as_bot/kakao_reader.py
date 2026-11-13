"""카카오톡 PC 채팅방 창에서 대화 텍스트를 가져온다 (Windows 전용).

동작 방식:
  1) 채팅방 이름으로 창을 찾는다. 없으면 카카오톡 메인 창에서 검색해서 연다.
  2) 대화 목록 영역에 Ctrl+A, Ctrl+C 를 보내 클립보드로 복사한다.
  3) 클립보드 텍스트를 돌려준다.

복사되는 텍스트 형식 예:
  2026년 11월 13일 금요일
  [이천지사 임범동 부장] [오후 1:50] [에이닷 전화 연락처 공유]
  이름: ...
"""
import time

try:
    import win32api
    import win32clipboard
    import win32con
    import win32gui
except ImportError:  # Windows 가 아니면 이 모듈은 쓸 수 없다
    win32gui = None


LIST_CONTROL_CLASS = "EVA_VH_ListControl_Dblclk"


def _require_windows():
    if win32gui is None:
        raise RuntimeError("카카오톡 직접 읽기는 Windows 에서만 됩니다 (pip install pywin32).")


def _post_key(hwnd, key, with_ctrl=True):
    """창이 앞에 없어도 키 입력을 보낸다."""
    if with_ctrl:
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    lparam = win32api.MAKELONG(0, win32api.MapVirtualKey(key, 0))
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, key, lparam)
    time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, key, lparam | 0xC0000000)
    if with_ctrl:
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def _open_room_from_main(room_name):
    """카카오톡 메인 창의 검색창에 방 이름을 넣고 Enter 로 연다."""
    main = win32gui.FindWindow(None, "카카오톡")
    if not main:
        raise RuntimeError("카카오톡 PC 프로그램이 실행/로그인되어 있지 않습니다.")
    child = win32gui.FindWindowEx(main, None, "EVA_ChildWindow", None)
    wnd1 = win32gui.FindWindowEx(child, None, "EVA_Window", None)
    wnd2 = win32gui.FindWindowEx(child, wnd1, "EVA_Window", None)  # 채팅 탭
    edit = win32gui.FindWindowEx(wnd2, None, "Edit", None)
    if not edit:
        raise RuntimeError("카카오톡 검색창을 찾지 못했습니다. 채팅방을 한 번 직접 열어 두세요.")
    win32api.SendMessage(edit, win32con.WM_SETTEXT, 0, room_name)
    time.sleep(1)
    win32api.PostMessage(edit, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
    time.sleep(0.05)
    win32api.PostMessage(edit, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
    time.sleep(2)


def _get_clipboard_text():
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                return ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("클립보드를 읽지 못했습니다.")


def read_room_text(room_name):
    _require_windows()
    hwnd = win32gui.FindWindow(None, room_name)
    if not hwnd:
        _open_room_from_main(room_name)
        hwnd = win32gui.FindWindow(None, room_name)
    if not hwnd:
        raise RuntimeError(f"채팅방 창 '{room_name}' 을(를) 찾지 못했습니다. 방 이름을 확인하세요.")

    list_ctrl = win32gui.FindWindowEx(hwnd, None, LIST_CONTROL_CLASS, None)
    if not list_ctrl:
        raise RuntimeError("채팅 목록 영역을 찾지 못했습니다 (카카오톡 버전 변경 가능성).")

    # 기존 클립보드 비우기 → 복사 실패를 감지하기 위해
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.CloseClipboard()

    _post_key(list_ctrl, ord("A"))
    time.sleep(0.5)
    _post_key(list_ctrl, ord("C"))
    time.sleep(1)
    text = _get_clipboard_text()
    if not text.strip():
        raise RuntimeError("대화 내용을 복사하지 못했습니다. 채팅방 창을 열어 둔 상태인지 확인하세요.")
    return text
