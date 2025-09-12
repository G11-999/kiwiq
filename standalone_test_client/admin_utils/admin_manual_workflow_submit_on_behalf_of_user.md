# Manually submit workflow run: 

API: /api/v1/runs

X-Active-Org: df983d34-6327-49e6-8058-304cbd1ff512

{
  "workflow_id": "bcc8afbc-c519-463d-9f96-ba594798f549",
  "inputs": {
    "company_name": "kiwiq",
    "entity_username": "example-user",
    "run_blog_analysis": true,
    "run_linkedin_exec": true,
    "linkedin_profile_url": "https://www.linkedin.com/in/example-user",
    "company_url": "https://www.kiwiq.ai",
    "blog_start_urls": [
      "https://www.kiwiq.ai"
    ]
  },
  "resume_after_hitl": false,
  "on_behalf_of_user_id": "8da761d4-abf0-4955-919b-9e0982cccf2b",
  "include_active_overrides": true,
  "streaming_mode": false
}
