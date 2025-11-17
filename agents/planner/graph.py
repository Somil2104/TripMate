# /agents/planner/graph.py
import os
from typing import Literal, Optional, Dict, Any

# LangChain/LangGraph imports
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_core.output_parsers.pydantic import PydanticOutputParser
from langchain_openai import ChatOpenAI # Replace with your chosen LLM (e.g., Anthropic, Gemini, etc.)

# Assuming your models are structured under a 'models' directory
from models.state import AppState, TripSlots, Message
from models.itinerary import Itinerary 

# --- Configuration ---
# You must set an environment variable for your API key (e.g., OPENAI_API_KEY)
# For production, this should be handled securely, but for now:
# os.environ["OPENAI_API_KEY"] = "YOUR_API_KEY"

# Initialize the LLM
# NOTE: Using a model that supports structured output (like GPT-4o, GPT-3.5-turbo, or specific Gemini/Claude models)
# with LangChain's structured output tools is the most reliable approach.
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# 1. Define the LLM Chain for Slot Extraction
# We use PydanticOutputParser (or structured output binding) to force the LLM 
# to return a JSON object conforming to the TripSlots schema.

def create_slot_extraction_chain() -> Runnable:
    """
    Creates a LangChain Runnable for extracting and validating TripSlots.
    """
    # 1. Instantiate the Parser for the desired output format
    # The PydanticOutputParser will inject format instructions into the prompt.
    parser = PydanticOutputParser(pydantic_object=TripSlots)
    format_instructions = parser.get_format_instructions()

    # 2. Define the Prompt Template
    system_prompt = (
        "You are an expert travel assistant. Your goal is to extract key travel details "
        "from the user's latest request and format them strictly into the provided JSON schema. "
        "The trip MUST be domestic. If a field is missing, set it to null or default (e.g., interests=[]). "
        "Always infer the required format from the context (e.g., convert 'next week' to an ISO date if possible)."
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt + "\n\n{format_instructions}"),
        # The user's request is the latest message in the conversation history
        ("human", "{user_input}"), 
    ]).partial(format_instructions=format_instructions)

    # 3. Create the Chain: Prompt | LLM | Parser
    # This chain takes text input and returns a TripSlots object.
    return prompt | llm | parser

# Store the chain for use in the graph node
slot_chain = create_slot_extraction_chain()

# --- 2. The LangGraph Node Function ---

def extract_slots(state: AppState) -> Dict[str, Any]:
    """
    LangGraph node function to extract trip slots from the latest user message.
    It returns an update dictionary for the AppState.
    """
    print("--- Executing Planner Node: Slot Extraction ---")
    
    # Get the latest user message
    # We assume the last message is the most relevant user input for a new request
    latest_user_message = next((msg.content for msg in reversed(state.messages) if msg.role == "user"), "")
    
    if not latest_user_message:
        return {"next_action": "respond_clarification", "errors": ["No user input found to extract slots."]}

    try:
        # Invoke the LangChain runnable to get the structured TripSlots object
        extracted_slots: TripSlots = slot_chain.invoke({"user_input": latest_user_message})
        
        # Merge the new slots into the AppState
        return {
            "trip_slots": extracted_slots.model_dump(),
            "next_action": "validate_slots" # Next node for the graph
        }
    
    except Exception as e:
        # Handle LLM or Parsing errors (e.g., if the LLM fails to format JSON)
        return {
            "errors": [f"Slot Extraction failed. Needs clarification: {e}"],
            "next_action": "respond_clarification"
        }

# --- 3. The Planner Conditional Edge (Decision Function) ---

def should_generate_itinerary(state: AppState) -> Literal["generate_itinerary", "respond_clarification"]:
    """
    Decision function to check if enough key slots (destination, dates) are filled
    to proceed to the itinerary generation stage.
    """
    slots = TripSlots(**state.trip_slots)
    
    # Define minimal required slots for the Planner to start working
    if slots.destination and slots.start_date and slots.end_date:
        print("--- Slot Check: SUCCESS. Moving to Itinerary Generation. ---")
        return "generate_itinerary"
    else:
        print("--- Slot Check: FAILURE. Missing key slots. ---")
        return "respond_clarification"