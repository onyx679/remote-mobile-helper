import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from judge_english_word import is_likely_english_word, normalize_word


API_URL = "https://api.51ddedu.com/question-service/duolingoQuestion/getQuestionList"


def judge_word(word: str, threshold: float) -> tuple[bool, str, float]:
    normalized = normalize_word(word)
    predicted, score = is_likely_english_word(normalized, threshold)
    return predicted, normalized, score


def post_json(payload: dict, timeout: float) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://det.91ddedu.com",
            "Referer": "https://det.91ddedu.com/",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def question_list_payload(page_no: int, page_size: int) -> dict:
    return {
        "category": 0,
        "sortType": 2,
        "difficulty": 0,
        "collectColorType": 0,
        "templateType": 0,
        "questionType": 15,
        "practiceType": 0,
        "markColorType": 0,
        "newQuestionTag": 0,
        "realOrFake": 0,
        "pageNo": page_no,
        "pageSize": page_size,
    }


def fetch_page(page_no: int, page_size: int, timeout: float) -> tuple[int, int, list[dict]]:
    result = post_json(question_list_payload(page_no, page_size), timeout)
    if result.get("code") != 200:
        raise RuntimeError(f"API returned code={result.get('code')} msg={result.get('msg')!r}")
    data = result.get("data") or {}
    total = int(data.get("total") or 0)
    return page_no, total, data.get("list") or []


def fetch_questions(page_size: int, timeout: float, delay: float, workers: int) -> list[dict]:
    page_no, total, batch = fetch_page(1, page_size, timeout)
    if not batch:
        return []

    effective_page_size = len(batch)
    page_count = (total + effective_page_size - 1) // effective_page_size
    pages: dict[int, list[dict]] = {page_no: batch}
    print(f"fetched page=1 rows={len(batch)} total_rows={len(batch)}/{total}", flush=True)

    if workers <= 1:
        for page_no in range(2, page_count + 1):
            if delay:
                time.sleep(delay)
            _, _, batch = fetch_page(page_no, page_size, timeout)
            pages[page_no] = batch
            done = sum(len(rows) for rows in pages.values())
            print(f"fetched page={page_no} rows={len(batch)} total_rows={done}/{total}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for page_no in range(2, page_count + 1):
                if delay:
                    time.sleep(delay)
                futures[executor.submit(fetch_page, page_no, page_size, timeout)] = page_no
            for future in as_completed(futures):
                page_no, _, batch = future.result()
                pages[page_no] = batch
                done = sum(len(rows) for rows in pages.values())
                print(f"fetched page={page_no} rows={len(batch)} total_rows={done}/{total}", flush=True)

    questions: list[dict] = []
    for page_no in sorted(pages):
        questions.extend(pages[page_no])
    return questions[:total]


def score_question(question: dict, threshold: float) -> dict:
    word = str(question.get("word") or "").strip()
    expected = int(question.get("correct") or 0) == 1
    predicted, normalized, score = judge_word(word, threshold)
    return {
        "questionId": question.get("questionId"),
        "word": word,
        "normalized": normalized,
        "expected": "yes" if expected else "no",
        "predicted": "yes" if predicted else "no",
        "score": round(score, 4),
        "difficulty": question.get("difficulty"),
        "occurrence": question.get("occurrence"),
        "newQuestionTag": question.get("newQuestionTag"),
        "is_error": expected != predicted,
    }


def summarize(rows: list[dict]) -> dict:
    tp = sum(1 for row in rows if row["expected"] == "yes" and row["predicted"] == "yes")
    tn = sum(1 for row in rows if row["expected"] == "no" and row["predicted"] == "no")
    fp = sum(1 for row in rows if row["expected"] == "no" and row["predicted"] == "yes")
    fn = sum(1 for row in rows if row["expected"] == "yes" and row["predicted"] == "no")
    total = len(rows)
    return {
        "total": total,
        "correct": tp + tn,
        "accuracy": round((tp + tn) / total, 4) if total else 0,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def threshold_sweep(questions: list[dict], start: float, stop: float, step: float) -> list[dict]:
    results = []
    count = int(round((stop - start) / step)) + 1
    for i in range(count):
        threshold = round(start + i * step, 4)
        rows = [score_question(question, threshold) for question in questions]
        summary = summarize(rows)
        summary["threshold"] = threshold
        results.append(summary)
    return sorted(results, key=lambda row: (-row["accuracy"], row["fp"] + row["fn"], row["threshold"]))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local English word judge against det.91ddedu.com word-bank answers.")
    parser.add_argument("--threshold", type=float, default=2.2)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cache", type=Path, default=Path("det-read-and-select-questions.json"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--errors-csv", type=Path, default=Path("det-word-judge-errors.csv"))
    parser.add_argument("--all-csv", type=Path, default=Path("det-word-judge-results.csv"))
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()

    if args.cache.exists() and not args.refresh:
        questions = json.loads(args.cache.read_text(encoding="utf-8"))
    else:
        try:
            questions = fetch_questions(args.page_size, args.timeout, args.delay, args.workers)
        except (HTTPError, URLError, TimeoutError) as error:
            raise SystemExit(f"Failed to fetch DET word bank: {error}") from error
        args.cache.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = [score_question(question, args.threshold) for question in questions]
    errors = [row for row in rows if row["is_error"]]
    write_csv(args.all_csv, rows)
    write_csv(args.errors_csv, errors)

    summary = summarize(rows)
    summary["threshold"] = args.threshold
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"wrote {args.all_csv} and {args.errors_csv}", flush=True)

    if args.sweep:
        print("top threshold sweep results:", flush=True)
        for row in threshold_sweep(questions, 0.5, 4.0, 0.05)[:12]:
            print(json.dumps(row, ensure_ascii=False, separators=(",", ":")), flush=True)

    false_positives = [row for row in errors if row["expected"] == "no"][:25]
    false_negatives = [row for row in errors if row["expected"] == "yes"][:25]
    print("sample false positives:", json.dumps(false_positives, ensure_ascii=False), flush=True)
    print("sample false negatives:", json.dumps(false_negatives, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
