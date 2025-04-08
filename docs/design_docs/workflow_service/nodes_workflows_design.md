
# Prompt constructor node!
## Dict Any -> take all prompt template vars and construct prompt based on config!
can construct multiple prompts!

input_format -> field_name => replace all fields named field_name across all prompt templates
input_format -> prompt_name[DELIMITER]field_name => replace all fields named field_name for prompt_name

(same config format, use can provide any number of key: values! it just needs to be serializable) 

config -> Dict[str: Any!]

Input Dynamic Schema -> aggregate all input edge into dynamic schema object
then do model_dump to get a JSON dict input!

Config Dynamic Schema (sent from)

prompt_templates = Dict [str: str]
prompt_var_overwrites = Dict [str: str]
(str format can be as above to replace global prompt vars in all templates or specific template!)

The output schema is also dynamic; node checks output model fields dynamically created and only fills those in output dict!
This way, output prompts can directly be routed to the llm node!


# LLM Node

## Central state

input
    - prompts [Optional] Dict[str, str] either oncstructed from prompt constructor, or set in config with simple text! checked in dict which prompt / user prompt template is provided! have prompt keys in constants!
    - system_prompt
    - user_prompt  # (can be user prompt or feedback both) allowing it to be user message implies it can be image, pdf (for anthropic), anything
    - messages_history (from central state)  # Is checked and if None, only then system prompt is used; otherwise assumed system prompt already used and this is a followup!
    - tool_outputs: List[Dict (tool_call_id -- not node ID) Any] Optional 
    NOTE: if none of user prompt or tool_output is provided, the LLM is just called with the system prompt template with a warning??!!

output
    - messages (to central state)
    - last state?
    - tool calls? route choice??
    - LLM info -> token use, etc!



- bind tools!


- llm configs
    - reasoning efforts
prompt_configs
    - user prompt template [Optional]
    - system prompt
        [form to fill in some vars in config, they become optional in inputs, but still may be overwritten!]
    - enable_empty_user_prompt = False!
Output config
    - text or JSON
    - JSON: either defined as dynamic schema, or hardcoded in class / subclass or fetched from schema registry!
    NOTE: as subclass may affix a schema and hide the dynamic parts to only work with fixed schemas! This can be common pattern for specialized, opinionated templates / subclasses, including for prompts (atleast defaults)!
tool_configs
    - must include tool name/version[optional] ofcourse!
    - NOTE: tools should be separately configured, by default on UI, 
        by default, only all input fields are filled by LLM
        user can do the following:
            - mark certain config fields to be filled by LLM (and also provide default values there)
            - unmark certain INput fields to not be filled by LLM while providing default / user provided values there
        - LLMs will try to fill whatever fields were marked as such for LLM filling via tool call spec

NOTE: IMPORTANT: the tool node input schema will have to be super descriptive (as shown in anthropic / fireworks doc!).

A tool can accept input data from central state or 
we can simulate adding fields to input data manually by adding to central state and edge from central state to tool!
Config -> all fields will be set by default template or overridden by user
TO create a tool node with config which can be fullfilled via the LLM, create a new tool node which has those config fields set as input with defaults!
LLM tool call -> it will only work with the tool's input schema!

tool call output from LLM node must be a List / dict (with function call IDs) to support parallel functions!
A tool node goes through all calls



TODO: dedicated node which takes config for all tools callable set and executes nodes in tool mode by calling process directly, also takes input from central state, itself calls the tools and reverts to LLM + output tool output to central state!
Any node can be run as tool, including later complex nodes which call subgraphs!
directly takes all tool calls from LLM nodes to call tools! If not tool calls, simply stops!




tool output
    - tool output schema is fixed and the LLM node must accept it as Optional input! maybe generally, it can accept any tool input(s) via `tool_inputs = Optional[Dict[str, Any]]`

# TOOL NODE adding to graph!

THe tool caller has a special field in its config -> all tools!
Those are instantiatiated and added during compile time to langgraph in process(input) format mode rather than run(...) mode with proper edges (virtual annotations) from tool node to these tool nodes!
Tool caller is handled specially thus and adds virtual nodes to the lang graph automatically!
This will be great for langgraph tracing!!! all tool nodes process/ calls will be handled transparently
also edges to and from tool node exist to process tool output, etc!



# Tool use

## Basic Tool Registry

Can router node pass on data?? YES!

## Tool execution routing
Fan-in back into node after parallel tool executions

# LLM Ops

## rate limiting and token billing!
- Add model rate limiting code based on net rate limits imposed by model providers on us and per user rate limiting from our side!
- Token billing, input token estimations etc!

https://github.com/AgentOps-AI/tokencost


## Prompt construction and context windows!

## Model / provider level configs -> costs, rate limits, context windows, output limits, etc!



# Global Var ovewrites for all LLM nodes!
[!] Else: just have copy button to copy on all LLM nodes in workflow any prompt var if name is same!

[X] Global configs in central state
Eg pass on specific prompt config var to all LLM nodes in workflow!



# TODO: 
Simulate node
How will all required inputs flow in

How will tools be dynamically configured!

# Router
Specify Edge name or ROUTE Name -> hence can call an edge `default` and refer to it! Useful for default router if/else cases!
