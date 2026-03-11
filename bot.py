import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

import yaml
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder


# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = "8633303763:AAEPeDPL-PX41f69eN8VgvzdQ4jFXr_D_zY"
FAQ_FILE = "faq.yaml"

MIN_WORD_LEN = 3
MIN_SCORE_TO_ACCEPT = 2

BASE_DIR = Path("pending_questions")
NO_ANSWER_DIR = BASE_DIR / "no_answer"
WITH_ANSWER_DIR = BASE_DIR / "with_answer"


# =========================
# СОСТОЯНИЯ
# =========================

class BotStates(StatesGroup):
    waiting_confirm_unknown_question = State()

    waiting_new_question_for_team = State()
    waiting_new_question_with_answer_question = State()
    waiting_new_question_with_answer_answer = State()

    waiting_select_open_question = State()
    waiting_answer_for_open_question = State()


# =========================
# РАБОТА С FAQ
# =========================


# Удаляем слова у которых длина меньше заданного значения (по умолчанию 3), чтобы не учитывать предлоги и тп
def split_words(text: str) -> set[str]:
    words = re.findall(r"[а-яА-Яa-zA-Z0-9ёЁ]+", text.lower())
    return {word for word in words if len(word) >= MIN_WORD_LEN}


# Загрузка FAQ
def load_faq(filename: str = FAQ_FILE) -> list[dict]:
    with open(filename, "r", encoding="utf-8") as file:
        faq_data = yaml.safe_load(file)
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

    min_prefix_len = 4

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
        score = calculate_score(question_words, entry["keywords"])
        results.append((score, entry))

    results.sort(key=lambda x: x[0], reverse=True)
    return results[:top_n]


# Вывод лучших совпадений в FAQ (топ 3)
def search_best_faq(question: str, faq_entries: list[dict], min_score: int = MIN_SCORE_TO_ACCEPT):
    results = search_top_faq(question, faq_entries, top_n=1)
    if not results:
        return None

    score, entry = results[0]
    if score < min_score:
        return None

    return score, entry



# Отсечение неподходящих элементов (количество набранных очков < 2 || разница в очках с лучшим вариантом > 1)
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

def ensure_dirs() -> None:
    NO_ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    WITH_ANSWER_DIR.mkdir(parents=True, exist_ok=True)


def make_filename(user_id: int | str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{user_id}_{timestamp}.json"


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


def is_similar_question_already_saved(question: str) -> bool:
    """
    Простая защита от дублей:
    если такой же текст уже есть среди неотвеченных или с ответом
    """
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
# КНОПКИ ПОД СООБЩЕНИЯМИ
# =========================

# Стартовая кнопка "Помочь команде"
def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Помочь команде", callback_data="help_team")
    builder.adjust(1)
    return builder.as_markup()


# Бот не нашел ответ на вопрос
def not_found_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, отправить вопрос", callback_data="save_unknown_question")
    builder.button(text="Нет", callback_data="cancel_unknown_question")
    builder.button(text="Помочь команде", callback_data="help_team")
    builder.adjust(1)
    return builder.as_markup()


#  Помощь команде
def help_team_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Предложить новый вопрос", callback_data="new_question_only")
    builder.button(text="Предложить новый вопрос с ответом", callback_data="new_question_with_answer")
    builder.button(text="Предложить ответ на открытый вопрос", callback_data="answer_open_question")
    builder.button(text="Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()


# Возврат в меню помощи команде
def back_to_help_team_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data="back_to_help_team")
    builder.adjust(1)
    return builder.as_markup()


# =========================
# ВСПОМОГАТЕЛЬНОЕ (для кнопок)
# =========================

def get_open_questions_text(limit: int = 10) -> str:
    questions = load_pending_questions_without_answers()

    if not questions:
        return "Сейчас нет открытых вопросов без ответа."

    lines = ["Открытые вопросы:"]
    for i, item in enumerate(questions[:limit], start=1):
        lines.append(f"{i}. {item['question']}")

    return "\n".join(lines)


# =========================
# ИНИЦИАЛИЗАЦИЯ
# =========================

faq_entries = []


# =========================
# ХЕНДЛЕРЫ
# =========================

async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет.\n\n"
        "Напиши вопрос, и я попробую найти ответ в FAQ.\n"
        "Если ответа не будет, я предложу отправить вопрос на добавление.\n\n"
        "Также есть отдельное меню помощи команде.",
        reply_markup=main_menu_keyboard()
    )


