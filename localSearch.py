import json
import re
from datetime import datetime
from pathlib import Path

import yaml


# =========================
# НАСТРОЙКИ
# =========================

FAQ_FILE = "faq.yaml"

# Минимальная длина слова, которое мы вообще учитываем при поиске (пропуск предлогов)
MIN_WORD_LEN = 3
# Минимальный счет который должен набрать запрос чтобы ответ из FAQ был выведен
MIN_SCORE_TO_ACCEPT = 2


BASE_DIR = Path("pending_questions")
NO_ANSWER_DIR = BASE_DIR / "no_answer"
WITH_ANSWER_DIR = BASE_DIR / "with_answer"


# =========================
# РАБОТА С FAQ
# =========================

# Разделение ввода на отдельные слова и приведение к нижнему регистру, отбрасывает слова с длиной меньше MIN_WORD_LEN
def split_words(text: str) -> set[str]:
    words = re.findall(r"[а-яА-Яa-zA-Z0-9ёЁ]+", text.lower())
    return {word for word in words if len(word) >= MIN_WORD_LEN}


#  Загрузка FAQ
def load_faq(filename: str = FAQ_FILE) -> list[dict]:
    file_path = Path(filename)

    if not file_path.exists():
        raise FileNotFoundError(f"Файл FAQ не найден: {filename}")

    with open(file_path, "r", encoding="utf-8") as file:
        faq_data = yaml.safe_load(file)

    if not faq_data or "data" not in faq_data:
        raise ValueError("Некорректный формат faq.yaml. Ожидается ключ 'data'.")

    return faq_data["data"]


# Сравнивает слова введенные пользователем и ключевые слова из FAQ
# Вес совпадения:
# 4 - точное совпадение
# 3 - частичное совпадение
# 2 - часть слова (начало) совпадает с ключевым
# 0 - нет совпадения
def compare_word_and_keyword(word: str, keyword_part: str) -> int:
    if word == keyword_part:
        return 4

    if word in keyword_part or keyword_part in word:
        return 3

    min_prefix_len = 3

    if len(word) >= min_prefix_len and len(keyword_part) >= min_prefix_len:
        if word[:min_prefix_len] == keyword_part[:min_prefix_len]:
            return 2

    return 0


# Подсчет количества очков для поиска лучшего совпадения
def calculate_score(question_words: set[str], keywords: list[str]) -> int:
    total_score = 0
    used_keyword_parts = set()

    for keyword in keywords:
        keyword_parts = split_words(keyword)

        for part in keyword_parts:
            best_score_for_part = 0

            for word in question_words:
                score = compare_word_and_keyword(word, part)
                if score > best_score_for_part:
                    best_score_for_part = score

            if best_score_for_part > 0 and part not in used_keyword_parts:
                total_score += best_score_for_part
                used_keyword_parts.add(part)

    return total_score


# Поиск лучших совпадений по базе FAQ
def search_top_faq(question: str, faq_entries: list[dict], top_n: int = 3) -> list[tuple[int, dict]]:
    question_words = split_words(question)
    results = []

    for entry in faq_entries:
        score = calculate_score(question_words, entry.get("keywords", []))
        results.append((score, entry))

    results.sort(key=lambda x: x[0], reverse=True)
    return results[:top_n]


# Отсечение неподходящих элементов (количество набранных очков < 2 || разница в очках с лучшим вариантом > 1, вывод первых 5 лучших вариантов)
def search_matching_faq(question: str, faq_entries: list[dict], min_score: int = MIN_SCORE_TO_ACCEPT, top_n: int = 5):
    results = search_top_faq(question, faq_entries, top_n=top_n)
    results = [(score, entry) for score, entry in results if score >= min_score]

    if not results:
        return []

    best_score = results[0][0]
    return [(score, entry) for score, entry in results if score >= best_score - 1]


# =========================
# РАБОТА С ХРАНИЛИЩЕМ
# =========================

