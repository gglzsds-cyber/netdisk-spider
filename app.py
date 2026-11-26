# -*- coding: utf-8 -*-
"""
网盘资源搜索 Web 后端
启动：python app.py [--port 8765]
仅监听 127.0.0.1，数据库只读，不会修改同步脚本写入的数据。
"""
import argparse
import re
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "search_engine.db"

app = Flask(__name__)


@app.after_request
def allow_local_preview(resp):
    """允许本地静态预览（file:// 或 127.0.0.1:10999）调用本机 API。"""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

PAN_LABELS = {"baidu": "百度网盘", "quark": "夸克网盘"}
TYPE_LABELS = {
    "movie": "影视", "music": "音乐", "ebook": "电子书",
    "software": "软件", "learning": "教程", "exam": "考证", "other": "其他",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def clean_query(raw):
    """去掉 FTS 查询语法里有特殊含义的字符，防止语法错误；限制长度防滥用。"""
    q = (raw or "").strip()
    q = q.replace('"', " ").replace("*", " ").replace("\\", " ")
    q = re.sub(r"\s+", " ", q).strip()
    return q[:80]


def clean_title(raw):
    """标题来自 Telegram 正文，含换行和控制字符，压成单行展示。"""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:180]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/stats")
def stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM resources WHERE valid=1").fetchone()[0]
    by_pan = dict(conn.execute(
        "SELECT pan_type, COUNT(*) FROM resources WHERE valid=1 GROUP BY pan_type"
    ).fetchall())
    by_type = dict(conn.execute(
        "SELECT resource_type, COUNT(*) FROM resources WHERE valid=1 GROUP BY resource_type"
    ).fetchall())
    latest = conn.execute("SELECT MAX(created_at) FROM resources").fetchone()[0]
    conn.close()
    return jsonify({
        "total": total,
        "by_pan": {PAN_LABELS.get(k, k): v for k, v in by_pan.items()},
        "by_type": {TYPE_LABELS.get(k, k): v for k, v in by_type.items()},
        "latest": latest,
    })


@app.get("/api/search")
def search():
    q = clean_query(request.args.get("q", ""))
    pan = request.args.get("pan", "")
    rtype = request.args.get("type", "")
    sort = request.args.get("sort", "")

    try:
        page = int(request.args.get("page", 1) or 1)
        size = int(request.args.get("size", 20) or 20)
    except ValueError:
        return jsonify({"error": "page/size 参数必须是整数"}), 400
    page = max(1, min(page, 100000))
    size = max(5, min(size, 100))

    where = ["r.valid = 1"]
    params = []
    join = ""
    order = "r.id DESC"

    if q:
        if len(q) >= 3:
            join = "JOIN resources_fts ON resources_fts.rowid = r.id"
            where.append("resources_fts MATCH ?")
            params.append('"' + q + '"')  # 短语匹配，避免 trigram 把多词拆开
            if sort != "latest":
                order = "bm25(resources_fts) ASC, r.id DESC"
        else:
            # trigram 至少需要 3 个字符，短词退回 LIKE
            where.append("(r.title LIKE ? OR r.source LIKE ?)")
            params.extend(["%" + q + "%", "%" + q + "%"])

    if pan in PAN_LABELS:
        where.append("r.pan_type = ?")
        params.append(pan)
    if rtype in TYPE_LABELS:
        where.append("r.resource_type = ?")
        params.append(rtype)

    sql_where = " AND ".join(where)
    conn = get_db()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM resources r {join} WHERE {sql_where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT r.id, r.title, r.share_url, r.share_password, r.pan_type, "
            f"r.resource_type, r.source, r.created_at "
            f"FROM resources r {join} WHERE {sql_where} "
            f"ORDER BY {order} LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size],
        ).fetchall()
    except sqlite3.Error as exc:
        return jsonify({"error": f"数据库查询失败: {exc}"}), 500
    finally:
        conn.close()

    items = [{
        "id": r["id"],
        "title": clean_title(r["title"]),
        "url": r["share_url"],
        "password": r["share_password"],
        "pan": r["pan_type"],
        "pan_label": PAN_LABELS.get(r["pan_type"], r["pan_type"]),
        "type": r["resource_type"],
        "type_label": TYPE_LABELS.get(r["resource_type"], r["resource_type"]),
        "source": r["source"],
        "created_at": r["created_at"],
    } for r in rows]

    return jsonify({
        "query": q,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
        "items": items,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="网盘资源搜索服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    parser.add_argument("--port", type=int, default=8765, help="端口，默认 8765")
    args = parser.parse_args()
    print(f"[搜索服务] http://{args.host}:{args.port}/  (Ctrl+C 停止)")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
