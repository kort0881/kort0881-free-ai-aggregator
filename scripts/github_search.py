#!/usr/bin/env python3
"""
Поиск репозиториев GitHub с AI-фильтрацией через Groq API.
Добавлен поиск trending-репозиториев: молодых, быстро растущих и часто обновляемых.
Добавлен автоматический перевод описаний на русский язык.
"""

import requests
import json
import os
import time
import re
import subprocess
import shutil
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from groq import Groq

# ====================== КОНФИГУРАЦИЯ ======================
def load_config():
    config_path = Path("config.json")
    if not config_path.exists():
        raise SystemExit("❌ config.json не найден.")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

# ====================== ВЫЧИСЛЕНИЕ TRENDING-МЕТРИК ======================
def compute_trending_metrics(repo: dict) -> dict:
    """
    Возвращает метрики роста для репозитория:
    - age_days: возраст в днях
    - stars_per_day: звёзд в день с момента создания
    - stars_per_week: звёзд в неделю
    - days_since_update: дней с последнего обновления
    - is_young: создан менее чем max_age_days назад (из конфига)
    - is_fast_growing: stars_per_day выше порога
    - is_active: обновлялся недавно
    - trending_score: итоговый скор 0-100
    """
    now = datetime.now(timezone.utc)

    created = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
    updated = datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00"))

    age_days = max((now - created).days, 1)
    days_since_update = (now - updated).days

    stars = repo.get("stars", 0)
    forks = repo.get("forks", 0)

    stars_per_day = stars / age_days
    stars_per_week = stars_per_day * 7

    # Бустим молодые репо: чем моложе при тех же звёздах — тем выше скор
    youth_bonus = max(0, 365 - age_days) / 365 * 30   # до +30 очков
    growth_score = min(stars_per_day * 10, 40)          # до +40 очков
    activity_score = max(0, 20 - days_since_update)     # до +20 очков
    fork_score = min(forks / max(stars, 1) * 10, 10)    # до +10 очков

    trending_score = youth_bonus + growth_score + activity_score + fork_score

    return {
        "age_days": age_days,
        "stars_per_day": round(stars_per_day, 3),
        "stars_per_week": round(stars_per_week, 1),
        "days_since_update": days_since_update,
        "trending_score": round(trending_score, 1),
    }

# ====================== GITHUB API ======================
def _build_date_filter(max_age_days: int) -> str:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    return f"created:>{cutoff}"

