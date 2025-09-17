# LinkedIn Profile Scraper Workflow - Evaluation Guidelines

## Overview
The LinkedIn Profile Scraper Workflow aims to scrape LinkedIn profile and post data for a given entity, filter the data to retain only essential fields, and store both raw and filtered versions for downstream analysis. The workflow retrieves profile information and up to 50 recent posts, applies extensive filtering using an allow-list approach, and maintains data lineage through separate storage of raw and processed data. This workflow serves as a critical data foundation for other content diagnostic workflows.

## Data Processing Node Evaluation Guidelines

### 1. LinkedIn Data Scraping Node
**Node ID**: `scrape_entity`  
**Task Type**: External API data retrieval and parallel job execution (Low complexity, High variance due to external dependencies)

#### What We Are Analyzing
This node executes two parallel scraping jobs to retrieve LinkedIn profile information and recent posts (up to 50) from the specified entity URL, returning raw scraped data for both profile and posts.

#### Ideal Output
- Complete profile information including basic details, location, education, and current position
- Up to 50 recent posts with engagement metrics, content, and metadata
- Successful parallel execution of both profile and posts scraping jobs
- Raw data structure maintained for audit trail and downstream processing
- Proper error handling when entities are private or unavailable

#### Evaluation Parameters
1. **Data Completeness**: Both profile and posts data are successfully retrieved with all available fields populated
2. **Posts Volume Accuracy**: Retrieval of up to 50 recent posts or all available posts if fewer than 50 exist
3. **Parallel Execution Success**: Both scraping jobs complete successfully without blocking each other
4. **Raw Data Integrity**: Original data structure and all fields are preserved without corruption or loss
5. **Error Handling Quality**: Graceful handling of private profiles, rate limits, or unavailable entities
6. **Performance Consistency**: Reliable execution times within acceptable ranges for API-dependent operations

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Data Filtering Node
**Node ID**: `filter_scraped_data`  
**Task Type**: Structured data transformation with allow-list filtering (Low complexity, Low variance)

#### What We Are Analyzing
This node applies extensive allow-list filtering to retain only essential profile and posts fields while preserving nested structures and data relationships, removing unnecessary fields to optimize data for downstream processing.

#### Ideal Output
- Clean profile data with only essential fields: username, firstName, lastName, headline, summary, geo, educations, position
- Filtered posts data retaining: urn, text, contentType, posting dates, engagement metrics, metadata flags
- Preserved nested structures for education arrays and position objects
- Consistent field presence validation with non-empty requirement
- Maintained data relationships and structural integrity

#### Evaluation Parameters
1. **Field Accuracy**: All specified allow-list fields are retained when present in source data
2. **Filtering Completeness**: All non-allowed fields are properly removed from the output
3. **Structure Preservation**: Nested arrays (education) and objects (position, geo) maintain their relationships
4. **Data Validation**: Non-empty validation correctly applied to prevent storage of blank fields
5. **Consistency Maintenance**: Filtered data structure is consistent across different entity types and profiles
6. **Information Loss Prevention**: Essential information is not inadvertently removed during filtering

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Data Storage Operations
**Node IDs**: `store_raw_data`, `store_filtered_data`  
**Task Type**: Document storage with namespace organization (Low complexity, Low variance)

#### What We Are Analyzing
These nodes store both raw and filtered versions of scraped data in appropriate namespaces, maintaining data lineage and enabling audit trails while preparing data for downstream workflow consumption.

#### Ideal Output
- Raw data stored in separate documents for profile and posts with complete original structure
- Filtered data stored in clean format ready for analysis workflows
- Proper namespace organization using entity_username for user-specific data segregation
- Successful upsert operations that update existing documents without versioning conflicts
- Clear separation between raw audit data and processed analytical data

#### Evaluation Parameters
1. **Storage Completeness**: Both raw and filtered versions successfully stored for profile and posts data
2. **Namespace Organization**: Proper use of entity_username in namespace creation for data segregation
3. **Data Lineage Maintenance**: Clear relationship between raw and filtered data through naming and structure
4. **Storage Operation Success**: Upsert operations complete without errors or data corruption
5. **Document Structure Integrity**: Stored documents maintain proper structure and accessibility for downstream workflows
6. **Performance Efficiency**: Storage operations complete within reasonable timeframes

#### Suggested Improvements
[To be filled based on evaluation results]

---

## General Evaluation Considerations

### Quality Thresholds
- **Critical**: More than 1 evaluation parameter failure or complete data loss/corruption
- **Needs Improvement**: 1 evaluation parameter failure or significant data quality issues
- **Acceptable**: All evaluation parameters met with minor issues in completeness or consistency
- **Excellent**: All parameters exceeded with comprehensive data capture and perfect filtering accuracy

### Evaluation Frequency
- Initial baseline evaluation should be conducted on a sample of 15-20 different LinkedIn profiles covering various entity types
- Regular spot checks should be performed daily given external API dependency and rate limit considerations
- Full evaluation should be repeated after any filtering logic changes or scraper updates
- Special evaluation when processing new entity types or encountering API changes

### Documentation Requirements
- Record examples of successful vs. failed scraping attempts with root cause analysis
- Document data completeness patterns across different profile types and privacy settings
- Track filtering accuracy and any information loss incidents
- Maintain examples of proper vs. corrupted data structures
- Monitor storage operation performance and any namespace organization issues

### External Dependency Considerations
- LinkedIn API availability and rate limiting can significantly impact workflow success
- Profile privacy settings affect data accessibility and completeness
- Network connectivity issues may cause intermittent failures
- LinkedIn platform changes could affect data structure and field availability
- Scraping service reliability and performance variations should be monitored

### Success Metrics
- **Data Retrieval Rate**: Percentage of successful profile and posts scraping attempts
- **Filtering Accuracy**: Percentage of correctly filtered fields without information loss
- **Storage Success Rate**: Percentage of successful raw and filtered data storage operations
- **Data Quality Score**: Assessment of completeness, accuracy, and structural integrity
- **Performance Consistency**: Variation in execution times and success rates over time

### Monitoring Recommendations
- Implement automated data quality checks for essential profile fields
- Monitor scraping success rates and identify patterns in failures
- Track data volume consistency (posts retrieved vs. expected)
- Set up alerts for significant drops in data quality or retrieval rates
- Regular validation of filtered data structure against downstream workflow requirements