# CLAUDE.md - AI Assistant Best Practices & Knowledge Base

## 🤖 Self-Maintenance Instructions
**IMPORTANT:** As an AI assistant working on this codebase, you should:
1. **Update this file** whenever you learn something new about the project
2. **Check this file first** when starting a new session for important context
3. **Add new sections** as needed to capture project-specific knowledge
4. **Document patterns** that work well or common pitfalls to avoid

---

## 📁 Project Overview
- **Project Type**: KiwiQ Standalone Client - Workflow Management System
- **Primary Language**: Python
- **Key Framework**: Workflow orchestration with HITL (Human-in-the-Loop) support
- **Testing**: Uses `poetry run python` for execution

---

## 🏗️ Project Structure

```
standalone_client/
├── kiwi_client/
│   ├── workflows/                 # Main workflows
│   │   ├── wf_*.py               # Individual workflow definitions
│   │   └── document_models/      # Document model definitions
│   ├── workflows_for_blog_teammate/  # Blog-specific workflows
│   │   ├── wf_*.py               # Blog workflow definitions
│   │   └── llm_inputs/           # LLM prompt templates
│   └── test_run_workflow_client.py  # Main testing utilities
├── scripts/                       # Utility scripts
├── pyproject.toml                # Poetry configuration
└── poetry.lock                   # Dependency lock file
```

---

## ⚡ Critical Workflow Rules & New Features

### ✅ Dot Notation Now Fully Supported! (MAJOR UPDATE)
- **NEW**: Full dot notation support in edge mappings for nested data access
- **Use extensively**: Access nested objects, arrays, and complex API responses directly
- **Examples**:
  ```python
  # ✅ NOW CORRECT - Dot notation fully supported:
  {"src_field": "linkedin_response.profile.experience.0.company.name", "dst_field": "lead_info.current_company"}
  {"src_field": "api_data.results.0.metadata.score", "dst_field": "analysis.quality_score"} 
  {"src_field": "user_profile.contact.personal.email", "dst_field": "notification_data.email"}
  ```
- **Benefits**: Eliminates need for many transform_data nodes, direct API response processing

### Node-Level Edge Declaration (NEW FEATURE)
- **Option 1**: Global edges list (traditional)
- **Option 2**: Declare edges within node configurations using `"edges": [...]` field
- **Don't mix**: Use either global or node-level, not both for the same node
- **Benefits**: Better organization for nodes with many outgoing connections

### Data-Only Edges (ADVANCED OPTIMIZATION)
- **Purpose**: Pass large data efficiently without affecting execution flow
- **Usage**: Add `"data_only_edge": true` to edge definition  
- **Benefits**: Memory optimization, direct data reuse, reduced central state storage
- **Use cases**: Large datasets (>10MB), non-consecutive data flow, API responses

### Runtime Configuration & Database Pool Tiers (NEW)
- **Purpose**: Optimize database connection pooling based on workflow intensity
- **Tiers**: `"small"` (default), `"medium"`, `"large"`
- **Usage**: Add to GraphSchema root level
  ```json
  {
    "runtime_config": {
      "db_concurrent_pool_tier": "medium"  // For moderate DB operations
    }
  }
  ```
- **Guidelines**: 
  - `"small"`: Simple workflows, development, minimal DB usage
  - `"medium"`: Moderate parallel operations, 10-25 concurrent DB ops
  - `"large"`: Heavy parallel processing, 25+ concurrent operations, data-intensive

### Private Mode Passthrough Data (ADVANCED)
- **Purpose**: Preserve context data through parallel processing branches
- **Key Configuration**: `"private_output_passthrough_data_to_central_state_keys": ["id", "name"]`
- **Critical Insight**: Preserves data from node's **INPUT** state, not output
- **Use Cases**: Item tracking through MapListRouter processing, metadata preservation
- **Supports**: Dot notation for nested path mappings

---

## 🔧 Common Commands & Patterns

### Running Workflows
```bash
# Run a workflow file directly
poetry run python kiwi_client/workflows/{workflow_file}.py

# Run with specific Python path
poetry run python -c "from kiwi_client.workflows.{module} import {function}; {function}()"
```

### Testing Workflows with HITL
- Workflows can have predefined HITL inputs in the main test function
- Look for `predefined_hitl_inputs` list in the workflow's main function
- Format: List of dictionaries with expected input fields

---

## 📝 Workflow Implementation Patterns

### Modern Data Flow Patterns (UPDATED)

