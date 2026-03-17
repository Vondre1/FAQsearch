import json
from pathlib import Path

from search_engine import search

from data_engine import (
    ensure_storage,
    save_question_only,
    save_question_with_answer,
    add_answer_to_existing_question,
    is_similar_question_already_saved,
    get_open_questions,
)


# =========================
# НАСТРОЙКИ
# =========================

FAQ_FILE = "faq.json"

# Минимальный счет который должен набрать запрос чтобы ответ из FAQ был выведен
MIN_SCORE_TO_ACCEPT = 2


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

    results = search(question, faq_entries, top_n=3)

    if results:
        print("\nВот что удалось найти:\n")
        for i, item in enumerate(results, start=1):
            if item["score"] >= MIN_SCORE_TO_ACCEPT:
                print(f"{i}. {item.get('answer', 'Ответ отсутствует')}")
        print()
        return

    print("\nЯ не нашёл подходящий ответ в FAQ.\n")
    choice = input("Отправить этот вопрос команде на добавление? (да/НЕТ): ").strip().lower()

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
        print("0. Выход")

        choice = input("Выбери действие: ").strip()

        if choice == "1":
            search_question_flow(faq_entries, user_id, username)
        elif choice == "2":
            help_team_menu(user_id, username)
        elif choice == "0":
            print("Выход из программы.")
            break
        else:
            print("Некорректный ввод.\n")


if __name__ == "__main__":
    main()