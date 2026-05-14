
from crewai import Agent, Task, Crew
from crewai.tools import tool

@tool("my_tool")
def my_tool_func(param: str) -> str:
    """A test tool."""
    return f"Tool result: {param}"

try:
    agent = Agent(
        role="Tester",
        goal="Test tools",
        backstory="Testing",
        tools=[my_tool_func]
    )
    print("Agent initialized with crewai tool successfully")
except Exception as e:
    print(f"Error: {e}")
