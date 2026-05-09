#!/usr/bin/env python3
"""
Поиск репозиториев GitHub по триггерам с AI-фильтрацией.
Сохраняет результаты в JSON, создаёт Markdown-файлы со ссылками,
обновляет README.md и автоматически пушит изменения в репозиторий (в CI).
"""

import requests
import json
import os
import time
import re
import subprocess
from datetime import datetime
from pathlib import Path

# ====================== КОНФИГУРАЦИЯ ======================
def load_config():
    config_path = Path("config.json")
    if not config_path.exists():
        raise SystemExit("❌ config.json не найден. Создайте его по примеру.")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

# ====================== GITHUB API ======================
def search_github_repos(query, config):
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    gh_config = config["github"]
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
    print(f"🔍 Поиск: {full_query}")
    
    repos = []
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        print(f"ℹ️ Всего доступно: {data.get('total_count', 0)}")
        for item in data.get("items", []):
            repos.append({
                "name": item["full_name"],
                "url": item["html_url"],
                "description": item.get("description") or "",
                "stars": item["stargazers_count"],
                "forks": item["forks_count"],
                "language": item.get("language") or "N/A",
                "license": item["license"]["key"] if item.get("license") else "none",
                "updated_at": item["updated_at"],
                "created_at": item["created_at"],
            })
        print(f"✅ Найдено: {len(repos)}")
    except Exception as e:
        print(f"❌ Ошибка поиска: {e}")
    return repos

# ====================== AI ФИЛЬТР ======================
def safe_json_parse(text):
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end+1]
    text = text.replace("\\'", "'")
    try:
        return json.loads(text)
    except:
        return None

def heuristic_filter(repo_info, config):
    ai_config = config.get("ai_filter", {})
    spam_keywords = ai_config.get("spam_keywords", [])
    min_score = ai_config.get("min_quality_score", 6)
    desc_lower = repo_info["description"].lower()
    for kw in spam_keywords:
        if kw.lower() in desc_lower:
            return {"is_spam": True, "reason": f"Спам слово: {kw}", "quality_score": 0}
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
    quality_score = max(0, 10 - len(reason_checks)*2 - days_old//365)
    if quality_score < min_score:
        return {"is_spam": True, "reason": f"Низкое качество: {', '.join(reason_checks)}", "quality_score": quality_score}
    return {"is_spam": False, "reason": "OK" if not reason_checks else f"Принят: {', '.join(reason_checks)}", "quality_score": quality_score}

def call_ai_filter(repo_info, config):
    ai_config = config.get("ai_filter", {})
    if not ai_config.get("enabled", False):
        return {"is_spam": False, "reason": "AI отключён", "quality_score": 10}
    rate_limit_delay = ai_config.get("rate_limit_delay", 1.5)
    time.sleep(rate_limit_delay)
    prompt = f"""Ты эксперт по GitHub. Репозиторий: {repo_info['name']}. Описание: {repo_info['description']}. Язык: {repo_info['language']}. Звёзды: {repo_info['stars']}. Форки: {repo_info['forks']}. Лицензия: {repo_info['license']}. Обновлён: {repo_info['updated_at']}. Мусор? Ответь JSON: {{"is_spam": true/false, "reason": "...", "quality_score": 0-10}}"""
    for attempt in range(3):
        try:
            api_key = os.getenv("MODELS_ROUTER")
            if not api_key:
                return heuristic_filter(repo_info, config)
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": ai_config.get("model", "openrouter/free"),
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500
                },
                timeout=60
            )
            if response.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            ai_text = response.json()["choices"][0]["message"]["content"]
            analysis = safe_json_parse(ai_text)
            if analysis:
                return analysis
        except Exception as e:
            print(f"⚠️ AI ошибка {repo_info['name']}: {e}")
        time.sleep(1)
    return heuristic_filter(repo_info, config)

# ====================== СОХРАНЕНИЕ И ОБНОВЛЕНИЕ README ======================
def save_json(trigger_name, repos, out_folder, analysis=None):
    os.makedirs(out_folder, exist_ok=True)
    safe = trigger_name.replace(" ", "_").replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{out_folder}/{safe}_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "trigger": trigger_name,
            "collected_at": timestamp,
            "total_repos": len(repos),
            "repositories": repos,
            "analysis": analysis or []
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 JSON: {path}")
    return path

def generate_markdown_links(trigger_name, repos, out_folder="links", suffix="filtered"):
    if not repos:
        return None
    os.makedirs(out_folder, exist_ok=True)
    safe = trigger_name.replace(" ", "_").replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{out_folder}/{safe}_links_{suffix}_{timestamp}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {trigger_name.upper()} репозитории (чистые)\n\n")
        f.write(f"*Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        for repo in repos:
            f.write(f"- [{repo['name']}]({repo['url']}) — ⭐️ {repo['stars']}\n")
            if repo['description']:
                f.write(f"  {repo['description'][:150]}\n")
    print(f"🔗 Markdown ссылки: {path}")
    return path

def update_readme(trigger_name, repos, readme_path="README.md"):
    if not repos:
        return
    header = f"## 🚀 {trigger_name.upper()} – чистые репозитории\n\n"
    table = "| Репозиторий | ⭐️ Звёзды | Описание |\n|-------------|-----------|-----------|\n"
    for repo in repos[:15]:
        name = repo['name']
        url = repo['url']
        stars = repo['stars']
        desc = repo['description'][:60] + "..." if len(repo['description']) > 60 else repo['description']
        table += f"| [{name}]({url}) | {stars} | {desc} |\n"
    if len(repos) > 15:
        table += f"\n*... и ещё {len(repos)-15} репозиториев. Полный список в папке [links/](links).*\n"
    block = header + table + "\n"
    start_marker = f"<!-- START_{trigger_name.upper()} -->"
    end_marker = f"<!-- END_{trigger_name.upper()} -->"
    new_block = f"{start_marker}\n{block}\n{end_marker}"
    
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
    print(f"📝 README.md обновлён для {trigger_name}")

def commit_and_push(files=["README.md", "links/"]):
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
        subprocess.run(["git", "commit", "-m", "Автообновление списков репозиториев [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Изменения запушены в репозиторий")
    except Exception as e:
        print(f"⚠️ Ошибка коммита/пуша: {e}")

# ====================== MAIN ======================
def main():
    config = load_config()
    all_results = {}
    
    for trigger in config["triggers"]:
        print(f"\n{'='*60}\n🎯 {trigger['name']}\n{'='*60}")
        query = trigger.get("query")
        if not query:
            continue
        repos = search_github_repos(query, config)
        if not repos:
            save_json(trigger["name"], [], trigger.get("output_folder", "output"))
            continue
        
        analysis_results = []
        filtered = []
        for repo in repos:
            analysis = call_ai_filter(repo, config)
            analysis_results.append({"repo": repo["name"], **analysis})
            if not analysis["is_spam"]:
                filtered.append(repo)
        
        save_json(trigger["name"], repos, trigger.get("output_folder", "output"), analysis_results)
        if filtered:
            save_json(f"{trigger['name']}_filtered", filtered, trigger.get("filtered_folder", "filtered"))
            generate_markdown_links(trigger["name"], filtered, trigger.get("links_folder", "links"))
            update_readme(trigger["name"], filtered)
        
        all_results[trigger["name"]] = {"total": len(repos), "filtered": len(filtered)}
        print(f"📊 Итог: {len(filtered)} / {len(repos)} прошли фильтр")
    
    commit_and_push(["README.md", "links/"])

if __name__ == "__main__":
    main()
