# LinkedIn Scraping Workflow

## Overview
This workflow scrapes LinkedIn profile and post data for a given entity (person or company), filters the data to keep only relevant fields, and stores both raw and filtered versions. It retrieves profile information and up to 50 recent posts, then applies extensive filtering to extract essential data points.

## Frontend User Flow
*To be documented later*

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/wf_linkedin_scraping.py`
- **LLM Inputs**: Not applicable (no LLM processing in this workflow)

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts LinkedIn entity information

**Input Requirements**:
- `entity_url`: URL of the LinkedIn entity (person or company) (required)
- `entity_username`: Name of the entity used for saving document names (required)

### 2. Scrape LinkedIn Data
**Node ID**: `scrape_entity`

**Purpose**: Scrapes profile information and posts from LinkedIn

**Process**:
- Executes two scraping jobs in parallel:
  - Job 1: Profile information scraping
  - Job 2: Entity posts scraping (up to 50 posts)
- Returns raw scraped data for both jobs

**Configuration**:
- **Profile Info Job**:
  - Job Type: `profile_info`
  - Output Field: `scraped_profile_job`
  - Profile Info Flag: `yes`
- **Entity Posts Job**:
  - Job Type: `entity_posts`
  - Output Field: `scraped_posts_job`
  - Post Limit: 50
  - Entity Posts Flag: `yes`
  - Post Comments: `no` (default)
  - Post Reactions: `no` (default)

**Test Mode**: Can be set to `true` for testing without API calls/credits

### 3. Store Raw Scraped Data
**Node ID**: `store_raw_data`

**Purpose**: Stores unprocessed scraped data for audit trail

**Process**:
- Saves raw profile data
- Saves raw posts data
- Maintains original structure from scraper

**Storage Configuration**:
- **Profile Storage**:
  - Namespace: `linkedin_scraped_profile_{entity_username}`
  - Document Name: `linkedin_scraped_profile_raw`
- **Posts Storage**:
  - Namespace: `linkedin_scraped_posts_{entity_username}`
  - Document Name: `linkedin_scraped_posts_raw`
- Versioning: No (upsert operation)
- Shared: No (user-specific)

### 4. Filter Scraped Data
**Node ID**: `filter_scraped_data`

**Purpose**: Filters raw data to retain only essential fields

**Process**:
- Uses allow-list filtering approach
- Preserves nested structures while removing unnecessary fields
- Maintains data integrity for downstream processing

**Profile Fields Retained**:
- Basic Info: `username`, `firstName`, `lastName`, `headline`, `summary`
- Location: `geo` (country, city, full)
- Education: Array with fields like `schoolName`, `degree`, `fieldOfStudy`, dates
- Position: Current position with `companyName`, `companyIndustry`, `location`, `description`

**Posts Fields Retained**:
- Identifiers: `urn`
- Content: `text`, `contentType`
- Metadata: `postedDate`, `postedDateTimestamp`, `reposted`, `isBrandPartnership`
- Engagement: `totalReactionCount`, `commentsCount`, `repostsCount`

**Configuration**:
- Non-target Fields Mode: `deny` (reject all fields not explicitly allowed)
- Filter Mode: `allow` for all specified fields
- Condition: Fields must be non-empty

### 5. Store Filtered Data
**Node ID**: `store_filtered_data`

**Purpose**: Stores cleaned and filtered data for analysis

**Process**:
- Saves filtered profile data
- Saves filtered posts data
- Prepares data for downstream workflows

**Storage Configuration**:
- **Profile Storage**:
  - Namespace: `linkedin_scraped_profile_{entity_username}`
  - Document Name: `linkedin_scraped_profile`
- **Posts Storage**:
  - Namespace: `linkedin_scraped_posts_{entity_username}`
  - Document Name: `linkedin_scraped_posts`
- Versioning: No (upsert operation)
- Shared: No (user-specific)

### 6. Output Node
**Node ID**: `output_node`

**Purpose**: Returns workflow execution results

**Configuration**:
- Enable Fan In: Yes

**Output**:
- `entity_username`: Entity name for reference
- `scraping_status_summary`: Execution summary from scraper
- `raw_data_paths`: Paths where raw data was stored
- `filtered_data_paths`: Paths where filtered data was stored

## Workflow Configuration Details

### Data Filtering Strategy
The workflow uses an extensive allow-list approach for filtering:
- Each field must be explicitly allowed
- Nested structures are preserved (education, position arrays)
- Only non-empty fields are retained
- Maintains data relationships and structure

### Post Limit Configuration
- Maximum posts scraped: 50 (configurable via `POST_LIMIT` constant)
- Balances data completeness with API usage
- Sufficient for most content analysis needs

### State Management
The workflow uses graph state to maintain:
- `entity_username`: For document naming across nodes
- `scraping_status_summary`: Execution status tracking

### Storage Pattern
- Raw data stored separately from filtered data
- Enables data lineage tracking
- Allows re-processing without re-scraping
- Maintains audit trail of original data

### Field Preservation Details

**Profile Fields Structure**:
```
- username
- firstName, lastName
- headline, summary
- geo:
  - country
  - city
  - full
- educations[]:
  - schoolName
  - degree
  - fieldOfStudy
  - start/end dates
  - description
  - grade
- position:
  - companyName
  - companyIndustry
  - location
  - description
```

**Posts Fields Structure**:
```
- urn (unique identifier)
- text (post content)
- contentType
- postedDate
- postedDateTimestamp
- reposted (boolean)
- isBrandPartnership (boolean)
- totalReactionCount
- commentsCount
- repostsCount
```

### Error Handling
- Test mode available for development/testing
- Graceful handling of missing fields
- Non-empty validation for all fields

### Performance Considerations
- Parallel execution of profile and posts scraping
- Efficient filtering with single pass
- Optimized storage operations