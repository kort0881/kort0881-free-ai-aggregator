#!/usr/bin/env python3
"""
Поиск репозиториев GitHub по триггерам с сохранением метаданных.
Поддерживает триггеры: free, ai, free ai
"""

import requests
import json
import os
from datetime import datetime
from pathlib import Path


def load_config():
    """Загрузка конфигурации из config.json"""
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def search_github_repos(query, config):
    """
    Поиск репозиториев через GitHub API.
    
    Args:
        query: Поисковый запрос (триггер)
        config: Конфигурация
        
    Returns:
        Список репозиториев с метаданными
    """
    github_token = os.getenv("GITHUB_TOKEN")
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    gh_config = config["github"]
    
    # Формируем запрос с фильтрами
    language_filter = " OR ".join([f"language:{lang}" for lang in gh_config["languages"]])
    full_query = f"{query} stars:>={gh_config['min_stars']} {language_filter}"
    
    url = "https://api.github.com/search/repositories"
    params = {
        "q": full_query,
        "sort": gh_config["sort_by"],
        "order": gh_config["order"],
        "per_page": gh_config["per_page"]
    }
    
    print(f"🔍 Поиск по запросу: {full_query}")
    
    repos = []
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
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
    
    return repos


def analyze_repo_with_ai(repo_info, config):
    """
    Анализ репозитория через AI для выявления мусора.
    
    Returns:
        dict: {is_spam: bool, reason: str, quality_score: int}
    """
    if not config["ai_filter"]["enabled"]:
        return {"is_spam": False, "reason": "AI фильтр отключен", "quality_score": 10}
    
    spam_keywords = config["ai_filter"]["spam_keywords"]
    min_score = config["ai_filter"]["min_quality_score"]
    
    # Быстрая эвристика до AI
    reason_checks = []
    
    # Проверка по ключевым словам спам
    desc_lower = repo_info["description"].lower()
    for keyword in spam_keywords:
        if keyword.lower() in desc_lower:
            return {
                "is_spam": True,
                "reason": f"Спам-ключевое слово: {keyword}",
                "quality_score": 0
            }
    
    # Устаревший репозиторий
    updated = datetime.fromisoformat(repo_info["updated_at"].replace("Z", "+00:00"))
    days_old = (datetime.now(updated.tzinfo) - updated).days
    if days_old > 1095:  # 3 года
        return {
            "is_spam": True,
            "reason": f"Устаревший: не обновлялся {days_old} дней",
            "quality_score": 2
        }
    
    # Нет README
    if not repo_info["has_readme"]:
        reason_checks.append("нет README")
    
    # Нет лицензии
    if repo_info["license"] == "none":
        reason_checks.append("нет лицензии")
    
    # Мало звёзд относительно дат создания
    created = datetime.fromisoformat(repo_info["created_at"].replace("Z", "+00:00"))
    days_since_creation = (datetime.now(created.tzinfo) - created).days
    stars_per_month = (repo_info["stars"] / days_since_creation) * 30 if days_since_creation > 0 else 0
    
    if stars_per_month < 1 and repo_info["stars"] < 100:
        reason_checks.append("низкая популярность")
    
    # Оценка качества
    quality_score = 10
    quality_score -= len(reason_checks) * 2
    quality_score -= days_old // 365  # -1 за каждый год
    
    if quality_score < 0:
        quality_score = 0
    
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
    """Сохранение репозиториев в JSON"""
    os.makedirs(output_folder, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{output_folder}/{trigger_name}_{timestamp}.json"
    
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
    """Основная функция"""
    config = load_config()
    
    all_results = {}
    
    for trigger in config["triggers"]:
        print(f"\n{'='*60}")
        print(f"🎯 Обработка триггера: {trigger['name']}")
        print(f"{'='*60}\n")
        
        # Поиск
        repos = search_github_repos(trigger["query"], config)
        
        if not repos:
            print("⚠️ Ничего не найдено, пропускаем")
            continue
        
        # AI-анализ
        analysis_results = []
        filtered_repos = []
        
        for repo in repos:
            analysis = analyze_repo_with_ai(repo, config)
            analysis_results.append({
                "repo": repo["name"],
                **analysis
            })
            
            if not analysis["is_spam"]:
                filtered_repos.append({**repo, "quality_score": analysis["quality_score"]})
        
        # Сохранение сырых данных
        save_repos(
            trigger["name"],
            repos,
            trigger["output_folder"]
        )
        
        # Сохранение отфильтрованных данных
        if filtered_repos:
            save_repos(
                f"{trigger['name']}_filtered",
                filtered_repos,
                trigger["filtered_folder"]
            )
        
        all_results[trigger["name"]] = {
            "total": len(repos),
            "filtered": len(filtered_repos),
            "spam": len(repos) - len(filtered_repos)
        }
        
        print(f"\n📊 Резюме для {trigger['name']}:")
        print(f"   Всего найденно: {len(repos)}")
        print(f"   Прошли фильтр: {len(filtered_repos)}")
        print(f"   Отбраковано (мусор): {len(repos) - len(filtered_repos)}")
    
    # Итоговый отчёт
    print(f"\n{'='*60}")
    print("🎉 ВСЕГО РЕЗУЛЬТАТЫ:")
    print(f"{'='*60}")
    for trigger, res in all_results.items():
        print(f"{trigger}: {res['total']} → {res['filtered']} чистых, {res['spam']} мусора")


if __name__ == "__main__":
    main()
