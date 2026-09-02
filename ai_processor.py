"""
WeekendPulse - AI post processor.
Uses Google Gemini (new google.genai SDK) as primary,
falls back to Groq on failure/rate-limit.
Reads the fixed prompt template from prompts/debate_post.txt.
"""
import json

from config import GEMINI_API_KEY, GROQ_API_KEY, GROQ_MODEL, GEMINI_MODEL, PROMPT_PATH


def _load_prompt_template():
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
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
        # internal reasoning before the real answer; too low and content is empty
        "max_tokens": 1200,
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


def turn_article_into_post_json(title, summary):
    """
    Generate a Facebook post AND a reel verdict from an article.
    Returns a dict: {post_text, reel_worthy, reel_emotion, reel_blurb, provider}.
    This path NEVER blocks posting: if JSON parse fails or post_text is missing,
    it falls back to treating the raw model output as the post text, with
    reel_worthy=False, reel_emotion="neutral", reel_blurb="" (identical to the
    legacy text-only behaviour).
    """
    prompt = _prompt_for(title, summary)

    def default_out(text, provider):
        return {
            "post_text": (text or "").strip(),
            "reel_worthy": False,
            "reel_emotion": "neutral",
            "reel_blurb": "",
            "provider": provider,
        }

    raw = None
    provider = None
    if GEMINI_API_KEY:
        try:
            raw = _generate_with_gemini(prompt)
            provider = "gemini"
        except Exception as e:
            print(f"[ai] Gemini failed: {e}")
    if not raw and GROQ_API_KEY:
        try:
            raw = _generate_with_groq(prompt)
            provider = "groq"
        except Exception as e:
            print(f"[ai] Groq failed: {e}")

    if not raw:
        raise RuntimeError("Both Gemini and Groq failed - cannot generate post.")

    data = _parse_json_result(raw)
    if data is None:
        print("[ai] could not parse JSON - falling back to text-only post")
        return default_out(raw, provider)

    post_text = (data.get("post_text") or "").strip()
    if not post_text:
        print("[ai] no post_text in JSON - falling back to text-only post")
        return default_out(raw, provider)

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


def turn_article_into_post(title, summary):
    """
    Legacy text-only path (used as a hard safe fallback).
    Returns (post_text, provider_used).
    """
    result = turn_article_into_post_json(title, summary)
    return result["post_text"], result["provider"]
