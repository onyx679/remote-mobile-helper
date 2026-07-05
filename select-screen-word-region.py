import json
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab


CONFIG_PATH = Path("screen-word-region.json")
PS1_PATH = Path("watch-phone-answer-fast.ps1")
REGION_PADDING = 0


def capture_virtual_screen():
    image = ImageGrab.grab(all_screens=True)
    frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    return frame, 0, 0


def fit_for_display(image, max_w=1400, max_h=900):
    height, width = image.shape[:2]
    scale = min(max_w / width, max_h / height, 1.0)
    display = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    return display, scale


def update_watch_script(region: tuple[int, int, int, int]) -> None:
    text = PS1_PATH.read_text(encoding="utf-8")
    screen_region = ",".join(str(part) for part in region)
    text = re.sub(
        r'(\[string\]\$ScreenRegion\s*=\s*)"[^"]*"',
        rf'\1"{screen_region}"',
        text,
        count=1,
    )
    text = re.sub(
        r'(\[string\]\$Crop\s*=\s*)"[^"]*"',
        r'\1"0.0,0.0,1.0,1.0"',
        text,
        count=1,
    )
    PS1_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    frame, origin_x, origin_y = capture_virtual_screen()
    display, scale = fit_for_display(frame)

    window = "Drag word area, then press ENTER/SPACE. Press C or ESC to cancel."
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    roi = cv2.selectROI(window, display, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()

    x, y, width, height = roi
    if width <= 0 or height <= 0:
        print("CANCELLED")
        return 1

    raw_x = int(round(x / scale))
    raw_y = int(round(y / scale))
    raw_w = int(round(width / scale))
    raw_h = int(round(height / scale))

    frame_h, frame_w = frame.shape[:2]
    padded_x = max(0, raw_x - REGION_PADDING)
    padded_y = max(0, raw_y - REGION_PADDING)
    padded_x2 = min(frame_w, raw_x + raw_w + REGION_PADDING)
    padded_y2 = min(frame_h, raw_y + raw_h + REGION_PADDING)

    sx = padded_x + origin_x
    sy = padded_y + origin_y
    sw = padded_x2 - padded_x
    sh = padded_y2 - padded_y
    region = (sx, sy, sw, sh)

    crop = frame[padded_y:padded_y2, padded_x:padded_x2]
    cv2.imwrite("latest-selected-screen-region.png", crop)

    CONFIG_PATH.write_text(
        json.dumps(
            {
                "screenRegion": {"x": sx, "y": sy, "width": sw, "height": sh},
                "watchScript": str(PS1_PATH),
                "updatedCrop": "0.0,0.0,1.0,1.0",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    update_watch_script(region)

    print(f"SCREEN_REGION={sx},{sy},{sw},{sh}")
    print(f"Saved: {CONFIG_PATH}")
    print("Preview saved: latest-selected-screen-region.png")
    print(f"Updated: {PS1_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
