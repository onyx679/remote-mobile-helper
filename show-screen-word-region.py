import json
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab


CONFIG_PATH = Path("screen-word-region.json")


def capture_virtual_screen():
    image = ImageGrab.grab(all_screens=True)
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def read_region() -> tuple[int, int, int, int]:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    region = data["screenRegion"]
    return int(region["x"]), int(region["y"]), int(region["width"]), int(region["height"])


def fit_for_display(image, max_w=1400, max_h=900):
    height, width = image.shape[:2]
    scale = min(max_w / width, max_h / height, 1.0)
    return cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA), scale


def main() -> int:
    if not CONFIG_PATH.exists():
        print("No screen-word-region.json. Run select-screen-word-region.cmd first.")
        return 1

    frame = capture_virtual_screen()
    x, y, width, height = read_region()
    cv2.rectangle(frame, (x, y), (x + width, y + height), (0, 255, 255), 4)
    cv2.putText(frame, "WORD OCR", (x, max(35, y - 12)), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3, cv2.LINE_AA)
    display, _ = fit_for_display(frame)

    window = "Screen word OCR region - press any key to close"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.imshow(window, display)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
