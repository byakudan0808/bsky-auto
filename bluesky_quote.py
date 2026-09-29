"""
Bluesky: アカウントAの新規投稿を、アカウントBが引用投稿する。
初回実行は既存投稿を既読にするだけ。2回目以降、新しく増えたAの投稿だけを引用する。
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atproto import Client, models

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
A_HANDLE = os.environ["BSKY_A_HANDLE"]
B_HANDLE = os.environ["BSKY_B_HANDLE"]
B_PASSWORD = os.environ["BSKY_B_PASSWORD"]

JST = timezone(timedelta(hours=9))

# {date} にはAの投稿日(JST)が YYYY.MM.DD 形式で入る
QUOTE_TEMPLATE = (
    "Mistress Blog 限定記事が公開されました📚\n"
    "チェック必須です▼▼▼\n"
    "{date}"
)


def build_text(post):
    created = datetime.fromisoformat(post.record.created_at.replace("Z", "+00:00"))
    return QUOTE_TEMPLATE.format(date=created.astimezone(JST).strftime("%Y.%m.%d"))


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return None


def save_state(seen):
    # 直近300件だけ保持
    STATE_FILE.write_text(json.dumps({"seen": seen[-300:]}, ensure_ascii=False))


def main():
    client = Client()
    client.login(B_HANDLE, B_PASSWORD)

    # Aの投稿を取得 (返信を除く)。リポストは reason 付きなので除外
    res = client.app.bsky.feed.get_author_feed(
        params={"actor": A_HANDLE, "filter": "posts_no_replies", "limit": 30}
    )
    posts = [
        item.post
        for item in res.feed
        if item.reason is None and item.post.author.handle == A_HANDLE
    ]
    posts.sort(key=lambda p: p.indexed_at)  # 古い順

    state = load_state()
    if state is None:
        # 初回: 既存投稿を既読化のみ
        save_state([p.uri for p in posts])
        print(f"初期化完了: {len(posts)}件を既読にした")
        return

    seen = state["seen"]
    new_posts = [p for p in posts if p.uri not in seen]

    for p in new_posts:
        try:
            embed = models.AppBskyEmbedRecord.Main(
                record=models.ComAtprotoRepoStrongRef.Main(uri=p.uri, cid=p.cid)
            )
            client.send_post(text=build_text(p), embed=embed)
            print(f"引用した: {p.uri}")
        except Exception as e:
            print(f"失敗 {p.uri}: {e}")
            continue  # 失敗分は既読にせず次回リトライ
        seen.append(p.uri)

    save_state(seen)


if __name__ == "__main__":
    main()
