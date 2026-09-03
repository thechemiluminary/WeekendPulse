"""
WeekendPulse - Orchestrator.
Flow: init db -> scrape feeds -> publish up to MAX_POSTS_PER_RUN freshly-scraped
      articles -> AI post -> publish to Facebook (real article photo, else text)
      -> mark posted -> append to manifest.
Only articles scraped during THIS run are eligible; old backlog is never reused.

Separate entry point: `python main.py --match-preview` runs the midnight
match-preview job - fetch today's PL fixtures and schedule a comment-bait post
5 hours before each kickoff (published=false + scheduled_publish_time).
"""
import json
import sys
import datetime
import time

import config
from db import init_db, get_conn, mark_posted as _mark_posted
from ai_processor import turn_article_into_post_json, turn_fixture_into_post
from publisher import post_text, post_text_with_image_url, schedule_post
import manifest
from manifest import append_post_entry, posted_titles
import fixtures as fixtures_mod


def _publish_one(article, conn, include_image=True):
    """Generate AI post + publish one article. Returns a result dict."""
    title = article["title"]
    summary = article["summary"] or ""
    image_url = article.get("image_url")
    print(f"[main]   article: {title[:80]}")

    if config.DRY_RUN:
        print("[main]   DRY_RUN - skipping AI + publish")
        return {"status": "dry_run", "article": title}

    post_result = turn_article_into_post_json(title, summary)
    post = post_result["post_text"]
    provider = post_result["provider"]
    reel_meta = {
        "reel_worthy": post_result["reel_worthy"],
        "reel_emotion": post_result["reel_emotion"],
        "reel_blurb": post_result["reel_blurb"],
    }
    print(f"[main]   AI ({provider}): {post[:80]}...")

    if include_image and image_url:
        ok, result = post_text_with_image_url(post, image_url)
        attach = "image"
    else:
        ok, result = post_text(post)
        attach = "text"

    if ok:
        _mark_posted(conn, article["id"], result)
        log_path = append_post_entry(result, article, reel_meta=reel_meta)
        print(f"[main]   POSTED ({attach}): {result}")
        return {
            "status": "posted",
            "provider": provider,
            "attach": attach,
            "post_id": result,
            "title": title,
        }
    else:
        print(f"[main]   PUBLISH FAILED: {result}")
        return {"status": "error", "error": result}


def run(include_image=True):
    from scraper import scrape_all, select_postable

    print(f"[main] === run start {datetime.datetime.utcnow().isoformat()}Z ===")
    print(f"[main] config: MAX_POSTS_PER_RUN={config.MAX_POSTS_PER_RUN}, "
          f"DRY_RUN={config.DRY_RUN}, DEDUP_THRESHOLD={config.DEDUP_THRESHOLD}")

    init_db()
    conn = get_conn()

    # 1. Scrape new articles.
    try:
        new, fresh = scrape_all(conn)
    except Exception as e:
        print(f"[main] SCRAPE ERROR: {e}")
        return {"status": "scrape_error", "error": str(e)}
    print(f"[main] scrape complete: {new} new articles, {len(fresh)} fresh rows returned")

    if not fresh:
        print("[main] NO FRESH ARTICLES - nothing to do.")
        return {"status": "no_content"}

    # 2. Post up to MAX_POSTS_PER_RUN articles from the fresh batch.
    titles_done = []
    results = []
    remaining = list(fresh)

    for i in range(config.MAX_POSTS_PER_RUN):
        if not remaining:
            break

        article = select_postable(conn, remaining, posted_titles())
        if article is None:
            print(f"[main] no more postable articles after {i} posts")
            break

        print(f"[main] posting {i+1}/{config.MAX_POSTS_PER_RUN}: {article['title'][:80]}")
        res = _publish_one(article, conn, include_image=include_image)
        results.append(res)

        if res["status"] == "posted":
            titles_done.append(article["title"])
            # Remove the posted article from remaining so next iteration skips it
            remaining = [r for r in remaining if r.get("url") != article.get("url")]
        elif res["status"] == "error":
            # Don't retry on publish failure
            break
        else:
            break

    posted_count = sum(1 for r in results if r["status"] == "posted")
    print(f"[main] === run end: {posted_count} posts made ===")
    return {"status": "done", "posted": posted_count, "results": results}


def run_match_preview():
    """
    Midnight match-preview job: fetch today's PL fixtures and schedule a
    comment-bait post 5h before each kickoff. Dedupes per fixture so each
    match is scheduled exactly once. Fully independent of the news bot - a
    fixture failure never blocks anything else.
    """
    import match_card

    init_db()
    if not config.FOOTBALL_API_TOKEN:
        return {"status": "no_token"}
    if config.DRY_RUN:
        print("[match] DRY_RUN - running fixture fetch + dedup only")
        fxs = fixtures_mod.get_today_fixtures()
        return {"status": "dry_run", "fixtures": len(fxs)}

    fxs = fixtures_mod.get_today_fixtures()
    if not fxs:
        return {"status": "no_fixtures_today"}

    hours_before = config.MATCH_POST_HOURS_BEFORE
    now = datetime.datetime.now(datetime.timezone.utc)
    scheduled, skipped = [], []
    for fx in fxs:
        try:
            mk = fixtures_mod.match_key(fx)
        except Exception:
            mk = ""
        fx["match_key"] = mk

        if manifest.already_posted_fixture(mk):
            skipped.append({"fixture": mk, "reason": "already_posted"})
            continue

        kickoff = fx.get("utc_kickoff")
        if not kickoff:
            skipped.append({"fixture": mk, "reason": "no_kickoff"})
            continue
        # Only schedule matches whose kickoff is MORE than `hours_before` away.
        if kickoff - now < datetime.timedelta(hours=hours_before):
            skipped.append({"fixture": mk, "reason": "too_soon_or_started"})
            continue

        try:
            scheduled_unix = int(kickoff.timestamp()) - hours_before * 3600
            label = kickoff.strftime("%H:%M UK")
            img = match_card.make_match_card(fx, label, out_name=f"match_{mk.replace('/','_')}.png")
            res = turn_fixture_into_post(
                fx.get("home"), fx.get("away"), fx.get("venue"),
                fx.get("matchday"), label,
            )
            post_text_value = res["post_text"]
            ok, post_id = schedule_post(post_text_value, img, scheduled_unix)
            if ok:
                manifest.append_match_entry(fx, post_id, scheduled_unix)
                scheduled.append({"fixture": mk, "post_id": post_id,
                                  "at": datetime.datetime.fromtimestamp(
                                      scheduled_unix, datetime.timezone.utc).isoformat()})
            else:
                skipped.append({"fixture": mk, "reason": f"publish_failed:{post_id}"})
        except Exception as e:
            import traceback
            traceback.print_exc()
            skipped.append({"fixture": mk, "reason": str(e)})

        if len(scheduled) >= config.MATCH_POST_MAX_PER_DAY:
            break

    return {"status": "done", "scheduled": scheduled, "skipped": skipped}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--match-preview":
        result = run_match_preview()
        print(json.dumps(result, default=str))
        sys.exit(0)

    if not config.FB_PAGE_TOKEN:
        print("WARNING: FB_PAGE_TOKEN empty - set env var. Use DRY_RUN=1 to test scrape+AI only.")
    result = run(include_image=True)
    print(json.dumps(result, default=str))