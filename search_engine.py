import re


# =========================
# НАСТРОЙКИ
# =========================

# Минимальная длина слова, которое мы вообще учитываем при поиске (пропуск предлогов)
MIN_WORD_LEN = 3


# =========================
# РАБОТА С FAQ
# =========================

# Разделение ввода на отдельные слова и приведение к нижнему регистру, отбрасывает слова с длиной меньше MIN_WORD_LEN
def split_words(text: str) -> set[str]:
    words = re.findall(r"[а-яА-Яa-zA-Z0-9ёЁ]+", text.lower())
    return {word for word in words if len(word) >= MIN_WORD_LEN}


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
def search_top_faq(question: str, faq_entries: list[dict], top_n: int = 5) -> list[tuple[int, dict]]:
    question_words = split_words(question)
    results = []

    for entry in faq_entries:
        score = calculate_score(question_words, entry.get("keywords", []))
        results.append((score, entry))

    results.sort(key=lambda x: x[0], reverse=True)
    return results[:top_n]


# Отсечение неподходящих элементов (количество набранных очков < 2 || разница в очках с лучшим вариантом > 1, вывод первых 5 лучших вариантов)
def search_matching_faq(question: str, faq_entries: list[dict], min_score: int = 2, top_n: int = 5):
    results = search_top_faq(question, faq_entries, top_n=top_n)
    results = [(score, entry) for score, entry in results if score >= min_score]

    if not results:
        return []

    best_score = results[0][0]
    return [(score, entry) for score, entry in results if score >= best_score - 1]


def search(query: str, faq_data: list[dict], top_n: int = 3) -> list[dict]:
    """
    Принимает запрос и список FAQ-записей.
    Возвращает топ-N результатов с полями: id, question, answer, score.
    """
    results = search_matching_faq(query, faq_data, min_score=2, top_n=top_n)

    formatted = []
    for score, entry in results:
        formatted.append({
            "id": entry.get("id"),
            "question": entry.get("question"),
            "answer": entry.get("answer"),
            "score": score,
        })

    return formatted