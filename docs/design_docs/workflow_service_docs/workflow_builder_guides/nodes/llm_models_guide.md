# LLM Models & Internal Tools Guide

This guide provides a comprehensive overview of supported LLM providers, their models, capabilities, and internal tools available in the workflow service.

## Table of Contents

1. [Quick Model Comparison](#quick-model-comparison)
2. [Provider Details](#provider-details)
   - [OpenAI](#openai)
   - [Anthropic](#anthropic)
   - [Perplexity](#perplexity)
   - [Google Gemini](#google-gemini)
   - [Fireworks](#fireworks)
   - [AWS Bedrock](#aws-bedrock)
3. [Internal Tools Overview](#internal-tools-overview)
4. [Configuration Examples](#configuration-examples)

## Quick Model Comparison

### Core Capabilities Matrix

| Provider | Model | Reasoning | Web Search | Code Interpreter | Tool Use | Multimodal | Context Limit | Output Tokens |
|----------|-------|-----------|------------|------------------|----------|------------|---------------|---------------|
| **OpenAI** | gpt-5 | ✅ | ✅ | ✅ | ✅ | ✅ | 400k | 128k |
| | gpt-5-mini | ✅ | ✅ | ✅ | ✅ | ✅ | 400k | 128k |
| | gpt-5-nano | ✅ | ❌ | ✅ | ✅ | ✅ | 400k | 128k |
| **OpenAI** | o4-mini | ✅ | ✅ | ✅ | ✅ | ✅ | 200k | 100k |
| | o4-mini-deep-research | ✅ | ⚠️ | ⚠️ | ✅ | ✅ | 200k | 100k |
| | o3-deep-research | ✅ | ⚠️ | ⚠️ | ✅ | ✅ | 200k | 100k |
| | o3-mini | ✅ | ✅ | ✅ | ✅ | ❌ | 200k | 100k |
| | o3 | ✅ | ✅ | ✅ | ✅ | ✅ | 200k | 100k |
| | o3-pro | ✅ | ✅ | ✅ | ✅ | ✅ | 200k | 100k |
| | gpt-4.1 | ❌ | ✅ | ✅ | ✅ | ✅ | 1M | 16k |
| | gpt-4o | ❌ | ✅ | ✅ | ✅ | ✅ | 128k | 16k |
| | chatgpt-4o-latest | ❌ | ❌ | ❌ | ❌ | ✅ | 128k | 16k |
| | gpt-4.1-mini | ❌ | ✅ | ✅ | ✅ | ✅ | 1M | 16k |
| | gpt-4o-mini | ❌ | ✅ | ✅ | ✅ | ✅ | 128k | 16k |
| | gpt-4.1-nano | ❌ | ❌ | ✅ | ✅ | ✅ | 1M | 16k |
| | gpt-4o-search-preview | ❌ | ✅ | ✅ | ✅ | ✅ | 128k | 16k |
| | gpt-4o-mini-search-preview | ❌ | ✅ | ✅ | ✅ | ✅ | 128k | 16k |
| **Anthropic** | claude-opus-4-20250514 | ✅ | ✅ | ✅ | ✅ | ✅ | 200k | 32k |
| | claude-sonnet-4-20250514 | ✅ | ✅ | ✅ | ✅ | ✅ | 200k | 64k |
| | claude-3-7-sonnet-20250219 | ✅ | ✅ | ✅ | ✅ | ✅ | 200k | 64k |
| | claude-3-5-sonnet-latest | ❌ | ✅ | ❌ | ✅ | ✅ | 200k | 8k |
| | claude-3-5-haiku-latest | ❌ | ✅ | ✅ | ✅ | ✅ | 200k | 8k |
| **Perplexity** | sonar-deep-research | ✅ | ✅ | ❌ | ❌ | ❌ | 128k | 16k |
| | sonar-reasoning-pro | ✅ | ✅ | ❌ | ❌ | ❌ | 128k | 8k |
| | sonar-reasoning | ✅ | ✅ | ❌ | ❌ | ❌ | 128k | 8k |
| | sonar-pro | ❌ | ✅ | ❌ | ❌ | ❌ | 128k | 8k |
| | sonar | ❌ | ✅ | ❌ | ❌ | ❌ | 127k | 127k |
| | r1-1776 | ✅ | ❌ | ❌ | ❌ | ❌ | 128k | 16k |
| **Gemini** | gemini-2.5-pro-preview-05-06 | ✅ | ❌ | ❌ | ✅ | ✅ | 1M | 65k |
| | gemini-2.5-flash-preview-05-20 | ❌ | ❌ | ❌ | ✅ | ✅ | 1M | 8k |
| | gemini-2.0-flash-thinking-exp-01-21 | ✅ | ❌ | ❌ | ✅ | ✅ | 1M | 8k |
| | gemini-2.0-flash-lite | ❌ | ❌ | ❌ | ❌ | ❌ | 1M | 8k |
| **Fireworks** | accounts/fireworks/models/deepseek-r1 | ✅ | ❌ | ❌ | ❌ | ❌ | 128k | 100k |
| | accounts/fireworks/models/deepseek-r1-basic | ✅ | ❌ | ❌ | ❌ | ❌ | 128k | 100k |
| **AWS Bedrock** | us.deepseek.r1-v1:0 | ✅ | ❌ | ❌ | ❌ | ❌ | 128k | 4k |

**Legend:**
- ✅ = Fully supported
- ⚠️ = Requires manual configuration (see Deep Research Models section)
- ❌ = Not supported

**Notes:**
- All OpenAI models support both code interpreter and web search tools, except:
  - `chatgpt-4o-latest`: No tool support (conversational use only)
  - `gpt-4.1-nano`: Code interpreter only (web search tools excluded)
- Deep Research models require tools to be manually configured to function properly

### Rate Limits Overview

| Provider | Model | Requests/min | Tokens/min | Special Limits |
|----------|-------|--------------|------------|----------------|
| **OpenAI** | gpt-5 | 15,000 | 40M | - |
| | gpt-5-mini | 30,000 | 180M | - |
| | gpt-5-nano | 30,000 | 180M | - |
| **OpenAI** | o4-mini | 30,000 | 150M | - |
| | o4-mini-deep-research | 30,000 | 150M | - |
| | o3-deep-research | 10,000 | 30M | - |
| | o3-mini | 30,000 | 150M | - |
| | o3 | 10,000 | 30M | - |
| | o3-pro | 10,000 | 30M | - |
| | gpt-4.1 | 10,000 | 30M | - |
| | gpt-4o | 10,000 | 30M | - |
| | chatgpt-4o-latest | 10,000 | 30M | - |
| | gpt-4.1-mini | 30,000 | 150M | - |
| | gpt-4o-mini | 30,000 | 150M | - |
| | gpt-4.1-nano | 30,000 | 150M | - |
| | gpt-4o-search-preview | 1,000 | 3M | - |
| | gpt-4o-mini-search-preview | 30,000 | 150M | - |
| **Anthropic** | claude-opus-4-20250514 | No limit | 1M input/400k output | - |
| | claude-sonnet-4-20250514 | No limit | 1M input/400k output | - |
| | claude-3-7-sonnet-20250219 | No limit | 1M input/400k output | - |
| **Perplexity** | sonar-deep-research | 5 | - | - |
| | sonar-reasoning-pro | 50 | - | - |
| | sonar-reasoning | 50 | - | - |
| | sonar-pro | 50 | - | - |
| | sonar | 50 | - | - |
| | r1-1776 | 50 | - | - |
| **Gemini** | gemini-2.5-pro-preview-05-06 | 20 | 2M | 100/day |
| | gemini-2.5-flash-preview-05-20 | 2,000 | 4M | - |
| | gemini-2.0-flash-thinking-exp-01-21 | 10 | 4M | - |
| | gemini-2.0-flash-lite | 4,000 | 4M | - |
| **Fireworks** | accounts/fireworks/models/deepseek-r1 | 100 | 100k | Auto-scaling |
| | accounts/fireworks/models/deepseek-r1-basic | 100 | 100k | Auto-scaling |
| **AWS Bedrock** | us.deepseek.r1-v1:0 | 20 | 20k | - |

## Deep Research Models

OpenAI's Deep Research models (`o4-mini-deep-research` and `o3-deep-research`) are specialized for research tasks and have unique configuration requirements:

### Key Characteristics:
- **Autonomous Research**: Designed to autonomously conduct research by using tools like web search and code execution
- **No Direct Reasoning Controls**: Unlike other reasoning models, you cannot configure `reasoning_effort_class`, `reasoning_effort_number`, or `reasoning_tokens_budget`
- **Tool-Driven**: Rely on external tools (web search, code interpreter) to perform research tasks
- **Cost Control**: Use `max_tool_calls` parameter to control costs instead of reasoning token budgets (this parameter is currently only supported for Deep Research models)

### Required Configuration:

**1. Web Search Tool (Required)**
Deep Research models must have web search capability configured to function properly:

```json
{
  "tools": [
    {
      "tool_name": "web_search",
      "is_provider_inbuilt_tool": true,
      "provider_inbuilt_user_config": {
        "search_context_size": "high",
        "user_location": {
          "type": "approximate",
          "approximate": {
            "country": "US",
            "city": "San Francisco",
            "region": "CA"
          }
        }
      }
    }
  ]
}
```

**2. Code Interpreter (Optional but Recommended)**
For data analysis and computational tasks:

```json
{
  "tools": [
    {
      "tool_name": "code_interpreter",
      "is_provider_inbuilt_tool": true,
      "provider_inbuilt_user_config": {
        "container": { "type": "auto" }
      }
    }
  ]
}
```

**3. Cost Control via max_tool_calls**
Deep Research models support `max_tool_calls` to control costs (this parameter is only available for these models):

```json
{
  "llm_config": {
    "max_tool_calls": 10,
    "model_spec": {
      "provider": "openai",
      "model": "o4-mini-deep-research"
    }
  }
}
```

### Example Configuration:

```json
{
  "node_config": {
    "llm_config": {
      "model_spec": {
        "provider": "openai",
        "model": "o4-mini-deep-research"
      },
      "temperature": 0.7,
      "max_tokens": 4096,
      "max_tool_calls": 15
    },
    "tool_calling_config": {
      "enable_tool_calling": true,
      "parallel_tool_calls": true
    },
    "tools": [
      {
        "tool_name": "web_search",
        "is_provider_inbuilt_tool": true,
        "provider_inbuilt_user_config": {
          "search_context_size": "high"
        }
      },
      {
        "tool_name": "code_interpreter",
        "is_provider_inbuilt_tool": true,
        "provider_inbuilt_user_config": {
          "container": { "type": "auto" }
        }
      }
    ]
  }
}
```

## Provider Details

### OpenAI

OpenAI provides the most comprehensive set of models with strong reasoning capabilities, code interpretation, and tool use.

#### Available Models
**GPT-5 Series:**
- `gpt-5` - Next-gen reasoning model with multimodal support and optional verbosity control
- `gpt-5-mini` - Smaller, cost-efficient tier (1/5th price of gpt-5)
- `gpt-5-nano` - Ultra-efficient tier (1/25th price of gpt-5); web search tool not supported


**Reasoning Models:**
- `o4-mini` - Enhanced reasoning with multimodal support
- `o3-mini` - Compact reasoning model
- `o3` - Full reasoning model with multimodal capabilities
- `o3-pro` - Professional reasoning model with multimodal capabilities

**Deep Research Models:**
- `o4-mini-deep-research` - Autonomous research with tool use (requires web search + optional code interpreter)
- `o3-deep-research` - Advanced research capabilities with tool use (requires web search + optional code interpreter)

**Standard Models:**
- `gpt-4o` - Latest GPT-4 with optimized performance
- `gpt-4o-mini` - Smaller, faster version
- `chatgpt-4o-latest` - Conversational model optimized for chat (no tool support)
- `gpt-4.1` - Extended context version (1M tokens)
- `gpt-4.1-mini` - Balanced performance and extended context
- `gpt-4.1-nano` - Lightweight option with extended context (no web search)

**Web Search Models:**
- `gpt-4o-search-preview` - GPT-4o with built-in web search capabilities
- `gpt-4o-mini-search-preview` - Smaller version with built-in web search

#### Internal Tools

**1. Web Search (`web_search`)**
- Real-time web search integration
- Configurable search context size
- User location support for localized results
- Available on all OpenAI models except `chatgpt-4o-latest` and `gpt-4.1-nano`

**2. Code Interpreter (`code_interpreter`)**
- Sandboxed Python execution environment
- Data analysis and visualization capabilities
- Iterative code development and debugging
- File processing and manipulation
- Available on all OpenAI models except `chatgpt-4o-latest`

#### Configuration Example

```json
{
  "node_config": {
    "llm_config": {
      "model_spec": {
        "provider": "openai",
        "model": "gpt-5"
      },
      "temperature": 0.7,
      "max_tokens": 4096,
      "verbosity": "low"
    },
    "tool_calling_config": {
      "enable_tool_calling": true,
      "parallel_tool_calls": true
    },
    "tools": [
      {
        "tool_name": "web_search",
        "is_provider_inbuilt_tool": true,
        "provider_inbuilt_user_config": {
          "search_context_size": "medium",
          "user_location": {
            "type": "approximate",
            "approximate": {
              "country": "US",
              "city": "San Francisco",
              "region": "CA"
            }
          }
        }
      },
      {
        "tool_name": "code_interpreter",
        "is_provider_inbuilt_tool": true,
        "provider_inbuilt_user_config": {
          "container": { "type": "auto" }
        }
      }
    ]
  }
}
```

#### Pricing (per 1M tokens)

- `gpt-5`: input $1.25, output $10.00
- `gpt-5-mini`: input $0.25, output $2.00 (1/5th of gpt-5)
- `gpt-5-nano`: input $0.05, output $0.40 (1/5th of mini)

All GPT-5 series models support an extra `reasoning_effort` value: `"minimal"` (in addition to standard OpenAI values), and a `verbosity` parameter `"low" | "medium" | "high"` (exposed in `llm_config.verbosity`). If omitted (`null`), the provider default of `"medium"` is used.

### Anthropic

Anthropic's Claude models excel at reasoning, analysis, and have built-in web search capabilities.

#### Available Models

**Reasoning Models:**
- `claude-opus-4-20250514` - Highest capability model with extended thinking
- `claude-sonnet-4-20250514` - Balanced performance with reasoning  
- `claude-3-7-sonnet-20250219` - Strong reasoning capabilities

**Standard Models:**
- `claude-3-5-sonnet-latest` - Latest Sonnet model with continuous updates
- `claude-3-5-haiku-latest` - Fast, efficient model for lighter workloads

#### Internal Tools

**1. Web Search (`web_search`)**
- Comprehensive web search with citation support
- Domain filtering (allowed/blocked lists)
- Usage limits and localization
- Available on: All Anthropic models

**2. Code Execution (`code_execution`)**
- Secure Python code execution in sandboxed environment
- Data analysis and visualization capabilities
- File processing and computational tasks
- Available on: Claude Opus 4, Claude Sonnet 4, Claude 3.7 Sonnet, Claude 3.5 Haiku

#### Configuration Example

```json
{
  "node_config": {
    "llm_config": {
      "model_spec": {
        "provider": "anthropic",
        "model": "claude-3-7-sonnet"
      },
      "temperature": 0.8,
      "max_tokens": 8192,
      "reasoning_tokens_budget": 2048,
      "thinking_tokens_in_prompt": "latest_message"
    },
    "tool_calling_config": {
      "enable_tool_calling": true
    },
    "tools": [
      {
        "tool_name": "web_search",
        "is_provider_inbuilt_tool": true,
        "provider_inbuilt_user_config": {
          "max_uses": 5,
          "allowed_domains": ["wikipedia.org", "arxiv.org"],
          "user_location": {
            "type": "approximate",
            "city": "New York",
            "region": "NY",
            "country": "US"
          }
        }
      },
      {
        "tool_name": "code_execution",
        "is_provider_inbuilt_tool": true,
        "provider_inbuilt_user_config": null
      }
    ]
  }
}
```

### Perplexity

Perplexity specializes in web search and research with built-in real-time information access.

#### Available Models

**Research Models:**
- `sonar-deep-research` - Deep research with reasoning (5 req/min limit)
- `sonar-reasoning-pro` - Professional reasoning with search
- `sonar-reasoning` - Standard reasoning with search

**Search Models:**
- `sonar-pro` - Professional search capabilities
- `sonar` - Standard search model (large context window)

**Offline Models:**
- `r1-1776` - Reasoning without web search

#### Web Search Configuration

```json
{
  "node_config": {
    "llm_config": {
      "model_spec": {
        "provider": "perplexity",
        "model": "sonar-reasoning-pro"
      },
      "temperature": 0.6,
      "max_tokens": 8000
    },
    "web_search_options": {
      "search_recency_filter": "week",
      "search_domain_filter": ["academic.com", "research.org"],
      "search_context_size": "high"
    }
  }
}
```

### Google Gemini

Google's Gemini models offer large context windows and multimodal capabilities.

#### Available Models

**Advanced Models:**
- `gemini-2.5-pro-preview-05-06` - Enhanced reasoning and multimodal
- `gemini-2.5-flash-preview-05-20` - Fast processing with multimodal
- `gemini-2.0-flash-thinking-exp-01-21` - Experimental reasoning mode

**Lightweight Models:**
- `gemini-2.0-flash-lite` - Cost-efficient option (no tool use)

#### Configuration Example

```json
{
  "node_config": {
    "llm_config": {
      "model_spec": {
        "provider": "google_vertexai",
        "model": "gemini-2.5-pro"
      },
      "temperature": 0.7,
      "max_tokens": 8192
    },
    "tool_calling_config": {
      "enable_tool_calling": true
    }
  }
}
```

### Fireworks

Fireworks provides access to reasoning models with flexible scaling.

#### Available Models

- `accounts/fireworks/models/deepseek-r1` - Fast reasoning model
- `accounts/fireworks/models/deepseek-r1-basic` - Basic reasoning capabilities

#### Configuration Example

```json
{
  "node_config": {
    "llm_config": {
      "model_spec": {
        "provider": "fireworks",
        "model": "deepseek-r1"
      },
      "temperature": 0.8,
      "max_tokens": 4096,
      "reasoning_effort_class": "high",
      "reasoning_effort_number": 1000
    }
  }
}
```

### AWS Bedrock

AWS Bedrock provides enterprise-grade access to reasoning models.

#### Available Models

- `us.deepseek.r1-v1:0` - Reasoning model via AWS infrastructure

#### Configuration Example

```json
{
  "node_config": {
    "llm_config": {
      "model_spec": {
        "provider": "bedrock_converse",
        "model": "us.deepseek.r1-v1:0"
      },
      "temperature": 0.9,
      "max_tokens": 4096
    }
  }
}
```

## Internal Tools Overview

### OpenAI Tools

#### Web Search Preview
- **Purpose**: Real-time web search integration
- **Configuration**: Search context size, user location
- **Best for**: Current information, localized results

#### Code Interpreter
- **Purpose**: Python code execution and analysis
- **Configuration**: Container management (auto/custom)
- **Best for**: Data analysis, calculations, visualizations

### Anthropic Tools

#### Web Search
- **Purpose**: Research and information retrieval
- **Configuration**: Domain filtering, usage limits, localization
- **Best for**: Academic research, filtered searches

## Configuration Examples

### Basic Text Generation

```json
{
  "nodes": {
    "text_generator": {
      "node_id": "text_generator",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": {
            "provider": "openai",
            "model": "gpt-4o"
          },
          "temperature": 0.7,
          "max_tokens": 1024
        }
      }
    }
  }
}
```

### Structured Output with Reasoning

```json
{
  "nodes": {
    "data_extractor": {
      "node_id": "data_extractor",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": {
            "provider": "anthropic",
            "model": "claude-3-7-sonnet"
          },
          "temperature": 0.1,
          "max_tokens": 4096,
          "reasoning_tokens_budget": 1024
        },
        "output_schema": {
          "dynamic_schema_spec": {
            "schema_name": "ExtractedData",
            "fields": {
              "summary": {"type": "str", "required": true},
              "key_points": {"type": "list", "items_type": "str", "required": true},
              "confidence": {"type": "float", "required": true}
            }
          }
        }
      }
    }
  }
}
```

### Research with Web Search

```json
{
  "nodes": {
    "researcher": {
      "node_id": "researcher",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": {
            "provider": "perplexity",
            "model": "sonar-reasoning-pro"
          },
          "temperature": 0.5,
          "max_tokens": 8000
        },
        "web_search_options": {
          "search_recency_filter": "month",
          "search_context_size": "high",
          "search_domain_filter": ["arxiv.org", "nature.com"]
        }
      }
    }
  }
}
```

### Code Analysis and Execution

```json
{
  "nodes": {
    "code_analyst": {
      "node_id": "code_analyst",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": {
            "provider": "openai",
            "model": "gpt-4o"
          },
          "temperature": 0.3,
          "max_tokens": 4096
        },
        "tool_calling_config": {
          "enable_tool_calling": true
        },
        "tools": [
          {
            "tool_name": "code_interpreter",
            "is_provider_inbuilt_tool": true,
            "provider_inbuilt_user_config": {
              "container": {"type": "auto"}
            }
          }
        ]
      }
    }
  }
}
```

## Best Practices

### Model Selection Guidelines

1. **For Reasoning Tasks**: Use OpenAI O-series, Anthropic Claude with reasoning, or Perplexity reasoning models
2. **For Web Research**: Perplexity models or OpenAI/Anthropic with web search tools
3. **For Code Tasks**: OpenAI models with code interpreter
4. **For Cost Efficiency**: Mini/lite variants of models
5. **For Large Context**: Gemini models (1M+ tokens)

### Performance Optimization

1. **Temperature Settings**:
   - 0.1-0.3 for factual/analytical tasks
   - 0.5-0.7 for balanced creativity
   - 0.8-1.0 for creative tasks

2. **Token Management**:
   - Set appropriate `max_tokens` based on expected output length
   - Monitor token usage via metadata

3. **Tool Configuration**:
   - Enable tools only when needed
   - Configure tool-specific parameters appropriately
   - Use parallel tool calls when supported

### Error Handling

- Always check `finish_reason` in metadata
- Handle rate limits gracefully
- Implement fallback strategies for model unavailability
- Monitor token usage to avoid exceeding limits

For detailed configuration options and schemas, refer to the [LLM Node Guide](llm_node_guide.md).
