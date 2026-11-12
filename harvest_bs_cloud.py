#!/usr/bin/env python3
import os
import sys
import json
import gzip
import time
import subprocess
import urllib.request
import urllib.error
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

GITHUB_USER = "parshant65-lang"
ARTICLES_PER_RUN = 1000
ARTICLES_PER_FILE = 250
WORKER_THREADS = 10

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"
]

VAULT_MAP = [
    {"name": "business-standard-vault-1", "start": 2015, "end": 2017},
    {"name": "business-standard-vault-2", "start": 2018, "end": 2020},
    {"name": "business-standard-vault-3", "start": 2021, "end": 2023},
    {"name": "business-standard-vault-4", "start": 2024, "end": 2026}
]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"}

def safe_git(cmd, cwd):
    for attempt in range(3):
        try:
            return subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.STDOUT).decode().strip()
        except subprocess.CalledProcessError as e:
            err = e.output.decode() if e.output else str(e)
            print(f"[GIT-WARN] Attempt {attempt+1} failed: {err}")
            time.sleep(3)
    raise RuntimeError(f"Git failed: {' '.join(cmd)}")

def fetch_sitemap_urls(year, month_name):
    url = f"https://www.business-standard.com/sitemap/{year}-{month_name}-1.xml"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            locs = re.findall(r"<loc>(.*?)</loc>", content)
            return locs
    except Exception as e:
        print(f"[SITEMAP-ERR] Failed to fetch sitemap {url}: {e}")
        return []

