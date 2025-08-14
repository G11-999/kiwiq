import asyncio
from uuid import UUID
from scripts.initial_setup.customer_data_uploader import SimpleDataUploader, DocumentConfig

"""
Company Data Uploader
- Edit the CONFIG and DATA sections below, then run this file to upload.
- The organization is determined by your authentication (see AuthenticatedClient setup).
- If uploading a non-system entity document and you want to act on behalf of a specific user,
  set USER_ID to that user's UUID. Leave it None for your own user.

Supported features:
- Versioned upsert (creates if missing, updates if present) and sets the version active
- Shared vs user-specific docs
- System entity docs (stored under system paths, not tied to a specific org user)
- Optional schema template attachment
"""

# === CONFIG (edit these) ===
NAMESPACE = "linkedin_executive_profile_namespace_santiycr"
DOCNAME = "linkedin_executive_profile_doc"
VERSION = None
IS_SHARED = False
IS_SYSTEM_ENTITY = False
SCHEMA_TEMPLATE_NAME = None  # e.g., "my_schema_template"
SCHEMA_TEMPLATE_VERSION = None  # e.g., "1.0.0"

# For non-system entities, optionally act on behalf of a specific user in your org
# Provide a valid UUID string or set to None
USER_ID = "de15b8c4-a892-479e-89ad-bc422af20b86"

# === DATA (edit this payload) ===
EXECUTIVE_PROFILE_DATA = {
    "name": "Santiago Suarez",
    "title": "CEO & Founder",
    "company": "Momentum",
    "industry_experience": "15 years in project management and SaaS",
    "expertise_areas": [
        "AI-powered project management",
        "Team productivity optimization",
        "Remote work culture",
        "SaaS product development",
    ],
    "thought_leadership_focus": [
        "The future of work and AI integration",
        "Building efficient remote teams",
        "Project management best practices",
        "Technology adoption in growing companies",
    ],
    "linkedin_goals": [
        "Build thought leadership in project management space",
        "Share insights on AI adoption",
        "Connect with other industry leaders",
        "Promote Momentum's vision",
    ],
}
# EXECUTIVE_PROFILE_DATA =

async def upload_company_data():
    uploader = SimpleDataUploader()

    config = DocumentConfig(
        namespace=NAMESPACE,
        docname=DOCNAME,
        is_shared=IS_SHARED,
        is_system_entity=IS_SYSTEM_ENTITY,
        version=VERSION,
        schema_template_name=SCHEMA_TEMPLATE_NAME,
        schema_template_version=SCHEMA_TEMPLATE_VERSION,
    )

    user_id_uuid = None
    if USER_ID:
        try:
            user_id_uuid = UUID(USER_ID)
        except Exception:
            print(f"⚠️  USER_ID is not a valid UUID string: {USER_ID}. Proceeding without on-behalf-of.")
            user_id_uuid = None

    print("📝 Uploading company data...")
    print(f"📍 Target: {config.namespace}/{config.docname}")
    print(f"🔖 Version: {config.version} | Shared: {config.is_shared} | System: {config.is_system_entity}")
    if config.schema_template_name and config.schema_template_version:
        print(f"📐 Schema: {config.schema_template_name} v{config.schema_template_version}")
    if user_id_uuid and not config.is_system_entity:
        print(f"👤 On behalf of user: {user_id_uuid}")

    try:
        response = await uploader.store_data_simple(
            config=config,
            data=EXECUTIVE_PROFILE_DATA,
            user_id=user_id_uuid,
        )

        if response:
            print("✅ SUCCESS: Company data uploaded!")
            print(f"🎯 Location: {config.namespace}/{config.docname}")
            print(f"📋 Operation: {response.operation_performed}")
        else:
            print("❌ FAILED: Upload did not return a success response.")
    except Exception as e:
        print(f"💥 ERROR during upload: {e}")
        raise


if __name__ == "__main__":
    print("🚀 Starting company data upload...")
    asyncio.run(upload_company_data())
    print("🏁 Upload process completed.") 