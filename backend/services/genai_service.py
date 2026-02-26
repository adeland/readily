import json
import logging
from google import genai
from google.genai import types
from google.genai.errors import APIError
from core.config import settings
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Initialize the Gemini API client
client = genai.Client(api_key=settings.google_api_key)

# The correct model name for Google's API in 2026 for the 3.0 Pro preview
# This handles the 404 errors by using the correct formatted name.
GEMINI_MODEL = "gemini-3-pro-preview"

# Setup automatic exponential backoff for Google API Rate Limits (429s)
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def _generate_content_with_retry(prompt: str, schema: dict):
    """Wraps the generate_content call with an exponential backoff retry for Rate Limits."""
    return client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.1
        )
    )

def generate_embedding(text: str) -> List[float]:
    """Generates an embedding for the given text."""
    result = client.models.embed_content(
        model='gemini-embedding-001', # gemini-embedding-001 is supported by v1beta API and requires exactly 3072 dimensions
        contents=text,
    )
    return result.embeddings[0].values

def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generates embeddings for a list of texts in a single batch API call."""
    if not texts:
        return []
    result = client.models.embed_content(
        model='gemini-embedding-001',
        contents=texts,
    )
    return [emb.values for emb in result.embeddings]

def _parse_json_response(response) -> dict:
    """Helper to safely parse JSON from LLM responses, stripping markdown and checking for safety errors."""
    if not hasattr(response, 'text') or response.text is None:
        return {"status": "Error", "evidence": "Blocked by AI Safety Filters or empty LLM response."}

    text = response.text
    clean_text = text.strip()
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    if clean_text.startswith("```"):
        clean_text = clean_text[3:]
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]
    
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError as e:
        return {"status": "Error", "evidence": f"Failed to parse LLM JSON: {e}"}

def extract_questions(text: str) -> List[str]:
    """Uses Gemini with Structured Outputs to extract a list of audit questions."""
    prompt = f"Extract all the audit questions from the following text:\n\n{text}"
    schema = {"type": "object", "properties": {"questions": {"type": "array", "items": {"type": "string"}}}}
    
    try:
        response = _generate_content_with_retry(prompt, schema)
        result = _parse_json_response(response)
        return result.get("questions", [])
    except APIError as e:
        logger.error(f"Google GenAI API Failed completely for extraction: {e}")
        return []

def evaluate_question(question: str, policy_chunks: List[str]) -> dict:
    """Uses Gemini with Structured Outputs to evaluate a question against policy evidence."""
    context = "\n\n---\n\n".join(policy_chunks)
    prompt = f"""You are an expert compliance auditor. 
    Based ONLY on the following policy document excerpts, evaluate whether the audit requirement is 'Met' or 'Not Met'.
    Extract the precise evidence or reason for your decision.
    If the policy does not contain enough information to determine, mark it as 'Not Met' and state that there is no evidence.
    
    IMPORTANT: You must include the relevant policy name (provided in brackets like [Policy: NAME] before each excerpt) in your final evidence statement, so we know exactly where it is stated.
    
    Audit Requirement / Question: {question}
    
    Policy Excerpts (each starts with its source policy name):
    {context}
    """
    
    schema = {
        "type": "object", 
        "properties": {
            "status": {"type": "string", "description": "Must be 'Met' or 'Not Met'"},
            "evidence": {"type": "string", "description": "Evidence from the policy document"}
        },
        "required": ["status", "evidence"]
    }
    
    try:
        response = _generate_content_with_retry(prompt, schema)
        return _parse_json_response(response)
    except APIError as e:
        logger.error(f"Google GenAI API Failed completely for evaluation: {e}")
        return {"status": "Error", "evidence": f"API Rate Limit or Model Error: {e.message}"}
