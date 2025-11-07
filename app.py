import os
import re
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request
# FIX: Corrected the import path for GoogleSearch from the serpapi library
from serpapi.google_search import GoogleSearch 
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lsa import LsaSummarizer

# --- Simple cache to reduce repeated API calls ---
cache = {
    # Keep the example cache entry for testing
    "who is create you": {
        "summary": ["His name is Vishal"],
        "error": None, # Use None for no error, which is cleaner
        "urls_found": ["novix-chat-3.onrender.com"]
    }
}

# The Flask application instance is named 'app'
app = Flask(__name__)

# --- Helper Functions ---
def clean_text(text):
    """Removes common unwanted elements and cleans whitespace."""
    text = re.sub(r'\[\d+\]', '', text)  # Removes citation brackets like [1], [2]
    text = re.sub(r'\d{1,3}\.\d+;\s*-?\d{1,3}\.\d+', '', text) # Removes coordinate patterns
    text = re.sub(r'\s+', ' ', text) # Normalizes whitespace
    
    # Remove common footer/header noise
    for keyword in ['Home Store Tour Dates', 'Newsletter', 'Sign up for']:
        text = text.replace(keyword, '')
        
    return text.strip()

def scrape_and_clean_text(url):
    """Fetches, cleans, and filters text content from a given URL."""
    try:
        # Increase timeout and use standard headers
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}, timeout=8)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error fetching {url}: {e}")
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Remove navigation, ads, and irrelevant tags
    for tag in soup(["script", "style", "noscript", "iframe", "nav", "footer", "header", ".ad", ".sidebar", "aside"]):
        tag.decompose()

    # Prefer the 'main' content area if available, otherwise use the body
    main_content = soup.find('main') or soup.body
    if not main_content:
        return ""

    text_elements = main_content.find_all(string=True)

    def is_visible(element):
        """Simple visibility check for text elements."""
        if element.parent.name in ['style', 'script', 'head', 'title', 'meta', '[document]']:
            return False
        return element.strip() != ""

    visible_texts = filter(is_visible, text_elements)
    full_text = "\n".join(visible_texts)
    full_text = clean_text(full_text)

    # Basic content quality check
    if len(full_text) < 150:
        print(f"⚠️ Not enough relevant content from {url}. Length: {len(full_text)}")
        return ""
    return full_text

def summarize_text(full_text):
    """Generates an LSA summary of the provided text."""
    if not full_text or len(full_text) < 150:
        return []
    
    # Sumy expects a file-like object or string; we use from_string
    parser = PlaintextParser.from_string(full_text, Tokenizer("english"))
    summarizer = LsaSummarizer()
    
    # You may need to download NLTK data (handled in requirements.txt/Procfile)
    try:
        summary = summarizer(parser.document, 5) # Generate 5 sentences
    except LookupError:
        print("⚠️ NLTK data (punkt) not found. Summary failed.")
        return ["Error: NLTK data missing. Ensure it's downloaded in the environment setup."]
        
    return [str(sentence) for sentence in summary]

# --- Flask Routes ---
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        topic = request.form.get('topic')
        if not topic:
            return render_template('index.html', error="Please enter a topic.")

        # Check cache
        if topic in cache:
            cached_data = cache[topic]
            return render_template(
                'index.html',
                summary=cached_data.get('summary'),
                topic=topic,
                error=cached_data.get('error'),
                urls_found=cached_data.get('urls_found')
            )

        # Environment variable check
        api_key = os.environ.get("SERPAPI_API_KEY")
        if not api_key:
            # For local testing, you might use a placeholder, but for Render, this is correct.
            return render_template('index.html', error="SERPAPI_API_KEY environment variable is not set. Please set it in Render's environment settings.")

        params = {
            "engine": "google",
            "q": topic,
            "api_key": api_key,
            "num": "5" # Requesting 5 results
        }

        all_text = ""
        urls_found = []
        error_message = None

        try:
            # Instantiate GoogleSearch object
            search = GoogleSearch(params)
            results = search.get_dict()
            
            # Use 'organic_results' key from SerpApi
            organic_results = results.get("organic_results", [])
            urls = [result["link"] for result in organic_results if "link" in result]

            if not urls:
                error_message = "No relevant search results found. Try another topic."
            else:
                for url in urls:
                    page_text = scrape_and_clean_text(url)
                    if page_text:
                        all_text += page_text + "\n\n"
                        urls_found.append(url)
                    time.sleep(1) # Be respectful of target websites

        except Exception as e:
            print(f"⚠️ API or network error: {e}")
            error_message = f"An API or network error occurred: {e}"

        # Summarize the collected text
        summary_sentences = summarize_text(all_text)
        
        if not summary_sentences and not error_message:
             error_message = "Could not extract enough content to generate a summary from any of the search results."
        
        # Cache the new result
        cache[topic] = {
            "summary": summary_sentences,
            "error": error_message,
            "urls_found": urls_found
        }

        return render_template(
            'index.html',
            summary=summary_sentences,
            topic=topic,
            error=error_message,
            urls_found=urls_found
        )

    # Default GET request
    return render_template('index.html')

# --- Run App ---
if __name__ == '__main__':
    # Use Gunicorn locally for consistency, but the Procfile handles it on Render
    port = int(os.environ.get("PORT", 5000))
    # Note: On Render, the Procfile command handles running with Gunicorn, 
    # but the port environment variable is respected here for local testing.
    app.run(host="0.0.0.0", port=port, debug=True)