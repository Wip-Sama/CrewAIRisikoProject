
import os
from dotenv import load_dotenv
load_dotenv()
from crewai import Agent
from langchain_groq import ChatGroq

try:
    api_key = os.getenv("GROQ_API_KEY")
    llm = ChatGroq(model=os.getenv("GROQ_MODEL_NAME", "llama-3.1-8b-instant"), groq_api_key=api_key)
    print(f"LLM initialized: {llm}")
    
    from crewai import LLM
    llm3 = LLM(model="groq/llama-3.1-8b-instant", api_key=api_key)
    agent = Agent(
        role="Test Role",
        goal="Test Goal",
        backstory="Test Backstory",
        llm=llm3
    )
    print("Agent initialized with crewai.LLM successfully")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