async def help_command_handler(message: Message):
    await message.answer(
        "Меню помощи команде:",
        reply_markup=help_team_keyboard()
    )


async def help_team_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "Меню помощи команде:",
        reply_markup=help_team_keyboard()
    )
    await callback.answer()


async def back_to_help_team_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Меню помощи команде:",
        reply_markup=help_team_keyboard()
    )
    await callback.answer()


async def back_to_main_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Напиши свой вопрос в чат, и я попробую найти ответ.",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


async def message_search_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        return

    results = search_matching_faq(text, faq_entries, min_score=MIN_SCORE_TO_ACCEPT, top_n=3)

    if results:
        await state.clear()

        answers = []
        for i, (score, entry) in enumerate(results, start=1):
            answers.append(f"{i}. {entry['answer']}")

        await message.answer(
            "Вот что удалось найти:\n\n" + "\n\n".join(answers),
            reply_markup=main_menu_keyboard()
        )
        return

    await state.set_state(BotStates.waiting_confirm_unknown_question)
    await state.update_data(last_unknown_question=text)

    await message.answer(
        "Я не нашёл подходящий ответ в FAQ.\n\n"
        "Хочешь отправить этот вопрос команде на добавление?",
        reply_markup=not_found_keyboard()
    )


async def save_unknown_question_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    question = data.get("last_unknown_question")

    if not question:
        await callback.message.answer("Не удалось получить текст вопроса.")
        await callback.answer()
        return

    user_id = callback.from_user.id
    username = callback.from_user.username

    if is_similar_question_already_saved(question):
        await callback.message.edit_text(
            "Такой вопрос уже был отправлен ранее.",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        await callback.answer()
        return

    save_question_only(user_id, username, question)

    await callback.message.edit_text(
        "Спасибо. Вопрос сохранён и отправлен команде на рассмотрение.",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()
    await callback.answer()


async def cancel_unknown_question_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Хорошо, вопрос не отправлен.",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


# ---------- Предложить новый вопрос без ответа ----------

async def new_question_only_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_new_question_for_team)
    await callback.message.edit_text(
        "Напиши вопрос, который стоит добавить в FAQ.",
        reply_markup=back_to_help_team_keyboard()
    )
    await callback.answer()


async def save_new_question_only_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if not text:
        await message.answer("Вопрос пустой. Напиши текст вопроса.")
        return

    if is_similar_question_already_saved(text):
        await message.answer(
            "Такой вопрос уже есть среди отправленных.",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return

    save_question_only(message.from_user.id, message.from_user.username, text)

    await message.answer(
        "Спасибо. Новый вопрос сохранён и отправлен команде.",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()


# ---------- Предложить новый вопрос с ответом ----------

async def new_question_with_answer_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_new_question_with_answer_question)
    await callback.message.edit_text(
        "Напиши новый вопрос, который стоит добавить в FAQ.",
        reply_markup=back_to_help_team_keyboard()
    )
    await callback.answer()


async def new_question_with_answer_question_handler(message: Message, state: FSMContext):
    question = (message.text or "").strip()

    if not question:
        await message.answer("Вопрос пустой. Напиши текст вопроса.")
        return

    await state.update_data(proposed_question=question)
    await state.set_state(BotStates.waiting_new_question_with_answer_answer)

    await message.answer(
        "Теперь напиши свой вариант ответа на этот вопрос.",
    reply_markup=back_to_help_team_keyboard()
    )


async def new_question_with_answer_answer_handler(message: Message, state: FSMContext):
    suggested_answer = (message.text or "").strip()

    if not suggested_answer:
        await message.answer("Ответ пустой. Напиши вариант ответа.")
        return

    data = await state.get_data()
    question = data.get("proposed_question")

    if not question:
        await message.answer("Не удалось получить вопрос.")
        await state.clear()
        return

    save_question_with_answer(
        user_id=message.from_user.id,
        username=message.from_user.username,
        question=question,
        suggested_answer=suggested_answer
    )

    await message.answer(
        "Спасибо. Вопрос с предложенным ответом сохранён и отправлен команде на проверку.",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()


# ---------- Предложить ответ на открытый вопрос ----------

async def answer_open_question_callback(callback: CallbackQuery, state: FSMContext):
    questions = load_pending_questions_without_answers()

    if not questions:
        await callback.message.edit_text(
            "Сейчас нет открытых вопросов без ответа.",
            reply_markup=help_team_keyboard()
        )
        await callback.answer()
        return

    await state.set_state(BotStates.waiting_select_open_question)
    await callback.message.edit_text(
        get_open_questions_text(limit=10) +
        "\n\nНапиши номер вопроса, на который хочешь предложить ответ.",
        reply_markup=back_to_help_team_keyboard()
    )
    await callback.answer()


async def select_open_question_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    questions = load_pending_questions_without_answers()

    if not questions:
        await message.answer(
            "Сейчас нет открытых вопросов без ответа.",
            reply_markup=help_team_keyboard()
        )
        await state.clear()
        return

    if not text.isdigit():
        await message.answer("Напиши именно номер вопроса, например: 1")
        return

    index = int(text)

    if index < 1 or index > min(len(questions), 10):
        await message.answer("Некорректный номер вопроса.")
        return

    selected = questions[index - 1]

    await state.update_data(selected_open_question_file=selected["_file"])
    await state.set_state(BotStates.waiting_answer_for_open_question)

    await message.answer(
        f"Выбран вопрос:\n{selected['question']}\n\n"
        "Теперь напиши свой вариант ответа."
    )


async def answer_for_open_question_handler(message: Message, state: FSMContext):
    suggested_answer = (message.text or "").strip()

    if not suggested_answer:
        await message.answer("Ответ пустой. Напиши вариант ответа.")
        return

    data = await state.get_data()
    file_path = data.get("selected_open_question_file")

    if not file_path:
        await message.answer("Не удалось получить выбранный вопрос.")
        await state.clear()
        return

    add_answer_to_existing_question(file_path, suggested_answer)

    await message.answer(
        "Спасибо. Твой вариант ответа сохранён и отправлен команде на проверку.",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()


# =========================
# MAIN
# =========================

async def main():
    global faq_entries

    ensure_dirs()
    faq_entries = load_faq(FAQ_FILE)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start_handler, CommandStart())
    dp.message.register(help_command_handler, Command("helpteam"))

    dp.callback_query.register(help_team_callback, F.data == "help_team")
    dp.callback_query.register(back_to_help_team_callback, F.data == "back_to_help_team")
    dp.callback_query.register(back_to_main_callback, F.data == "back_to_main")

    dp.callback_query.register(save_unknown_question_callback, F.data == "save_unknown_question")
    dp.callback_query.register(cancel_unknown_question_callback, F.data == "cancel_unknown_question")

    dp.callback_query.register(new_question_only_callback, F.data == "new_question_only")
    dp.callback_query.register(new_question_with_answer_callback, F.data == "new_question_with_answer")
    dp.callback_query.register(answer_open_question_callback, F.data == "answer_open_question")

    dp.message.register(
        save_new_question_only_handler,
        BotStates.waiting_new_question_for_team
    )

    dp.message.register(
        new_question_with_answer_question_handler,
        BotStates.waiting_new_question_with_answer_question
    )
    dp.message.register(
        new_question_with_answer_answer_handler,
        BotStates.waiting_new_question_with_answer_answer
    )

    dp.message.register(
        select_open_question_handler,
        BotStates.waiting_select_open_question
    )
    dp.message.register(
        answer_for_open_question_handler,
        BotStates.waiting_answer_for_open_question
    )

    dp.message.register(message_search_handler)

    print("Бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())