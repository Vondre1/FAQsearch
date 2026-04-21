import json
from collections import Counter
from pathlib import Path

from search_engine import split_words


SUGGESTIONS_FILE = Path("suggestions.jsonl")


def ensure_suggestions_storage() -> None:
    SUGGESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SUGGESTIONS_FILE.exists():
        SUGGESTIONS_FILE.touch()


def save_suggestion(query: str, timestamp: str) -> None:
    """
    Дописывает вопрос в suggestions.jsonl
    """
    ensure_suggestions_storage()

    query = query.strip()
    if not query:
        return

    record = {
        "timestamp": timestamp,
        "user": "system",
        "type": "new_question",
        "question": query,
        "answer": None,
    }

    with open(SUGGESTIONS_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def questions_are_similar(query1: str, query2: str, threshold: float = 0.5) -> bool:
    """
    Считает вопросы похожими, если у них достаточно большое пересечение по словам
    """
    words1 = split_words(query1)
    words2 = split_words(query2)

    if not words1 or not words2:
        return False

    common_words = words1 & words2
    similarity = len(common_words) / min(len(words1), len(words2))

    return similarity >= threshold


def get_gaps(path: str | Path = SUGGESTIONS_FILE, top_n: int = 10) -> list[dict]:
    """
    Читает suggestions.jsonl, группирует похожие вопросы и возвращает топ-N по частоте

    Формат результата:
    [
        {
            "query": "когда сдавать лабу",
            "count": 5,
            "examples": [
                "когда сдавать лабу",
                "до какого числа лабораторная",
                "какой дедлайн у лабы"
            ]
        }
    ]
    """
    file_path = Path(path)
    records = []

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                record_type = record.get("type")
                query = str(record.get("query") or record.get("question") or "").strip()
                timestamp = record.get("timestamp")

                if record_type == "answer_open_question":
                    continue

                if query:
                    records.append({
                        "query": query,
                        "timestamp": timestamp
                    })
    except FileNotFoundError:
        return []

    groups = []

    for record in records:
        query = record["query"]
        placed = False

        for group in groups:
            if questions_are_similar(query, group["query"]):
                group["queries"].append(query)
                group["count"] += 1
                placed = True
                break

        if not placed:
            groups.append({
                "query": query,
                "queries": [query],
                "count": 1
            })

    result = []

    for group in groups:
        query_counter = Counter(group["queries"])
        most_common_query = query_counter.most_common(1)[0][0]
        examples = [query for query, _ in query_counter.most_common(3)]

        result.append({
            "query": most_common_query,
            "count": group["count"],
            "examples": examples
        })

    result.sort(key=lambda item: item["count"], reverse=True)
    return result[:top_n]
