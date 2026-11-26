# -*- coding: utf-8 -*-
r"""
初始化本地 SQLite 数据库（原仓库缺少建库脚本，同步脚本依赖此表结构）

用法：
    .venv\Scripts\python.exe init_db.py

只会建表，不会清空已有数据：已有数据库重复运行是安全的。
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "search_engine.db"


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT NOT NULL DEFAULT '',
            share_url     TEXT NOT NULL UNIQUE,
            share_password TEXT NOT NULL DEFAULT '',
            pan_type      TEXT NOT NULL DEFAULT '',
            resource_type TEXT NOT NULL DEFAULT 'other',
            source        TEXT NOT NULL DEFAULT '',
            valid         INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_resources_pan_type ON resources(pan_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(resource_type)")

    # trigram 分词：中文按字/子串匹配效果好于默认的 unicode61
    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts
        USING fts5(title, resource_type, source, tokenize='trigram')
    """)

    # 直接向 resources 写入数据时自动同步索引
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS resources_ai AFTER INSERT ON resources BEGIN
            INSERT INTO resources_fts(rowid, title, resource_type, source)
            VALUES (new.id, new.title, new.resource_type, new.source);
        END
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS resources_ad AFTER DELETE ON resources BEGIN
            DELETE FROM resources_fts WHERE rowid = old.id;
        END
    """)
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS resources_au AFTER UPDATE ON resources BEGIN
            DELETE FROM resources_fts WHERE rowid = old.id;
            INSERT INTO resources_fts(rowid, title, resource_type, source)
            VALUES (new.id, new.title, new.resource_type, new.source);
        END
    """)

    conn.commit()
    n = c.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
    print(f"[OK] 数据库已就绪: {DB_PATH}（现有 {n} 条资源）")
    conn.close()


if __name__ == "__main__":
    main()
