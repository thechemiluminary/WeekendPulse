"""
WeekendPulse - Orchestrator.
Flow: init db -> scrape feeds -> publish ONE freshly-scraped (FUTURE) article only
      -> AI post -> publish to Facebook (real article photo, else text)
      -> mark posted -> append to posts_log.csv.
Only articles scraped during THIS run are eligible; old backlog is never reused.
"""
import json

import config
from db import init_db, get_conn, mark_posted as _mark_posted
from scraper import scrape_all, select_postable
from ai_processor import turn_article_into_post
from publisher import post_text, post_text_with_image_url
from post_log import append_post, posted_titles


def run(include_image=True):
    init_db()
    conn = get_conn()

    # 1. Scrape new articles. Only freshly-scraped rows are returned -
    #    the bot NEVER touches older backlog (future-only rule).
    try:
        new, fresh = scrape_all(conn)
    except Exception as e:
        print(f"[main] scrape error: {e}")
        return {"status": "scrape_error", "error": str(e)}
    print(f"[main] scraped, new articles: {new}")

    if not fresh:
        print("[main] no freshly-scraped articles - nothing to do.")
        return {"status": "no_content"}

    # 2. Pick the first fresh article that is NOT a duplicate of an already-posted
    #    story (or of another magazine in this same batch). Everything duplicating
    #    an earlier post is skipped; if all are dups, post nothing.
    article = select_postable(conn, fresh, posted_titles())
    if article is None:
        print("[main] all fresh articles duplicate already-posted stories - nothing to do.")
        return {"status": "no_content"}

    title = article["title"]
    summary = article["summary"] or ""
    image_url = article["image_url"] if article.keys() and "image_url" in article.keys() else None
    print(f"[main] picked fresh article: {title}")

    # 3. AI generate the post.
    if config.DRY_RUN:
        print("[main] DRY_RUN - skipping AI + publish")
        return {"status": "dry_run", "article": title}

    post, provider = turn_article_into_post(title, summary)
    print(f"[main] AI generated ({provider})")

    # 4. Publish with the article's REAL image when available, else text-only.
    if include_image and image_url:
        ok, result = post_text_with_image_url(post, image_url)
        attach = "image"
    else:
        ok, result = post_text(post)
        attach = "text"

    if ok:
        _mark_posted(conn, article["id"], result)
        log_path = append_post(result, article, image_used=(attach == "image"))
        print(f"[main] posted OK ({attach}): {result}")
        print(f"[main] logged to {log_path}")
        return {
            "status": "posted",
            "provider": provider,
            "attach": attach,
            "post_id": result,
            "log_path": log_path,
        }
    else:
        print(f"[main] publish FAILED: {result}")
        return {"status": "error", "error": result}


if __name__ == "__main__":
    ok = bool(config.FB_PAGE_TOKEN)
    if not ok:
        print("WARNING: FB_PAGE_TOKEN empty - set env var. Use DRY_RUN=1 to test scrape+AI only.")
    result = run(include_image=True)
    print(json.dumps(result, default=str))