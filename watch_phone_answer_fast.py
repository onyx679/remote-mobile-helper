import argparse
import ctypes
import csv
import gzip
import io
import json
import re
import subprocess
import sys
import tempfile
import time
from collections import deque
from pathlib import Path
from ctypes import wintypes

import cv2
import msgpack
import numpy as np
from PIL import ImageGrab

from det_word_bank import load_det_overrides


DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DEFAULT_WORD_DATA = Path(sys.prefix) / "Lib/site-packages/wordfreq/data/large_en.msgpack.gz"
BI_RGB = 0
DIB_RGB_COLORS = 0
PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
STOP_TOKENS = {
    "is", "this", "a", "real", "english", "word", "yes", "no", "ves",
    "incorrect", "correct", "answer", "got", "it", "question",
    "submit", "saved", "time", "times", "up",
}
NON_STANDARD_TOKENS = {
    "nite", "wate",
}
ENGLISH_WORDS: dict[str, int] | None = None
DET_OVERRIDES = load_det_overrides()
OCR_ANGLES = (-8, -6, -4, -2, 0)
OCR_FALLBACK_PASSES = (
    (-12, "gray", "6"),
    (-12, "otsu", "6"),
    (-6, "gray", "6"),
    (0, "otsu", "6"),
)
_WIN32_CAPTURE_API_CONFIGURED = False


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def stable_preview_choice(observations: deque[tuple[float, str, str, float]], now: float = 0.0, window_seconds: float = 1.8):
    while observations and now - observations[0][0] > window_seconds:
        observations.popleft()
    if len(observations) < 3:
        return None

    rows = [(word, answer, score) for _, word, answer, score in observations if word]
    if len(rows) < 3:
        return None

    max_len = max(len(word) for word, _, _ in rows)
    if max_len >= 5:
        rows = [(word, answer, score) for word, answer, score in rows if len(word) >= max_len - 1]
    if not rows:
        return None

    counts = {}
    for word, answer, score in rows:
        counts.setdefault(word, {"count": 0, "answer": answer, "score": score})
        counts[word]["count"] += 1

    word, data = max(counts.items(), key=lambda item: (item[1]["count"], len(item[0])))
    competing_words = [row_word for row_word, _, _ in rows if row_word != word and len(row_word) >= len(word)]
    if data["count"] >= 3 and data["count"] / len(rows) >= 0.75 and not competing_words:
        return word, data["answer"], data["score"], "stable-exact-word"
    return None


def run_text(args: list[str], timeout: float = 5.0) -> str:
    completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    return completed.stdout.decode("utf-8", errors="ignore")