#### Direct API Response Processing (NEW - Replaces Transform Nodes)
```json
// ✅ NEW: Extract nested API data directly with dot notation
{
  "src_node_id": "linkedin_scraper",
  "dst_node_id": "analysis_node",
  "mappings": [
    {"src_field": "scraping_results.profiles.0.basic_info.name", "dst_field": "analysis_input.lead_name"},
    {"src_field": "scraping_results.profiles.0.experience.0.company.name", "dst_field": "analysis_input.current_company"},
    {"src_field": "scraping_results.profiles.0.skills", "dst_field": "analysis_input.technical_skills"}
  ]
}
```

#### Organized Central State Pattern (NEW)
```json
// ✅ Use nested paths for organized central state management
{"src_field": "quality_score", "dst_field": "lead_analysis.quality.score"},
{"src_field": "confidence_level", "dst_field": "lead_analysis.quality.confidence"},
{"src_field": "processing_time", "dst_field": "workflow_metrics.timing.analysis_duration"}
```

#### Data-Only Edge Pattern (NEW - Memory Optimization)
```json
// ✅ Pass large datasets efficiently without execution flow impact
{
  "src_node_id": "load_large_dataset",
  "dst_node_id": "deep_analysis",
  "data_only_edge": true,
  "mappings": [{"src_field": "customer_profiles", "dst_field": "analysis_data"}]
}
```

### Check Iteration Limit Pattern
When implementing iteration limits for HITL feedback loops:

1. **Add MAX_ITERATIONS constant** (typically set to 10)
```python
MAX_ITERATIONS = 10  # Maximum iterations for HITL feedback loops
```

2. **Add check_iteration_limit node** - Now with dot notation access:
```python
"check_iteration_limit": {
    "node_id": "check_iteration_limit",
    "node_name": "if_else_condition",
    "node_config": {
        "tagged_conditions": [{
            "tag": "iteration_limit_check",
            "condition_groups": [{
                "logical_operator": "and",
                "conditions": [{
                    "field": "generation_metadata.iteration_count",  # Dot notation supported
                    "operator": "less_than",
                    "value": MAX_ITERATIONS
                }]
            }],
            "group_logical_operator": "and"
        }],
        "branch_logic_operator": "and"
    }
}
```

3. **Add route_on_limit_check node** to handle routing based on limit
4. **Update routing nodes** to go through check_iteration_limit
5. **Add generation_metadata to state reducer**
6. **Update LLM nodes** to store metadata with iteration counts

### Parallel Processing with Context Preservation (UPDATED)
```json
// ✅ Most common pattern from real workflows
{
  "private_input_mode": true,
  "output_private_output_to_central_state": true,
  "private_output_passthrough_data_to_central_state_keys": ["id", "name"],  // Preserve from INPUT
  "private_output_to_central_state_node_output_key": "output"
}
```

### Edge Declaration Choice (NEW)
- **Node-level**: Use `"edges": [...]` in node config for many outgoing connections
- **Global**: Use traditional `"edges"` list for complex multi-source patterns
- **Consistency**: Pick one style per node, don't mix

### Node Numbering
- Don't focus on updating comment numbers when adding/modifying nodes
- The system doesn't rely on comment numbering for functionality

---

## ⚠️ Common Pitfalls & Solutions

### HITL Testing Issues
- **Problem**: Workflow hangs waiting for HITL input
- **Solution**: Add `predefined_hitl_inputs` in the main test function

### Document Already Exists Errors
- **Problem**: 409/500 errors when initializing documents
- **Solution**: Check if document exists first, handle gracefully

### Long Workflow Execution Times
- **Problem**: Workflows with multiple LLM calls can take 5-10+ minutes
- **Solution**: Be patient, use background execution, set appropriate timeouts

### New Feature-Related Pitfalls (UPDATED)

#### Dot Notation Path Errors
- **Problem**: `src_field` path doesn't exist in source data (e.g., `results.0.title` when results is empty)
- **Solution**: System handles gracefully with warnings, but verify data structure. Consider bounds checking for arrays

#### Edge Declaration Mixing
- **Problem**: Using both node-level `edges` and global `edges` list for same node
- **Solution**: Choose one style per node - either node-level OR global, not both

#### Data-Only Edge Confusion  
- **Problem**: Expecting data-only edges to trigger node execution
- **Solution**: Data-only edges only pass data, use regular edges for execution control

#### Database Pool Tier Mismatching
- **Problem**: Using wrong pool tier causing performance issues or resource waste
- **Solution**: 
  - `"small"`: Simple workflows, development
  - `"medium"`: 10-25 concurrent DB operations
  - `"large"`: 25+ concurrent operations, data-intensive

