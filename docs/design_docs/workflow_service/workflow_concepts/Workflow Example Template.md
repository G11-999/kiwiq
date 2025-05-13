# Workflow Example Template

# AI-Human Feedback Loop Workflow: Detailed Template (3 Pages)

## 1. Workflow Overview

**Name**: AI Content Generation with Human Review Loop

**Purpose**: Generate AI content based on a user prompt, have a human review it, and either finalize or refine based on feedback

**Primary Input**: User prompt (text string)

**Primary Output**: Approved content with iteration history

## Diagrams

**(NOTE: may render better in light theme / white background!)**

**(NOTE: adding mermaid codes too to make doc machine readable more easily)**

### **Workflow Sequence Diagram —>**

```mermaid
sequenceDiagram
    participant User
    participant Input as Input Node
    participant AI as AI Generator
    participant CS as Central State
    participant HITL as Human Review
    participant Router as Approval Router
    participant Final as Final Processor

    User->>Input: Provide user_prompt
    Input->>AI: Pass user_prompt
    AI->>CS: Store messages in messages_history
    AI->>HITL: Send messages for review
    CS->>HITL: Provide full messages_history
    
    Note over HITL: Human reviews content
    
    HITL->>CS: Store approved status
    HITL->>CS: Store review_comments
    HITL->>Router: Send approval decision
    
    alt Not Approved
        Router->>AI: Route back for refinement
        CS->>AI: Provide message history + feedback
        Note over AI: Generate improved content
        AI->>CS: Store updated messages
        AI->>HITL: Send for review again
    else Approved
        Router->>Final: Route to finalize
        CS->>Final: Provide complete message history
        Final->>User: Return final approved content
    end
```

### **Workflow Flow**

```mermaid
flowchart TD
    Start([Workflow Begins]) --> InputNode[Receive User Prompt]
    InputNode --> FirstAI[AI: Generate Initial Content]
    FirstAI --> CS1[Update Central State: messages_history]
    CS1 --> HumanReview1[Human Review Content]
    
    HumanReview1 --> Decision1{Approved?}
    Decision1 -->|No| StoreRejection[Update Central State:<br>approved=no<br>review_comments]
    Decision1 -->|Yes| StoreApproval[Update Central State:<br>approved=yes]
    
    StoreRejection --> RouterReject[Router: Route to AI]
    StoreApproval --> RouterApprove[Router: Route to Final]
    
    RouterReject --> AIRefine[AI: Generate Refined Content<br>Based on Feedback]
    AIRefine --> CS2[Update Central State: messages_history]
    CS2 --> HumanReview2[Human Review Updated Content]
    HumanReview2 --> Decision1
    
    RouterApprove --> FinalProcess[Final: Process Approved Content]
    FinalProcess --> End([Return Results to User])
    
    style Start fill:#d0e0ff,stroke:#0066cc
    style End fill:#d0ffd0,stroke:#006600
    style InputNode fill:#d0e0ff,stroke:#0066cc
    style FirstAI fill:#ffe0d0,stroke:#cc6600
    style AIRefine fill:#ffe0d0,stroke:#cc6600
    style CS1 fill:#d0ffff,stroke:#00cccc
    style CS2 fill:#d0ffff,stroke:#00cccc
    style HumanReview1 fill:#ffd0e0,stroke:#cc0066
    style HumanReview2 fill:#ffd0e0,stroke:#cc0066
    style Decision1 fill:#f0f0f0,stroke:#666666
    style StoreRejection fill:#d0ffff,stroke:#00cccc
    style StoreApproval fill:#d0ffff,stroke:#00cccc
    style RouterReject fill:#f0d0ff,stroke:#9900cc
    style RouterApprove fill:#f0d0ff,stroke:#9900cc
    style FinalProcess fill:#d0ffd0,stroke:#006600
```

### Full Workflow Diagram (image zoomable)