def find_adb() -> str:
    candidates = [
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages/Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe/scrcpy-win64-v4.0/adb.exe",
        Path("adb.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "adb"


def latest_remote_photo(adb: str, serial: str, remote_dir: str) -> tuple[float, str] | None:
    command = (
        f"find '{remote_dir}' -maxdepth 1 -type f "
        "\\( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \\) "
        "-printf '%T@ %p\\n' 2>/dev/null | sort -nr | head -n 1"
    )
    text = run_text([adb, "-s", serial, "shell", command], timeout=4.0).strip()
    match = re.match(r"(?P<ts>\d+(?:\.\d+)?)\s+(?P<path>.+)", text)
    if not match:
        return None
    return float(match.group("ts")), match.group("path")


def remote_size(adb: str, serial: str, path: str) -> int:
    escaped = path.replace("'", "'\\''")
    text = run_text([adb, "-s", serial, "shell", f"stat -c %s '{escaped}' 2>/dev/null"], timeout=2.0).strip()
    return int(text) if text.isdigit() else -1


def wait_remote_stable(adb: str, serial: str, path: str) -> bool:
    a = remote_size(adb, serial, path)
    time.sleep(0.12)
    b = remote_size(adb, serial, path)
    return a > 0 and a == b


def pull_photo(adb: str, serial: str, remote_path: str, local_path: Path) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([adb, "-s", serial, "pull", remote_path, str(local_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def capture_desktop_region(region: tuple[int, int, int, int]):
    x, y, width, height = region
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def parse_screen_region_argument(value: str) -> tuple[str, tuple[int, int, int, int] | None]:
    value = value.strip()
    if not value:
        return "adb", None
    if value.lower() == "scrcpy":
        return "scrcpy", None
    return "desktop", tuple(int(part.strip()) for part in value.split(","))


def is_scrcpy_window_title(title: str) -> bool:
    return title.strip().lower() == "android-remote-wifi"


def configure_win32_capture_api() -> None:
    global _WIN32_CAPTURE_API_CONFIGURED
    if _WIN32_CAPTURE_API_CONFIGURED:
        return

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_uint]
    user32.PrintWindow.restype = wintypes.BOOL

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(BITMAPINFO),
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int

    _WIN32_CAPTURE_API_CONFIGURED = True


def find_scrcpy_window_handle(title_substring: str = "Android-Remote-WiFi"):
    configure_win32_capture_api()
    user32 = ctypes.windll.user32
    found: list[int] = []
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    @enum_proc_type
    def enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if is_scrcpy_window_title(buffer.value):
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(enum_proc, 0)
    return found[0] if found else None


def print_window_client_image(hwnd: int):
    configure_win32_capture_api()
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd = wintypes.HWND(hwnd)

    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None

    hdc_window = user32.GetWindowDC(hwnd)
    if not hdc_window:
        return None

    hdc_mem = None
    bitmap = None
    old_bitmap = None
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
        if not hdc_mem:
            return None
        bitmap = gdi32.CreateCompatibleBitmap(hdc_window, width, height)
        if not bitmap:
            return None
        old_bitmap = gdi32.SelectObject(hdc_mem, bitmap)
        if not old_bitmap:
            return None

        flags = PW_CLIENTONLY | PW_RENDERFULLCONTENT
        if not user32.PrintWindow(hwnd, hdc_mem, flags):
            return None

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        raw = ctypes.create_string_buffer(width * height * 4)
        lines = gdi32.GetDIBits(
            hdc_mem,
            bitmap,
            0,
            height,
            ctypes.cast(raw, ctypes.c_void_p),
            ctypes.byref(bmi),
            DIB_RGB_COLORS,
        )
        if lines != height:
            return None

        bgra = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))
        return bgra[:, :, :3].copy()
    finally:
        if old_bitmap and hdc_mem:
            gdi32.SelectObject(hdc_mem, old_bitmap)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if hdc_mem:
            gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_window)


def find_window_client_rect(title_substring: str) -> tuple[int, int, int, int] | None:
    user32 = ctypes.windll.user32
    found: list[tuple[int, int, int, int]] = []
    hwnd_topmost = wintypes.HWND(-1)
    swp_nomove = 0x0002
    swp_nosize = 0x0001
    swp_showwindow = 0x0040

    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    @enum_proc_type
    def enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if not is_scrcpy_window_title(buffer.value):
            return True

        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return True
        point = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
            return True
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width > 0 and height > 0:
            user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, swp_nomove | swp_nosize | swp_showwindow)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            found.append((point.x, point.y, width, height))
        return False

    user32.EnumWindows(enum_proc, 0)
    return found[0] if found else None


def capture_scrcpy_window(title_substring: str = "Android-Remote-WiFi"):
    hwnd = find_scrcpy_window_handle(title_substring)
    if hwnd is None:
        return None
    return print_window_client_image(hwnd)


def capture_preview_image(adb: str, serial: str, capture_source: tuple[str, tuple[int, int, int, int] | None]):
    source, region = capture_source
    if source == "desktop" and region is not None:
        return capture_desktop_region(region)
    if source == "scrcpy":
        return capture_scrcpy_window()
    return capture_screen(adb, serial)


