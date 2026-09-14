import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

with open(r"A:\ai\VideoAI\assets\temp_audio.mp3", "rb") as audio_file:
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="verbose_json",
        timestamp_granularities=["word"]
    )

for word in transcript.words:
    print(f"[{word.start:.2f}s - {word.end:.2f}s] {word.word}")
