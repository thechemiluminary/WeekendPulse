"""
WeekendPulse - AI post processor.
Uses Google Gemini (new google.genai SDK) as primary,
falls back to Groq on failure/rate-limit.
Reads the fixed prompt template from prompts/debate_post.txt.
"""
import json

from config import (
    GEMINI_API_KEY, GROQ_API_KEY, GROQ_MODEL, GEMINI_MODEL, PROMPT_PATH, MATCH_PROMPT_PATH,
)


def _load_prompt_template():
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read().strip()


def _load_match_prompt_template():
    with open(MATCH_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read().strip()


def _generate_with_gemini(prompt):
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    # GEMINI_MODEL default is "models/gemini-2.5-flash"
    model = GEMINI_MODEL if "/" in GEMINI_MODEL else f"models/{GEMINI_MODEL}"
    resp = client.models.generate_content(model=model, contents=prompt)
    text = resp.text
    if not text:
        raise RuntimeError("Gemini returned empty response")
    return text.strip()


def _generate_with_groq(prompt):
    import requests

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        # generous budget: reasoning-capable GPT-OSS models spend tokens on
        # internal reasoning before the real answer; too low and the JSON gets
        # truncated mid-output (which previously caused raw JSON to be posted).
        "max_tokens": 2500,
        # JSON mode: guarantees a well-formed JSON object, sharply reducing
        # parse failures and truncated/corrupt output on the live page.
        "response_format": {"type": "json_object"},
    }
    r = requests.post(url, json=payload, headers=headers, timeout=90)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"].get("content", "").strip()
    if not content:
        raise RuntimeError("Groq returned empty content")
    return content


def _prompt_for(title, summary):
    template = _load_prompt_template()
    return template.replace("{title}", title).replace("{summary}", summary or "")


def _parse_json_result(text):
    """
    Strictly parse a JSON object out of the model text.
    Handles ```json fences, leading/trailing prose, and stray text by finding the
    first balanced {..} block. Returns the parsed dict, or None on failure.
    """
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    # find a balanced {...} block (robust to fences + surrounding prose)
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


def _generate_once(prompt):
    """Try Gemini then Groq for the RAW model output. Returns (raw, provider) or (None, None)."""
    if GEMINI_API_KEY:
        try:
            raw = _generate_with_gemini(prompt)
            if raw:
                return raw, "gemini"
        except Exception as e:
            print(f"[ai] Gemini failed: {e}")
    if GROQ_API_KEY:
        try:
            raw = _generate_with_groq(prompt)
            if raw:
                return raw, "groq"
        except Exception as e:
            print(f"[ai] Groq failed: {e}")
    return None, None


def _looks_like_json(text):
    """True if text still looks like a raw JSON object (never post this as a caption)."""
    t = (text or "").strip()
    if not t:
        return False
    if t.startswith("{") or (t.startswith("\"") and "\"post_text\"" in t):
        return True
    head = t[:60].lower()
    return "\"post_text\"" in t or ("\"reel_worthy\"" in t)


def turn_article_into_post_json(title, summary):
    """
    Generate a Facebook post AND a reel verdict from an article.
    Returns a dict: {post_text, reel_worthy, reel_emotion, reel_blurb, provider}.
    Robustness: if JSON parsing fails or post_text is missing, the request is
    RETRIED up to _MAX_ATTEMPTS times (fresh generation each time). If still
    invalid, the article is SKIPPED (raises RuntimeError) rather than posting
    raw/truncated model output - the page never publishes garbage JSON.
    """
    prompt = _prompt_for(title, summary)

    _MAX_ATTEMPTS = 3

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        raw, provider = _generate_once(prompt)
        if not raw:
            raise RuntimeError("Both Gemini and Groq failed - cannot generate post.")

        data = _parse_json_result(raw)
        post_text = ""
        if data is not None:
            post_text = (data.get("post_text") or "").strip()

        text_fine = bool(post_text) and not _looks_like_json(post_text)

        if data is not None and text_fine:
            worthy = bool(data.get("reel_worthy"))
            emotion = str(data.get("reel_emotion") or "").lower()
            if emotion not in ("neutral", "excited", "surprised"):
                emotion = "neutral"
            blurb = (data.get("reel_blurb") or "").strip()
            if not worthy:
                blurb = ""
                emotion = "neutral"
            return {
                "post_text": post_text,
                "reel_worthy": worthy,
                "reel_emotion": emotion,
                "reel_blurb": blurb,
                "provider": provider,
            }

        reason = "could not parse JSON" if data is None else (
            "no usable post_text" if not post_text else "post_text looks like raw JSON")
        print(f"[ai] attempt {attempt}/{_MAX_ATTEMPTS}: {reason} - regenerating")

    # All retries failed -> SKIP this article (never post raw/truncated output).
    raise RuntimeError(
        f"After {_MAX_ATTEMPTS} attempts the AI produced no valid post text - "
        "skipping article to avoid posting malformed JSON.")


def turn_article_into_post(title, summary):
    """
    Legacy text-only path (used as a hard safe fallback).
    Returns (post_text, provider_used).
    """
    result = turn_article_into_post_json(title, summary)
    return result["post_text"], result["provider"]


def turn_fixture_into_post(home, away, venue, matchday, kickoff_local):
    """
    Generate a comment-bait match-preview post for a fixture.
    Returns a dict {post_text, provider}. Falls back to a plain template-driven
    line if both AI providers fail, so the scheduler NEVER crashes.
    """
    template = _load_match_prompt_template()
    prompt = (
        template
        .replace("{home}", home or "")
        .replace("{away}", away or "")
        .replace("{venue}", venue or "")
        .replace("{matchday}", str(matchday or ""))
        .replace("{kickoff_local}", kickoff_local or "")
    )

    raw = None
    provider = None
    if GEMINI_API_KEY:
        try:
            raw = _generate_with_gemini(prompt)
            provider = "gemini"
        except Exception as e:
            print(f"[ai] Gemini failed (fixture): {e}")
    if not raw and GROQ_API_KEY:
        try:
            raw = _generate_with_groq(prompt)
            provider = "groq"
        except Exception as e:
            print(f"[ai] Groq failed (fixture): {e}")

    if raw:
        data = _parse_json_result(raw)
        if data is not None:
            text = (data.get("post_text") or "").strip()
            if text:
                return {"post_text": text, "provider": provider}
        return {"post_text": raw.strip(), "provider": provider}

    # Hard safe fallback: fixed comment-bait template (never crashes the run).
    return {
        "post_text": (
            f"{home} clash with {away} at {venue or 'their ground'} tonight.\n\n"
            f"Who takes all three points? Drop your call in the comments \ud83d\udc47\n\n"
            f"#WeekendPulse #PremierLeague"
        ),
        "provider": "template",
    }
