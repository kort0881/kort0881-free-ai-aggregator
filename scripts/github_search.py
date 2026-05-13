#!/usr/bin/env python3
"""
Поиск репозиториев GitHub с AI-фильтрацией через Groq API.
Добавлен поиск trending-репозиториев: молодых, быстро растущих и часто обновляемых.
"""

import requests
import json
import os
import time
import re
import subprocess
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
                             suffix: str = "filtered", trending_mode: bool = False) -> str | None:
    if not repos:
        return None
    os.makedirs(out_folder, exist_ok=True)
    safe = re.sub(r"[^\w]", "", trigger_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{out_folder}/{safe}_links_{suffix}_{timestamp}.md"
    with open(path, "w", encoding="utf-8") as f:
        title = "🔥 TRENDING (молодые и быстро растущие)" if trending_mode else trigger_name.upper()
        f.write(f"# {title}\n\n")
        f.write(f"Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for repo in repos:
            m = repo.get("metrics", {})
            f.write(f"- [{repo['name']}]({repo['url']}) — ⭐️ {repo['stars']}")
            if trending_mode and m:
                f.write(f" | 📈 {m['stars_per_day']} зв/день | 🕐 {m['age_days']} дней | 🔄 {m['days_since_update']} дн. назад")
            f.write("\n")
            if repo["description"]:
                f.write(f"  {repo['description'][:150]}\n")
    print(f"🔗 Markdown: {path}")
    return path

def update_readme(trigger_name: str, repos: list, readme_path: str = "README.md",
                  trending_mode: bool = False):
    if not repos:
        return

    if trending_mode:
        header = f"## 🔥 {trigger_name.upper()} – Trending (молодые + быстро растущие)\n\n"
        table = "| Репозиторий | ⭐️ | 📈 зв/день | 🕐 Возраст | 🔄 Обновлён | Описание |\n"
        table += "|-------------|-----|-----------|-----------|------------|----------|\n"
        for repo in repos[:15]:
            m = repo.get("metrics", {})
            url, name = repo["url"], repo["name"]
            desc = (repo["description"][:50] + "...") if len(repo["description"]) > 50 else repo["description"]
            table += (f"| [{name}]({url}) | {repo['stars']} | {m.get('stars_per_day','?')} "
                      f"| {m.get('age_days','?')}д | {m.get('days_since_update','?')}д назад | {desc} |\n")
    else:
        header = f"## 🚀 {trigger_name.upper()} – чистые репозитории\n\n"
        table = "| Репозиторий | ⭐️ | Описание |\n|-------------|-----|----------|\n"
        for repo in repos[:15]:
            url, name = repo["url"], repo["name"]
            desc = (repo["description"][:60] + "...") if len(repo["description"]) > 60 else repo["description"]
            table += f"| [{name}]({url}) | {repo['stars']} | {desc} |\n"

    if len(repos) > 15:
        table += f"\n*... и ещё {len(repos) - 15} репозиториев. Полный список в папке links/*\n"

    block = header + table + "\n"
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
    print(f"📝 README.md обновлён: {trigger_name}")

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
            generate_markdown_links(name, filtered, links_folder, suffix="filtered")
            update_readme(name, filtered)
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
                                    suffix="trending", trending_mode=True)
            update_readme(trend_name, trend_filtered, trending_mode=True)
        print(f"📊 Trending итог: {len(trend_filtered)} / {len(trending_repos)}")


def main():
    config = load_config()
    for trigger in config["triggers"]:
        process_trigger(trigger, config)
    commit_and_push(["README.md", "links/"])
    print("\n🎉 Готово!")


if __name__ == "__main__":
    main()
