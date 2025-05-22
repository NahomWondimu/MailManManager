import google.generativeai as genai
import os
import json
import time
from enum import Enum
from dotenv import load_dotenv

load_dotenv()
genaiKey = os.getenv("GEMINI_API_KEY")

# Engineer the prompt for Gemini based on email inputs and user-defined context
def engineerPrompt(emails: list[str], user_context: str = "") -> str:
    base_instructions = (
        "You are an AI assistant that categorizes emails into the following folders:\n"
        "- 'Time Sensitive' for urgent or deadline-based messages.\n"
        "- 'For Review' for messages that require attention but are not urgent.\n"
        "- 'Junk' for promotions, spam, or irrelevant content.\n"
    )

    if user_context:
        base_instructions += f"\nThe user has additional rules or preferences:\n{user_context.strip()}\n"

    base_instructions += "\nCategorize the following emails:\n"

    for i, email in enumerate(emails, 1):
        base_instructions += f"Email {i}: {email}\n"

    base_instructions += (
        "\nRespond in *strict* JSON format as follows:\n"
        '{\n  "Time Sensitive": [...],\n  "For Review": [...],\n  "Junk": [...]\n}'
    )

    return base_instructions

# Add retry and logging

def getFolderRecommendation(emails: list[str], retries=3, delay=2) -> dict:
    genai.configure(api_key=genaiKey)
    model = genai.GenerativeModel("gemini-1.5-flash")
    user_context = (
        "Please follow these user-specific categorization rules:\n"
        "- Always treat advertisements, newsletters, and college letters as 'Junk' unless they mention the University of Maryland, College Park **specifically by name**.\n"
        "- Any emails related to interviews, job offers, or internship opportunities should be categorized as 'Time Sensitive'.\n"
        "- Job search alerts or listings from ZipRecruiter, Scholarships360, or similar services should be categorized as 'Junk', even if they mention jobs or deadlines.\n"
        "- Do NOT consider generic college names or decision emails from any university other than UMD as time sensitive — these are Junk.\n"
        "- Your priority is to reduce clutter. Only true actionable items should be considered 'Time Sensitive'."
    )


    prompt = engineerPrompt(emails, user_context)

    for attempt in range(retries):
        try:
            print(f"[Gemini] Sending request, attempt {attempt + 1}")
            response = model.generate_content([{"text": prompt}], generation_config={"response_mime_type": "application/json"})
            content = response.text.strip()

            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()

            print("[Gemini] Response received and cleaned.")
            return json.loads(content)

        except Exception as e:
            print(f"[Gemini] Error: {e}. Retrying in {delay} seconds...")
            time.sleep(delay)

    print("[Gemini] Failed after multiple retries. Returning empty folder set.")
    return {
        "Time Sensitive": [],
        "For Review": [],
        "Junk": []
    }
