import pdfplumber
import io

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extracts all text from a PDF file provided as bytes."""
    text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def split_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Splits a string into overlapping chunks, attempting to split on word boundaries."""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        
        # If we are not at the end of the text, find the nearest space backward to avoid cutting words
        if end < text_length:
            last_space = text.rfind(' ', start, end)
            if last_space != -1 and last_space > start + (chunk_size // 2):
                end = last_space

        chunks.append(text[start:end].strip())
        
        # Calculate next start position, adjusting for overlap
        next_start = end - overlap
        
        # Find the nearest space forward from next_start to avoid starting mid-word
        if next_start < text_length and next_start > 0:
            next_space = text.find(' ', next_start, end)
            if next_space != -1:
                start = next_space + 1
            else:
                start = next_start
        else:
            start = next_start

    return [c for c in chunks if c] # Filter empty chunks
