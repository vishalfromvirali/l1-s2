import os
import re
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request
from serpapi.google_search_results import GoogleSearchResults
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lsa import LsaSummarizer

# Cache
cache = {
    "who is create you": {
        "summary": ["His name is Vishal"],
        "error": None,
        "urls_found": ["novix-chat-3.onrender.com"]
    }
}

app = Flask(__name__)

# Clean HTML text
def clean_text(text):
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# Scrape webpages
def scrape_and_clean_text(url):
    try:
        response = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0"
        }, timeout=8)
        response.raise_for_status()
    except:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "footer", "header", "nav"]):
        tag.decompose()

    body = soup.find("main") or soup.body
    if not body:
        return ""

    text = " ".join(body.stripped_strings)
    text = clean_text(text)

    if len(text) < 150:
        return ""

    return text

# Summarize
def summarize_text(full_text):
    if not full_text:
        return []

    parser = PlaintextParser.from_string(full_text, Tokenizer("english"))
    summarizer = LsaSummarizer()
    summary = summarizer(parser.document, 5)
    return [str(s) for s in summary]

# Routes
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        topic = request.form.get("topic")

        if topic in cache:
            return render_template("index.html", **cache[topic], topic=topic)

        api_key = os.environ.get("SERPAPI_API_KEY")
        if not api_key:
            return render_template("index.html", error="SERPAPI_API_KEY not set.")

        params = {
            "engine": "google",
            "q": topic,
            "api_key": api_key,
            "num": "5",
        }

        try:
            search = GoogleSearchResults(params)
            results = search.get_dict()
            organic = results.get("organic_results", [])
            urls = [x["link"] for x in organic if "link" in x]
        except Exception as e:
            return render_template("index.html", error=str(e))

        all_text = ""
        urls_found = []

        for url in urls:
            text = scrape_and_clean_text(url)
            if text:
                all_text += text + "\n\n"
                urls_found.append(url)
            time.sleep(1)

        summary = summarize_text(all_text)

        cache[topic] = {
            "summary": summary,
            "error": None if summary else "Not enough content",
            "urls_found": urls_found
        }

        return render_template("index.html", summary=summary, topic=topic, urls_found=urls_found)

    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