def capture_screen(adb: str, serial: str):
    completed = subprocess.run([adb, "-s", serial, "exec-out", "screencap", "-p"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8, check=False)
    data = np.frombuffer(completed.stdout, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def read_image(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def crop_question_area(image, crop: tuple[float, float, float, float]):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = crop
    return image[int(h * y1):int(h * y2), int(w * x1):int(w * x2)]


def auto_word_area(image):
    h, w = image.shape[:2]
    sx1, sy1, sx2, sy2 = int(w * 0.06), int(h * 0.50), int(w * 0.94), int(h * 0.76)
    search = image[sy1:sy2, sx1:sx2]
    gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, dark = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
    grouped = cv2.dilate(dark, kernel, iterations=1)
    contours, _ = cv2.findContours(grouped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_score = -1.0
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        full_x = sx1 + x
        full_y = sy1 + y
        center_y = full_y + bh / 2
        center_x = full_x + bw / 2
        if bw < 18 or bh < 5:
            continue
        if bw > w * 0.45 or bh > h * 0.08:
            continue
        if center_y < h * 0.54 or center_y > h * 0.75:
            continue
        if center_x < w * 0.28 or center_x > w * 0.78:
            continue
        aspect = bw / max(bh, 1)
        if aspect < 1.15 or aspect > 7:
            continue
        candidate_region = image[max(0, full_y):min(h, full_y + bh), max(0, full_x):min(w, full_x + bw)]
        if candidate_region.size:
            hsv = cv2.cvtColor(candidate_region, cv2.COLOR_BGR2HSV)
            blue_mask = ((hsv[:, :, 0] >= 85) & (hsv[:, :, 0] <= 135) & (hsv[:, :, 1] > 60))
            if float(np.count_nonzero(blue_mask)) / float(blue_mask.size) > 0.08:
                continue

        center_penalty = abs(center_y - h * 0.69) * 0.05
        x_penalty = abs(center_x - w * 0.52) * 0.08
        score = (bh * bh * 14.0) + (bw * 0.15) - center_penalty - x_penalty
        if score > best_score:
            best_score = score
            best = (full_x, full_y, bw, bh)

    if best is None:
        return crop_question_area(image, (0.20, 0.56, 0.82, 0.76))

    x, y, bw, bh = best
    pad_x = max(120, int(bw * 1.8))
    pad_y = max(18, int(bh * 0.90))
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(w, x + bw + pad_x)
    y2 = min(h, y + bh + pad_y)
    return image[y1:y2, x1:x2]


def preprocess_for_ocr(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    height = gray.shape[0]
    if 0 < height < 260:
        scale = min(4.0, 260.0 / height)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return gray


def is_prompt_token(token: str) -> bool:
    lower = token.lower()
    if lower in STOP_TOKENS:
        return True
    return any(part in lower for part in ("english", "eng", "word", "this", "real", "question", "answer"))


def extract_ocr_candidates(raw_text: str) -> list[str]:
    candidates = []
    for token in TOKEN_RE.findall(raw_text):
        normalized = correct_ocr_token(token)
        if 3 <= len(normalized) <= 24 and not is_prompt_token(normalized):
            candidates.append(normalized)
    return candidates


def edit_distance_limited(left: str, right: str, limit: int) -> int:
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        row_min = current[0]
        for j, right_char in enumerate(right, 1):
            cost = 0 if left_char == right_char else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def is_related_ocr_token(token: str, expected: str) -> bool:
    if not token or not expected:
        return False
    if token in expected or expected in token:
        return True
    limit = max(2, min(4, len(expected) // 3))
    return edit_distance_limited(token, expected, limit) <= limit


def ocr_candidate_rank(token: str, count: int = 1, expected: str = ""):
    normalized = correct_ocr_token(token)
    if not (3 <= len(normalized) <= 24) or is_prompt_token(normalized):
        return None

    words = load_english_words()
    bucket = words.get(normalized)
    if normalized in DET_OVERRIDES or normalized in NON_STANDARD_TOKENS:
        known_tier = 3
    elif bucket is not None:
        known_tier = 2
    else:
        known_tier = 1

    if expected:
        related_tier = 1 if is_related_ocr_token(normalized, expected) else 0
        length_distance = abs(len(normalized) - len(expected))
    else:
        related_tier = 0
        length_distance = 0

    return (
        related_tier,
        count,
        known_tier,
        -length_distance,
        len(normalized),
        -(bucket or 99999),
    )


def choose_best_ocr_candidate(candidates: list[str], expected: str = "") -> str:
    counts: dict[str, int] = {}
    for candidate in candidates:
        normalized = correct_ocr_token(candidate)
        if 3 <= len(normalized) <= 24 and not is_prompt_token(normalized):
            counts[normalized] = counts.get(normalized, 0) + 1
    if not counts:
        return ""

    ranked = []
    for token, count in counts.items():
        rank = ocr_candidate_rank(token, count, expected)
        if rank is not None:
            ranked.append((rank, token))
    if not ranked:
        return ""

    ranked.sort(reverse=True)
    best = ranked[0][1]
    expected = correct_ocr_token(expected)
    if expected and expected in counts:
        best_count = counts[best]
        expected_count = counts[expected]
        if expected_count >= best_count - 1 and not is_prompt_token(expected):
            return expected
    return best


def prepare_ocr_fallback_image(rotated, mode: str):
    gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    if mode == "otsu":
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return gray


def rotate_image(image, degrees: float):
    if not degrees:
        return image
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)


def run_tesseract_image(image, tesseract: str, psm: str = "7") -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        cv2.imwrite(str(temp_path), image)
        completed = subprocess.run(
            [
                tesseract,
                str(temp_path),
                "stdout",
                "-l",
                "eng",
                "--psm",
                psm,
                "--oem",
                "1",
                "-c",
                "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        return completed.stdout.decode("utf-8", errors="ignore")
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def ocr_word_variants(word_area, tesseract: str) -> tuple[str, str]:
    observations = []
    raw_parts = []
    for angle in OCR_ANGLES:
        rotated = rotate_image(word_area, angle)
        gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        raw_text = run_tesseract_image(gray, tesseract, "7")
        raw_parts.append(f"{angle}:{raw_text.strip()}")
        candidates = extract_ocr_candidates(raw_text)
        if candidates:
            observations.append(choose_best_ocr_candidate(candidates))

    if not observations:
        return "", " | ".join(raw_parts)

    best = choose_best_ocr_candidate(observations)
    if best and observations.count(best) >= 2:
        return correct_ocr_token(best), " | ".join(raw_parts)
    return "", " | ".join(raw_parts)


def ocr_word_fallback(word_area, tesseract: str, expected: str = "") -> tuple[str, str]:
    observations = []
    raw_parts = []
    for angle, mode, psm in OCR_FALLBACK_PASSES:
        rotated = rotate_image(word_area, angle)
        prepared = prepare_ocr_fallback_image(rotated, mode)
        raw_text = run_tesseract_image(prepared, tesseract, psm)
        compact = raw_text.strip().replace("\n", " / ")
        raw_parts.append(f"{angle}:{mode}:psm{psm}:{compact}")
        observations.extend(extract_ocr_candidates(raw_text))

    word = choose_best_ocr_candidate(observations, expected)
    return word, " | ".join(raw_parts)


def run_tesseract_tsv(image, tesseract: str) -> list[dict]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        cv2.imwrite(str(temp_path), gray)
        completed = subprocess.run(
            [tesseract, str(temp_path), "stdout", "-l", "eng", "--psm", "11", "--oem", "1", "tsv"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        text = completed.stdout.decode("utf-8", errors="ignore")
        return list(csv.DictReader(io.StringIO(text), delimiter="\t"))
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def choose_word_from_tsv(rows: list[dict]) -> tuple[str, str]:
    candidates = []
    raw_parts = []
    prompt_bottom = None
    for row in rows:
        raw = row.get("text") or ""
        token_parts = TOKEN_RE.findall(raw)
        if not token_parts:
            continue
        token = "".join(token_parts).lower()
        raw_parts.append(token)
        try:
            top = float(row.get("top") or 0)
            height = float(row.get("height") or 0)
            width = float(row.get("width") or 0)
            conf = float(row.get("conf") or 0)
        except ValueError:
            continue
        if token in {"is", "this", "real", "english", "word"}:
            bottom = top + height
            prompt_bottom = bottom if prompt_bottom is None else max(prompt_bottom, bottom)
        if not (3 <= len(token) <= 24) or is_prompt_token(token):
            continue
        if width <= 0 or height <= 0:
            continue
        aspect = width / max(height, 1.0)
        if aspect > 8:
            continue
        if prompt_bottom is not None:
            dy = top - prompt_bottom
            if dy < 18 or dy > 450:
                continue
        score = height * 4.0 + top * 0.08 + conf * 0.15
        candidates.append((score, token))
    if not candidates:
        return "", " ".join(raw_parts)
    candidates.sort(reverse=True)
    return correct_ocr_token(candidates[0][1]), " ".join(raw_parts)


def ocr_word(path: Path, crop: tuple[float, float, float, float] | None, crop_out: Path, tesseract: str) -> tuple[str, str]:
    image = read_image(path)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return ocr_word_from_image(image, crop, crop_out, tesseract)


def ocr_word_from_image(image, crop: tuple[float, float, float, float] | None, crop_out: Path | None, tesseract: str) -> tuple[str, str]:
    word_area = auto_word_area(image) if crop is None else crop_question_area(image, crop)
    cv2.imwrite("latest-word-area.png", word_area)
    if crop is None:
        word, raw_text = ocr_word_variants(word_area, tesseract)
        if word:
            return word, raw_text
    prepared = preprocess_for_ocr(word_area)
    if crop_out is not None:
        cv2.imwrite(str(crop_out), prepared)
    raw_text = run_tesseract_image(prepared, tesseract)
    tokens = [correct_ocr_token(x) for x in TOKEN_RE.findall(raw_text)]
    joined = " ".join(tokens).lower()
    has_prompt = "english" in joined and ("word" in joined or "real" in joined)
    candidates = extract_ocr_candidates(raw_text)
    if candidates:
        fast_word = choose_best_ocr_candidate(candidates)
        answer, score = judge(fast_word, 700.0)
        if score > 0 or fast_word in DET_OVERRIDES or fast_word in NON_STANDARD_TOKENS:
            return fast_word, raw_text
        fallback_word, fallback_text = ocr_word_fallback(word_area, tesseract, fast_word)
        if fallback_word:
            return fallback_word, f"{raw_text.strip()} | fallback: {fallback_text}"
        return fast_word, raw_text
    fallback_word, fallback_text = ocr_word_fallback(word_area, tesseract)
    if fallback_word:
        return fallback_word, f"{raw_text.strip()} | fallback: {fallback_text}"
    word, tsv_text = choose_word_from_tsv(run_tesseract_tsv(word_area, tesseract))
    if word:
        return word, tsv_text
    if not has_prompt:
        return "", raw_text
    return "", raw_text


def load_english_words() -> dict[str, int]:
    global ENGLISH_WORDS
    if ENGLISH_WORDS is not None:
        return ENGLISH_WORDS
    if DEFAULT_WORD_DATA.exists():
        packed = msgpack.unpackb(gzip.open(DEFAULT_WORD_DATA, "rb").read(), raw=False)
        ENGLISH_WORDS = {word.lower(): bucket_index for bucket_index, bucket in enumerate(packed[1:], 1) if bucket for word in bucket}
    else:
        fallback_words = {
            "a", "able", "about", "above", "after", "again", "all", "also", "an", "and",
            "are", "as", "at", "be", "because", "but", "by", "can", "come", "day",
            "do", "for", "from", "get", "give", "go", "good", "have", "he", "her",
            "him", "his", "how", "i", "if", "in", "into", "is", "it", "like", "look",
            "make", "many", "me", "more", "my", "new", "no", "not", "now", "of",
            "on", "one", "or", "other", "our", "out", "part", "parts", "people",
            "see", "she", "so", "some", "take", "than", "that", "the", "their",
            "them", "then", "there", "these", "they", "think", "this", "time", "to",
            "two", "up", "use", "was", "way", "we", "well", "were", "what", "when",
            "which", "who", "will", "with", "word", "would", "yes", "you", "your",
        }
        ENGLISH_WORDS = {word: 500 for word in fallback_words}
    return ENGLISH_WORDS


def judge(word: str, threshold: float) -> tuple[str, float]:
    if not word:
        return "no", 0.0
    normalized = word.lower().strip("'")
    if normalized in DET_OVERRIDES:
        bucket = load_english_words().get(normalized)
        return ("yes" if DET_OVERRIDES[normalized] else "no"), float(bucket or 0.0)
    if normalized in NON_STANDARD_TOKENS:
        return "no", 0.0
    words = load_english_words()
    bucket = words.get(normalized)
    if bucket is None:
        return "no", 0.0
    max_bucket = threshold if threshold >= 10 else 700.0
    return ("yes" if bucket <= max_bucket else "no"), float(bucket)


def correct_ocr_token(word: str) -> str:
    if not word:
        return word
    normalized = word.lower().strip("'")
    return normalized


def write_result(result: dict, json_path: Path, txt_path: Path) -> None:
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(str(result["answer"]).upper(), encoding="utf-8")


def write_status(status: str, detail: str, json_path: Path, txt_path: Path) -> None:
    result = {
        "answer": "unknown",
        "word": "",
        "status": status,
        "detail": detail,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text("UNKNOWN", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast single-process phone photo OCR answer loop.")
    parser.add_argument("--mode", choices=["preview", "photo"], default="preview")
    parser.add_argument("--serial", default="adb-2252475e-baGT88._adb-tls-connect._tcp")
    parser.add_argument("--remote-dir", default="/sdcard/DCIM/Camera")
    parser.add_argument("--local-dir", type=Path, default=Path("camera-inbox"))
    parser.add_argument("--crop", default="")
    parser.add_argument("--screen-region", default="", help="Capture a desktop region x,y,w,h instead of adb screencap.")
    parser.add_argument("--rotate-180", action="store_true", default=False)
    parser.add_argument("--poll", type=float, default=0.15)
    parser.add_argument("--threshold", type=float, default=700.0)
    parser.add_argument("--copy-answer", action="store_true")
    parser.add_argument("--simple-output", action="store_true", help="Only print READY and final answers for CMD use.")
    parser.add_argument("--once", action="store_true", help="Run one detection pass and exit.")
    parser.add_argument("--pull-existing", action="store_true")
    parser.add_argument("--tesseract", default=DEFAULT_TESSERACT)
    args = parser.parse_args()

    if not args.crop:
        args.crop = "auto" if args.mode == "preview" else "0.30,0.42,0.75,0.60"
    crop = None if args.crop.strip().lower() == "auto" else tuple(float(part.strip()) for part in args.crop.split(","))
    adb = find_adb()
    capture_source = parse_screen_region_argument(args.screen_region)

    load_english_words()

    latest = latest_remote_photo(adb, args.serial, args.remote_dir) if args.mode == "photo" else None
    seen_path = "" if args.pull_existing or latest is None else latest[1]
    last_preview_word = ""
    last_preview_at = 0.0
    last_no_prompt_at = 0.0
    last_no_frame_at = 0.0
    preview_observations = deque()

    if args.simple_output:
        print("READY", flush=True)
    else:
        print("FAST PHONE ANSWER WATCHER", flush=True)
        print(f"mode={args.mode}", flush=True)
        print(f"adb={adb}", flush=True)
        print(f"device={args.serial}", flush=True)
        print(f"remote={args.remote_dir}", flush=True)
        print(f"crop={args.crop}", flush=True)
        print("Waiting for camera preview word..." if args.mode == "preview" else "Waiting for next phone photo...", flush=True)
        print("", flush=True)

    while True:
        try:
            if args.mode == "preview":
                started = time.perf_counter()
                capture_started = time.perf_counter()
                image = capture_preview_image(adb, args.serial, capture_source)
                capture_ms = (time.perf_counter() - capture_started) * 1000
                if image is None:
                    now = time.perf_counter()
                    if now - last_no_frame_at > 2.0:
                        last_no_frame_at = now
                        write_status("no_frame", "screencap returned no decodable image", Path("latest-result.json"), Path("latest-answer.txt"))
                    if not args.simple_output:
                        print(time.strftime("[%H:%M:%S]"), "NO FRAME from phone screen capture", flush=True)
                        print("", flush=True)
                    if args.once:
                        print("NO_FRAME", flush=True)
                        return 2
                    time.sleep(args.poll)
                    continue

                if float(image.mean()) < 3.0:
                    now = time.perf_counter()
                    if now - last_no_frame_at > 2.0:
                        last_no_frame_at = now
                        write_status("black_frame", "phone screencap is black; unlock/open camera preview", Path("latest-result.json"), Path("latest-answer.txt"))
                        if not args.simple_output:
                            print(time.strftime("[%H:%M:%S]"), f"BLACK FRAME    CAP: {capture_ms:.0f} ms    unlock/open camera preview", flush=True)
                            print("", flush=True)
                    if args.once:
                        print("BLACK_FRAME", flush=True)
                        return 2
                    time.sleep(args.poll)
                    continue

                if args.rotate_180 and capture_source[0] == "adb":
                    image = cv2.rotate(image, cv2.ROTATE_180)

                ocr_started = time.perf_counter()
                word, raw_text = ocr_word_from_image(image, crop, Path("latest-crop.png"), args.tesseract)
                ocr_ms = (time.perf_counter() - ocr_started) * 1000
                answer, score = judge(word, args.threshold)
                total_ms = (time.perf_counter() - started) * 1000

                now = time.perf_counter()
                if not word:
                    if now - last_preview_at > 5.0 and now - last_no_prompt_at > 2.0:
                        last_no_prompt_at = now
                        write_status("no_prompt", "question prompt not found in crop; adjust camera framing/zoom", Path("latest-result.json"), Path("latest-answer.txt"))
                        if not args.simple_output:
                            print(time.strftime("[%H:%M:%S]"), f"NO VALID PROMPT    CAP: {capture_ms:.0f} ms  OCR: {ocr_ms:.0f} ms  TOTAL: {total_ms:.0f} ms", flush=True)
                            print("             Check camera zoom/framing: the question word must fill the center area.", flush=True)
                            print("", flush=True)
                    if args.once:
                        print(f"NO_PROMPT {raw_text.strip()}", flush=True)
                        return 2
                    time.sleep(args.poll)
                    continue

                if args.once or crop is not None:
                    stable = (word, answer, score, "single-frame")
                else:
                    preview_observations.append((now, word, answer, score))
                    stable = stable_preview_choice(preview_observations, now)

                if stable:
                    stable_word, stable_answer, stable_score, stable_status = stable
                else:
                    time.sleep(args.poll)
                    continue

                if stable_word and stable_word != last_preview_word:
                    last_preview_word = stable_word
                    last_preview_at = now
                    result = {
                        "answer": stable_answer,
                        "word": stable_word,
                        "score": round(stable_score, 3),
                        "mode": "preview",
                        "status": stable_status,
                        "observations": [item[1] for item in preview_observations],
                        "rawText": raw_text.strip(),
                        "captureMs": round(capture_ms, 1),
                        "ocrMs": round(ocr_ms, 1),
                        "totalMs": round(total_ms, 1),
                        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    }
                    write_result(result, Path("latest-result.json"), Path("latest-answer.txt"))

                    if args.copy_answer:
                        subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{stable_answer.upper()}'"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

                    if args.simple_output:
                        print(f"{stable_answer.upper()} {stable_word}", flush=True)
                    else:
                        line = f"ANSWER: {stable_answer.upper():<3}  WORD: {stable_word:<16} CAP: {capture_ms:.0f} ms  OCR: {ocr_ms:.0f} ms  TOTAL: {total_ms:.0f} ms"
                        print(time.strftime("[%H:%M:%S]"), line, flush=True)
                        print("", flush=True)

                    if args.once:
                        return 0

                time.sleep(args.poll)
                continue

            found = latest_remote_photo(adb, args.serial, args.remote_dir)
            if found is None:
                time.sleep(args.poll)
                continue

            remote_ts, remote_path = found
            if remote_path == seen_path:
                time.sleep(args.poll)
                continue

            if not wait_remote_stable(adb, args.serial, remote_path):
                time.sleep(args.poll)
                continue

            seen_path = remote_path
            local_path = args.local_dir / Path(remote_path).name
            started = time.perf_counter()
            pull_started = time.perf_counter()
            pull_photo(adb, args.serial, remote_path, local_path)
            pull_ms = (time.perf_counter() - pull_started) * 1000

            ocr_started = time.perf_counter()
            word, raw_text = ocr_word(local_path, crop, Path("latest-crop.png"), args.tesseract)
            ocr_ms = (time.perf_counter() - ocr_started) * 1000
            answer, score = judge(word, args.threshold)
            total_ms = (time.perf_counter() - started) * 1000

            result = {
                "answer": answer,
                "word": word,
                "score": round(score, 3),
                "image": str(local_path),
                "rawText": raw_text.strip(),
                "pullMs": round(pull_ms, 1),
                "ocrMs": round(ocr_ms, 1),
                "totalMs": round(total_ms, 1),
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            write_result(result, Path("latest-result.json"), Path("latest-answer.txt"))

            if args.copy_answer:
                subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{answer.upper()}'"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

            if args.simple_output:
                print(f"{answer.upper()} {word}", flush=True)
            else:
                line = f"ANSWER: {answer.upper():<3}  WORD: {word:<16} PULL: {pull_ms:.0f} ms  OCR: {ocr_ms:.0f} ms  TOTAL: {total_ms:.0f} ms"
                print(time.strftime("[%H:%M:%S]"), line, flush=True)
                print("", flush=True)
            if args.once:
                return 0
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}", flush=True)
            time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
