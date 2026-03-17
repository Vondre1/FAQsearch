import json
from datetime import datetime
from pathlib import Path


# =========================
# НАСТРОЙКИ ХРАНИЛИЩА
# =========================

SUGGESTIONS_FILE = Path("suggestions.jsonl")


# =========================
# РАБОТА С ХРАНИЛИЩЕМ
# =========================

# Создает файл suggestions.jsonl если его еще нет
def ensure_storage() -> None:
    SUGGESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SUGGESTIONS_FILE.exists():
        SUGGESTIONS_FILE.touch()


# Сохранение вопроса без ответа
def save_question_only(user_id: int | str, username: str | None, question: str) -> Path:
    ensure_storage()

    data = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user": username or str(user_id),
        "type": "new_question",
        "question": question,
        "answer": None
    }

    with open(SUGGESTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

    return SUGGESTIONS_FILE


# Сохранение вопроса с ответом
def save_question_with_answer(
    user_id: int | str,
    username: str | None,
    question: str,
    suggested_answer: str,
) -> Path:
    ensure_storage()

    data = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user": username or str(user_id),
        "type": "new_question_with_answer",
        "question": question,
        "answer": suggested_answer
    }

    with open(SUGGESTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

    return SUGGESTIONS_FILE


# Загрузка всех вопросов без ответа
def load_pending_questions_without_answers() -> list[dict]:
    ensure_storage()

    all_items = []
    answered_questions = set()

    with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            question = data.get("question", "").strip().lower()
            item_type = data.get("type")

            # Если кто-то предложил ответ на открытый вопрос,
            # такой вопрос больше не считаем открытым
            if item_type == "answer_open_question" and question:
                answered_questions.add(question)

            all_items.append((line_number, data))

    items = []

    for line_number, data in all_items:
        question = data.get("question", "").strip().lower()

        if data.get("type") == "new_question" and not data.get("answer"):
            if question not in answered_questions:
                data["_line_number"] = line_number
                items.append(data)

    items.sort(key=lambda x: x.get("timestamp", ""))
    return items


# Добавляет ответ к уже существующему вопросу
def add_answer_to_existing_question(
    line_number: int,
    user_id: int | str,
    username: str | None,
    suggested_answer: str
) -> Path:
    ensure_storage()

    lines = SUGGESTIONS_FILE.read_text(encoding="utf-8").splitlines()
    if line_number < 1 or line_number > len(lines):
        raise ValueError("Некорректный номер записи.")

    raw_line = lines[line_number - 1].strip()
    if not raw_line:
        raise ValueError("Выбранная запись пуста.")

    data = json.loads(raw_line)

    new_data = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user": username or str(user_id),
        "type": "answer_open_question",
        "question": data.get("question"),
        "answer": suggested_answer
    }

    with open(SUGGESTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(new_data, ensure_ascii=False) + "\n")

    return SUGGESTIONS_FILE


# Если есть полностью одинаковые вопросы от пользователей, новый не сохраняется
# проверка пока глупая, ес вопрос хоть немного отличается, его добавят
def is_similar_question_already_saved(question: str) -> bool:
    normalized = question.strip().lower()

    ensure_storage()

    with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if data.get("question", "").strip().lower() == normalized:
                return True

    return False


# Возвращение limit первых нерешенных вопросов (по умолчанию 10)
def get_open_questions(limit: int = 10) -> list[dict]:
    return load_pending_questions_without_answers()[:limit]