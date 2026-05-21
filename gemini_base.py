# This file is a template for the Gemini API.
# Not used in the project except as a reference.
import os
from typing import Optional
from google import genai


def explain_experiment(title: str, description: str, outcome: str, model_id: str = "gemini-2.0-flash") -> str:
    """
    Generate a short teaching guide for a red-team experiment.

    Falls back to a local explanation when the API key is missing.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return (
            "Teaching Guide (local fallback)\n"
            f"Experiment: {title}\n"
            f"Attack Objective: {description}\n"
            f"Observed Outcome: {outcome}\n"
            "Red-Team Lens: Identify what failed, what succeeded, and what to try next.\n"
            "Note: Set GEMINI_API_KEY to generate an LLM explanation."
        )

    client = genai.Client(api_key=api_key)
    prompt = (
        "You are a red-team instructor. Write a concise teaching guide for students.\n"
        f"Experiment: {title}\n"
        f"Attack Objective: {description}\n"
        f"Observed Outcome: {outcome}\n"
        "Focus on offensive mindset: what the attacker tried, what defense blocked (if any), "
        "and one concrete next probe to escalate.\n"
        "Format as short bullet points without headers."
    )

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt
        )
        if response.text:
            return response.text.strip()
        return "No text returned by Gemini."
    except Exception as exc:
        return f"Gemini error while generating explanation: {exc}"

def main():
    # 1. Setup: Get API Key from environment or paste it directly (not recommended for sharing)
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.")
        return

    # 2. Initialize the Client
    client = genai.Client(api_key=api_key)

    # 3. Configuration
    model_id = "gemini-2.0-flash" 
    prompt = "What is the capital of France?"

    print(f"Asking {model_id}: '{prompt}'...\n")

    try:
        # 4. Make the API Call
        response = client.models.generate_content(
            model=model_id,
            contents=prompt
        )

        # 5. Print the Response
        if response.text:
            print("Response:")
            print(response.text)
        else:
            print("No text returned.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()