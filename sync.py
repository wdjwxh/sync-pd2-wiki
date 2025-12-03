# -*- coding: utf-8 -*-
"""
MediaWiki 最近变更同步工具 - 绯红终版
支持：
1. 正常全量同步（无参数）
2. 手动指定时间起点：--since 2025-11-28T00:00:00Z
3. 只同步单个页面：--title "页面名称"
4. 单个页面时可选更新全局时间戳：--update-timestamp
5. 全部使用官方 action=compare 生成最完美的 diff
"""

import os
import argparse
from pathlib import Path
from datetime import datetime
import requests
from dotenv import load_dotenv

# ==================== 配置区 ====================
load_dotenv()
WIKI_API_URL = os.getenv("WIKI_API_URL")   # 从.env文件加载
OUTPUT_DIR = Path("wiki_sync_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# 全局变量，存储本次执行的输出目录
CURRENT_OUTPUT_DIR = None

LAST_TIMESTAMP_FILE = "last_sync_timestamp.txt"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "WikiSyncTool/3.0 (your-email@example.com; MediaWiki Sync Bot)"
})
# ================================================

def load_last_timestamp():
    if not os.path.exists(LAST_TIMESTAMP_FILE):
        return None
    with open(LAST_TIMESTAMP_FILE, encoding="utf-8") as f:
        return f.read().strip()

def save_last_timestamp(ts):
    with open(LAST_TIMESTAMP_FILE, "w", encoding="utf-8") as f:
        f.write(ts)

def get_recent_changes(since):
    """获取自 since 时间后每个页面的最新 revid（自动去重）"""
    params = {
        "action": "query",
        "list": "recentchanges",
        "rcprop": "title|ids|timestamp",
        "rctype": "edit|new",
        "rcdir": "newer",
        "rcstart": since,
        "rclimit": 500,
        "format": "json"
    }
    latest = {}
    while True:
        try:
            r = SESSION.get(WIKI_API_URL, params=params)
            r.raise_for_status()
            response_data = r.json()
            if "error" in response_data:
                raise Exception(response_data["error"])
            for rc in response_data.get("query", {}).get("recentchanges", []):
                latest[rc["title"]] = (rc["revid"], rc["timestamp"])
            if "continue" not in response_data:
                break
            params.update(response_data["continue"])
        except Exception as e:
            print(f"获取最近更改时出错: {e}")
            break
    return latest

def get_old_revid(title, end_time):
    """获取 ≤ end_time 的最后一次修订的 revid（用于 fromrev）"""
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvprop": "ids|timestamp",
        "rvlimit": 1,  # 获取2个版本，确保能找到不同的版本
        "rvdir": "older",
        "rvstart": end_time,
        "format": "json"
    }
    try:
        r = SESSION.get(WIKI_API_URL, params=params).json()
        url = WIKI_API_URL + "?" + "&".join([f"{k}={v}" for k, v in params.items()])
        print(f"  请求URL: {url}")
        pages = r["query"]["pages"]
        page = next(iter(pages.values()))
        if "revisions" not in page:
            print(f"  页面 '{title}' 在指定时间前没有找到修订版本")
            return None
        
        revisions = page["revisions"]
        if len(revisions) >= 1:
            return revisions[0]["revid"]
        print(f"  页面 '{title}' 在指定时间前没有找到修订版本")
        return None
    except Exception as e:
        print(f"获取旧版本ID时出错: {e}")
        return None

def get_official_diff_and_content(title, from_revid, to_revid):
    # 获取官方 diff（HTML）
    diff_params = {
        "action": "compare",
        "fromrev": from_revid or "",
        "torev": to_revid,
        "format": "json"
    }
    
    print(f"  获取diff: fromrev={from_revid}, torev={to_revid}")
    
    try:
        diff_resp = SESSION.get(WIKI_API_URL, params=diff_params).json()
        print(f"  Diff响应: {list(diff_resp.keys())}")
        diff_html = diff_resp.get("compare", {}).get("*", "<p>无法获取 diff</p>")
        print(f"  Diff内容长度: {len(diff_html)} 字符")

        # 获取最新完整内容
        content_params = {
            "action": "query",
            "prop": "revisions",
            "titles": title,
            "rvprop": "content|timestamp",
            "rvslots": "main",
            "format": "json"
        }
        r = SESSION.get(WIKI_API_URL, params=content_params).json()
        page = next(iter(r["query"]["pages"].values()))
        if "revisions" not in page:
            return None, None, None
        rev = page["revisions"][0]
        full_text = rev["slots"]["main"]["*"]
        ts = rev["timestamp"]
        return diff_html, full_text, ts
    except Exception as e:
        print(f"获取diff和内容时出错: {e}")
        return None, None, None