#### Private Mode Passthrough Misunderstanding
- **Problem**: Expecting passthrough keys from node OUTPUT instead of INPUT
- **Solution**: `private_output_passthrough_data_to_central_state_keys` preserves from INPUT state, not output

---

## 🧪 Testing Best Practices

1. **Always test with predefined HITL inputs** when possible
2. **Use poetry run python** for consistent environment
3. **Check workflow completion status** to verify implementations
4. **Monitor logs** for iteration count tracking

---

## 📊 Key Workflow Components

### Essential Nodes
- `input_node` - Entry point
- `output_node` - Exit point  
- `hitl_node__default` - Human interaction points
- `router_node` - Conditional routing
- `if_else_condition` - Conditional logic
- `llm` - LLM processing nodes

### State Management
- Use `$graph_state` for state persistence
- Define reducers for state fields (replace, add_messages, etc.)
- Track metadata like `generation_metadata` for iteration counting

---

## 🔍 Debugging Tips

1. **Check workflow validation**: Workflows validate schema before execution
2. **Monitor event streams**: Workflows emit events during execution
3. **Review HITL job IDs**: Each HITL pause has a unique job ID
4. **Examine state dumps**: Failed runs save state to data directory

---

## 📚 Recent Learnings

### 2025-09-15: Major Workflow System Upgrade
- **Dot Notation Revolution**: Full support for nested data access in edge mappings
  - Eliminates need for many transform_data nodes
  - Direct API response processing: `api_response.data.results.0.metadata.score`
  - Array access patterns: `user_list.0.profile.name`
- **Data-Only Edges**: Memory optimization for large datasets (>10MB)
  - Pass data without execution flow impact
  - Reduces central state storage requirements
- **Node-Level Edge Declaration**: Better organization with `"edges": [...]` in node config
- **Advanced Database Pool Tiers**: Optimize performance with `runtime_config`
  - Small/Medium/Large tiers for different workflow intensities
- **Private Mode Passthrough Evolution**: Enhanced context preservation through parallel branches
  - Key insight: Preserves from INPUT state, not output
  - Supports complex nested path mappings with dot notation

### 2025-08-07: Iteration Limit Implementation
- Successfully implemented `check_iteration_limit` across 4 workflows
- Pattern involves condition nodes, routing nodes, and metadata tracking
- Prevents infinite HITL loops by limiting to MAX_ITERATIONS (10)
- Now enhanced with dot notation support for condition field access

### Workflow Execution
- Workflows require proper authentication (configure TEST_USER_EMAIL in .env)
- API endpoint: Configure via API_BASE_HOST env var
- Workflows create temporary workflow instances during testing
- HITL inputs must match expected schema exactly
- Runtime config now supports optimized database connection pooling

---

## 🚀 Future Improvements & TODOs

### Completed ✅
- [x] Dot notation support in edge mappings (Sep 2025)
- [x] Node-level edge declaration (Sep 2025)
- [x] Data-only edges for memory optimization (Sep 2025)
- [x] Advanced database pool tiers (Sep 2025)
- [x] Enhanced private mode passthrough data (Sep 2025)

### In Progress 🔄
- [ ] Add automated testing for iteration limit functionality
- [ ] Create workflow templates for common patterns using new dot notation
- [ ] Document all HITL input schemas with dynamic schema support
- [ ] Add performance benchmarks for workflows with new optimization features

### New Opportunities 🆕
- [ ] Create best practice guides for dot notation patterns
- [ ] Develop data-only edge usage guidelines for different data sizes
- [ ] Build automated pool tier recommendation system
- [ ] Create advanced passthrough data pattern library
- [ ] Explore mixed edge type optimization strategies

---

## 📖 Additional Resources

- Workflow documentation: Check individual workflow files for docstrings
- LLM inputs: See `llm_inputs/` directories for prompt templates
- Document models: Review `document_models/` for data structures

---

## 🎯 Key Takeaways for New AI Assistants

1. **Dot Notation is Your Friend**: The old restriction against dot notation is GONE. Use it extensively for direct API response processing and nested data access.

2. **Optimize Memory Usage**: For workflows with large data (>10MB), use data-only edges instead of central state storage.

3. **Choose Your Edge Style**: Node-level edge declaration improves organization for complex nodes with many outputs.

4. **Right-Size Your Database**: Use appropriate pool tiers - don't over-provision for simple workflows or under-provision for data-intensive ones.

5. **Master Private Mode**: Understand that passthrough data preserves from INPUT state, not output. Essential for parallel processing.

---

*Last Updated: 2025-09-15 (Major Feature Update)*
*Previous Update: 2025-08-07*
*Remember to update this file when you learn something new!*