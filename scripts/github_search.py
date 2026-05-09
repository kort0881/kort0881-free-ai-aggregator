#!/usr/bin/env python3
"""
Поиск репозиториев GitHub по триггерам с сохранением метаданных.
Поддерживает триггеры: free, ai, free ai
С AI-фильтрацией мусора через OpenRouter
"""

import requests
import json
import os
from datetime import datetime
from pathlib import Path


def load_config():
    """Загрузка конфигурации из config.json с проверкой существования файла."""
    config_path = Path("config.json")
    if not config_path.exists():
        raise SystemExit(
            "❌ config.json не найден.\n"
            "Создайте файл конфигурации на основе примера (см. документацию)."
        )
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def search_github_repos(query, config):
    """
    Поиск репозиториев через GitHub API.
    """
    github_token = os.getenv("GITHUB_TOKEN")
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    gh_config = config["github"]
    
    # ✅ ИСПРАВЛЕНО: корректный синтаксис для нескольких языков (AND через пробел)
    languages = gh_config.get("languages", [])
    if languages:
        lang_query = " ".join(f"language:{lang}" for lang in languages)
        full_query = f"{query} stars:>={gh_config['min_stars']} {lang_query}".strip()
    else:
        full_query = f"{query} stars:>={gh_config['min_stars']}"
    
    url = "https://api.github.com/search/repositories"
    params = {
        "q": full_query,
        "sort": gh_config.get("sort_by", "stars"),
        "order": gh_config.get("order", "desc"),
        "per_page": min(gh_config.get("per_page", 30), 100)  # максимум 100
    }
    
    print(f"🔍 Поиск по запросу: {full_query}")
    
    repos = []
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if "total_count" in data:
            print(f"ℹ️ Всего доступно: {data['total_count']}")
        
        for item in data.get("items", []):
            repo_info = {
                "name": item["full_name"],
                "url": item["html_url"],
                "description": item["description"] or "",
                "stars": item["stargazers_count"],
                "forks": item["forks_count"],
                "open_issues": item["open_issues_count"],
                "language": item["language"] or "N/A",
                "license": item["license"]["key"] if item["license"] else "none",
                "updated_at": item["updated_at"],
                "created_at": item["created_at"],
                "owner": item["owner"]["login"],
                "has_readme": item["has_readme"],
                "default_branch": item["default_branch"]
            }
            repos.append(repo_info)
        
        print(f"✅ Найдено репозиториев: {len(repos)}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка поиска: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"📋 Ответ сервера: {e.response.text[:500]}")
    
    return repos


def call_ai_filter(repo_info, config):
    """
    Вызов AI для анализа репозитория через OpenRouter Free Router.
    """
    ai_config = config.get("ai_filter", {})
    
    if not ai_config.get("enabled", False):
        return {"is_spam": False, "reason": "AI фильтр отключён", "quality_score": 10}
    
    api_type = ai_config.get("api_type", "openrouter/free")
    model = ai_config.get("model", "openrouter/free")
    
    prompt = f"""
Ты эксперт по оценке качества GitHub репозиториев. Проанализируй репозиторий и определи, является ли он мусором/спамом.

Данные репозитория:
- Название: {repo_info['name']}
- Описание: {repo_info['description']}
- Язык: {repo_info['language']}
- Звёзды: {repo_info['stars']}
- Форки: {repo_info['forks']}
- Лицензия: {repo_info['license']}
- Последнее обновление: {repo_info['updated_at']}
- Есть README: {repo_info['has_readme']}

Критерии мусора:
- Крипта, bitcoin, скам, платный контент под видом бесплатного
- Пустые репозитории без кода
- Устаревшие (>3 года без обновлений)
- Фейковые звёзды, накрутка
- Не по теме (в названии "ai" но не про ИИ)
- Только бинарники без исходного кода
- OnlyFans, cam, adult, porn

Ответ ТОЛЬКО в формате JSON (без markdown, без пояснений):
{{
    "is_spam": true/false,
    "reason": "краткое объяснение",
    "quality_score": число от 0 до 10
}}
""".strip()

    try:
        if api_type in ["openrouter/free", "openrouter"]:
            api_key = os.getenv("MODELS_ROUTER")
            if not api_key:
                print("⚠️ MODELS_ROUTER не задан – AI-фильтр отключён для этого вызова")
                return heuristic_filter(repo_info, config)
            
            api_url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/free-ai-aggregator",
                "X-Title": "Free AI Aggregator"
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "Ты эксперт по оценке GitHub репозиториев. Ответ ТОЛЬКО JSON."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": ai_config.get("token_limit", 4000)
            }
            response = requests.post(api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            ai_response = response.json()["choices"][0]["message"]["content"]
        
        elif api_type == "ollama":
            api_url = ai_config.get("api_url", "http://localhost:11434/api/generate")
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": ai_config.get("token_limit", 4000)}
            }
            response = requests.post(api_url, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            ai_response = result.get("response", "{}")
        
        else:
            return {"is_spam": False, "reason": f"Неизвестный API: {api_type}", "quality_score": 10}
        
        ai_response = ai_response.strip().strip("`")
        if ai_response.startswith("json"):
            ai_response = ai_response[4:].strip()
        
        analysis = json.loads(ai_response)
        
        return {
            "is_spam": analysis.get("is_spam", False),
            "reason": analysis.get("reason", "AI не дал причины"),
            "quality_score": analysis.get("quality_score", 5)
        }
        
    except Exception as e:
        print(f"⚠️ Ошибка AI-анализа для {repo_info['name']}: {e}")
        return heuristic_filter(repo_info, config)


def heuristic_filter(repo_info, config):
    """Быстрая эвристика как запасной вариант."""
    ai_config = config.get("ai_filter", {})
    spam_keywords = ai_config.get("spam_keywords", [])
    min_score = ai_config.get("min_quality_score", 6)
    
    # Проверка на спам-слова в описании
    desc_lower = repo_info["description"].lower()
    for keyword in spam_keywords:
        if keyword.lower() in desc_lower:
            return {
                "is_spam": True,
                "reason": f"Спам-ключевое слово: {keyword}",
                "quality_score": 0
            }
    
    # Проверка на устаревший репозиторий (более 3 лет без обновлений)
    updated = datetime.fromisoformat(repo_info["updated_at"].replace("Z", "+00:00"))
    days_old = (datetime.now(updated.tzinfo) - updated).days
    if days_old > 1095:
        return {
            "is_spam": True,
            "reason": f"Устаревший: не обновлялся {days_old} дней",
            "quality_score": 2
        }
    
    # Набор замечаний (не критичных, но снижающих оценку)
    reason_checks = []
    if not repo_info["has_readme"]:
        reason_checks.append("нет README")
    if repo_info["license"] == "none":
        reason_checks.append("нет лицензии")
    
    created = datetime.fromisoformat(repo_info["created_at"].replace("Z", "+00:00"))
    days_since_creation = (datetime.now(created.tzinfo) - created).days
    stars_per_month = (repo_info["stars"] / days_since_creation) * 30 if days_since_creation > 0 else 0
    if stars_per_month < 1 and repo_info["stars"] < 100:
        reason_checks.append("низкая популярность")
    
    # Качество: базовое 10 минус штрафы
    quality_score = 10 - len(reason_checks) * 2 - days_old // 365
    quality_score = max(0, quality_score)
    
    if quality_score < min_score:
        return {
            "is_spam": True,
            "reason": f"Низкое качество: {'; '.join(reason_checks)}",
            "quality_score": quality_score
        }
    
    return {
        "is_spam": False,
        "reason": "OK" if not reason_checks else f"Принят с замечаниями: {'; '.join(reason_checks)}",
        "quality_score": quality_score
    }


def save_repos(trigger_name, repos, output_folder, analysis_results=None):
    """Сохранение репозиториев в JSON (имя файла безопасно от пробелов)."""
    os.makedirs(output_folder, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = trigger_name.replace(" ", "_").replace("/", "_")  # убираем пробелы и слеши
    filename = f"{output_folder}/{safe_name}_{timestamp}.json"
    
    data = {
        "trigger": trigger_name,
        "collected_at": timestamp,
        "total_repos": len(repos),
        "repositories": repos,
        "analysis": analysis_results or []
    }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Сохранено в: {filename}")
    return filename


def main():
    """Основная функция."""
    config = load_config()
    all_results = {}
    
    for trigger in config["triggers"]:
        print(f"\n{'='*60}")
        print(f"🎯 Обработка триггера: {trigger['name']}")
        print(f"{'='*60}\n")
        
        # Проверяем наличие обязательных полей
        query = trigger.get("query")
        if not query:
            print(f"⚠️ Пропуск триггера '{trigger['name']}': отсутствует поле 'query'")
            continue
        
        output_folder = trigger.get("output_folder", "output")
        filtered_folder = trigger.get("filtered_folder", "filtered")  # значение по умолчанию
        
        repos = search_github_repos(query, config)
        
        if not repos:
            print("⚠️ Ничего не найдено, пропускаем")
            save_repos(trigger["name"], [], output_folder)
            all_results[trigger["name"]] = {"total": 0, "filtered": 0, "spam": 0}
            continue
        
        analysis_results = []
        filtered_repos = []
        
        for repo in repos:
            analysis = call_ai_filter(repo, config)   # напрямую, без лишней обёртки
            analysis_results.append({
                "repo": repo["name"],
                **analysis
            })
            
            if not analysis["is_spam"]:
                filtered_repos.append({**repo, "quality_score": analysis["quality_score"]})
        
        save_repos(trigger["name"], repos, output_folder, analysis_results)
        
        if filtered_repos:
            save_repos(f"{trigger['name']}_filtered", filtered_repos, filtered_folder)
        
        all_results[trigger["name"]] = {
            "total": len(repos),
            "filtered": len(filtered_repos),
            "spam": len(repos) - len(filtered_repos)
        }
        
        print(f"\n📊 Резюме для {trigger['name']}:")
        print(f"   Всего найдено: {len(repos)}")
        print(f"   Прошли фильтр: {len(filtered_repos)}")
        print(f"   Отбраковано (мусор): {len(repos) - len(filtered_repos)}")
    
    # Общий итог
    print(f"\n{'='*60}")
    print("🎉 ОБЩИЕ РЕЗУЛЬТАТЫ:")
    print(f"{'='*60}")
    for trigger, res in all_results.items():
        print(f"{trigger}: {res['total']} → {res['filtered']} чистых, {res['spam']} мусора")


if __name__ == "__main__":
    main()
