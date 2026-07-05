import argparse
import json
import re
import time
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from wordfreq import zipf_frequency

from det_word_bank import load_det_overrides


DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
STOP_TOKENS = {
    "is", "this", "a", "real", "english", "word", "yes", "no", "ves",
    "incorrect", "correct", "answer", "got", "it", "question",
}
DET_OVERRIDES = load_det_overrides()


def normalize_token(text: str) -> str:
    return text.strip("'").lower()


def is_prompt_token(token: str) -> bool:
    lower = token.lower()
    if lower in STOP_TOKENS:
        return True
    return any(part in lower for part in ("english", "word", "this", "real"))


def judge_word(word: str, threshold: float) -> tuple[str, float]:
    score = zipf_frequency(word, "en")
    normalized = normalize_token(word)
    if normalized in DET_OVERRIDES:
        return ("yes" if DET_OVERRIDES[normalized] else "no"), score
    return ("yes" if score >= threshold else "no"), score


def crop_question_area(image, crop: tuple[float, float, float, float]):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = crop
    return image[int(h * y1):int(h * y2), int(w * x1):int(w * x2)]


def preprocess_for_ocr(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresholded = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresholded


def ocr_word(image_path: Path, crop: tuple[float, float, float, float], save_crop: Path | None) -> tuple[str, str]:
    image_data = np.fromfile(str(image_path), dtype=np.uint8)
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    cropped = crop_question_area(image, crop)
    prepared = preprocess_for_ocr(cropped)
    if save_crop:
        save_crop.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(save_crop), prepared)

    config = "--psm 6 --oem 1 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    raw_text = pytesseract.image_to_string(prepared, lang="eng", config=config)
    tokens = [normalize_token(x) for x in TOKEN_RE.findall(raw_text)]
    candidates = [
        token for token in tokens
        if 2 <= len(token) <= 24 and not is_prompt_token(token)
    ]

    if not candidates:
        return "", raw_text

    return candidates[-1], raw_text


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR a Duolingo real-word practice photo and answer yes/no.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--threshold", type=float, default=1.35)
    parser.add_argument("--crop", default="0.30,0.42,0.75,0.60", help="x1,y1,x2,y2 fractions")
    parser.add_argument("--tesseract", default=DEFAULT_TESSERACT)
    parser.add_argument("--json-out", type=Path, default=Path("latest-result.json"))
    parser.add_argument("--txt-out", type=Path, default=Path("latest-answer.txt"))
    parser.add_argument("--save-crop", type=Path, default=Path("latest-crop.png"))
    args = parser.parse_args()

    pytesseract.pytesseract.tesseract_cmd = args.tesseract
    crop = tuple(float(part.strip()) for part in args.crop.split(","))
    if len(crop) != 4:
        raise ValueError("--crop must have 4 comma-separated numbers")

    started = time.perf_counter()
    word, raw_text = ocr_word(args.image, crop, args.save_crop)
    if word:
        answer, score = judge_word(word, args.threshold)
    else:
        answer, score = "unknown", 0.0

    elapsed_ms = (time.perf_counter() - started) * 1000
    result = {
        "answer": answer,
        "word": word,
        "score": round(score, 3),
        "image": str(args.image),
        "rawText": raw_text.strip(),
        "elapsedMs": round(elapsed_ms, 1),
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    args.txt_out.write_text(answer.upper(), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
