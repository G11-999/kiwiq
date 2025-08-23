from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.perplexity.ai"
)

stream = client.chat.completions.create(
    model="sonar-pro",
    messages=[
        {"role": "user", "content": "Compare renewable energy technologies"}
    ],
    stream=True
)

content = ""
search_results = []
usage_info = None

for chunk in stream:
    # Content arrives progressively
    if chunk.choices[0].delta.content is not None:
        content_chunk = chunk.choices[0].delta.content
        content += content_chunk
        print(content_chunk, end="")
    
    # Metadata arrives in final chunks
    if hasattr(chunk, 'search_results') and chunk.search_results:
                search_results = chunk.search_results
    
    if hasattr(chunk, 'usage') and chunk.usage:
        usage_info = chunk.usage
    
    # Handle completion
    if chunk.choices[0].finish_reason is not None:
        print(f"\n\nFinish reason: {chunk.choices[0].finish_reason}")
        print(f"Search Results: {search_results}")
        print(f"Usage: {usage_info}")

import ipdb; ipdb.set_trace()
