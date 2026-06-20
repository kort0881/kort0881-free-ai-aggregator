# GitHub Free AI Aggregator


<!-- START_FREE -->
## 🚀 FREE – новые проекты

_Новых проектов за последние 7 дней не найдено._


<!-- END_FREE -->

<!-- START_AI -->
## 🚀 AI – новые проекты

_Новых проектов за последние 7 дней не найдено._


<!-- END_AI -->

<!-- START_FREE_AI -->
## 🚀 FREE_AI – новые проекты

_Новых проектов за последние 7 дней не найдено._


<!-- END_FREE_AI -->

> **Полные списки** (со всеми проектами) лежат в папке [`links/`](links).  
> Также все сырые и отфильтрованные данные сохраняются в `data/raw/` и `data/filtered/` в виде JSON.

---

## 🛠 Как это работает

1. **Поиск** – GitHub API принимает запрос вида:  
   `free stars:>=50 language:python language:javascript language:typescript`
2. **AI‑анализ** – для каждого репозитория вызывается Groq с промптом на оценку «мусор / не мусор» и выставлением `quality_score`.
3. **Фильтрация** – если AI не сработал (ошибка, лимиты), включается эвристический фильтр (спам‑слова, возраст, лицензия, популярность).
4. **Сохранение** – результаты записываются в JSON, Markdown‑списки, а README обновляется через специальные комментарии-маркеры (`<!-- START_xxx -->`).
5. **Публикация** – в CI (GitHub Actions) изменения коммитятся и пушатся обратно в репозиторий.

---

## 🚀 Локальный запуск (опционально)

```bash
git clone https://github.com/kort0881/kort0881-free-ai-aggregator.git
cd kort0881-free-ai-aggregator
pip install -r requirements.txt

export GITHUB_TOKEN=your_github_token
export MODELS_ROUTER=your_groq_api_key

python scripts/github_search.py
Примечание: Для работы AI‑фильтра обязательно нужен ключ Groq (бесплатный на console.groq.com).
Без него скрипт использует только эвристику – результат будет хуже, но тоже рабочий.

📁 Структура проекта
text
.
├── .github/workflows/           # CI (ежедневный запуск)
├── scripts/
│   └── github_search.py         # основной скрипт
├── data/
│   ├── raw/                     # сырые ответы GitHub (по триггерам)
│   └── filtered/                # после AI‑фильтрации
├── links/                       # Markdown‑файлы с активными ссылками
├── config.json                  # настройки поиска и AI
├── requirements.txt
└── README.md                    # этот файл (обновляется автоматически)
📃 Лицензия
MIT © 2025 — свободное использование, модификация, распространение.

🙌 Благодарности
Groq за быстрые и бесплатные LLM‑модели.

GitHub API за доступ к метаданным репозиториев.

GitHub Actions за автоматизацию.

Файл README автоматически обновляется каждый день в 10:00 UTC. Последнее обновление: – вставляет скрипт.

text

---

## Пояснения по использованию

1. **Бейджи** – настроены под типовой репозиторий. При желании вы можете заменить ссылки на свои или убрать.
2. **Маркеры `<!-- START_FREE -->
## 🚀 FREE – новые проекты

_Новых проектов за последние 7 дней не найдено._


<!-- END_FREE -->`** – именно их будет искать и заменять скрипт. В исходном шаблоне они пустые, после первого запуска внутри появятся таблицы.
3. **Папка `links/`** – скрипт создаёт в ней файлы вида `free_links_filtered_*.md`, на которые есть ссылка в README.
4. **Адаптация под ваш аккаунт** – замените `kort0881/kort0881-free-ai-aggregator` в команде `git clone` на ваш реальный путь (можно оставить как есть, так как это ваш репозиторий).

## Как применить

- Скопируйте содержимое этого сообщения.
- Откройте в своём репозитории файл `README.md`.
- Замените его содержимое на скопированное.
- Сохраните и запушьте.

После ближайшего запуска GitHub Actions (или ручного) скрипт сам заполнит таблицы между маркерами, и README станет полностью информативным.

Если хотите изменить стиль (например, убрать бейджи, добавить секцию «Примеры использования»), напишите – поправлю.


<!-- START_FREE_TRENDING -->
## 🔥 FREE_TRENDING – свежие Trending-проекты

| # | Репозиторий | ⭐ Звёзд | 📈 зв/день | 🕐 Возраст | 🔄 Обновлён | Описание |
|---|-------------|----------|-----------|-----------|------------|----------|
| 1 | [paulfruitful/freeaitokens](https://github.com/paulfruitful/freeaitokens) | 11 | 11.0 | 1д | 0д назад | Free Local AI inference without need for GPUs or h... |
| 2 | [jinhanchen/Murmur](https://github.com/jinhanchen/Murmur) | 5 | 5.0 | 1д | 0д назад | Free, local, privacy-first voice typing for Window... |
| 3 | [inni918/warashi](https://github.com/inni918/warashi) | 82 | 27.333 | 3д | 0д назад | Warashi — a free, open-source desktop AI companion... |
| 4 | [AlexJefri3107/Crypto_Market_Analyzer](https://github.com/AlexJefri3107/Crypto_Market_Analyzer) | 5 | 0.833 | 6д | 0д назад | Live crypto market dashboard showing top gainers a... |
| 5 | [halitsever/watchbear](https://github.com/halitsever/watchbear) | 26 | 3.714 | 7д | 0д назад | 🐻 Watch together in sync; Free Chrome extension fo... |

📦 **Архив всех проектов**: [links/free_trending_links_trending_20260620_181645.md](links/free_trending_links_trending_20260620_181645.md)


<!-- END_FREE_TRENDING -->

<!-- START_AI_TRENDING -->
## 🔥 AI_TRENDING – свежие Trending-проекты

| # | Репозиторий | ⭐ Звёзд | 📈 зв/день | 🕐 Возраст | 🔄 Обновлён | Описание |
|---|-------------|----------|-----------|-----------|------------|----------|
| 1 | [paulfruitful/freeaitokens](https://github.com/paulfruitful/freeaitokens) | 11 | 11.0 | 1д | 0д назад | Free Local AI inference without need for GPUs or h... |

📦 **Архив всех проектов**: [links/ai_trending_links_trending_20260620_181831.md](links/ai_trending_links_trending_20260620_181831.md)


<!-- END_AI_TRENDING -->

<!-- START_FREE_AI_TRENDING -->
## 🔥 FREE_AI_TRENDING – свежие Trending-проекты

| # | Репозиторий | ⭐ Звёзд | 📈 зв/день | 🕐 Возраст | 🔄 Обновлён | Описание |
|---|-------------|----------|-----------|-----------|------------|----------|
| 1 | [ezBuilder/omnigen-vault](https://github.com/ezBuilder/omnigen-vault) | 25 | 8.333 | 3д | 0д назад | Infinite text-free AI image generator + SQLite-ind... |

📦 **Архив всех проектов**: [links/free_ai_trending_links_trending_20260620_182015.md](links/free_ai_trending_links_trending_20260620_182015.md)


<!-- END_FREE_AI_TRENDING -->
