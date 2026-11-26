# -*- coding: utf-8 -*-
"""GitHub 公开书单采集器：从 Markdown 清单中提取百度/夸克链接。
输出 data/batch_github_YYYYMMDD_HHMM.json，格式与云端爬虫一致。
可本地运行（GitHub raw 可直连），也可放 Actions 跑。
"""
import re
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
OUT_DIR = PROJECT / "data"

# 已验证的公开书单仓库（纯 Markdown，含百度/夸克直链）
REPOS = [
    "mtcsol/awesome-k12-books",  # 304 条中小学教材/练习册（夸克）
    "yeayee/yeayee",             # 234 条金融/精品电子书（夸克）
    "mzhren/ebooks",             # 33 条专题电子书（夸克）
    "szu-sg/book",               # 34 条书籍资料（夸克+百度）
]

PAN_RE = re.compile(r"https?://pan\.(?:quark\.cn|baidu\.com)/[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.I)
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.I)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
UA = {"User-Agent": "workbuddy-netdisk-collector/1.0"}

# 与云端爬虫一致的分类关键词
TYPE_KWS = {
    "exam": ["二建", "一建", "建造师", "监理", "造价", "消防", "考研", "考试", "备考",
             "教师资格", "资格证", "真题", "押题", "公考", "公务员", "事业编", "会计师"],
    "ebook": ["电子书", "pdf", "epub", "书籍", "图书", "教材", "小说", "名著", "文学"],
    "learning": ["教程", "课程", "学习", "入门", "网课", "小学", "初中", "高中",
                 "一年级", "二年级", "三年级", "四年级", "五年级", "六年级", "七年级", "八年级",
                 "九年级", "数学", "语文", "英语", "物理", "化学", "编程", "python"],
    "software": ["软件", "工具", "破解", "激活", "app"],
    "movie": ["电影", "剧集", "4k", "1080p"],
    "music": ["音乐", "专辑", "mp3", "flac"],
}


def classify(title):
    t = (title or "").lower()
    for typ, kws in TYPE_KWS.items():
        for kw in kws:
            if kw.lower() in t:
                return typ
    return "ebook"  # 书单仓库默认电子书


def clean_title(s):
    s = re.sub(r"^\s*[-*+]\s*", "", s or "")
    s = re.sub(r"\s+", " ", s).strip(" ：:|")
    # 去掉"链接:""提取码: xxxx"这类无信息量残留
    s = re.sub(r"^(链接|提取码|密码|pwd)\s*[:：]?\s*", "", s)
    s = re.sub(r"(链接|提取码|密码|pwd)\s*[:：]\s*[a-zA-Z0-9]*", "", s)
    return s.strip(" ：:|，,。.")[:100]


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def parse_markdown(text, repo):
    """逐行解析：标题与链接同行，或链接单独成行时回溯上一行。"""
    out = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        links = [m.group(0) for m in PAN_RE.finditer(line)]
        if not links:
            continue
        # 去掉链接后剩余文字作为标题
        title_part = PAN_RE.sub(" ", line)
        # Markdown 链接 [标题](url) -> 取方括号里的文字
        md_titles = MD_LINK_RE.findall(title_part)
        if md_titles:
            title = " ".join(t for t, _ in md_titles)
            title_part = MD_LINK_RE.sub(" ", title_part)
        else:
            title = title_part
        title = clean_title(title)
        # 标题太短：回溯前一行非空文字（很多书单是"标题\n链接"两行式）
        if len(title) < 4:
            back = idx - 1
            while back >= 0 and len(title) < 4:
                prev = lines[back].strip()
                if prev and not prev.startswith(("http", "![", "#", "-", "*")) and "pan." not in prev:
                    title = clean_title(prev)
                back -= 1
                if idx - back > 3:
                    break
        if len(title) < 4:
            continue
        for url in links:
            url = url.rstrip(").,，。")
            ptype = "quark" if "quark.cn" in url else "baidu"
            pwd = ""
            if ptype == "baidu" and "?pwd=" in url:
                m = re.search(r"[?&]pwd=([a-zA-Z0-9]+)", url)
                if m:
                    pwd = m.group(1)
                    url = re.sub(r"[?&]pwd=[a-zA-Z0-9]+", "", url)
            out.append({
                "title": title,
                "share_url": url,
                "share_password": pwd,
                "pan_type": ptype,
                "resource_type": classify(title),
                "source": f"github:{repo}",
                "msg_time": "",
            })
    return out


def main():
    now = datetime.now(timezone.utc)
    all_items = []
    for repo in REPOS:
        try:
            tree = json.loads(fetch(f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1"))
        except Exception as e:
            print(f"[跳过] {repo} tree: {type(e).__name__} {e}")
            continue
        mds = [x["path"] for x in tree.get("tree", [])
               if x.get("type") == "blob" and x["path"].lower().endswith(".md")]
        added = 0
        for path in mds:
            try:
                text = fetch(f"https://raw.githubusercontent.com/{repo}/HEAD/{path}")
            except Exception as e:
                print(f"[跳过] {repo}/{path}: {type(e).__name__}")
                continue
            items = parse_markdown(text, repo)
            all_items.extend(items)
            added += len(items)
        print(f"[{repo}] {len(mds)} 个 md, {added} 条链接")

    # 按 URL 去重
    seen = set()
    unique = []
    for i in all_items:
        if i["share_url"] in seen:
            continue
        seen.add(i["share_url"])
        unique.append(i)

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"batch_github_{now.strftime('%Y%m%d_%H%M')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"results": unique}, f, ensure_ascii=False, indent=1)
    print(f"[完成] {len(unique)} 条 -> {out}")


if __name__ == "__main__":
    main()
