import json
from pathlib import Path
from datetime import datetime

from search_engine import search_with_confidence
from suggestion import get_gaps


# =========================
# НАСТРОЙКИ
# =========================

FAQ_FILE = "faq.json"

# Минимальный счет который должен набрать запрос чтобы ответ из FAQ был выведен
MIN_SCORE_TO_ACCEPT = 2

# Порог уверенности
CONFIDENCE_THRESHOLD = 4


# =========================
# НАСТРОЙКИ ХРАНИЛИЩА
# =========================

SUGGESTIONS_FILE = Path("suggestions.jsonl")


# =========================
# РАБОТА С FAQ
# =========================

#  Загрузка FAQ
def load_faq(filename: str = FAQ_FILE) -> list[dict]:
    file_path = Path(filename)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл FAQ не найден: {filename}")

    with open(file_path, "r", encoding="utf-8") as file:
        faq_data = json.load(file)

    if not isinstance(faq_data, list):
        raise ValueError("Некорректный формат faq.json. Ожидается список объектов.")

    return faq_data


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


# =========================
# ВСПОМОГАТЕЛЬНОЕ
# =========================


# Выводит limit первых вопросов в консоль
def print_open_questions(limit: int = 10) -> None:
    questions = get_open_questions(limit=limit)

    if not questions:
        print("\nСейчас нет открытых вопросов без ответа.\n")
        return

    print("\nОткрытые вопросы:")
    for i, item in enumerate(questions, start=1):
        print(f"{i}. {item['question']}")
    print()


# Реакция на пустой ввод от пользователя
def ask_non_empty(prompt: str) -> str:
    while True:
        text = input(prompt).strip()
        if text:
            return text
        print("Пустой ввод. Попробуй еще раз.")


# =========================
# ФУНКЦИИ КОНСОЛЬНОГО ИНТЕРФЕЙСА
# =========================

# Поиск по FAQ
def search_question_flow(faq_entries: list[dict], user_id: str, username: str | None):
    question = ask_non_empty("\nВведите вопрос: ")

    search_result = search_with_confidence(
        query=question,
        faq_data=faq_entries,
        top_n=3,
        confidence_threshold=CONFIDENCE_THRESHOLD
    )

    results = search_result["results"]
    confident = search_result["confident"]

    # Уверенно нашли ответ
    if results and confident:
        print("\nВот что удалось найти:\n")
        for i, item in enumerate(results, start=1):
            if item["score"] >= MIN_SCORE_TO_ACCEPT:
                print(f"{i}. {item.get('answer', 'Ответ отсутствует')}")
        print()
        return

    # Если поиск неуверенный или вообще ничего не найдено —
    # сохраняем это как потенциальный пробел в FAQ

    if results:
        print("\nНашлись похожие ответы, но я не уверен, что это именно то, что нужно:\n")
        for i, item in enumerate(results, start=1):
            print(f"{i}. {item.get('answer', 'Ответ отсутствует')} (score={item['score']})")
        print()
    else:
        print("\nЯ не нашёл подходящий ответ в FAQ.\n")

    print("Этот запрос сохранён как возможный пробел в FAQ.\n")

    choice = input("Отправить этот вопрос команде на добавление? (да/НЕТ): ").strip().lower()

    if choice not in ("да", "д", "yes", "y"):
        print("\nХорошо, вопрос не отправлен команде.\n")
        return

    if is_similar_question_already_saved(question):
        print("\nТакой вопрос уже был отправлен ранее.\n")
        return

    save_question_only(user_id, username, question)
    print("\nСпасибо. Вопрос сохранён и отправлен команде на рассмотрение.\n")


# Пользователь предлагает новый вопрос без ответа
def new_question_only_flow(user_id: str, username: str | None):
    question = ask_non_empty("\nНапиши вопрос, который стоит добавить в FAQ: ")

    if is_similar_question_already_saved(question):
        print("\nТакой вопрос уже есть среди отправленных.\n")
        return

    save_question_only(user_id, username, question)
    print("\nСпасибо. Новый вопрос сохранён и отправлен команде.\n")


