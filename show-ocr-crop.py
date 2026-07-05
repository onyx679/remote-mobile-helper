import argparse
import re
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np


DEFAULT_SERIAL = "adb-2252475e-baGT88._adb-tls-connect._tcp"


def find_adb() -> str:
    candidates = [
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages/Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe/scrcpy-win64-v4.0/adb.exe",
        Path("adb.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "adb"


def read_crop(ps1_path: Path) -> tuple[float, float, float, float]:
    text = ps1_path.read_text(encoding="utf-8")
    match = re.search(r'\[string\]\$Crop\s*=\s*"([^"]+)"', text)
    if not match:
        raise RuntimeError(f"Could not find Crop parameter in {ps1_path}")
    parts = [float(part.strip()) for part in match.group(1).split(",")]
    if len(parts) != 4:
        raise RuntimeError(f"Invalid crop: {match.group(1)}")
    return tuple(parts)


def capture_screen(adb: str, serial: str):
    completed = subprocess.run(
        [adb, "-s", serial, "exec-out", "screencap", "-p"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=8,
        check=False,
    )
    data = np.frombuffer(completed.stdout, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def draw_crop(image, crop: tuple[float, float, float, float]):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = crop
    p1 = (int(w * x1), int(h * y1))
    p2 = (int(w * x2), int(h * y2))
    cv2.rectangle(image, p1, p2, (0, 255, 255), 4)
    cv2.putText(
        image,
        "OCR",
        (p1[0], max(35, p1[1] - 12)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (0, 255, 255),
        3,
        cv2.LINE_AA,
    )
    return image


def fit_window(image, max_w: int, max_h: int):
    h, w = image.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def main() -> int:
    parser = argparse.ArgumentParser(description="Show current OCR crop rectangle on phone screen.")
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--ps1", type=Path, default=Path("watch-phone-answer-fast.ps1"))
    parser.add_argument("--poll", type=float, default=0.4)
    parser.add_argument("--no-rotate-180", action="store_true")
    args = parser.parse_args()

    adb = find_adb()
    window = "OCR crop preview - press Q/ESC to close"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    while True:
        crop = read_crop(args.ps1)
        image = capture_screen(adb, args.serial)
        if image is not None:
            if not args.no_rotate_180:
                image = cv2.rotate(image, cv2.ROTATE_180)
            image = draw_crop(image, crop)
            cv2.imshow(window, fit_window(image, 1000, 850))
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q"), ord("Q")):
            break
        time.sleep(args.poll)

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
