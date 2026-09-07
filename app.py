import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from google import genai
from google.genai import types

from chatbot_config import SYSTEM_PROMPT

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.1-flash-lite"
KNOWLEDGE_FILE = Path(os.getenv("KNOWLEDGE_FILE", "knowledge.txt"))

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not configured in the .env file.")

client = genai.Client(api_key=API_KEY)


def load_knowledge():
    if not KNOWLEDGE_FILE.exists():
        return ""
    return KNOWLEDGE_FILE.read_text(encoding="utf-8")


def retrieve_context(query, knowledge, max_chunks=6):
    """Retrieve study material using simple keyword-overlap scoring."""
    if not knowledge.strip():
        return ""

    query_words = {
        word.strip(".,!?;:()[]{}\"'").lower()
        for word in query.split()
        if len(word.strip(".,!?;:()[]{}\"'")) > 2
    }

    chunks = [
        chunk.strip()
        for chunk in knowledge.split("\n\n")
        if chunk.strip() and not chunk.lstrip().startswith("#")
    ]

    scored_chunks = []
    for chunk in chunks:
        chunk_words = set(chunk.lower().split())
        score = sum(word in chunk_words for word in query_words)

        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)

    return "\n\n".join(chunk for _, chunk in scored_chunks[:max_chunks])


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()

    if not question:
        return jsonify({"error": "Please enter a Prompt Engineering question."}), 400

    knowledge = load_knowledge()
    context = retrieve_context(question, knowledge)

    prompt = f"""
{SYSTEM_PROMPT}

RETRIEVED PROMPT ENGINEERING STUDY MATERIAL:
{context if context else "No relevant study material was retrieved."}

STUDENT QUESTION:
{question}

Instructions:
1. Answer only questions related to Prompt Engineering.
2. Use the retrieved study material as the primary source.
3. If the material does not contain enough information, say that the answer is
   not available in the provided study material.
4. Do not invent facts or pretend that information exists in the material.
5. If the question is unrelated to Prompt Engineering or study, politely refuse
   and explain that you only answer Prompt Engineering study questions.
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=800,
            ),
        )

        answer = (response.text or "").strip()

        if not answer:
            answer = "I could not generate an answer from the provided study material."

        return jsonify({"answer": answer})

    except Exception:
        app.logger.exception("Gemini API request failed.")
        return jsonify({"error": "Unable to generate a response right now."}), 500


if __name__ == "__main__":
    app.run(debug=True)
