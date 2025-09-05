from kiwi_client.run_client import *


# --- Example Usage --- (for testing this module directly)
async def get_logs_state_for_run(run_id: Union[str, uuid.UUID], test_name: str):
    """Demonstrates using the updated WorkflowRunTestClient with schema validation."""
    print("--- Starting Workflow Run API Test --- ")
    created_run_id: Optional[uuid.UUID] = run_id

    # Need an authenticated client first
    try:
        async with AuthenticatedClient() as auth_client:
            print("Authenticated.")
            # Initialize test clients
            run_tester = WorkflowRunTestClient(auth_client)
            print(f"\n5. Getting logs for run {created_run_id}...")
            logs_data, logs_path = await run_tester.get_run_logs(
                run_id=created_run_id,
                save_to_file=True,
                test_name=test_name
            )
            if logs_data:
                log_count = len(logs_data.get("logs", []))
                print(f"   Successfully retrieved {log_count} log entries for run {created_run_id}")
                print(f"   Saved logs to file: Example_Basic_LLM_Test_run_{created_run_id}_logs.json \nPATH: {logs_path}\n")
            else:
                print(f"   Failed to retrieve logs for run {created_run_id}")

            print(f"\n6. Getting state for run {created_run_id} (requires superuser)...")
            state_data, state_path = await run_tester.get_run_state(
                run_id=created_run_id,
                save_to_file=True,
                test_name=test_name
            )
            if state_data:
                print(f"   Successfully retrieved state for run {created_run_id}")
                print(f"   Saved state to file: Example_Basic_LLM_Test_run_{created_run_id}_state.json \nPATH: {state_path}\n")
            else:
                print(f"   Failed to retrieve state for run {created_run_id} (likely not a superuser)")
            # --- End Handle Direct Completion ---
    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in the main test execution: {e}")
        logger.exception("Main test execution error:")
    

if __name__ == "__main__":
    run_id = "57913692-0b32-4fda-b312-b13e02582197"
    test_name = "Test_workflow_run_blog_content_playbook_generation"
    asyncio.run(get_logs_state_for_run(run_id, test_name)) # Run the main test function
