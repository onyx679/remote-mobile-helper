import argparse
import re
import subprocess
import sys
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


def capture_screen(adb: str, serial: str):
    completed = subprocess.run(
        [adb, "-s", serial, "exec-out", "screencap", "-p"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="ignore") or "screencap failed")
    data = np.frombuffer(completed.stdout, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("screencap returned an undecodable image")
    return image


def update_ps1_crop(ps1_path: Path, crop: str) -> None:
    text = ps1_path.read_text(encoding="utf-8")
    updated = re.sub(
        r'(\[string\]\$Crop\s*=\s*)"[^"]*"',
        rf'\1"{crop}"',
        text,
        count=1,
    )
    if updated == text:
        raise RuntimeError(f"Could not find Crop parameter in {ps1_path}")
    ps1_path.write_text(updated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Select OCR crop area from the current phone screen.")
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--ps1", type=Path, default=Path("watch-phone-answer-fast.ps1"))
    parser.add_argument("--no-rotate-180", action="store_true")
    args = parser.parse_args()

    adb = find_adb()
    image = capture_screen(adb, args.serial)
    if not args.no_rotate_180:
        image = cv2.rotate(image, cv2.ROTATE_180)

    height, width = image.shape[:2]
    max_w, max_h = 1100, 850
    scale = min(max_w / width, max_h / height, 1.0)
    display = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)

    window = "Drag OCR area, then press ENTER/SPACE. Press C or ESC to cancel."
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    roi = cv2.selectROI(window, display, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()

    x, y, w, h = roi
    if w <= 0 or h <= 0:
        print("CANCELLED")
        return 1

    x1 = x / scale
    y1 = y / scale
    x2 = (x + w) / scale
    y2 = (y + h) / scale
    crop = f"{x1 / width:.4f},{y1 / height:.4f},{x2 / width:.4f},{y2 / height:.4f}"

    crop_image = image[int(y1):int(y2), int(x1):int(x2)]
    cv2.imwrite("latest-selected-crop.png", crop_image)
    update_ps1_crop(args.ps1, crop)

    print(f"OCR_CROP={crop}")
    print(f"Updated: {args.ps1}")
    print("Preview saved: latest-selected-crop.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
