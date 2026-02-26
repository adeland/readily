from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
import io
import asyncio
import os
import shutil
from pathlib import Path
from typing import List, Dict

from models.schemas import PolicyChunkResponse, AuditProcessResponse, AuditResult, QuestionEvaluation
from services.pdf_parser import extract_text_from_pdf_bytes, split_into_chunks
from services.genai_service import generate_embeddings_batch, generate_embedding, extract_questions, evaluate_question
from services.supabase_service import insert_policy_chunks, match_policy_chunks, insert_audit_result, get_all_audit_results, clear_data

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

router = APIRouter()

def batch_list(iterable, n=1):
    """Helper to chunk lists into batches."""
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx:min(ndx + n, l)]

async def process_pdf_file(filename: str, contents: bytes) -> tuple[int, int]:
    """Processes a single PDF file and inserts its chunks into Supabase. Returns (chunks_created, chunks_inserted)."""
    logger.info(f"Starting extraction for PDF: {filename} ({len(contents)} bytes)")
    
    # CPU-bound PDF extraction needs to be run in a separate thread to prevent blocking FastAPI
    text = await asyncio.to_thread(extract_text_from_pdf_bytes, contents)
    logger.info(f"Extracted {len(text)} characters from {filename}")
    
    # Split the document into overlapping chunks (now using word-aware splitting)
    chunks = split_into_chunks(text, chunk_size=1000, overlap=200)
    
    # Filter out extremely short chunks
    valid_chunks = [chunk for chunk in chunks if len(chunk.strip()) > 50]
    logger.info(f"Generated {len(valid_chunks)} valid chunks for {filename}")
    
    # Generate embeddings in a single batched API call (or batches of 100 to respect Gemini limits)
    chunk_records = []
    
    logger.info(f"Embedding {len(valid_chunks)} chunks using Google GenAI...")
    for chunk_batch in batch_list(valid_chunks, 100):
        # Batch embedding generation avoids sequential N+1 HTTP calls
        embeddings = await asyncio.to_thread(generate_embeddings_batch, chunk_batch)
        
        for i, chunk in enumerate(chunk_batch):
            chunk_records.append({
                "policy_name": filename,
                "chunk_text": chunk,
                "embedding": embeddings[i]
            })
    
    logger.info(f"Finished embedding chunks. Inserting {len(chunk_records)} records into Supabase...")
    # Batch insert to Supabase
    inserted_count = 0
    for chunk_record_batch in batch_list(chunk_records, 200):
        if chunk_record_batch:
            await asyncio.to_thread(insert_policy_chunks, chunk_record_batch)
            inserted_count += len(chunk_record_batch)
            
    logger.info(f"Successfully inserted {inserted_count} chunks into Supabase for {filename}.")
    return len(valid_chunks), inserted_count

@router.post("/ingest-policy", response_model=PolicyChunkResponse)
async def ingest_policy(files: List[UploadFile] = File(...)):
    """Ingests one or multiple policy PDFs and stores their embeddings in the database."""
    logger.info(f"Received request to ingest {len(files)} files.")
    total_valid_chunks = 0
    total_inserted = 0
    processed_files = []
    
    for file in files:
        if file.content_type != "application/pdf":
            logger.warning(f"Skipping non-PDF file: {file.filename} (content_type: {file.content_type})")
            continue # Skip non-PDFs if uploaded via directory drop
            
        logger.info(f"--- Processing File: {file.filename} ---")
        contents = await file.read()
        valid, inserted = await process_pdf_file(file.filename, contents)
        
        total_valid_chunks += valid
        total_inserted += inserted
        processed_files.append(file.filename)
        
    logger.info(f"--- Ingestion Complete ---")
    logger.info(f"Processed {len(processed_files)} files.")
    logger.info(f"Total Chunks Generated: {total_valid_chunks}")
    logger.info(f"Total Chunks Inserted: {total_inserted}")
    
    if not processed_files:
        logger.error("No valid PDF files were found in the upload.")
        raise HTTPException(status_code=400, detail="No valid PDF files were found in the upload.")
        
    return {
        "message": f"Successfully ingested {len(processed_files)} policy documents.",
        "chunks_inserted": total_inserted
    }

# We'll use a global variable to lazily initialize the semaphore in the correct event loop
_process_semaphore = None

def get_semaphore():
    global _process_semaphore
    if _process_semaphore is None:
        # Limit concurrency to 2 to prevent Supabase Statement Timeouts and Google 429 Rate Limits
        _process_semaphore = asyncio.Semaphore(2)
    return _process_semaphore

