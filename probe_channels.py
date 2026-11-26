# -*- coding: utf-8 -*-
"""候选频道探测：统计每个频道最近消息的网盘链接数与内容主题。
在 GitHub Actions 上运行（可直连 t.me）。输出 PROBE_RESULT JSON 行。
"""
import re
import json
import html as html_module
from collections import Counter

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

CANDIDATES = [
    # 云盘资源
    "aliyundriveShare", "bdwpzhpd", "zaihuayun", "studydayday", "quanziyuanshe",
    "aliyunshares", "qianxingba1",
    # 中文书籍
    "Readfine", "tianyast", "sharebooks4you", "libraryforalls", "ziyuanfeng59",
    "TGeBook", "PDFtushuguan", "rsstianya", "bookusefor3", "MothLib",
    "BooksThatMakeYouThink", "pdf_001", "daxiabook", "bookusefor4",
    # 英文书籍
    "amazonebook", "eBookRoom", "Books", "golden_bookstore", "dummiesbook",
    "compbook", "MedicalBooksStore55", "AllBooksStore",
    # 报刊杂志
    "itsallinenglish", "readingclubus", "Qikan2023", "magazinesclub",
    # 之前 0 产出的复核
    "gotopan", "xuendj1", "aboutstudychannel",
    # 补充候选
    "shumozy", "jxwpzy",
]

PAN_HOSTS = {"pan.baidu.com", "pan.quark.cn", "drive.quark.cn"}
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.I)


def pan_of(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in PAN_HOSTS)


from urllib.parse import urlparse


def clean(s):
    s = html_module.unescape(s or "")
    s = re.sub(r"[\U0001F300-\U0001F9FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def probe(channel):
    url = "https://t.me/s/" + channel
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    except Exception as e:
        return {"channel": channel, "error": type(e).__name__}
    if r.status_code != 200 or "tgme_widget_message" not in r.text:
        return {"channel": channel, "error": "HTTP %s / no messages" % r.status_code}
    soup = BeautifulSoup(r.text, "html.parser")
    wraps = soup.find_all("div", class_="tgme_widget_message_wrap")
    baidu = quark = 0
    titles = []
    dates = []
    for w in wraps:
        text_el = w.find("div", class_="tgme_widget_message_text")
        raw = text_el.get_text("\n").strip() if text_el else ""
        for m in URL_RE.finditer(raw):
            if pan_of(m.group(0)):
                if "baidu" in m.group(0):
                    baidu += 1
                else:
                    quark += 1
        t = w.find("time")
        if t and t.get("datetime"):
            dates.append(t["datetime"])
        title = clean(raw.split("\n")[0])[:60] if raw else ""
        if title:
            titles.append(title)
    return {
        "channel": channel,
        "messages": len(wraps),
        "baidu": baidu,
        "quark": quark,
        "total_links": baidu + quark,
        "latest": dates[-1] if dates else "",
        "samples": titles[:3],
    }


if __name__ == "__main__":
    for ch in CANDIDATES:
        try:
            d = probe(ch)
        except Exception as e:
            d = {"channel": ch, "error": "EXC " + type(e).__name__}
        print("PROBE_RESULT " + json.dumps(d, ensure_ascii=False))