def save_files(title, diff_html, full_text, timestamp, note="", revid=None):
    global CURRENT_OUTPUT_DIR
    
    # 确保本次执行的输出目录已经创建
    if CURRENT_OUTPUT_DIR is None:
        current_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        CURRENT_OUTPUT_DIR = OUTPUT_DIR / current_time_str
        CURRENT_OUTPUT_DIR.mkdir(exist_ok=True)
        print(f"创建本次执行的输出目录: {CURRENT_OUTPUT_DIR}")
    
    safe_title = "".join(c if c.isalnum() or c in " -_." else "_" for c in title)
    time_str = timestamp[:19].replace("-", "").replace(":", "").replace("T", "_")
    # 简化文件名格式，只包含标题、时间和revid
    base_filename = f"{safe_title}-{time_str}-{revid}" if revid else f"{safe_title}-{time_str}"
    
    diff_file = CURRENT_OUTPUT_DIR / f"{base_filename}.diff.html"
    full_file = CURRENT_OUTPUT_DIR / f"{base_filename}.full.txt"

    # 美化 HTML diff，使用类似git diff的配色方案
    # 先处理diff_html，将ins/del标签替换为span标签
    processed_diff_html = diff_html.replace('<ins class="diffchange', '<span class="diffchange added"').replace('</ins>', '</span>').replace('<del class="diffchange', '<span class="diffchange deleted"').replace('</del>', '</span>')
    # 再处理diff标记，将data-marker属性替换为实际的span元素
    processed_diff_html = processed_diff_html.replace('<td class="diff-marker" data-marker="−"></td>', '<td class="diff-marker"><span class="minus-marker">−</span></td>').replace('<td class="diff-marker" data-marker="+"></td>', '<td class="diff-marker"><span class="plus-marker">+</span></td>')
    
    html_wrapper = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Diff: {title}</title>
<style>
body {{
  font-family: system-ui, sans-serif;
  margin: 20px;
}}
table.diff {{
  border-collapse: collapse;
  font-family: monospace;
  width: 100%;
  table-layout: fixed;
}}
table.diff td {{
  padding: 0 5px;
  vertical-align: top;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 14px;
  line-height: 1.4;
}}
table.diff col.diff-marker {{
  width: 20px;
  text-align: right;
  background-color: #fafafa;
}}
table.diff col.diff-content {{
  width: auto;
}}
table.diff col.diff-addedline,
table.diff col.diff-deletedline {{
  width: 50%;
}}
.diff-addedline {{
  background-color: #dfd;
}}
.diff-addedline .diffchange {{
  background-color: #9e9;
  color: #000;
}}
.diff-deletedline {{
  background-color: #fee8e8;
}}
.diff-deletedline .diffchange {{
  background-color: #faa;
  color: #000;
}}
.diff-context {{
  background-color: #fafafa;
}}
.diff-context td {{
  color: #777;
}}
.diff-marker {{
  font-weight: bold;
  text-align: right;
  padding: 0 4px;
}}
.diff-lineno {{
  background-color: #f0f0f0;
  text-align: right;
  padding: 0 4px;
}}
.diff-addedline .diff-marker {{
  color: #080;
}}
.diff-deletedline .diff-marker {{
  color: #800;
}}

/* 新增的diff标记样式 */
.plus-marker {{
  color: #080;
  font-weight: bold;
}}
.minus-marker {{
  color: #800;
  font-weight: bold;
}}

/* 确保变更行有明显的视觉区分 */
.diff-addedline div,
.diff-deletedline div {{
  display: inline-block;
  width: 100%;
}}

/* 增加一些额外的视觉提示 */
.diff-addedline {{
  border-left: 4px solid #080;
}}
.diff-deletedline {{
  border-left: 4px solid #800;
}}
.diff-context {{
  border-left: 4px solid #ccc;
}}

