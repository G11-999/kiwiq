# Manually submit workflow run: 

API: /api/v1/runs

X-Active-Org: 00000000-0000-0000-0000-000000000001

{
  "workflow_id": "00000000-0000-0000-0000-000000000002",
  "inputs": {
    "company_name": "example-company",
    "entity_username": "example-user",
    "run_blog_analysis": true,
    "run_linkedin_exec": true,
    "linkedin_profile_url": "https://www.linkedin.com/in/example-user",
    "company_url": "https://www.example.com",
    "blog_start_urls": [
      "https://www.example.com"
    ]
  },
  "resume_after_hitl": false,
  "on_behalf_of_user_id": "00000000-0000-0000-0000-000000000003",
  "include_active_overrides": true,
  "streaming_mode": false
}
