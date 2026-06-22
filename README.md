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
| 1 | [Johell1NS/browser-search](https://github.com/Johell1NS/browser-search) | 13 | 13.0 | 1д | 0д назад | A skill for AI agents: search the web with SearXNG... |
| 2 | [ekkoee/thelimitsofmylanguagemeanthelimitsofmyworld](https://github.com/ekkoee/thelimitsofmylanguagemeanthelimitsofmyworld) | 20 | 20.0 | 1д | 0д назад | 免費開源的 Chrome 雙語對照閱讀器：原文一行、中文一行,支援 X / Reddit / You... |
| 3 | [SulgX/V2X-Panel](https://github.com/SulgX/V2X-Panel) | 14 | 14.0 | 1д | 0д назад | 🚀 V2X Panel: A single-file, powerful, and free pan... |
| 4 | [TheProductArchitect/appshots](https://github.com/TheProductArchitect/appshots) | 7 | 7.0 | 1д | 0д назад | Free App Store & Google Play screenshot generator ... |
| 5 | [Env-Kit/envkit-releases](https://github.com/Env-Kit/envkit-releases) | 14 | 7.0 | 2д | 0д назад | EnvKit — free local development environment for Wi... |
| 6 | [harn3ss/open-infra](https://github.com/harn3ss/open-infra) | 6 | 2.0 | 3д | 0д назад | A free, self-hostable mini-cloud: write one infra.... |
| 7 | [blueprintparadise/Screex](https://github.com/blueprintparadise/Screex) | 12 | 1.714 | 7д | 0д назад | Screen-recording understanding for agents — turn a... |

📦 **Архив всех проектов**: [links/free_trending_links_trending_20260622_152844.md](links/free_trending_links_trending_20260622_152844.md)


<!-- END_FREE_TRENDING -->

<!-- START_AI_TRENDING -->
## 🔥 AI_TRENDING – свежие Trending-проекты

| # | Репозиторий | ⭐ Звёзд | 📈 зв/день | 🕐 Возраст | 🔄 Обновлён | Описание |
|---|-------------|----------|-----------|-----------|------------|----------|
| 1 | [patibandlavenkatamanideep/memoryops-ai](https://github.com/patibandlavenkatamanideep/memoryops-ai) | 5 | 5.0 | 1д | 0д назад | Enterprise-shaped memory governance layer for AI a... |
| 2 | [bhoon716/flowness](https://github.com/bhoon716/flowness) | 6 | 2.0 | 3д | 0д назад | Issue-driven AI development operating system and w... |
| 3 | [brunoflma/jurisprudenciaia-mcp](https://github.com/brunoflma/jurisprudenciaia-mcp) | 6 | 0.857 | 7д | 0д назад | Conector MCP para usar o JurisprudênciaIA no Claud... |

📦 **Архив всех проектов**: [links/ai_trending_links_trending_20260622_153055.md](links/ai_trending_links_trending_20260622_153055.md)


<!-- END_AI_TRENDING -->

<!-- START_FREE_AI_TRENDING -->
## 🔥 FREE_AI_TRENDING – свежие Trending-проекты

| # | Репозиторий | ⭐ Звёзд | 📈 зв/день | 🕐 Возраст | 🔄 Обновлён | Описание |
|---|-------------|----------|-----------|-----------|------------|----------|
| 1 | [ezBuilder/omnigen-vault](https://github.com/ezBuilder/omnigen-vault) | 26 | 5.2 | 5д | 1д назад | Infinite text-free AI image generator + SQLite-ind... |

📦 **Архив всех проектов**: [links/free_ai_trending_links_trending_20260622_153241.md](links/free_ai_trending_links_trending_20260622_153241.md)


<!-- END_FREE_AI_TRENDING -->
