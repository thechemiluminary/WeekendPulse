"""
WeekendPulse - AI post processor.
Uses Google Gemini (new google.genai SDK) as primary,
falls back to Groq on failure/rate-limit.
Reads the fixed prompt template from prompts/debate_post.txt.
"""
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


def turn_article_into_post(title, summary):
    """
    Generate a Facebook debate post from an article.
    Tries Gemini first, then Groq. Returns (post_text, provider_used).
    """
    template = _load_prompt_template()
    prompt = template.replace("{title}", title).replace("{summary}", summary or "")

    if GEMINI_API_KEY:
        try:
            text = _generate_with_gemini(prompt)
            if text:
                return text, "gemini"
        except Exception as e:
            print(f"[ai] Gemini failed: {e}")

    if GROQ_API_KEY:
        try:
            text = _generate_with_groq(prompt)
            if text:
                return text, "groq"
        except Exception as e:
            print(f"[ai] Groq failed: {e}")

    raise RuntimeError("Both Gemini and Groq failed - cannot generate post.")
