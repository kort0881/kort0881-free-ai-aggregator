#!/usr/bin/env python3
"""
Поиск репозиториев GitHub по триггерам с сохранением метаданных.
Поддерживает триггеры: free, ai, free ai
С AI-фильтрацией мусора через OpenRouter
Генерирует отдельный Markdown-файл со списком активных ссылок на чистые репозитории.
"""

import requests
import json
import os
import time
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
    
    # Корректный синтаксис для нескольких языков (AND через пробел)
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
        "per_page": min(gh_config.get("per_page", 30), 100)
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
                "description": item.get("description") or "",
                "stars": item["stargazers_count"],
                "forks": item["forks_count"],
                "open_issues": item["open_issues_count"],
                "language": item.get("language") or "N/A",
                "license": item["license"]["key"] if item.get("license") else "none",
                "updated_at": item["updated_at"],
                "created_at": item["created_at"],
                "owner": item["owner"]["login"]
            }
            repos.append(repo_info)
        
        print(f"✅ Найдено репозиториев: {len(repos)}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка поиска: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"📋 Ответ сервера: {e.response.text[:500]}")
    
    return repos


def safe_json_parse(text):
    """Безопасный парсинг JSON с очисткой от маркдауна и лишних символов."""
    if not text:
        return None
    text = text.strip()
    # Удаляем обрамление ```json ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Пробуем найти JSON-подобный фрагмент
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end+1]
    # Исправляем распространённые ошибки экранирования
    # Например, заменяем \' на ' (но осторожно)
    text = text.replace("\\'", "'")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Если не удалось, пробуем eval (очень опасно, но для доверенного AI допустимо)
        # Лучше вернуть None
        return None


def call_ai_filter(repo_info, config):
    """
    Вызов AI для анализа репозитория через OpenRouter Free Router.
    С повторными попытками при 429 и задержками.
    """
    ai_config = config.get("ai_filter", {})
    
    if not ai_config.get("enabled", False):
        return {"is_spam": False, "reason": "AI фильтр отключён", "quality_score": 10}
    
    api_type = ai_config.get("api_type", "openrouter/free")
    model = ai_config.get("model", "openrouter/free")
    max_retries = ai_config.get("max_retries", 3)
    retry_delay = ai_config.get("retry_delay", 2)  # секунд
    rate_limit_delay = ai_config.get("rate_limit_delay", 1.5)  # задержка между вызовами
    
    # Простая задержка, чтобы не превысить лимит запросов
    time.sleep(rate_limit_delay)
    
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
- Создан: {repo_info['created_at']}

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

    for attempt in range(max_retries):
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
                
                if response.status_code == 429:
                    # Too Many Requests – ждём и повторяем
                    wait = retry_delay * (2 ** attempt)
                    print(f"⚠️ 429 Too Many Requests для {repo_info['name']}, ждём {wait} сек...")
                    time.sleep(wait)
                    continue
                
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
            
            # Парсим ответ
            analysis = safe_json_parse(ai_response)
            if analysis is None:
                raise ValueError(f"Невалидный JSON от AI: {ai_response[:200]}")
            
            return {
                "is_spam": analysis.get("is_spam", False),
                "reason": analysis.get("reason", "AI не дал причины"),
                "quality_score": analysis.get("quality_score", 5)
            }
            
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                print(f"⚠️ Ошибка AI-анализа для {repo_info['name']} после {max_retries} попыток: {e}")
                return heuristic_filter(repo_info, config)
            else:
                wait = retry_delay * (2 ** attempt)
                print(f"⚠️ Ошибка {e}, повтор через {wait} сек...")
                time.sleep(wait)
        except Exception as e:
            print(f"⚠️ Ошибка AI-анализа для {repo_info['name']}: {e}")
            return heuristic_filter(repo_info, config)
    
    # Если вышли из цикла без результата
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
    safe_name = trigger_name.replace(" ", "_").replace("/", "_")
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