# Пользователь предлагает новый вопрос без ответа
def new_question_with_answer_flow(user_id: str, username: str | None):
    question = ask_non_empty("\nНапиши новый вопрос, который стоит добавить в FAQ: ")
    answer = ask_non_empty("Теперь напиши свой вариант ответа на этот вопрос: ")

    save_question_with_answer(
        user_id=user_id,
        username=username,
        question=question,
        suggested_answer=answer
    )

    print("\nСпасибо. Вопрос с предложенным ответом сохранён и отправлен команде на проверку.\n")


def answer_open_question_flow(user_id: str, username: str | None):
    questions = get_open_questions(limit=10)

    if not questions:
        print("\nСейчас нет открытых вопросов без ответа.\n")
        return

    print_open_questions(limit=10)

    while True:
        raw = input("Напиши номер вопроса, на который хочешь предложить ответ: ").strip()

        if not raw.isdigit():
            print("Нужно ввести именно номер, например: 1")
            continue

        index = int(raw)

        if index < 1 or index > len(questions):
            print("Некорректный номер вопроса.")
            continue

        selected = questions[index - 1]
        break

    print(f"\nВыбран вопрос:\n{selected['question']}\n")
    suggested_answer = ask_non_empty("Теперь напиши свой вариант ответа: ")

    add_answer_to_existing_question(
        selected["_line_number"],
        user_id=user_id,
        username=username,
        suggested_answer=suggested_answer
    )
    print("\nСпасибо. Твой вариант ответа сохранён и отправлен команде на проверку.\n")


# Вывод похожих запросов
def print_faq_gaps(limit: int = 10) -> None:
    gaps = get_gaps(str(SUGGESTIONS_FILE), top_n=limit)

    if not gaps:
        print("\nПока нет сохранённых запросов FAQ.\n")
        return

    print("\nТоп запросов FAQ:")
    for i, item in enumerate(gaps, start=1):
        print(f"{i}. {item['query']} — {item['count']} шт.")
        examples = item.get("examples", [])
        if examples:
            print(f"   Примеры: {'; '.join(examples)}")
    print()


# Меню помощи команде
def help_team_menu(user_id: str, username: str | None):
    while True:
        print("=== Меню помощи команде ===")
        print("1. Предложить новый вопрос")
        print("2. Предложить новый вопрос с ответом")
        print("3. Предложить ответ на открытый вопрос")
        print("0. Назад")

        choice = input("Выбери действие: ").strip()

        if choice == "1":
            new_question_only_flow(user_id, username)
        elif choice == "2":
            new_question_with_answer_flow(user_id, username)
        elif choice == "3":
            answer_open_question_flow(user_id, username)
        elif choice == "0":
            print()
            return
        else:
            print("Некорректный ввод.\n")


# =========================
# MAIN
# =========================

def main():
    ensure_storage()

    try:
        faq_entries = load_faq(FAQ_FILE)
    except Exception as e:
        print(f"Ошибка загрузки FAQ: {e}")
        return

    print("Добро пожаловать в программу для поиска по FAQ.")
    print("Можно искать ответы, предлагать новые вопросы и ответы.")
    print()

    username = input("Введите имя пользователя (можно оставить пустым): ").strip() or None
    user_id = username if username else "local_user"

    while True:
        print("=== Главное меню ===")
        print("1. Найти ответ в FAQ")
        print("2. Помочь команде")
        print("3. Показать частые запросы FAQ")
        print("0. Выход")

        choice = input("Выбери действие: ").strip()

        if choice == "1":
            search_question_flow(faq_entries, user_id, username)
        elif choice == "2":
            help_team_menu(user_id, username)
        elif choice == "3":
            print_faq_gaps(limit=10)
        elif choice == "0":
            print("Выход из программы.")
            break
        else:
            print("Некорректный ввод.\n")


if __name__ == "__main__":
    main()
