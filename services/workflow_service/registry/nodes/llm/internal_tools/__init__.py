from workflow_service.registry.nodes.llm.internal_tools.openai_tools import OpenAIWebSearchTool
from workflow_service.registry.nodes.llm.internal_tools.anthropic_tools import AnthropicWebSearchTool

OPENAI_TOOLS = [OpenAIWebSearchTool]
ANTHROPIC_TOOLS = [AnthropicWebSearchTool]
OPENAI_TOOLS_REGISTRY = {}
ANTHROPIC_TOOLS_REGISTRY = {}

for tool_list, tool_list_registry in [(OPENAI_TOOLS, OPENAI_TOOLS_REGISTRY), (ANTHROPIC_TOOLS, ANTHROPIC_TOOLS_REGISTRY)]:
    for i, tool in enumerate(tool_list):
        json_schema = tool.get_tool_json_schema()
        tool_list[i] = {
            "name": json_schema["name"],
            "json_schema": json_schema,
            "tool_class": tool,
            "description": tool.__doc__,
        }
        if tool_list[i]["name"] in tool_list_registry:
            raise ValueError(f"Tool name {tool_list[i]['name']} already exists in {tool_list_registry.keys()}")
        tool_list_registry[tool_list[i]["name"]] = tool_list[i]

__all__ = ["OPENAI_TOOLS_REGISTRY", "ANTHROPIC_TOOLS_REGISTRY"]
