
from crewai import Agent, Task, Crew, LLM
from crewai.tools import tool
import os
from dotenv import load_dotenv

# Load .env to get local settings
load_dotenv()

def test_lmstudio_gemma():
    print("--- LM Studio / Gemma Connection Test ---")
    
    model_name = os.getenv("LMSTUDIO_MODEL_NAME", "gemma-4-e4b")
    base_url = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    
    print(f"Target Model: {model_name}")
    print(f"Base URL: {base_url}")
    
    try:
        # 1. Initialize the LLM wrapper
        # We prefix with openai/ because LM Studio uses an OpenAI-compatible API
        llm = LLM(
            model=f"openai/{model_name}",
            base_url=base_url,
            api_key="not-needed"
        )
        
        # 2. Define a simple tool
        @tool("calculator")
        def add(a: int, b: int) -> str:
            """Adds two numbers."""
            return str(a + b)

        # 3. Create a test agent
        agent = Agent(
            role="Local Model Tester",
            goal="Verify that you can process instructions and use tools locally.",
            backstory="You are a test agent running on a local Gemma model.",
            tools=[add],
            llm=llm,
            verbose=True
        )

        # 4. Create a simple task
        task = Task(
            description="Add 15 and 27 using your tool, then tell me the result in a friendly way.",
            expected_output="A friendly message with the sum of 15 and 27.",
            agent=agent
        )

        # 5. Run the crew
        crew = Crew(agents=[agent], tasks=[task])
        
        print("\nStarting task execution...")
        result = crew.kickoff()
        
        print("\n--- TEST SUCCESSFUL ---")
        print(f"Agent Response: {result}")
        
    except Exception as e:
        print("\n--- TEST FAILED ---")
        print(f"Error: {e}")
        print("\nTroubleshooting Tips:")
        print(f"1. Is LM Studio running?")
        print(f"2. Is the Local Server started in LM Studio on port {base_url.split(':')[-1].split('/')[0]}?")
        print(f"3. Is the model '{model_name}' loaded in LM Studio?")
        print(f"4. Check LM Studio's console for any incoming request errors.")

if __name__ == "__main__":
    test_lmstudio_gemma()