```mermaid
graph TD
    subgraph "Central State"
        CS_MH["messages_history: List[AnyMessage]<br>Reducer: add_messages"]
        CS_A["approved: Approved(Enum)<br>Reducer: replace"]
        CS_RC["review_comments: Optional[str]<br>Reducer: replace"]
    end

    subgraph "Input Node"
        IN_O["Output:<br>• user_prompt: str"]
    end

    subgraph "AI Generator Node"
        AI_I["Input:<br>• user_prompt: str<br>• messages: List[AnyMessage]"]
        AI_O["Output:<br>• messages: List[AnyMessage]"]
    end

    subgraph "Human Review Node (HITL)"
        HR_I["Input (Dynamic):<br>• last_messages: List[AnyMessage]<br>• all_messages: List[AnyMessage]"]
        HR_O["Output:<br>• approved: Approved(Enum)<br>• review_comments: Optional[str]"]
    end

    subgraph "Approval Router Node"
        AR_I["Input (Dynamic):<br>• approved: Approved(Enum)"]
        AR_O["Output (Dynamic):<br>• choices: List[str]<br>• approved: Approved(Enum)"]
        AR_C["Config:<br>• field_name: 'approved'<br>• field_value: 'yes'<br>• route_if_true: 'final_processor'<br>• route_if_false: 'ai_generator'"]
    end

    subgraph "Final Processor Node"
        FP_I["Input (Dynamic):<br>• messages: List[AnyMessage]"]
        FP_O["Output:<br>• approved_content: str<br>• review_iterations: int<br>• messages: List[AnyMessage]"]
    end

    %% Direct Node-to-Node Edges
    IN_O -->|user_prompt| AI_I
    AI_O -->|messages| HR_I
    HR_O -->|approved| AR_I
    AR_O -->|if not approved| AI_I
    AR_O -->|if approved| FP_I

    %% Node to Central State Edges
    AI_O -->|messages| CS_MH
    HR_O -->|approved| CS_A
    HR_O -->|review_comments| CS_RC

    %% Central State to Node Edges
    CS_MH -->|messages_history| AI_I
    CS_MH -->|messages_history| HR_I
    CS_MH -->|messages_history| FP_I

    %% Styling
    style IN_O fill:#d0e0ff,stroke:#0066cc
    style AI_I fill:#ffe0d0,stroke:#cc6600
    style AI_O fill:#ffe0d0,stroke:#cc6600
    style HR_I fill:#ffd0e0,stroke:#cc0066
    style HR_O fill:#ffd0e0,stroke:#cc0066
    style AR_I fill:#f0d0ff,stroke:#9900cc
    style AR_O fill:#f0d0ff,stroke:#9900cc
    style AR_C fill:#fff0d0,stroke:#cc9900
    style FP_I fill:#d0ffd0,stroke:#006600
    style FP_O fill:#d0ffd0,stroke:#006600
    style CS_MH fill:#d0ffff,stroke:#00cccc
    style CS_A fill:#d0ffff,stroke:#00cccc
    style CS_RC fill:#d0ffff,stroke:#00cccc
```


## 2. Detailed Node Schemas

### 2.1 Input Node

**Type**: System Input Node

- **Input Schema**: N/A (system node)
- **Output Schema**:
    
    ```python
    class InputSchema(BaseSchema):
        user_prompt: str = Field(description="User prompt for AI generation")
    
    ```
    
- **Config Schema**: None (system node)
- **Purpose**: Entry point that receives the initial user prompt

### 2.2 AI Generator Node

**Type**: Processing Node

- **Input Schema**:
    
    ```python
    class MessagesWithUserPromptSchema(MessagesSchema):
        user_prompt: str = Field(description="User prompt for AI generation")
        messages: List[AnyMessage] = Field(default_factory=list, description="Previous conversation history")
    
    ```
    
- **Output Schema**:
    
    ```python
    class MessagesSchema(BaseSchema):
        messages: List[AnyMessage] = Field(default_factory=list, description="Generated AI messages")
    
    ```
    
- **Config Schema**: None
- **Purpose**: Generates AI content based on prompt and previous feedback
- **Logic Details**:
    - Counts existing AI messages to track iteration number
    - Generates different responses for initial requests vs. refinements
    - Metadata includes iteration count and timestamps

### 2.3 Human Review Node (HITL)

**Type**: Human-in-the-Loop