def search_github_repos(query: str, config: dict, trending_mode: bool = False) -> list:
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    gh_config = config["github"]
    trend_config = config.get("trending", {})

    min_stars = gh_config.get("min_stars", 0)
    filter_readme = gh_config.get("filter_has_readme", False)
    languages = gh_config.get("languages", [])

    parts = [query]
    if min_stars > 0:
        parts.append(f"stars:>={min_stars}")
    if filter_readme:
        parts.append("has:readme")
    if languages:
        parts.append(" ".join(f"language:{lang}" for lang in languages))

    sort_by = gh_config.get("sort_by", "stars")
    order = gh_config.get("order", "desc")

    # --- TRENDING MODE: ищем молодые репо по дате создания ---
    if trending_mode:
        max_age_days = trend_config.get("max_age_days", 90)
        parts.append(_build_date_filter(max_age_days))
        # Для молодых репо сортируем по обновлению, чтобы поймать активные
        sort_by = trend_config.get("sort_by", "updated")
        order = "desc"
        # Снижаем порог звёзд для молодых репо
        trending_min_stars = trend_config.get("min_stars", 10)
        # Убираем общий min_stars и ставим трендовый
        parts = [p for p in parts if not p.startswith("stars:")]
        if trending_min_stars > 0:
            parts.append(f"stars:>={trending_min_stars}")
        print(f"🔥 Trending-режим: репо моложе {max_age_days} дней, min_stars={trending_min_stars}")

    full_query = " ".join(parts)
    params = {
        "q": full_query,
        "sort": sort_by,
        "order": order,
        "per_page": min(gh_config.get("per_page", 30), 100),
    }
    print(f"🔍 Поиск: {full_query}")

    repos = []
    try:
        response = requests.get(
            "https://api.github.com/search/repositories",
            headers=headers, params=params, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        print(f"ℹ️ Всего доступно: {data.get('total_count', 0)}")
        for item in data.get("items", []):
            repo = {
                "name": item["full_name"],
                "url": item["html_url"],
                "description": item.get("description") or "",
                "stars": item["stargazers_count"],
                "forks": item["forks_count"],
                "language": item.get("language") or "N/A",
                "license": item["license"]["key"] if item.get("license") else "none",
                "updated_at": item["updated_at"],
                "created_at": item["created_at"],
                "open_issues": item.get("open_issues_count", 0),
                "watchers": item.get("watchers_count", 0),
            }
            # Добавляем метрики роста для каждого репо
            repo["metrics"] = compute_trending_metrics(repo)
            repos.append(repo)

        print(f"✅ Найдено: {len(repos)}")
    except Exception as e:
        print(f"❌ Ошибка поиска: {e}")

    return repos

# ====================== РАНЖИРОВАНИЕ TRENDING ======================
def rank_trending(repos: list, config: dict) -> list:
    """
    Фильтрует и сортирует репозитории по trending_score.
    Применяет пороги из конфига trending.
    """
    trend_config = config.get("trending", {})
    min_trending_score = trend_config.get("min_trending_score", 15)
    max_age_days = trend_config.get("max_age_days", 90)
    min_stars_per_day = trend_config.get("min_stars_per_day", 0.5)
    max_days_since_update = trend_config.get("max_days_since_update", 14)

    filtered = []
    for repo in repos:
        m = repo.get("metrics", {})
        reasons_skip = []

        if m.get("age_days", 9999) > max_age_days:
            reasons_skip.append(f"слишком старый ({m['age_days']} дней)")
        if m.get("stars_per_day", 0) < min_stars_per_day:
            reasons_skip.append(f"медленный рост ({m['stars_per_day']} звёзд/день)")
        if m.get("days_since_update", 9999) > max_days_since_update:
            reasons_skip.append(f"давно не обновлялся ({m['days_since_update']} дней)")
        if m.get("trending_score", 0) < min_trending_score:
            reasons_skip.append(f"низкий trending_score ({m['trending_score']})")

        if reasons_skip:
            print(f"  ⏭ {repo['name']}: {'; '.join(reasons_skip)}")
        else:
            filtered.append(repo)

    # Сортируем по trending_score убыванию
    filtered.sort(key=lambda r: r["metrics"]["trending_score"], reverse=True)
    return filtered

# ====================== ЭВРИСТИЧЕСКИЙ ФИЛЬТР ======================
def heuristic_filter(repo_info: dict, config: dict) -> dict:
    ai_config = config.get("ai_filter", {})
    spam_keywords = ai_config.get("spam_keywords", [])
    min_score = ai_config.get("min_quality_score", 6)

    desc_lower = repo_info["description"].lower()
    for kw in spam_keywords:
        if kw.lower() in desc_lower:
            return {"is_spam": True, "reason": f"Спам: {kw}", "quality_score": 0}

    updated = datetime.fromisoformat(repo_info["updated_at"].replace("Z", "+00:00"))
    days_old = (datetime.now(updated.tzinfo) - updated).days
    if days_old > 1095:
        return {"is_spam": True, "reason": f"Устарел: {days_old} дней", "quality_score": 2}

    reason_checks = []
    if repo_info["license"] == "none":
        reason_checks.append("нет лицензии")

    created = datetime.fromisoformat(repo_info["created_at"].replace("Z", "+00:00"))
    days_since = (datetime.now(created.tzinfo) - created).days
    stars_per_month = (repo_info["stars"] / days_since) * 30 if days_since > 0 else 0
    if stars_per_month < 1 and repo_info["stars"] < 100:
        reason_checks.append("низкая популярность")

    quality_score = max(0, 10 - len(reason_checks) * 2 - days_old // 365)
    if quality_score < min_score:
        return {"is_spam": True, "reason": f"Низкое качество: {', '.join(reason_checks)}", "quality_score": quality_score}

    return {"is_spam": False, "reason": "OK", "quality_score": quality_score}

# ====================== AI ФИЛЬТР (GROQ) ======================
def call_ai_filter(repo_info: dict, config: dict, trending_mode: bool = False) -> dict:
    ai_config = config.get("ai_filter", {})
    if not ai_config.get("enabled", False):
        return {"is_spam": False, "reason": "AI отключён", "quality_score": 10}

    api_key = os.getenv("MODELS_ROUTER")
    if not api_key:
        print("⚠️ MODELS_ROUTER не задан, используется эвристика.")
        return heuristic_filter(repo_info, config)

    time.sleep(ai_config.get("rate_limit_delay", 2.0))

    m = repo_info.get("metrics", {})
    trending_block = ""
    if trending_mode:
        trending_block = f"""
Trending-метрики:
- Возраст: {m.get('age_days', '?')} дней
- Звёзд/день: {m.get('stars_per_day', '?')}
- Звёзд/неделю: {m.get('stars_per_week', '?')}
- Дней без обновления: {m.get('days_since_update', '?')}
- Trending score: {m.get('trending_score', '?')}
Дополнительный критерий: репозиторий молодой, но БЫСТРО РАСТЁТ. Это не спам, если он активно развивается и полезен сообществу.
"""

    prompt = f"""Ты эксперт по GitHub. Оцени репозиторий строго по критериям:
Данные:
- Название: {repo_info['name']}
- Описание: {repo_info['description']}
- Звёзды: {repo_info['stars']}
- Форки: {repo_info['forks']}
- Язык: {repo_info['language']}
- Лицензия: {repo_info['license']}
- Обновлён: {repo_info['updated_at']}
- Создан: {repo_info['created_at']}
{trending_block}
Критерии мусора: крипта/скам, пустые репо, устаревшие (>3 лет), накрутка звёзд, не по теме, adult-контент, только бинарники.

Ответь ТОЛЬКО JSON: {{"is_spam": true/false, "reason": "краткая причина", "quality_score": число 0-10}}"""

    main_model = ai_config.get("model", "llama-3.3-70b-versatile")
    models_to_try = [main_model, "llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant"]

    for model in models_to_try:
        try:
            client = Groq(api_key=api_key)
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Ты строгий эксперт. Отвечай только JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.2,
                max_tokens=500,
            )
            raw = chat_completion.choices[0].message.content.strip().strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
            analysis = json.loads(raw)
            return {
                "is_spam": analysis.get("is_spam", False),
                "reason": analysis.get("reason", "—"),
                "quality_score": analysis.get("quality_score", 5),
            }
        except Exception as e:
            print(f"⚠️ Модель {model} — ошибка для {repo_info['name']}: {e}")
            continue

    return heuristic_filter(repo_info, config)

# ====================== ПЕРЕВОД ОПИСАНИЙ НА РУССКИЙ ======================
_translation_cache = {}
_cache_path = Path("translation_cache.json")

def load_translation_cache():
    global _translation_cache
    if _cache_path.exists():
        try:
            with open(_cache_path, "r", encoding="utf-8") as f:
                _translation_cache = json.load(f)
            print(f"📚 Загружен кэш переводов: {len(_translation_cache)} записей")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки кэша переводов: {e}")
            _translation_cache = {}

def save_translation_cache():
    try:
        with open(_cache_path, "w", encoding="utf-8") as f:
            json.dump(_translation_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения кэша переводов: {e}")

def translate_to_russian(text: str, config: dict) -> str:
    """Переводит текст описания на русский язык с кэшированием."""
    if not text or not text.strip():
        return ""
    
    # Хэш для кэширования
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    if text_hash in _translation_cache:
        return _translation_cache[text_hash]

    # Попытка перевода через Groq
    api_key = os.getenv("MODELS_ROUTER")
    if not api_key:
        print("⚠️ MODELS_ROUTER не задан — пропуск перевода.")
        return text

    ai_config = config.get("ai_filter", {})
    models_to_try = [
        ai_config.get("model", "llama-3.3-70b-versatile"),
        "llama-4-scout-17b-16e-instruct",
        "mixtral-8x7b-32768"
    ]

    prompt = f"""Переведи следующее описание репозитория GitHub на русский язык кратко и точно. 
Не добавляй комментарии, только перевод.

Оригинал: "{text}"

Перевод:"""

    for model in models_to_try:
        try:
            client = Groq(api_key=api_key)
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Ты — профессиональный технический переводчик."},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.1,
                max_tokens=200,
            )
            translation = chat_completion.choices[0].message.content.strip()
            # Очищаем лишние кавычки или форматирование
            translation = re.sub(r'^[""""]+|[""""]+$', '', translation)
            _translation_cache[text_hash] = translation
            save_translation_cache()
            return translation
        except Exception as e:
            print(f"⚠️ Ошибка перевода модели {model}: {e}")
            continue

    # Если все модели упали — возвращаем оригинал
    return text

# ====================== СОХРАНЕНИЕ ======================
def save_json(trigger_name: str, repos: list, out_folder: str, analysis=None) -> str:
    os.makedirs(out_folder, exist_ok=True)
    safe = re.sub(r"[^\w]", "", trigger_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{out_folder}/{safe}_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "trigger": trigger_name,
            "collected_at": timestamp,
            "total_repos": len(repos),
            "repositories": repos,
            "analysis": analysis or [],
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 JSON: {path}")
    return path

def generate_markdown_links(trigger_name: str, repos: list, out_folder: str = "links",
                             suffix: str = "filtered", trending_mode: bool = False, config: dict = None) -> str | None:
    if not repos:
        return None
    os.makedirs(out_folder, exist_ok=True)
    safe = re.sub(r"[^\w]", "", trigger_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{out_folder}/{safe}_links_{suffix}_{timestamp}.md"
    with open(path, "w", encoding="utf-8") as f:
        title = "🔥 TRENDING (молодые и быстро растущие)" if trending_mode else trigger_name.upper()
        f.write(f"# 📦 Архив проектов: {title}\n\n")
        f.write(f"📅 Дата архивации: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
        f.write("| # | Репозиторий | ⭐ Звёзд | 📅 Создан | 🔄 Обновлён | Описание |\n")
        f.write("|---|-------------|----------|-----------|------------|----------|\n")
        for idx, repo in enumerate(repos, start=1):
            m = repo.get("metrics", {})
            created = repo.get("created_at", "")[:10]
            updated = repo.get("updated_at", "")[:10]
            
            # Переводим описание
            raw_desc = repo["description"] or ""
            if config:
                translated_desc = translate_to_russian(raw_desc, config)
            else:
                translated_desc = raw_desc
            desc = translated_desc[:100] if translated_desc else ""
            
            f.write(f"| {idx} | [{repo['name']}]({repo['url']}) | {repo['stars']} | {created} | {updated} | {desc} |\n")
    print(f"🔗 Markdown: {path}")
    return path

# ====================== НОВЫЕ ФУНКЦИИ ДЛЯ ОБНОВЛЕНИЯ README И АРХИВИРОВАНИЯ ======================
def get_latest_archive_link(trigger_name: str, links_folder: str = "links") -> str | None:
    """Возвращает имя последнего архивного файла для данного триггера (по времени модификации)."""
    pattern = re.compile(rf"{re.escape(trigger_name)}.*\.md")
    files = []
    for f in Path(links_folder).glob("*.md"):
        if pattern.match(f.name):
            files.append(f)
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return str(latest)

def rotate_archives(links_folder: str = "links", keep_days: int = 7):
    """Перемещает файлы старше keep_days дней в подпапку archive/"""
    archive_dir = Path(links_folder) / "archive"
    archive_dir.mkdir(exist_ok=True)

    now = datetime.now(timezone.utc)
    for f in Path(links_folder).glob("*.md"):
        # Из имени файла вытаскиваем дату (формат YYYYMMDD)
        match = re.search(r'(\d{8})', f.name)
        if match:
            file_date = datetime.strptime(match.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
            if (now - file_date).days > keep_days:
                shutil.move(str(f), archive_dir / f.name)
                print(f"📦 Архив: {f.name} → archive/")

def update_readme(trigger_name: str, repos: list, readme_path: str = "README.md",
                  trending_mode: bool = False, max_days_in_readme: int = 7, config: dict = None):
    """
    Обновляет README, показывая только проекты младше max_days_in_readme дней.
    Добавляет нумерацию и русские заголовки.
    """
    if not repos:
        return

    now = datetime.now(timezone.utc)
    # Фильтруем свежие проекты (по created_at)
    fresh_repos = []
    for repo in repos:
        created = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
        age_days = (now - created).days
        if age_days <= max_days_in_readme:
            fresh_repos.append(repo)
    # Сортируем от новых к старым
    fresh_repos.sort(key=lambda r: r["created_at"], reverse=True)

    # Если новых нет – выводим сообщение
    if not fresh_repos:
        block = f"## 🚀 {trigger_name.upper()} – новые проекты\n\n_Новых проектов за последние {max_days_in_readme} дней не найдено._\n\n"
    else:
        if trending_mode:
            header = f"## 🔥 {trigger_name.upper()} – свежие Trending-проекты\n\n"
            table = "| # | Репозиторий | ⭐ Звёзд | 📈 зв/день | 🕐 Возраст | 🔄 Обновлён | Описание |\n"
            table += "|---|-------------|----------|-----------|-----------|------------|----------|\n"
            for idx, repo in enumerate(fresh_repos[:15], start=1):
                m = repo.get("metrics", {})
                url, name = repo["url"], repo["name"]
                
                # Переводим описание
                raw_desc = repo["description"] or ""
                if config:
                    translated_desc = translate_to_russian(raw_desc, config)
                else:
                    translated_desc = raw_desc
                desc = (translated_desc[:50] + "...") if len(translated_desc) > 50 else translated_desc
                
                table += (f"| {idx} | [{name}]({url}) | {repo['stars']} | {m.get('stars_per_day','?')} "
                          f"| {m.get('age_days','?')}д | {m.get('days_since_update','?')}д назад | {desc} |\n")
        else:
            header = f"## 🚀 {trigger_name.upper()} – свежие проекты\n\n"
            table = "| # | Репозиторий | ⭐ Звёзд | Описание |\n"
            table += "|---|-------------|----------|----------|\n"
            for idx, repo in enumerate(fresh_repos[:15], start=1):
                url, name = repo["url"], repo["name"]
                
                # Переводим описание
                raw_desc = repo["description"] or ""
                if config:
                    translated_desc = translate_to_russian(raw_desc, config)
                else:
                    translated_desc = raw_desc
                desc = (translated_desc[:60] + "...") if len(translated_desc) > 60 else translated_desc
                
                table += f"| {idx} | [{name}]({url}) | {repo['stars']} | {desc} |\n"

        if len(fresh_repos) > 15:
            table += f"\n*... и ещё {len(fresh_repos) - 15} новых проектов. Полный архив — см. ниже.*\n"

        # Добавляем ссылку на последний архивный файл (если есть)
        archive_link = get_latest_archive_link(trigger_name)
        if archive_link:
            table += f"\n📦 **Архив всех проектов**: [{archive_link}]({archive_link})\n"

        block = header + table + "\n"

    # Вставка/замена между маркерами
    marker_key = trigger_name.upper().replace(" ", "_")
    start_marker = f"<!-- START_{marker_key} -->"
    end_marker = f"<!-- END_{marker_key} -->"
    new_block = f"{start_marker}\n{block}\n{end_marker}"

    content = ""
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = "# GitHub Free AI Aggregator\n\n"

    if start_marker in content and end_marker in content:
        pattern = rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}"
        content = re.sub(pattern, new_block, content, flags=re.DOTALL)
    else:
        content += f"\n{new_block}\n"

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📝 README обновлён: {trigger_name} (показано {len(fresh_repos)} новых проектов)")

def commit_and_push(files=None):
    if files is None:
        files = ["README.md", "links/"]
    if not os.getenv("CI"):
        print("⏩ Не CI-окружение, пропускаем автокоммит.")
        return
    try:
        subprocess.run(["git", "config", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "user.name", "GitHub Action"], check=True)
        subprocess.run(["git", "add"] + files, check=True)
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            print("✅ Нет изменений для коммита.")
            return
        subprocess.run(["git", "commit", "-m", "Автообновление + trending [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Запушено.")
    except Exception as e:
        print(f"⚠️ Ошибка коммита: {e}")

# ====================== ОСНОВНАЯ ФУНКЦИЯ ======================
def process_trigger(trigger: dict, config: dict):
    name = trigger["name"]
    query = trigger.get("query")
    if not query:
        return

    out_folder = trigger.get("output_folder", "output")
    filtered_folder = trigger.get("filtered_folder", "filtered")
    links_folder = trigger.get("links_folder", "links")

    # --- Обычный поиск ---
    print(f"\n{'='*60}\n🎯 {name} [обычный]\n{'='*60}")
    repos = search_github_repos(query, config, trending_mode=False)
    if not repos:
        save_json(name, [], out_folder)
    else:
        analysis_results, filtered = [], []
        for repo in repos:
            analysis = call_ai_filter(repo, config, trending_mode=False)
            analysis_results.append({"repo": repo["name"], **analysis})
            if not analysis["is_spam"]:
                filtered.append(repo)
        save_json(name, repos, out_folder, analysis_results)
        if filtered:
            save_json(f"{name}_filtered", filtered, filtered_folder)
            generate_markdown_links(name, filtered, links_folder, suffix="filtered", config=config)
            # Обновляем README с фильтром по дате
            max_days = config.get("readme", {}).get("max_days_to_show", 7)
            update_readme(name, filtered, trending_mode=False, max_days_in_readme=max_days, config=config)
        print(f"📊 Обычный итог: {len(filtered)} / {len(repos)}")

    # --- Trending поиск (молодые + быстро растущие) ---
    trend_config = config.get("trending", {})
    if trend_config.get("enabled", False):
        print(f"\n{'='*60}\n🔥 {name} [trending]\n{'='*60}")
        trending_repos = search_github_repos(query, config, trending_mode=True)

        # Предварительная фильтрация по метрикам роста
        ranked = rank_trending(trending_repos, config)
        print(f"📈 После trending-фильтра: {len(ranked)} / {len(trending_repos)}")

        # AI-фильтрация
        trend_analysis, trend_filtered = [], []
        for repo in ranked:
            analysis = call_ai_filter(repo, config, trending_mode=True)
            trend_analysis.append({"repo": repo["name"], **analysis})
            if not analysis["is_spam"]:
                trend_filtered.append(repo)

        trend_name = f"{name}_trending"
        save_json(trend_name, trending_repos, out_folder, trend_analysis)
        if trend_filtered:
            save_json(f"{trend_name}_filtered", trend_filtered, filtered_folder)
            generate_markdown_links(trend_name, trend_filtered, links_folder,
                                    suffix="trending", trending_mode=True, config=config)
            max_days = config.get("readme", {}).get("max_days_to_show", 7)
            update_readme(trend_name, trend_filtered, trending_mode=True, max_days_in_readme=max_days, config=config)
        print(f"📊 Trending итог: {len(trend_filtered)} / {len(trending_repos)}")

def main():
    # Загружаем кэш переводов
    load_translation_cache()
    
    config = load_config()
    for trigger in config["triggers"]:
        process_trigger(trigger, config)

    # Ротация архивов: перемещаем старые файлы из links/ в links/archive/
    max_days = config.get("readme", {}).get("max_days_to_show", 7)
    rotate_archives(links_folder="links", keep_days=max_days)

    commit_and_push(["README.md", "links/"])
    print("\n🎉 Готово!")

if __name__ == "__main__":
    main()
