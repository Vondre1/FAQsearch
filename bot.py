import asyncio
import json
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from search_engine import search


# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = "8633303763:AAEPeDPL-PX41f69eN8VgvzdQ4jFXr_D_zY"
FAQ_FILE = "faq.json"

# Минимальный счет который должен набрать запрос чтобы ответ из FAQ был выведен
MIN_SCORE_TO_ACCEPT = 2

SUGGESTIONS_FILE = Path("suggestions.jsonl")


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

# Загрузка FAQ
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
    items = []

    with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if data.get("type") == "new_question" and not data.get("answer"):
                data["_line_number"] = line_number
                items.append(data)

    items.sort(key=lambda x: x.get("timestamp", ""))
    return items


# Добавляет ответ к уже существующему вопросу
def add_answer_to_existing_question(line_number: int, user_id: int | str, username: str | None, suggested_answer: str) -> Path:
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


# Помощь команде
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

# Возвращает limit первых открытых вопросов одной строкой для вывода в сообщение
def get_open_questions_text(limit: int = 10) -> str:
    questions = load_pending_questions_without_answers()

    if not questions:
        return "Сейчас нет открытых вопросов без ответа."

    lines = ["Открытые вопросы:"]
    for i, item in enumerate(questions[:limit], start=1):
        lines.append(f"{i}. {item['question']}")

    return "\n".join(lines)


# Безопасное редактирование сообщения чтобы не ловить ошибку если текст тот же самый
async def safe_edit_text(message: Message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


# =========================
# ИНИЦИАЛИЗАЦИЯ
# =========================

faq_entries = []


# =========================
# ХЕНДЛЕРЫ
# =========================

# Команда /start
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет.\n\n"
        "Напиши вопрос, и я попробую найти ответ в FAQ.\n"
        "Если ответа не будет, я предложу отправить вопрос на добавление.\n\n"
        "Также есть отдельное меню помощи команде.",
        reply_markup=main_menu_keyboard()
    )


# Команда /helpteam
async def help_command_handler(message: Message):
    await message.answer(
        "Меню помощи команде:",
        reply_markup=help_team_keyboard()
    )


# Открывает меню помощи команде
async def help_team_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "Меню помощи команде:",
        reply_markup=help_team_keyboard()
    )
    await callback.answer()


# Возвращает пользователя в меню помощи команде и очищает состояние
async def back_to_help_team_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Меню помощи команде:",
        reply_markup=help_team_keyboard()
    )
    await callback.answer()


# Возвращает пользователя в главное меню и очищает состояние
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Напиши свой вопрос в чат, и я попробую найти ответ.",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


# Основной обработчик вопросов пользователя
async def message_search_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        return

    results = search(text, faq_entries, top_n=3)
    results = [item for item in results if item.get("score", 0) >= MIN_SCORE_TO_ACCEPT]

    if results:
        await state.clear()

        answers = []
        for i, item in enumerate(results, start=1):
            answers.append(f"{i}. {item.get('answer', 'Ответ отсутствует')}")

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


# Сохраняет вопрос который бот не смог найти в FAQ
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


# Отменяет отправку нераспознанного вопроса
async def cancel_unknown_question_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Хорошо, вопрос не отправлен.",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


# =========================
# ПРЕДЛОЖИТЬ НОВЫЙ ВОПРОС БЕЗ ОТВЕТА
# =========================

# Переводит бота в режим ожидания нового вопроса
async def new_question_only_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_new_question_for_team)
    await callback.message.edit_text(
        "Напиши вопрос, который стоит добавить в FAQ.",
        reply_markup=back_to_help_team_keyboard()
    )
    await callback.answer()


# Сохраняет новый вопрос без ответа
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


# =========================
# ПРЕДЛОЖИТЬ НОВЫЙ ВОПРОС С ОТВЕТОМ
# =========================

# Переводит бота в режим ввода нового вопроса с ответом
async def new_question_with_answer_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_new_question_with_answer_question)
    await callback.message.edit_text(
        "Напиши новый вопрос, который стоит добавить в FAQ.",
        reply_markup=back_to_help_team_keyboard()
    )
    await callback.answer()


# Сохраняет текст вопроса и просит пользователя ввести ответ
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


# Сохраняет новый вопрос вместе с предложенным ответом
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


# =========================
# ПРЕДЛОЖИТЬ ОТВЕТ НА ОТКРЫТЫЙ ВОПРОС
# =========================

# Показывает список открытых вопросов и просит выбрать номер
async def answer_open_question_callback(callback: CallbackQuery, state: FSMContext):
    questions = load_pending_questions_without_answers()

    if not questions:
        await safe_edit_text(
            callback.message,
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


# Принимает номер выбранного вопроса
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

    await state.update_data(selected_open_question_line=selected["_line_number"])
    await state.set_state(BotStates.waiting_answer_for_open_question)

    await message.answer(
        f"Выбран вопрос:\n{selected['question']}\n\n"
        "Теперь напиши свой вариант ответа."
    )


# Сохраняет ответ на выбранный открытый вопрос
async def answer_for_open_question_handler(message: Message, state: FSMContext):
    suggested_answer = (message.text or "").strip()

    if not suggested_answer:
        await message.answer("Ответ пустой. Напиши вариант ответа.")
        return

    data = await state.get_data()
    line_number = data.get("selected_open_question_line")

    if not line_number:
        await message.answer("Не удалось получить выбранный вопрос.")
        await state.clear()
        return

    add_answer_to_existing_question(
        line_number=line_number,
        user_id=message.from_user.id,
        username=message.from_user.username,
        suggested_answer=suggested_answer
    )

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

    ensure_storage()
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