- **Input Schema**: **DYNAMIC** (explained below)
- **Output Schema**:
    
    ```python
    class UserInputSchema(BaseSchema):
        approved: Approved = Field(description="Approval status (yes/no as enum)")
        review_comments: Optional[str] = Field(None, description="Review comments if not approved")
    
    ```
    
- **Config Schema**: None
- **Purpose**: Collects human review of AI content
- **Special Logic**:
    - Validates that review comments are provided when content is rejected
    - Presents context of full conversation to reviewer

### 2.4 Approval Router Node

**Type**: Router

- **Input Schema**: **DYNAMIC** (explained below)
- **Output Schema**: **DYNAMIC** - **—> HYBRID SCHEMA!**

**NOTE:** Dynamic schemas may be hybrid → a few fields defined as normal schema and rest fields assembled at runtime dynamically from edges!

`choices` here is a normal non-dynamic field and rest of the schema is assembled at runtime.
    
    ```python
    class ApprovalRouterChoiceOutputDynamicSchema(DynamicSchema):
        choices: List[str] = Field(description="List of routing choices", min_length=1)
    
    ```
    
- **Config Schema**:
    
    ```python
    class ApprovalRouterConfigSchema(RouterSchema):
        field_name: str = Field(description="Field name to check for approval")
        field_value: str = Field(description="Value to check for approval")
        route_if_true: str = Field(description="Route to take if field is true")
        route_if_false: str = Field(description="Route to take if field is false")
    
    ```
    
- **Purpose**: Routes workflow based on human approval decision
- **Config Values**:
    - `field_name`: "approved"
    - `field_value`: "yes"
    - `route_if_true`: "final_processor"
    - `route_if_false`: "ai_generator"

### 2.5 Final Processor Node

**Type**: Processing/Output

- **Input Schema**: **DYNAMIC** (explained below)
- **Output Schema**:
    
    ```python
    class FinalOutputSchema(BaseSchema):
        approved_content: str = Field(description="Final approved content")
        review_iterations: int = Field(description="Number of review iterations")
        messages: List[AnyMessage] = Field(description="Complete conversation history")
    
    ```
    
- **Config Schema**: None
- **Purpose**: Formats final output with approved content and metadata

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '16px', 'fontFamily': 'arial' }}}%%
graph TB
    subgraph "1. Input Node"
        direction TB
        IN_O["Input Node Output:<br>• user_prompt: str"]
    end

    subgraph "2. AI Generator Node"
        direction TB
        AI_I["AI Generator Input:<br>• user_prompt: str<br>• messages: List[AnyMessage]"]
        AI_O["AI Generator Output:<br>• messages: List[AnyMessage]"]
    end

    subgraph "3. Human Review Node (HITL)"
        direction TB
        HR_I["HITL Input:<br>• last_messages: List[AnyMessage]<br>• all_messages: List[AnyMessage]"]
        HR_O["HITL Output:<br>• approved: Approved(Enum)<br>• review_comments: Optional[str]"]
    end

    subgraph "4. Approval Router Node"
        direction TB
        AR_I["Router Input:<br>• approved: Approved(Enum)"]
        AR_O["Router Output:<br>• choices: List[str]<br>• approved: Approved(Enum)"]
        AR_C["Router Config:<br>• field_name: 'approved'<br>• field_value: 'yes'<br>• route_if_true: 'final_processor'<br>• route_if_false: 'ai_generator'"]
    end

    subgraph "5. Final Processor Node"
        direction TB
        FP_I["Final Processor Input:<br>• messages: List[AnyMessage]"]
        FP_O["Final Processor Output:<br>• approved_content: str<br>• review_iterations: int<br>• messages: List[AnyMessage]"]
    end

    subgraph "Central State"
        direction TB
        CS_MH["messages_history:<br>List[AnyMessage]<br><i>Reducer: add_messages</i>"]
        CS_A["approved:<br>Approved(Enum)<br><i>Reducer: replace</i>"]
        CS_RC["review_comments:<br>Optional[str]<br><i>Reducer: replace</i>"]
    end

    %% Force vertical arrangement
    IN_O --> AI_I
    AI_I --> AI_O
    AI_O --> HR_I
    HR_I --> HR_O
    HR_O --> AR_I
    AR_I --> AR_O
    AR_O --> AR_C
    AR_C --> FP_I
    FP_I --> FP_O

    %% Styling
    style CS_MH fill:#d0ffff,stroke:#00cccc,stroke-width:2px
    style CS_A fill:#d0ffff,stroke:#00cccc,stroke-width:2px
    style CS_RC fill:#d0ffff,stroke:#00cccc,stroke-width:2px
    
    style IN_O fill:#d0e0ff,stroke:#0066cc,stroke-width:2px
    
    style AI_I fill:#ffe0d0,stroke:#cc6600,stroke-width:2px
    style AI_O fill:#ffe0d0,stroke:#cc6600,stroke-width:2px
    
    style HR_I fill:#ffd0e0,stroke:#cc0066,stroke-width:2px
    style HR_O fill:#ffd0e0,stroke:#cc0066,stroke-width:2px
    
    style AR_I fill:#f0d0ff,stroke:#9900cc,stroke-width:2px
    style AR_O fill:#f0d0ff,stroke:#9900cc,stroke-width:2px
    style AR_C fill:#fff0d0,stroke:#cc9900,stroke-width:2px
    
    style FP_I fill:#d0ffd0,stroke:#006600,stroke-width:2px
    style FP_O fill:#d0ffd0,stroke:#006600,stroke-width:2px
