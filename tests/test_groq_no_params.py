
from crewai import Agent, Task, Crew, LLM
from crewai.tools import tool
import os

@tool("get_state_tool")
def get_state_tool(reason: str) -> str:
    """Returns the current game state. Provide a reason for this request."""
    return "{}"

api_key = os.getenv("GROQ_API_KEY")
llm = LLM(model="groq/llama-3.1-8b-instant", api_key=api_key)

agent = Agent(
    role="Tester",
    goal="Test tool with no params",
    backstory="Testing",
    tools=[get_state_tool],
    llm=llm
)

task = Task(
    description="Use the get_state_tool.",
    expected_output="Output",
    agent=agent
)

crew = Crew(agents=[agent], tasks=[task])

try:
    print("Testing crew kickoff with no-param tool on Groq...")
    res = crew.kickoff()
    print(f"Kickoff success: {res}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