def extract_single_article(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
            if not m:
                return None
            data = json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("data", {})
            html_content = data.get("htmlContent", "")
            clean_body = ""
            if html_content:
                clean_body = BeautifulSoup(html_content, "html.parser").get_text(separator=" ").strip()
            
            # If htmlContent is empty, fallback to description
            if not clean_body:
                clean_body = data.get("description", "")

            heading = data.get("heading1", "")
            if isinstance(heading, str):
                heading = heading.strip()
                
            return {
                "id": data.get("articleId"),
                "title": heading,
                "subheading": data.get("subHeading", ""),
                "publish_date": data.get("publishDate"),
                "modification_date": data.get("modificationDate"),
                "url": url,
                "category": data.get("defaultArticleCat", {}).get("category_name", ""),
                "tags": data.get("articleTags", ""),
                "body": clean_body
            }
        except Exception:
            time.sleep(1 * (attempt + 1))
    return None

def find_active_vault(pat):
    # Check vaults in order
    for v_info in VAULT_MAP:
        v_name = v_info["name"]
        remote = f"https://x-access-token:{pat}@github.com/{GITHUB_USER}/{v_name}.git"
        temp_dir = f"temp_{v_name}"
        if os.path.exists(temp_dir):
            subprocess.run(["rm", "-rf", temp_dir])
            
        safe_git(["git", "clone", "--depth", "1", remote, temp_dir], cwd=".")
        ckpt_file = os.path.join(temp_dir, "checkpoint.json")
        with open(ckpt_file, "r", encoding="utf-8") as f:
            ckpt = json.load(f)
            
        cur_year = ckpt.get("current_year", v_info["start"])
        end_year = v_info["end"]
        
        if cur_year <= end_year:
            # Found active vault!
            return v_info, temp_dir, ckpt
            
        # If this vault is already complete, remove temp dir and continue to next
        subprocess.run(["rm", "-rf", temp_dir])
        
    return None, None, None

def main():
    pat = os.environ.get("VAULT_PAT")
    if not pat:
        print("[ERROR] VAULT_PAT not set!")
        sys.exit(1)
        
    print("[INIT] Detecting active Business Standard vault...")
    v_info, vault_dir, ckpt = find_active_vault(pat)
    
    if not v_info:
        print("[COMPLETE] All Business Standard vaults (2015-2026) are fully harvested!")
        return

    v_name = v_info["name"]
    safe_git(["git", "config", "user.name", "BSCloudBot"], cwd=vault_dir)
    safe_git(["git", "config", "user.email", "bot@intelligence.internal"], cwd=vault_dir)

    cur_year = ckpt.get("current_year", v_info["start"])
    cur_month_idx = ckpt.get("current_month_idx", 0)
    cur_offset = ckpt.get("current_url_offset", 0)
    total_articles = ckpt.get("articles_collected", 0)
    
    print(f"[ACTIVE] Vault: {v_name} | Year: {cur_year} | Month: {MONTHS[cur_month_idx]} | Offset: {cur_offset} | Total Collected: {total_articles:,}")

    collected_in_run = 0
    
    while collected_in_run < ARTICLES_PER_RUN and cur_year <= v_info["end"]:
        month_name = MONTHS[cur_month_idx]
        print(f"\n[FETCH] Loading sitemap for {cur_year} {month_name}...")
        urls = fetch_sitemap_urls(cur_year, month_name)
        
        if not urls:
            print(f"[WARN] No URLs for {cur_year} {month_name}. Advancing to next month.")
            cur_month_idx += 1
            cur_offset = 0
            if cur_month_idx >= 12:
                cur_year += 1
                cur_month_idx = 0
            ckpt["current_year"] = cur_year
            ckpt["current_month_idx"] = cur_month_idx
            ckpt["current_url_offset"] = 0
            continue
            
        print(f"  Found {len(urls)} total articles in {cur_year} {month_name} sitemap. Processing from offset {cur_offset}...")
        
        remaining_urls = urls[cur_offset:]
        if not remaining_urls:
            print(f"[DONE] Completed {cur_year} {month_name}.")
            cur_month_idx += 1
            cur_offset = 0
            if cur_month_idx >= 12:
                cur_year += 1
                cur_month_idx = 0
            ckpt["current_year"] = cur_year
            ckpt["current_month_idx"] = cur_month_idx
            ckpt["current_url_offset"] = 0
            continue
            
        needed = ARTICLES_PER_RUN - collected_in_run
        batch_urls = remaining_urls[:needed]
        
        print(f"[EXTRACT] Multi-threaded extraction for {len(batch_urls)} articles ({WORKER_THREADS} threads)...")
        t0 = time.time()
        
        extracted_batch = []
        with ThreadPoolExecutor(max_workers=WORKER_THREADS) as executor:
            future_to_url = {executor.submit(extract_single_article, u): u for u in batch_urls}
            for future in as_completed(future_to_url):
                res = future.result()
                if res and res.get("body"):
                    extracted_batch.append(res)
                    
        dt = time.time() - t0
        valid_count = len(extracted_batch)
        collected_in_run += valid_count
        total_articles += valid_count
        cur_offset += len(batch_urls)
        
        print(f"  ✓ Extracted {valid_count}/{len(batch_urls)} articles in {dt:.2f}s ({valid_count/max(dt,1):.1f} arts/s)")
        
        # Save batch file in compressed chunks
        if extracted_batch:
            year_dir = os.path.join(vault_dir, "data", str(cur_year))
            os.makedirs(year_dir, exist_ok=True)
            
            for i in range(0, len(extracted_batch), ARTICLES_PER_FILE):
                sub_chunk = extracted_batch[i:i+ARTICLES_PER_FILE]
                file_name = f"{cur_year}_{month_name}_part_{cur_offset - len(batch_urls) + i:06d}.json.gz"
                file_path = os.path.join(year_dir, file_name)
                comp = gzip.compress(json.dumps(sub_chunk, ensure_ascii=False).encode("utf-8"))
                with open(file_path, "wb") as f:
                    f.write(comp)
                print(f"[SAVED] {file_name} ({len(sub_chunk)} articles, {len(comp)/1024:.1f} KB)")
                
        # Check if month completed
        if cur_offset >= len(urls):
            print(f"[COMPLETE-MONTH] Finished all {len(urls)} articles for {cur_year} {month_name}!")
            cur_month_idx += 1
            cur_offset = 0
            if cur_month_idx >= 12:
                cur_year += 1
                cur_month_idx = 0
                
        ckpt["current_year"] = cur_year
        ckpt["current_month_idx"] = cur_month_idx
        ckpt["current_url_offset"] = cur_offset
        ckpt["articles_collected"] = total_articles
        ckpt["updated_at"] = datetime.utcnow().isoformat() + "Z"

    # Save checkpoint
    ckpt_path = os.path.join(vault_dir, "checkpoint.json")
    with open(ckpt_path, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, indent=2)

    # Git commit and push
    if collected_in_run > 0:
        safe_git(["git", "add", "-A"], cwd=vault_dir)
        commit_msg = f"[BS-CLOUD] Ingest {cur_year} (+{collected_in_run:,} articles, Total Vault: {total_articles:,}) [skip ci]"
        safe_git(["git", "commit", "-m", commit_msg], cwd=vault_dir)
        print(f"[PUSH] Pushing to {v_name}...")
        safe_git(["git", "push", "origin", "main"], cwd=vault_dir)
        print(f"[SUCCESS] Pushed batch: {commit_msg}")
    else:
        print("[INFO] No articles collected in this cycle.")

    subprocess.run(["rm", "-rf", vault_dir])

if __name__ == "__main__":
    main()
