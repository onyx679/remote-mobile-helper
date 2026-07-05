import argparse
import re
import sys
import time

from wordfreq import zipf_frequency

from det_word_bank import load_det_overrides


WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
DET_OVERRIDES = load_det_overrides()


def normalize_word(text: str) -> str:
    match = WORD_RE.search(text.strip())
    return match.group(0).strip("'").lower() if match else ""


def is_likely_english_word(word: str, threshold: float) -> tuple[bool, float]:
    normalized = normalize_word(word)
    if not normalized:
        return False, 0.0

    score = zipf_frequency(normalized, "en")
    if normalized in DET_OVERRIDES:
        return DET_OVERRIDES[normalized], score
    return score >= threshold, score


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast local English-word judgment.")
    parser.add_argument("word", nargs="?", help="Word to judge. If omitted, read words from stdin.")
    parser.add_argument("--threshold", type=float, default=1.35)
    parser.add_argument("--label", action="store_true", help="Print TRUE/FALSE instead of yes/no.")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    def output(text: str) -> None:
        start = time.perf_counter()
        normalized = normalize_word(text)
        result, score = is_likely_english_word(normalized, args.threshold)
        answer = "TRUE" if result else "FALSE"
        if not args.label:
            answer = "yes" if result else "no"

        if args.debug:
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(f"{answer}\tword={normalized}\tscore={score:.3f}\tms={elapsed_ms:.2f}", flush=True)
        else:
            print(answer, flush=True)

    if args.word is not None:
        output(args.word)
        return 0

    for line in sys.stdin:
        if line.strip():
            output(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