async def process_single_question(question: str):
    """Processes a single question, throttled to prevent DB/LLM overload."""
    semaphore = get_semaphore()
    async with semaphore:
        try:
            # Step 1: Embed the question
            logger.info(f"[EMBED] Generating embedding for question: {question[:30]}...")
            question_embedding = await asyncio.to_thread(generate_embedding, question)
            
            # Step 2: Retrieve relevant chunks
            logger.info(f"[DB] Searching Supabase for relevant chunks...")
            matched_chunks = await asyncio.to_thread(
                match_policy_chunks, embedding=question_embedding, match_count=5, match_threshold=0.6
            )
            
            policy_texts = []
            for chunk in matched_chunks:
                # The policy_name is stored in the policy_chunks table
                policy_name = chunk.get("policy_name", "Unknown Policy")
                
                # Strip .pdf and anything after the first underscore (e.g., GG.1655_CEO20240924_v20240901.pdf -> GG.1655)
                stripped_name = policy_name.replace(".pdf", "").split("_")[0]
                
                # Prepend the stripped policy name to the chunk text
                policy_texts.append(f"[Policy: {stripped_name}]\n{chunk.get('chunk_text', '')}")
                
            if not policy_texts:
                 policy_texts = ["No relevant policy sections found."]
            
            # Step 3: Evaluate the question
            logger.info(f"[EVAL] Evaluating with LLM: {question[:30]}...")
            evaluation = await asyncio.to_thread(evaluate_question, question=question, policy_chunks=policy_texts)
            
            # Validate with Pydantic
            validated_eval = QuestionEvaluation(**evaluation)
            status = validated_eval.status
            evidence = validated_eval.evidence
            logger.info(f"[DONE] Question: {question[:30]}... -> Status: {status}")
        except Exception as e:
            logger.error(f"[ERROR] Evaluation failed for '{question[:30]}...': {e}")
            status = "Error"
            evidence = f"Evaluation failed: {str(e)}"
            
        # Step 4: Insert result to DB
        db_response = await asyncio.to_thread(
            insert_audit_result, question_text=question, status=status, evidence=evidence
        )
        
        if db_response.data:
            inserted_record = db_response.data[0]
            return {
                "id": inserted_record["id"],
                "question_text": inserted_record["question_text"],
                "status": inserted_record["status"],
                "evidence": inserted_record["evidence"]
            }
        return None

@router.post("/run-audit", response_model=AuditProcessResponse)
async def run_audit(file: UploadFile = File(...)):
    logger.info(f"Received request to run audit with PDF: {file.filename}")
    if file.content_type != "application/pdf":
        logger.error(f"Audit file rejected: {file.content_type} is not application/pdf")
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    contents = await file.read()
    
    logger.info("Extracting text from audit PDF...")
    # CPU-bound PDF extraction needs to be run in a separate thread to prevent blocking FastAPI
    text = await asyncio.to_thread(extract_text_from_pdf_bytes, contents)
    logger.info(f"Extracted {len(text)} characters from audit PDF.")
    
    # Phase 2: Extract audit questions from the text
    try:
        logger.info("Extracting audit questions using LLM...")
        # Use to_thread to prevent blocking the event loop while extracting questions
        questions = await asyncio.to_thread(extract_questions, text)
        logger.info(f"Successfully extracted {len(questions)} questions.")
    except Exception as e:
        logger.error(f"Failed to extract questions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract questions: {str(e)}")
        
    if not questions:
        logger.warning("No audit questions were extracted from the document.")
        raise HTTPException(status_code=400, detail="No audit questions were extracted from the document.")
        
    # Phase 3 & 4: RAG Evaluation and Database Sync running concurrently!
    # Using asyncio.gather processes all questions in parallel, reducing latency drastically.
    logger.info(f"Beginning concurrent RAG evaluation for {len(questions)} questions...")
    tasks = [process_single_question(q) for q in questions]
    processed_results = await asyncio.gather(*tasks)
    
    # Filter out any None values (if DB insert somehow failed but didn't throw)
    processed_results = [r for r in processed_results if r is not None]
    
    logger.info(f"--- Audit Evaluation Complete ---")
    logger.info(f"Processed Results: {len(processed_results)}")
            
    return {
        "message": f"Successfully processed {len(processed_results)} audit questions.",
        "results": processed_results
    }

@router.get("/results", response_model=List[AuditResult])
async def get_results():
    response = get_all_audit_results()
    return response.data

@router.post("/reset")
async def reset_database():
    return clear_data()
