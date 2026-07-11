import os
import sys
import json
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

try:
    import trafilatura
except ImportError:
    trafilatura = None

load_dotenv()

if "OPENROUTER_API_KEY" not in os.environ or "SERPER_API_KEY" not in os.environ:
    print("some error occured in getting api keys")
    sys.exit(1)

from openai import OpenAI
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

MODEL = "openrouter/free"
MAX_ITERATIONS = 8

SERPER_API_KEY = os.environ["SERPER_API_KEY"]
def web_search(query: str, num_results: int = 5) -> list[dict]:
    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": num_results},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("organic", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results
    except Exception as e:
        return [{"error": f"some error occured in searching with serper: {str(e)}"}]

def web_fetch(url: str) -> str:
    try:
        """Fetch the content of a URL and return it as text."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return f"some error occured in fetching response:{str(e)}"
    
def fetch_clean(url: str) -> str:
    try:
        html = web_fetch(url)
        if "some error occured in fetching response" in html:
            return html
        if trafilatura is None:
            return "Error: 'trafilatura' library is not installed. Cannot clean web content."
        text = trafilatura.extract(html, include_comments=False, include_tables=True)
        return text or ""
    except Exception as e:
        return f"some error occured in using trafilatura {str(e)}"

MAX_CHARS = 8000

def fetch_for_agent(url: str) -> str:
    content = fetch_clean(url)
    if len(content) > MAX_CHARS:
        content = content[:MAX_CHARS] + "\n\n[...truncated]"
    return content

if __name__ == "__main__":
    print("--- Web Tools Sanity Check ---")
    search_test = web_search("DeepSeek-V3 architecture")
    print(search_test)