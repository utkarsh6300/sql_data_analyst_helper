# import openai
from typing import List, Dict, Any
import os
from dotenv import load_dotenv
import logging

from services.generic.llm import bedrock

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_sql_query(
    query_text: str,
    schema: str,
    documentation: str = None,
    sample_queries: Dict[str, str] = None,
    query_history: List[Dict[str, Any]] = None
) -> str:
    logger.info(f"🔍 Generating SQL for query: '{query_text}'")
    
    # Construct the prompt with context
    context = ""
    
    if schema and schema.strip():
        context += f"Database Schema:\n{schema}\n\n"
    
    if documentation and documentation.strip():
        context += f"Documentation:\n{documentation}\n\n"
    
    if sample_queries and len(sample_queries) > 0:
        context += "Sample Queries:\n"
        for text, sql in sample_queries.items():
            context += f"Text: {text}\nSQL: {sql}\n\n"
    
    if query_history and len(query_history) > 0:
        context += "Previous queries in this conversation:\n"
        for item in query_history:
            context += f"Text: {item['text']}\nSQL: {item['sql']}\nCorrect: {item.get('is_correct', True)}\n\n"
    
    prompt = f"{context}\nGenerate SQL for: {query_text}\nSQL:"
    logger.info(f"Prompt: {prompt}")
    
    logger.info(f"📝 Constructed prompt length: {len(prompt)} characters")
    logger.info(f"📋 Schema provided: {'Yes' if schema and schema.strip() else 'No'}")
    logger.info(f"📚 Documentation provided: {'Yes' if documentation and documentation.strip() else 'No'}")
    logger.info(f"❓ Sample queries provided: {len(sample_queries) if sample_queries else 0}")
    logger.info(f"🔄 Query history length: {len(query_history) if query_history else 0}")

    # Ensure we have a valid prompt
    if not context.strip():
        logger.warning("⚠️  No context provided (no schema, documentation, or sample queries)")
    
    if not query_text.strip():
        logger.error("❌ Empty query text provided")
        raise Exception("Query text cannot be empty")

    try:
        # response = openai.chat.completions.create(
        #     model="gpt-4-turbo-preview",
        #     messages=[
        #         {"role": "system", "content": "You are a SQL expert. Generate accurate SQL queries based on natural language inputs and the provided database schema and context. Return only the SQL query without any explanations or markdown formatting."},
        #         {"role": "user", "content": prompt}
        #     ],
        #     temperature=0.3,
        #     max_tokens=500
        # )
        # generated_sql = response.choices[0].message.content.strip()

        system_content = "You are a SQL expert. Generate accurate SQL queries based on natural language inputs and the provided database schema and context. Return only the SQL query without any explanations or markdown formatting."
        response = bedrock.generate_text(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            prompt=prompt,
            system_prompts=[{"text": system_content}],
            temperature=0.3,
        )
        
        generated_sql = response.strip()
        logger.info(f"✅ Generated SQL: {generated_sql}")
        logger.info(f"📊 Tokens used: {response.usage.total_tokens if response.usage else 'Unknown'}")
        
        return generated_sql
        
    except Exception as e:
        logger.error(f"❌ Error generating SQL: {str(e)}")
        raise Exception(f"Failed to generate SQL: {str(e)}")

def regenerate_sql_query(
    query_text: str,
    schema: str,
    documentation: str = None,
    sample_queries: Dict[str, str] = None,
    query_history: List[Dict[str, Any]] = None
) -> str:
    logger.info(f"🔄 Regenerating SQL for query: '{query_text}'")
    
    # Add specific instruction about previous incorrect attempts
    incorrect_attempts = [
        q for q in query_history if q["text"] == query_text and not q.get("is_correct", True)
    ] if query_history else []
    
    context = ""
    
    if schema and schema.strip():
        context += f"Database Schema:\n{schema}\n\n"
    
    if documentation and documentation.strip():
        context += f"Documentation:\n{documentation}\n\n"
    
    if sample_queries and len(sample_queries) > 0:
        context += "Sample Queries:\n"
        for text, sql in sample_queries.items():
            context += f"Text: {text}\nSQL: {sql}\n\n"
    
    if incorrect_attempts and len(incorrect_attempts) > 0:
        context += "Previous incorrect attempts:\n"
        for attempt in incorrect_attempts:
            context += f"Incorrect SQL: {attempt['sql']}\n"
        logger.info(f"⚠️  Found {len(incorrect_attempts)} previous incorrect attempts")
    
    prompt = f"{context}\nGenerate a corrected SQL query for: {query_text}\nSQL:"
    
    logger.info(f"📝 Constructed regeneration prompt length: {len(prompt)} characters")
    logger.info(f"📋 Schema provided: {'Yes' if schema and schema.strip() else 'No'}")
    logger.info(f"📚 Documentation provided: {'Yes' if documentation and documentation.strip() else 'No'}")
    logger.info(f"❓ Sample queries provided: {len(sample_queries) if sample_queries else 0}")

    # Ensure we have a valid prompt
    if not context.strip():
        logger.warning("⚠️  No context provided for regeneration (no schema, documentation, or sample queries)")
    
    if not query_text.strip():
        logger.error("❌ Empty query text provided for regeneration")
        raise Exception("Query text cannot be empty")

    try:
        # response = openai.chat.completions.create(
        #     model="gpt-4-turbo-preview",
        #     messages=[
        #         {"role": "system", "content": "You are a SQL expert. Generate a corrected SQL query, avoiding the mistakes in previous attempts. Return only the SQL query without any explanations or markdown formatting."},
        #         {"role": "user", "content": prompt}
        #     ],
        #     temperature=0.3,
        #     max_tokens=500
        # )
        
        # generated_sql = response.choices[0].message.content.strip()
        system_content = "You are a SQL expert. Generate a corrected SQL query, avoiding the mistakes in previous attempts. Return only the SQL query without any explanations or markdown formatting."
        response = bedrock.generate_text(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            prompt=prompt,
            system_prompts=[{"text": system_content}],
            temperature=0.3,
        )
        generated_sql = response.strip()
        logger.info(f"✅ Regenerated SQL: {generated_sql}")
        logger.info(f"📊 Tokens used: {response.usage.total_tokens if response.usage else 'Unknown'}")
        
        return generated_sql
        
    except Exception as e:
        logger.error(f"❌ Error regenerating SQL: {str(e)}")
        raise Exception(f"Failed to regenerate SQL: {str(e)}")