```

## 3. Dynamic Schema Explanation

### 3.1 Why Schemas Are Dynamic

**Human Review Node - Input Schema**:

- **Why Dynamic?**: The HITL node must see both messages from the AI node and the full conversation history from central state
- **Generated From**: Edges from AI Generator node and central state
- **Resulting Schema**:
    
    ```python
    class DynamicHITLInputSchema(DynamicSchema):
        last_messages: List[AnyMessage] = Field(description="Latest messages from AI")
        all_messages: List[AnyMessage] = Field(description="Full message history from central state")
    
    ```
    

**Approval Router Node - Input Schema**:

- **Why Dynamic?**: Needs to receive approval status from HITL node
- **Generated From**: Edge from Human Review node
- **Resulting Schema**:
    
    ```python
    class DynamicRouterInputSchema(DynamicSchema):
        approved: Approved = Field(description="Approval status from human review")
    
    ```
    

**Approval Router Node - Output Schema**:

- **Why Dynamic?**: Needs to pass through the approval status to preserve it in routing decisions
- **Generated From**: Input fields + choices field
- **Resulting Schema**: Combines standard router output with fields from input
    
    ```python
    # Generated schema includes both choices and approved field
    
    ```
    

**Final Processor Node - Input Schema**:

- **Why Dynamic?**: Needs to receive the complete message history
- **Generated From**: Edge from central state
- **Resulting Schema**:
    
    ```python
    class DynamicProcessorInputSchema(DynamicSchema):
        messages: List[AnyMessage] = Field(description="Complete message history from central state")
    
    ```
    

### 3.2 Dynamic Schema Generation Process

1. **Edge Analysis**: The system examines all edges connecting to a node with dynamic schemas
2. **Field Collection**: For each incoming edge, collects the field name and type from the source
3. **Schema Construction**: Creates a new schema class with all collected fields
4. **Validation Rules**: Preserves validation rules (required/optional) from source fields
5. **Type Consistency**: Ensures compatible types when multiple edges target the same field

## 4. Central State Fields

| Field Name | Type | Purpose | Reducer Type | Reducer Logic |
| --- | --- | --- | --- | --- |
| `messages_history` | List[AnyMessage] | Store conversation | add_messages | Adds new messages to history, preserving order |
| `approved` | Approved (Enum) | Track approval status | replace | Replaces previous value with new approval status |
| `review_comments` | Optional[str] | Store feedback | replace | Replaces previous value with new comments |

## 5. Edge Definitions with Detailed Field Mappings

### 5.1 Input to AI Generator

- **Source**: Input Node → `user_prompt` (str)
- **Destination**: AI Generator → `user_prompt` (str)
- **Purpose**: Passes initial prompt to AI generator

### 5.2 Central State to AI Generator

- **Source**: Central State → `messages_history` (List[AnyMessage])
- **Destination**: AI Generator → `messages` (List[AnyMessage])
- **Purpose**: Provides conversation history for context in iterations
- **When Used**: After first iteration, supplies previous messages for refinement

### 5.3 AI Generator to Central State

- **Source**: AI Generator → `messages` (List[AnyMessage])
- **Destination**: Central State → `messages_history` (List[AnyMessage])
- **Purpose**: Updates central message history with new AI response
- **Reducer**: add_messages (appends rather than replaces)

### 5.4 AI Generator to Human Review

- **Source**: AI Generator → `messages` (List[AnyMessage])
- **Destination**: Human Review → `last_messages` (List[AnyMessage])
- **Purpose**: Passes most recent AI output for human review

### 5.5 Central State to Human Review

- **Source**: Central State → `messages_history` (List[AnyMessage])
- **Destination**: Human Review → `all_messages` (List[AnyMessage])
- **Purpose**: Provides full conversation context for human reviewer

### 5.6 Human Review to Central State (2 edges)

- **Source 1**: Human Review → `approved` (Approved enum)
- **Destination 1**: Central State → `approved` (Approved enum)
- **Source 2**: Human Review → `review_comments` (Optional[str])
- **Destination 2**: Central State → `review_comments` (Optional[str])
- **Purpose**: Stores review decisions in central state

### 5.7 Human Review to Approval Router

- **Source**: Human Review → `approved` (Approved enum)
- **Destination**: Approval Router → `approved` (Approved enum)
- **Purpose**: Passes approval status for routing decision

### 5.8 Approval Router to Next Nodes (Conditional)

- **To AI Generator**: No field mapping (conditional execution only)
    - **Condition**: `choices[0] == 'ai_generator'` (when not approved)
- **To Final Processor**: No field mapping (conditional execution only)
    - **Condition**: `choices[0] == 'final_processor'` (when approved)

### 5.9 Central State to Final Processor

- **Source**: Central State → `messages_history` (List[AnyMessage])
- **Destination**: Final Processor → `messages` (List[AnyMessage])
- **Purpose**: Provides complete conversation for output preparation

## 6. Loop Mechanism Explained

### 6.1 Loop Structure

- AI Generator → Human Review → Approval Router → (back to) AI Generator

### 6.2 How the Loop Works

1. AI generates content (stored in central state)
2. Human reviews and provides approval/comments
3. Router checks approval status
4. If not approved, routes back to AI Generator
5. AI has access to previous messages via central state
6. AI incorporates feedback and generates improved content
7. Loop continues until human approves

### 6.3 Loop Exit Condition

- Human reviewer sets `approved = "yes"`
- Router directs flow to Final Processor instead of back to AI
- Final Processor creates output with approved content

## 7. Technical Implementation Notes

### 7.1 Message Handling with Reducers

- The `add_messages` reducer ensures messages are appended to history
- This allows the AI to see all previous messages when refining content
- Implementation uses `langchain_core.messages.add_messages` field annotation

### 7.2 Enum Type for Approval

- Uses Enum for approved status to enforce valid options
- Simplifies router logic by having standardized values

### 7.3 Schema Validation

- UserInputSchema validates that review comments are provided when content is rejected
- Uses Pydantic's `model_validator` to enforce this business rule

### 7.4 Dynamic Schema Implementation

- DynamicSchema base class enables extensible schemas
- Fields are added at runtime based on edge connections
- Router outputs inherit input fields to maintain state during routing

## 8. Design Considerations and Rationale

### 8.1 Why Use Central State for Message History

- **Persistence**: Messages need to be available across multiple iterations
- **Cross-Node Access**: Both AI and Final Processor need access
- **Append Operation**: Messages need to accumulate rather than replace

### 8.2 Why Make Router Schema Dynamic

- Allows router to pass through input fields to maintain workflow state
- Simplifies edge design by not requiring explicit mappings for pass-through data
- Enables more flexible routing patterns

### 8.3 Design Decisions for HITL Node

- Separates latest messages from full history for clearer presentation
- Requires comments when rejecting to ensure meaningful feedback
- Exposes validation logic explicitly for better user experience