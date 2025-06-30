from flask import Flask, request, jsonify, render_template
from googleapiclient.discovery import build
from openai import OpenAI
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs
import requests
import xml.etree.ElementTree as ET
import re
import os

# Load environment variables from .env file
load_dotenv()

# Get API keys securely from environment
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
YOUTUBE_API_KEY = os.getenv("GOOGLE_API_KEY")

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/summarize", methods=["POST"])
def summarize():
    try:
        data = request.get_json()
        video_url = data.get("url", "")
        print("Received URL:", video_url)

        # Extract YouTube video ID from any format
        parsed_url = urlparse(video_url)
        query = parse_qs(parsed_url.query)
        video_id = query.get("v", [None])[0]

        # Handle youtu.be short links
        if not video_id and "youtu.be" in parsed_url.netloc:
            video_id = parsed_url.path.strip("/")

        if not video_id:
            return jsonify({"error": "Invalid YouTube URL."})

        # Fetch captions through ScraperAPI
        scraper_api_key = os.getenv("SCRAPER_API_KEY")
        original_url = f"https://video.google.com/timedtext?lang=en&v={video_id}"
        encoded_url = urllib.parse.quote_plus(original_url)
        scraped_url = f"http://api.scraperapi.com?api_key={scraper_api_key}&url={encoded_url}&ultra_premium=true"
        response = requests.get(scraped_url)

        if response.status_code != 200 or not response.text.strip():
            print("Caption fetch failed:", response.text[:500])
            return jsonify({"error": "No English transcript available for this video."})

        root = ET.fromstring(response.content)
        full_text = "\n".join([elem.text for elem in root.findall("text") if elem.text])

        # Get video metadata
        youtube = build("youtube", "v3", developerKey=os.getenv("GOOGLE_API_KEY"))
        video_data = youtube.videos().list(part="snippet,contentDetails", id=video_id).execute()
        if not video_data["items"]:
            return jsonify({"error": "Failed to fetch video metadata."})

        video_info = video_data["items"][0]
        title = video_info["snippet"]["title"]
        channel = video_info["snippet"]["channelTitle"]
        duration = video_info["contentDetails"]["duration"]

        prompt = (
            f"Video Title: {title}\n"
            f"Channel: {channel}\n"
            f"Duration: {duration}\n\n"
            "Summarize this YouTube transcript clearly and concisely. "
            "If it's a recipe, list ingredients and steps. "
            "If it's educational, list key takeaways:\n\n"
            f"{full_text}"
        )

        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=700
        )

        summary = completion.choices[0].message.content.strip()
        return jsonify({
            "summary": summary,
            "title": title,
            "channel": channel,
            "duration": duration
        })

    except Exception as e:
        print("Error occurred:", str(e))
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
