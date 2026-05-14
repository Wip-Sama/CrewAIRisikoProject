
from crewai import Agent
from crewai.tools import tool

def create_tools(prefix: str):
    @tool(f"{prefix}_tool")
    def my_tool(param: str) -> str:
        """A test tool with prefix."""
        return f"{prefix}: {param}"
    return [my_tool]

try:
    tools = create_tools("game")
    agent = Agent(
        role="Tester",
        goal="Test tools",
        backstory="Testing",
        tools=tools
    )
    print(f"Agent initialized with tool: {agent.tools[0].name}")
except Exception as e:
    print(f"Error: {e}")
