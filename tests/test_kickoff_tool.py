
from crewai import Agent, Task, Crew, LLM
from crewai.tools import tool
import os

@tool("my_tool")
def my_tool_func(param: str) -> str:
    """A test tool."""
    return f"Tool result: {param}"

api_key = os.getenv("GROQ_API_KEY")
llm = LLM(model="groq/llama-3.1-8b-instant", api_key=api_key)

agent = Agent(
    role="Tester",
    goal="Test tools",
    backstory="Testing",
    tools=[my_tool_func],
    llm=llm
)

task = Task(
    description="Just say hello and use the tool with 'hello'.",
    expected_output="Output",
    agent=agent
)

crew = Crew(agents=[agent], tasks=[task])

try:
    print("Testing crew kickoff with crewai tool...")
    res = crew.kickoff()
    print(f"Kickoff success: {res}")
except Exception as e:
    print(f"Error: {e}")