# Создаем папки для запросов пользователей (то что не нашлоось в FAQ)
def ensure_dirs() -> None:
    NO_ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    WITH_ANSWER_DIR.mkdir(parents=True, exist_ok=True)


# Генерирует уникальное имя файла
def make_filename(user_id: int | str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{user_id}_{timestamp}.json"


# Сохранение вопроса без ответа
def save_question_only(user_id: int | str, username: str | None, question: str) -> Path:
    ensure_dirs()

    data = {
        "user_id": user_id,
        "username": username,
        "question": question,
        "created_at": datetime.now().isoformat(),
        "status": "new"
    }

    filepath = NO_ANSWER_DIR / make_filename(user_id)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


# Сохранение вопроса с ответом
def save_question_with_answer(
    user_id: int | str,
    username: str | None,
    question: str,
    suggested_answer: str,
) -> Path:
    ensure_dirs()

    data = {
        "user_id": user_id,
        "username": username,
        "question": question,
        "suggested_answer": suggested_answer,
        "created_at": datetime.now().isoformat(),
        "status": "new"
    }

    filepath = WITH_ANSWER_DIR / make_filename(user_id)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


# Загрузка всех вопросов без ответа
def load_pending_questions_without_answers() -> list[dict]:
    ensure_dirs()
    items = []

    for file_path in NO_ANSWER_DIR.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["_file"] = str(file_path)
            items.append(data)

    items.sort(key=lambda x: x.get("created_at", ""))
    return items


# Добавляет ответ к уже существующему вопросу
def add_answer_to_existing_question(file_path: str, suggested_answer: str) -> Path:
    ensure_dirs()

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["suggested_answer"] = suggested_answer

    new_path = WITH_ANSWER_DIR / Path(file_path).name
    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    Path(file_path).unlink(missing_ok=True)
    return new_path


# Если есть полностью одинаковые вопросы от пользователей, новый не сохраняется
# проверка пока глупая, ес вопрос хоть немного отличается, его добавят
def is_similar_question_already_saved(question: str) -> bool:
    normalized = question.strip().lower()

    ensure_dirs()

    for folder in [NO_ANSWER_DIR, WITH_ANSWER_DIR]:
        for file_path in folder.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("question", "").strip().lower() == normalized:
                    return True
            except Exception:
                continue

    return False


# =========================
# ВСПОМОГАТЕЛЬНОЕ
# =========================

# Возвращение limit первых нерешенных вопросов (по умолчанию 10)
def get_open_questions(limit: int = 10) -> list[dict]:
    return load_pending_questions_without_answers()[:limit]


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

    results = search_matching_faq(question, faq_entries, min_score=MIN_SCORE_TO_ACCEPT, top_n=3)

    if results:
        print("\nВот что удалось найти:\n")
        for i, (score, entry) in enumerate(results, start=1):
            print(f"{i}. {entry.get('answer', 'Ответ отсутствует')}")
        print()
        return

    print("\nЯ не нашёл подходящий ответ в FAQ.\n")
    choice = input("Отправить этот вопрос команде на добавление? (да/нет): ").strip().lower()

    if choice not in ("да", "д", "yes", "y"):
        print("\nХорошо, вопрос не отправлен.\n")
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


def answer_open_question_flow():
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

    add_answer_to_existing_question(selected["_file"], suggested_answer)
    print("\nСпасибо. Твой вариант ответа сохранён и отправлен команде на проверку.\n")


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
            answer_open_question_flow()
        elif choice == "0":
            print()
            return
        else:
            print("Некорректный ввод.\n")


# =========================
# MAIN
# =========================

def main():
    ensure_dirs()

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
        print("3. Показать открытые вопросы")
        print("0. Выход")

        choice = input("Выбери действие: ").strip()

        if choice == "1":
            search_question_flow(faq_entries, user_id, username)
        elif choice == "2":
            help_team_menu(user_id, username)
        elif choice == "3":
            print_open_questions(limit=10)
        elif choice == "0":
            print("Выход из программы.")
            break
        else:
            print("Некорректный ввод.\n")


if __name__ == "__main__":
    main()