def generate_links_markdown(trigger_name, repos, output_folder, suffix="filtered"):
    """
    Генерирует Markdown-файл с активными ссылками на репозитории.
    Параметры:
        trigger_name - имя триггера
        repos - список репозиториев (каждый содержит 'name' и 'url')
        output_folder - папка для сохранения
        suffix - суффикс файла (например, 'filtered' или 'all')
    """
    if not repos:
        print(f"⚠️ Нет данных для генерации ссылок по триггеру '{trigger_name}'")
        return None
    
    os.makedirs(output_folder, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = trigger_name.replace(" ", "_").replace("/", "_")
    filename = f"{output_folder}/{safe_name}_links_{suffix}_{timestamp}.md"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Репозитории по триггеру: {trigger_name}\n\n")
        f.write(f"*Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write(f"Всего репозиториев: {len(repos)}\n\n")
        f.write("## Список ссылок\n\n")
        
        for idx, repo in enumerate(repos, 1):
            name = repo.get("name", "Unknown")
            url = repo.get("url", "#")
            stars = repo.get("stars", 0)
            description = repo.get("description", "")
            if len(description) > 100:
                description = description[:97] + "..."
            
            line = f"- [{name}]({url}) — ⭐️ {stars}"
            if description:
                line += f": {description}"
            f.write(line + "\n")
    
    print(f"🔗 Ссылки сохранены в: {filename}")
    return filename


def main():
    """Основная функция."""
    config = load_config()
    all_results = {}
    
    for trigger in config["triggers"]:
        print(f"\n{'='*60}")
        print(f"🎯 Обработка триггера: {trigger['name']}")
        print(f"{'='*60}\n")
        
        query = trigger.get("query")
        if not query:
            print(f"⚠️ Пропуск триггера '{trigger['name']}': отсутствует поле 'query'")
            continue
        
        output_folder = trigger.get("output_folder", "output")
        filtered_folder = trigger.get("filtered_folder", "filtered")
        links_folder = trigger.get("links_folder", "links")  # новая опция
        
        repos = search_github_repos(query, config)
        
        if not repos:
            print("⚠️ Ничего не найдено, пропускаем")
            save_repos(trigger["name"], [], output_folder)
            all_results[trigger["name"]] = {"total": 0, "filtered": 0, "spam": 0}
            continue
        
        analysis_results = []
        filtered_repos = []
        
        for repo in repos:
            analysis = call_ai_filter(repo, config)
            analysis_results.append({
                "repo": repo["name"],
                **analysis
            })
            
            if not analysis["is_spam"]:
                filtered_repos.append({**repo, "quality_score": analysis["quality_score"]})
        
        # Сохраняем полные JSON
        save_repos(trigger["name"], repos, output_folder, analysis_results)
        
        if filtered_repos:
            save_repos(f"{trigger['name']}_filtered", filtered_repos, filtered_folder)
            # Генерируем Markdown с активными ссылками для отфильтрованных репозиториев
            generate_links_markdown(trigger["name"], filtered_repos, links_folder, suffix="filtered")
        
        # Опционально: можно также сгенерировать ссылки для всех репозиториев (включая спам)
        # generate_links_markdown(trigger["name"], repos, links_folder, suffix="all")
        
        all_results[trigger["name"]] = {
            "total": len(repos),
            "filtered": len(filtered_repos),
            "spam": len(repos) - len(filtered_repos)
        }
        
        print(f"\n📊 Резюме для {trigger['name']}:")
        print(f"   Всего найдено: {len(repos)}")
        print(f"   Прошли фильтр: {len(filtered_repos)}")
        print(f"   Отбраковано (мусор): {len(repos) - len(filtered_repos)}")
    
    print(f"\n{'='*60}")
    print("🎉 ОБЩИЕ РЕЗУЛЬТАТЫ:")
    print(f"{'='*60}")
    for trigger, res in all_results.items():
        print(f"{trigger}: {res['total']} → {res['filtered']} чистых, {res['spam']} мусора")


if __name__ == "__main__":
    main()