/* 替换ins/del标签为span标签的样式 */
.diffchange.added {{
  background-color: #9e9;
  color: #000;
  font-weight: bold;
  text-decoration: none;
}}
.diffchange.deleted {{
  background-color: #faa;
  color: #000;
  font-weight: bold;
  text-decoration: line-through;
}}
</style></head><body>
<h2>{title}</h2>
<p>修改时间: {timestamp}</p>
{processed_diff_html}
</body></html>'''

    try:
        with open(diff_file, "w", encoding="utf-8") as f:
            f.write(html_wrapper)
        with open(full_file, "w", encoding="utf-8") as f:
            f.write(full_text)
        
        print(f"  → 已保存: {diff_file.relative_to(OUTPUT_DIR)}")
        print(f"  → 已保存: {full_file.relative_to(OUTPUT_DIR)}")
    except Exception as e:
        print(f"  → 保存文件时出错: {e}")

    print(f"  → 完整路径: {diff_file}")
    print(f"  → 完整路径: {full_file}")

def process_single_page(title, since_time, update_timestamp=False):
    """只处理单个页面"""
    print(f"正在单独处理页面：{title}")
    
    # 获取当前最新 revid
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvprop": "ids|timestamp",
        "rvlimit": 1,
        "format": "json"
    }
    try:
        r = SESSION.get(WIKI_API_URL, params=params).json()
        page = next(iter(r["query"]["pages"].values()))
        if "revisions" not in page:
            print("页面不存在或被删除")
            return None
        latest_revid = page["revisions"][0]["revid"]
        latest_ts = page["revisions"][0]["timestamp"]

        # 获取旧 revid
        old_revid = get_old_revid(title, since_time)

        diff_html, full_text, new_ts = get_official_diff_and_content(title, old_revid, latest_revid)
        if diff_html is not None and full_text is not None:
            # 移除旧的note标记，使用更简洁的命名方式
            if not old_revid:
                diff_html = "<p style='color:green;font-weight:bold'>新创建页面（无历史版本）</p>"
            save_files(title, diff_html, full_text, new_ts, "", latest_revid)
        else:
            print(f"  警告: 未能获取完整的差异或内容数据")

        if update_timestamp:
            save_last_timestamp(latest_ts)
            print(f"已更新全局时间戳 → {latest_ts}")
        
        return latest_ts
    except Exception as e:
        print(f"处理页面 '{title}' 时出错: {e}")
        return None

def process_all_pages_since(since_time):
    """处理自指定时间以来的所有页面变更"""
    print("正在获取最近变更列表...")
    changes = get_recent_changes(since_time)
    if not changes:
        print("没有发现任何变更")
        return

    latest_global_ts = since_time
    for title, (latest_revid, ts) in changes.items():
        print(f"\n处理：{title}")
        # 复用单页处理逻辑
        page_latest_ts = process_single_page(title, since_time)
        
        if page_latest_ts and page_latest_ts > latest_global_ts:
            latest_global_ts = page_latest_ts

    save_last_timestamp(latest_global_ts)
    print(f"\n全量同步完成！本次最新时间戳已更新为：{latest_global_ts}")
    print(f"文件保存在：{CURRENT_OUTPUT_DIR.resolve() if CURRENT_OUTPUT_DIR else OUTPUT_DIR.resolve()}")

def main():
    parser = argparse.ArgumentParser(description="MediaWiki 同步工具 - 支持全量/单页/自定义时间")
    parser.add_argument("--since", type=str, help="强制从指定时间开始同步，格式如 2025-11-28T00:00:00Z")
    parser.add_argument("--title", type=str, help="只同步指定的单个页面标题")
    parser.add_argument("--update-timestamp", action="store_true", 
                        help="在单页模式下，完成后仍然更新全局 last_sync_timestamp.txt")
    parser.add_argument("--run", action="store_true",
                        help="执行同步操作（必须提供此参数才能真正执行同步）")
    
    args = parser.parse_args()

    # 如果没有提供 --run 参数，则显示帮助信息并退出
    if not args.run:
        parser.print_help()
        return

    # 确定实际使用的 since 时间
    if args.since:
        since_time = args.since
        print(f"使用命令行指定的时间起点：{since_time}")
    else:
        since_time = load_last_timestamp()
        if not since_time:
            from datetime import timedelta
            since_time = (datetime.utcnow() - timedelta(days=1)).isoformat(timespec='seconds') + "Z"
        print(f"使用上次记录的时间起点：{since_time}")

    # 单页面模式
    if args.title:
        process_single_page(args.title.strip(), since_time, args.update_timestamp)
        return

    # 全量模式 - 使用复用的单页处理逻辑
    process_all_pages_since(since_time)

if __name__ == "__main__":
    main()