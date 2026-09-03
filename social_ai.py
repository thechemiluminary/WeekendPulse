"""
WeekendPulse - Social engagement AI core (the ONLY Gemini usage in the engine).
Generates N self-scored engagement candidates from the pooled talking points,
picks the best above threshold, then fetches a real web image for it via
Gemini Search Grounding in the SAME request (grounding_chunks -> image_url).

Provider chain: GEMINI_KEY_SOCIAL -> GEMINI_API_KEY -> GROQ (text-only).
"""
import json
import os
import re

import config
import social_style
import social_state


def _load_social_prompt():
    with open(os.path.join(config.BASE_DIR, "prompts", "social_post.txt"), "r", encoding="utf-8") as f:
        return f.read().strip()


def _provider_key_and_model():
    """Pick the best available key. Returns (key, model) or (None, None)."""
    if config.GEMINI_KEY_SOCIAL:
        return config.GEMINI_KEY_SOCIAL, config.SOCIAL_EMBED_MODEL
    if config.GEMINI_API_KEY:
        return config.GEMINI_API_KEY, config.SOCIAL_EMBED_MODEL
    if config.GROQ_API_KEY:
        return config.GROQ_API_KEY, config.GROQ_MODEL
    return None, None


def _gemini_generate_candidates(prompt, api_key, model, grounded):
    """Call Gemini with optional Search Grounding; return (raw_text, grounding_chunks)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = model if "/" in model else f"models/{model}"

    config_obj = None
    if grounded:
        config_obj = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )

    resp = client.models.generate_content(model=model, contents=prompt, config=config_obj)
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned empty response")

    chunks = []
    if resp.candidates:
        for cand in resp.candidates:
            gm = (cand.grounding_metadata or None)
            if gm and gm.grounding_chunks:
                for chunk in gm.grounding_chunks:
                    web = (chunk.web or None)
                    img = (chunk.image or None)
                    if web:
                        chunks.append({
                            "url": web.uri or "",
                            "title": web.title or "",
                        })
                    if img is not None and getattr(img, "image_uri", None):
                        chunks.append({"url": getattr(img, "image_uri"), "image": True})
    return text, chunks


def _groq_generate_candidates(prompt):
    """Groq fallback (text-only, no grounding). Returns (raw_text, [])."""
    import requests
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": config.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 2500,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"].get("content", "").strip()
    if not content:
        raise RuntimeError("Groq returned empty content")
    return content, []


def _parse_json(text):
    """Parse a JSON object robustly (handles fences + surrounding prose)."""
    if not text:
        return None
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else None
    except Exception:
        pass
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                block = text[start:i + 1]
                try:
                    return json.loads(block)
                except Exception:
                    return None
    return None


def _build_prompt():
    today = __import__("datetime").datetime.now().strftime("%A %d %B %Y")
    fixtures = ""
    try:
        import fixtures as fm
        fxs = fm.get_today_fixtures()
        for fx in fxs[:12]:
            fixtures += (
                f"- {fx['home']} vs {fx['away']} "
                f"@ {fx.get('utc_kickoff_iso','')[:16].replace('T',' ')} UTC\n"
            )
    except Exception as e:
        print(f"[social_ai] fixtures note: {e}")
    pool = social_state.pool_texts(limit=60)
    pool_block = "\n".join(f"- {t}" for t in pool) or "(nothing collected yet)"

    template = _load_social_prompt()
    return (
        template
        .replace("{TODAY}", today)
        .replace("{FIXTURES}", fixtures or "(no fixtures today)")
        .replace("{POOL}", pool_block)
    )


def generate_candidates(prompts_n=config.SOCIAL_NUM_CANDIDATES):
    """
    Generate and self-score N social candidates.
    Returns (candidates, provider, grounding_candidates) where
    candidates is a list of dicts. Raises on total failure.
    """
    prompt = _build_prompt()
    api_key, model = _provider_key_and_model()
    if not api_key:
        raise RuntimeError("No AI key configured for social engine")

    raw = None
    provider = None
    chunks = []
    if api_key and "groq" not in (model or "").lower() and os.environ.get("_SOCIAL_GROQ_ONLY") != "1":
        try:
            raw, chunks = _gemini_generate_candidates(prompt, api_key, model, config.SOCIAL_GROUNDED)
            provider = "gemini"
        except Exception as e:
            print(f"[social_ai] Gemini failed: {e}")
    if (not raw) and config.GROQ_API_KEY:
        try:
            raw, chunks = _groq_generate_candidates(prompt)
            provider = "groq"
        except Exception as e:
            print(f"[social_ai] Groq failed: {e}")

    if not raw:
        raise RuntimeError("All provider calls failed - cannot generate social post.")

    data = _parse_json(raw)
    candidates = []
    if data and isinstance(data.get("candidates"), list):
        for c in data["candidates"]:
            if not isinstance(c, dict):
                continue
            text = (c.get("post_text") or "").strip()
            if not text:
                continue
            candidates.append({
                "post_text": text,
                "format": (c.get("format") or "").strip(),
                "topic": (c.get("topic") or "").strip(),
                "image_query": (c.get("image_query") or "").strip(),
                "predicted_engagement": int(c.get("predicted_engagement") or 0),
                "reel_worthy": bool(c.get("reel_worthy")),
                "reel_emotion": (c.get("reel_emotion") or "neutral"),
                "reel_blurb": (c.get("reel_blurb") or ""),
            })

    if not candidates:
        # safe fallback: treat raw output as a single text post
        candidates = [{
            "post_text": raw,
            "format": "text",
            "topic": "",
            "image_query": "",
            "predicted_engagement": 0,
            "reel_worthy": False,
            "reel_emotion": "neutral",
            "reel_blurb": "",
        }]

    return candidates, provider, chunks


def select_best(candidates, min_score=40):
    """
    Score each candidate against novelty/repetition guards + format variety and
    return the best. Scans so all candidates are evaluated for guard effects.
    Returns (best_dict_or_None, reasons)
    """
    recent_topics = social_state.recent_topics(25)
    today_formats = [c.get("format", "") for c in candidates]

    reasons = []
    best = None
    best_score = -1
    for c in candidates:
        topic = (c.get("topic") or "").strip().lower()
        base = int(c.get("predicted_engagement") or 0)
        score = base
        why = [f"base={base}"]
        if topic and topic in recent_topics:
            score -= 25
            why.append("-25 repeated topic")
        # format variety: don't pick two with the same format in a row ideally,
        # but we don't know yesterday's here; penalize duplicates within batch
        # lightly (not fatal).
        cnt = sum(1 for f in today_formats if f and f == c.get("format"))
        if cnt > 1:
            score -= 10
            why.append("-10 dup format")
        if topic and len(topic) < 1000:
            reasons.append((c, score, why))
        if score > best_score:
            best_score = score
            best = c

    if best is None or best_score < min_score:
        return None, reasons
    print(f"[social_ai] selected format={best.get('format')} score={best_score}")
    return best, reasons


def _extract_image_urls(chunks):
    """Collect real image URLs from grounding chunks (entries with image=True)."""
    urls = []
    for c in chunks or []:
        if c.get("image") and c.get("url"):
            urls.append(c["url"])
    return urls


def _trusted(url):
    if not url:
        return False
    low = url.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        return False
    return True


def _gemini_image_search(api_key, model, query):
    """Do a grounded image search and return collected image URLs."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = model if "/" in model else f"models/{model}"
    resp = client.models.generate_content(
        model=model,
        contents=(
            f"Search for a real photograph for a football page post. Query: {query}\n"
            "Return the direct image URLs you find (the grounding image results)."
        ),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    urls = []
    if resp.candidates:
        gm = resp.candidates[0].grounding_metadata
        for chunk in (gm.grounding_chunks or []):
            if chunk.image is not None:
                u = getattr(chunk.image, "image_uri", None)
                if u:
                    urls.append(u)
    return urls


def find_image_url(generation_chunks, image_query=""):
    """
    Return a trusted image URL for the chosen candidate.
    Preference: a live grounded image URL captured during generation, else a
    fresh grounding image search for the candidate. Returns None if unavailable.
    """
    api_key, model = _provider_key_and_model()
    if not api_key or "groq" in (model or "").lower():
        return None

    # 1) prefer already-grounded image URLs from the generation call
    for u in _extract_image_urls(generation_chunks):
        if _trusted(u):
            return u

    # 2) fresh grounded image search
    if image_query:
        try:
            urls = _gemini_image_search(api_key, model, image_query)
            for u in urls:
                if _trusted(u):
                    return u
        except Exception as e:
            print(f"[social_ai] grounding image search failed: {e}")
    return None


def apply_style(post_text):
    """Apply Unicode bold styling to *emphasized* runs in the final post."""
    return social_style.apply_markup(post_text, "bold_sans")
