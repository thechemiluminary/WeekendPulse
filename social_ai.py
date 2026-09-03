"""
WeekendPulse - Social engagement AI core.
Generates N self-scored engagement candidates from the pooled talking points
and picks the best above threshold.

Provider chain: OPENROUTER -> GROQ (multi-key rotation) -> CEREBRAS -> NIM
(all OpenAI-compatible, text-only). Groq uses multi-API-key rotation
(GROQ_API_KEY, _2, _3) so a rate-limited/dead key fails over to the next. No
Google Search Grounding, so no real web image URLs - social posts are text-only.
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
    if config.OPENROUTER_API_KEY:
        return config.OPENROUTER_API_KEY, config.OPENROUTER_MODEL
    if config.GROQ_API_KEY:
        return config.GROQ_API_KEY, config.GROQ_MODEL
    if config.CEREBRAS_API_KEY:
        return config.CEREBRAS_API_KEY, config.CEREBRAS_MODEL
    if config.NIM_API_KEY:
        return config.NIM_API_KEY, config.NIM_MODEL
    return None, None


def _groq_keys():
    """Return all non-empty Groq keys in priority order for rotation."""
    keys = []
    for name in ("GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3"):
        v = getattr(config, name, "") or ""
        if v:
            keys.append(v)
    return keys


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


def _groq_generate_candidates(prompt, api_key):
    """Groq fallback (text-only, no grounding) via a specific key.
    Returns (raw_text, [])."""
    import requests
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
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


def _openrouter_generate_candidates(prompt):
    """Primary social provider via OpenRouter (OpenAI-compatible, text-only).
    Returns (raw_text, []) - no grounding, so no image URLs here."""
    import requests
    url = f"{config.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 2500,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    body = r.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter returned no choices")
    content = (choices[0].get("message") or {}).get("content", "").strip()
    if not content:
        raise RuntimeError("OpenRouter returned empty content")
    return content, []


def _openai_compat_generate_candidates(prompt, api_key, base_url, model, label):
    """Generic OpenAI-compatible caller for Cerebras + NVIDIA NIM.
    Returns (raw_text, []) - text-only."""
    import requests
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 2500,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    body = r.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"{label} returned no choices")
    content = (choices[0].get("message") or {}).get("content", "").strip()
    if not content:
        raise RuntimeError(f"{label} returned empty content")
    return content, []


def _cerebras_generate_candidates(prompt):
    return _openai_compat_generate_candidates(
        prompt, config.CEREBRAS_API_KEY, config.CEREBRAS_BASE_URL,
        config.CEREBRAS_MODEL, "Cerebras")


def _nim_generate_candidates(prompt):
    return _openai_compat_generate_candidates(
        prompt, config.NIM_API_KEY, config.NIM_BASE_URL,
        config.NIM_MODEL, "NIM")


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
    if config.OPENROUTER_API_KEY and os.environ.get("_SOCIAL_GROQ_ONLY") != "1":
        try:
            raw, chunks = _openrouter_generate_candidates(prompt)
            provider = "openrouter"
        except Exception as e:
            print(f"[social_ai] OpenRouter failed: {e}")
    if not raw:
        # Groq multi-key rotation: try each key until one succeeds.
        for key in _groq_keys():
            try:
                raw, chunks = _groq_generate_candidates(prompt, key)
                provider = "groq"
                break
            except Exception as e:
                print(f"[social_ai] Groq failed (key): {e}")
    if not raw and config.CEREBRAS_API_KEY:
        try:
            raw, chunks = _cerebras_generate_candidates(prompt)
            provider = "cerebras"
        except Exception as e:
            print(f"[social_ai] Cerebras failed: {e}")
    if not raw and config.NIM_API_KEY:
        try:
            raw, chunks = _nim_generate_candidates(prompt)
            provider = "nim"
        except Exception as e:
            print(f"[social_ai] NIM failed: {e}")

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
    NOTE: OpenRouter and Groq providers are both text-only (no Google Search
    Grounding), so no real web image URLs are available. Returns None always,
    meaning social posts go out text-only via this path.
    """
    return None


def apply_style(post_text):
    """Apply Unicode bold styling to *emphasized* runs in the final post."""
    return social_style.apply_markup(post_text, "bold_sans")
