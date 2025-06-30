from flask import Flask, request, jsonify, render_template
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from googleapiclient.discovery import build
from openai import OpenAI
from dotenv import load_dotenv
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

        # Extract YouTube video ID
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", video_url)
        if not match:
            return jsonify({"error": "Invalid YouTube URL."})
        video_id = match.group(1)

        # Get transcript
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(["en"]).fetch()
        except (TranscriptsDisabled, NoTranscriptFound):
            return jsonify({"error": "No English transcript available for this video."})

        # Properly extract text from transcript objects
        full_text = "\n".join(t.text for t in transcript)

        # Get video metadata from YouTube API
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        response = youtube.videos().list(part="snippet,contentDetails", id=video_id).execute()
        if not response["items"]:
            return jsonify({"error": "Failed to fetch video metadata."})

        video_info = response["items"][0]
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

