import unittest
import uuid

from pydantic import HttpUrl, ValidationError

# Models and services to test
from kiwi_app.workflow_app.app_state import (
    UserStateEntry,
    UserState,
    StateUpdate,
    InitializeUserStateRequest,
    UpdateUserStateRequest,
    ApplicationActiveStatus,
    DocumentApplicationStatus,
    ListUserStateDocumentsWithStatusResponse,
    GetUserStateResponse,
    ActiveUserStateDocnamesResponse,
    list_active_user_state_docnames_core,
    get_user_state,
    update_user_state,
)



class TestUserStateEntryModel(unittest.TestCase):

    def test_valid_initialization(self):
        entry = UserStateEntry(state_value_type_name="str", description="Test", state_value="hello")
        self.assertEqual(entry.state_value, "hello")
        self.assertEqual(entry._actual_state_value_type, str)
        self.assertEqual(entry.description, "Test")

    def test_default_description(self):
        entry = UserStateEntry(state_value_type_name="int", state_value=10)
        self.assertEqual(entry.description, "") # Default description

    def test_type_coercion(self):
        entry = UserStateEntry(state_value_type_name="int", description="Coerced", state_value="123")
        self.assertEqual(entry.state_value, 123)

    def test_invalid_type_name(self):
        with self.assertRaises(ValidationError):
            UserStateEntry(state_value_type_name="invalid", description="Test", state_value="abc")

    def test_value_type_mismatch_no_coercion_list(self):
        with self.assertRaisesRegex(ValueError, "does not match state_value_type_name 'list'"):
             UserStateEntry(state_value_type_name="list", description="Test", state_value="not_a_list_at_all")
    
    def test_value_type_mismatch_no_coercion_dict(self):
        with self.assertRaisesRegex(ValueError, "does not match state_value_type_name 'dict'"):
            UserStateEntry(state_value_type_name="dict", description="Test", state_value="string_not_dict")

    def test_compute_substates_and_logic_all_true(self):
        entry = UserStateEntry(
            state_value_type_name="bool", description="Parent", state_value=False,
            combine_values_from_sub_states=True, sub_states_combine_logic="AND",
            sub_states={
                "c1": UserStateEntry(state_value_type_name="bool", description="c1", state_value=True),
                "c2": UserStateEntry(state_value_type_name="bool", description="c2", state_value=True),
            }
        )
        self.assertTrue(entry.state_value)

    def test_compute_substates_and_logic_one_false(self):
        entry = UserStateEntry(
            state_value_type_name="bool", description="Parent", state_value=True, # Initial value
            combine_values_from_sub_states=True, sub_states_combine_logic="AND",
            sub_states={
                "c1": UserStateEntry(state_value_type_name="bool", description="c1", state_value=True),
                "c2": UserStateEntry(state_value_type_name="bool", description="c2", state_value=False),
            }
        )
        self.assertFalse(entry.state_value) # Recomputed to False

    def test_compute_substates_or_logic(self):
        entry = UserStateEntry(
            state_value_type_name="bool", description="Parent OR", state_value=False,
            combine_values_from_sub_states=True, sub_states_combine_logic="OR",
            sub_states={
                "c1": UserStateEntry(state_value_type_name="bool", description="c1", state_value=False),
                "c2": UserStateEntry(state_value_type_name="bool", description="c2", state_value=True),
            }
        )
        self.assertTrue(entry.state_value)

    def test_compute_substates_sum_logic_int(self):
        entry = UserStateEntry(
            state_value_type_name="int", description="Parent SUM", state_value=0,
            combine_values_from_sub_states=True, sub_states_combine_logic="SUM",
            sub_states={
                "s1": UserStateEntry(state_value_type_name="int", description="s1", state_value=10),
                "s2": UserStateEntry(state_value_type_name="float", description="s2", state_value=5.5), # float
                "s3_bool": UserStateEntry(state_value_type_name="bool", description="s3", state_value=True), # bool to 1
            }
        )
        self.assertEqual(entry.state_value, 16) # 10 + 5.5 (as float) + 1 = 16.5, then cast to int

    def test_compute_substates_average_logic_float(self):
        entry = UserStateEntry(
            state_value_type_name="float", description="Parent AVG", state_value=0.0,
            combine_values_from_sub_states=True, sub_states_combine_logic="AVERAGE",
            sub_states={
                "s1": UserStateEntry(state_value_type_name="int", description="s1", state_value=10),
                "s2": UserStateEntry(state_value_type_name="float", description="s2", state_value=20.0),
            }
        )
        self.assertEqual(entry.state_value, 15.0)

    def test_compute_substates_no_combine_logic(self):
        entry = UserStateEntry(
            state_value_type_name="bool", description="Parent", state_value=False,
            combine_values_from_sub_states=True, # Logic is None
            sub_states={"c1": UserStateEntry(state_value_type_name="bool", description="c1", state_value=True)}
        )
        self.assertFalse(entry.state_value) # No change as logic is missing

    def test_compute_substates_combine_false(self):
        entry = UserStateEntry(
            state_value_type_name="bool", description="Parent", state_value=False,
            combine_values_from_sub_states=False, sub_states_combine_logic="AND",
            sub_states={"c1": UserStateEntry(state_value_type_name="bool", description="c1", state_value=True)}
        )
        self.assertFalse(entry.state_value) # No change


class TestUserStateModel(unittest.TestCase):

    def _get_sample_raw_state(self):
        return {
            "states": {
                "notifications_enabled": {
                    "state_value_type_name": "bool", "description": "All notifications", "state_value": False,
                    "combine_values_from_sub_states": True, "sub_states_combine_logic": "OR",
                    "sub_states": {
                        "email_enabled": {"state_value_type_name": "bool", "description": "Email", "state_value": False},
                        "sms_enabled": {"state_value_type_name": "bool", "description": "SMS", "state_value": False}
                    }
                },
                "user_score": {"state_value_type_name": "int", "description": "Score", "state_value": 100}
            }
        }

    def test_initialize(self):
        user_state = UserState.initialize(self._get_sample_raw_state())
        self.assertIn("notifications_enabled", user_state.states)
        self.assertEqual(user_state.states["user_score"].state_value, 100)
        # Check initial computation
        self.assertFalse(user_state.states["notifications_enabled"].state_value)

    def test_get_entry_at_path(self):
        user_state = UserState.initialize(self._get_sample_raw_state())
        entry = user_state._get_entry_at_path(["notifications_enabled", "email_enabled"])
        self.assertIsNotNone(entry)
        self.assertFalse(entry.state_value)
        self.assertIsNone(user_state._get_entry_at_path(["non_existent_key"]))

    def test_state_update_and_parent_recompute(self):
        user_state = UserState.initialize(self._get_sample_raw_state())
        
        # Update child, parent should recompute via OR logic
        updates = [StateUpdate(keys=["notifications_enabled", "sms_enabled"], update_value=True, set_parents=True)]
        changed = user_state.state_update(updates)
        
        self.assertTrue(changed)
        self.assertTrue(user_state.states["notifications_enabled"].sub_states["sms_enabled"].state_value)
        self.assertTrue(user_state.states["notifications_enabled"].state_value) # Parent becomes True

    def test_state_update_no_parent_recompute(self):
        user_state = UserState.initialize(self._get_sample_raw_state())
        updates = [StateUpdate(keys=["notifications_enabled", "sms_enabled"], update_value=True, set_parents=False)]
        user_state.state_update(updates)
        self.assertFalse(user_state.states["notifications_enabled"].state_value) # Parent not recomputed

    def test_state_update_invalid_path(self):
        user_state = UserState.initialize(self._get_sample_raw_state())
        updates = [StateUpdate(keys=["invalid", "path"], update_value=True)]
        with self.assertRaisesRegex(ValueError, "Invalid path: Could not find state entry"):
            user_state.state_update(updates)

    def test_state_update_type_mismatch(self):
        user_state = UserState.initialize(self._get_sample_raw_state())
        updates = [StateUpdate(keys=["user_score"], update_value="not_an_int")] # user_score is int
        with self.assertRaisesRegex(ValueError, "does not match target type 'int'"):
            user_state.state_update(updates)

    def test_get_state(self):
        user_state = UserState.initialize(self._get_sample_raw_state())
        
        # Get all (returns UserStateEntry)
        all_data = user_state.get_state([])
        self.assertEqual(all_data["user_score"], 100) # Expect direct value
        self.assertFalse(all_data["notifications_enabled"]) # Expect direct value
        
        # Get specific paths
        specific_data = user_state.get_state([["notifications_enabled", "email_enabled"], ["user_score"]])
        self.assertFalse(specific_data["notifications_enabled/email_enabled"]) # Expect direct value
        self.assertEqual(specific_data["user_score"], 100) # Expect direct value


class TestInitializeUserStateRequest(unittest.TestCase):
    """Test the InitializeUserStateRequest model and validation."""

    def test_valid_linkedin_ghostwriter_only(self):
        """Test valid request for linkedin_ghostwriter only."""
        request = InitializeUserStateRequest(
            linkedin_profile_url="https://linkedin.com/in/testuser",
            initialize_linkedin_ghostwriter=True,
            initialize_ai_answer_optimization=False
        )
        self.assertEqual(str(request.linkedin_profile_url), "https://linkedin.com/in/testuser")
        self.assertTrue(request.initialize_linkedin_ghostwriter)
        self.assertFalse(request.initialize_ai_answer_optimization)

    def test_valid_ai_answer_optimization_only(self):
        """Test valid request for ai_answer_optimization only."""
        request = InitializeUserStateRequest(
            company_name="Test Company",
            initialize_linkedin_ghostwriter=False,
            initialize_ai_answer_optimization=True
        )
        self.assertEqual(request.company_name, "Test Company")
        self.assertFalse(request.initialize_linkedin_ghostwriter)
        self.assertTrue(request.initialize_ai_answer_optimization)

    def test_valid_both_applications(self):
        """Test valid request for both applications."""
        request = InitializeUserStateRequest(
            linkedin_profile_url="https://linkedin.com/in/testuser",
            company_name="Test Company",
            initialize_linkedin_ghostwriter=True,
            initialize_ai_answer_optimization=True
        )
        self.assertEqual(str(request.linkedin_profile_url), "https://linkedin.com/in/testuser")
        self.assertEqual(request.company_name, "Test Company")
        self.assertTrue(request.initialize_linkedin_ghostwriter)
        self.assertTrue(request.initialize_ai_answer_optimization)

    def test_missing_linkedin_profile_url(self):
        """Test validation error when linkedin_profile_url is missing but linkedin_ghostwriter is enabled."""
        with self.assertRaisesRegex(ValueError, "linkedin_profile_url is required"):
            InitializeUserStateRequest(
                initialize_linkedin_ghostwriter=True,
                initialize_ai_answer_optimization=False
            )

    def test_missing_company_name(self):
        """Test validation error when company_name is missing but ai_answer_optimization is enabled."""
        with self.assertRaisesRegex(ValueError, "company_name is required"):
            InitializeUserStateRequest(
                initialize_linkedin_ghostwriter=False,
                initialize_ai_answer_optimization=True
            )

    def test_both_applications_disabled(self):
        """Test validation error when both applications are disabled."""
        with self.assertRaisesRegex(ValueError, "At least one of initialize_linkedin_ghostwriter or initialize_ai_answer_optimization must be True"):
            InitializeUserStateRequest(
                initialize_linkedin_ghostwriter=False,
                initialize_ai_answer_optimization=False
            )

    def test_defaults(self):
        """Test default values."""
        request = InitializeUserStateRequest(
            linkedin_profile_url="https://linkedin.com/in/testuser"
        )
        self.assertTrue(request.initialize_linkedin_ghostwriter)  # Default True
        self.assertFalse(request.initialize_ai_answer_optimization)  # Default False


class TestUpdateUserStateRequest(unittest.TestCase):
    """Test the UpdateUserStateRequest model and validation."""

    def test_valid_with_target_application(self):
        """Test valid request with target_application."""
        updates = [StateUpdate(keys=["is_active"], update_value=True)]
        request = UpdateUserStateRequest(
            updates=updates,
            target_application="linkedin_ghostwriter"
        )
        self.assertEqual(request.target_application, "linkedin_ghostwriter")
        self.assertEqual(len(request.updates), 1)

    def test_valid_without_target_application(self):
        """Test valid request without target_application."""
        updates = [StateUpdate(keys=["linkedin_ghostwriter", "is_active"], update_value=True)]
        request = UpdateUserStateRequest(updates=updates)
        self.assertIsNone(request.target_application)

    def test_validation_error_with_target_application(self):
        """Test validation error when target_application is specified but paths include app names."""
        updates = [StateUpdate(keys=["linkedin_ghostwriter", "is_active"], update_value=True)]
        with self.assertRaisesRegex(ValueError, "update paths should be relative to the app"):
            UpdateUserStateRequest(
                updates=updates,
                target_application="linkedin_ghostwriter"
            )

    def test_validation_error_different_app_in_path(self):
        """Test validation error when target_application conflicts with path."""
        updates = [StateUpdate(keys=["ai_answer_optimization", "is_active"], update_value=True)]
        with self.assertRaisesRegex(ValueError, "update paths should be relative to the app"):
            UpdateUserStateRequest(
                updates=updates,
                target_application="linkedin_ghostwriter"
            )


class TestApplicationModels(unittest.TestCase):
    """Test the new application-related models."""

    def test_application_active_status(self):
        """Test ApplicationActiveStatus model."""
        status = ApplicationActiveStatus(
            linkedin_ghostwriter_active=True,
            ai_answer_optimization_active=False
        )
        self.assertTrue(status.linkedin_ghostwriter_active)
        self.assertFalse(status.ai_answer_optimization_active)

    def test_application_active_status_defaults(self):
        """Test ApplicationActiveStatus model defaults."""
        status = ApplicationActiveStatus()
        self.assertFalse(status.linkedin_ghostwriter_active)
        self.assertFalse(status.ai_answer_optimization_active)

    def test_document_application_status(self):
        """Test DocumentApplicationStatus model."""
        app_status = ApplicationActiveStatus(linkedin_ghostwriter_active=True)
        doc_status = DocumentApplicationStatus(
            docname="test_doc",
            application_status=app_status
        )
        self.assertEqual(doc_status.docname, "test_doc")
        self.assertTrue(doc_status.application_status.linkedin_ghostwriter_active)

    def test_get_user_state_response(self):
        """Test GetUserStateResponse model."""
        response = GetUserStateResponse(
            retrieved_states={"key": "value"},
            available_applications=["linkedin_ghostwriter", "ai_answer_optimization"]
        )
        self.assertEqual(response.retrieved_states, {"key": "value"})
        self.assertEqual(response.available_applications, ["linkedin_ghostwriter", "ai_answer_optimization"])

    def test_get_user_state_response_defaults(self):
        """Test GetUserStateResponse model defaults."""
        response = GetUserStateResponse(retrieved_states={"key": "value"})
        self.assertEqual(response.available_applications, [])


class TestLinkedInGhostwriterState(unittest.TestCase):
    """Test the linkedin_ghostwriter application state structure."""

    def _get_linkedin_ghostwriter_state(self):
        """Helper to create a linkedin_ghostwriter state."""
        return {
            "states": {
                "linkedin_ghostwriter": {
                    "state_value_type_name": "dict",
                    "description": "LinkedIn ghostwriter application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the LinkedIn ghostwriter is active.",
                            "state_value": True
                        },
                        "linkedin_profile_url": {
                            "state_value_type_name": "str",
                            "description": "The user's LinkedIn profile URL.",
                            "state_value": "https://linkedin.com/in/testuser"
                        },
                        "entity_username": {
                            "state_value_type_name": "str",
                            "description": "The username from LinkedIn URL.",
                            "state_value": "testuser"
                        },
                        "onboarded": {
                            "state_value_type_name": "bool",
                            "description": "Overall onboarding completion status.",
                            "state_value": False,
                            "combine_values_from_sub_states": True,
                            "sub_states_combine_logic": "AND",
                            "sub_states": {
                                "page_1_linkedin": {
                                    "state_value_type_name": "bool",
                                    "description": "LinkedIn URL input.",
                                    "state_value": False
                                },
                                "page_2_sources": {
                                    "state_value_type_name": "bool",
                                    "description": "Upload source docs.",
                                    "state_value": False
                                }
                            }
                        }
                    }
                }
            }
        }

    def test_linkedin_ghostwriter_initialization(self):
        """Test initialization of linkedin_ghostwriter state."""
        user_state = UserState.initialize(self._get_linkedin_ghostwriter_state())
        self.assertIn("linkedin_ghostwriter", user_state.states)
        
        # Test accessing nested states
        result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
        self.assertTrue(result["linkedin_ghostwriter/is_active"])
        
        result = user_state.get_state([["linkedin_ghostwriter", "linkedin_profile_url"]])
        self.assertEqual(result["linkedin_ghostwriter/linkedin_profile_url"], "https://linkedin.com/in/testuser")

    def test_linkedin_ghostwriter_onboarding_logic(self):
        """Test the onboarding AND logic in linkedin_ghostwriter."""
        user_state = UserState.initialize(self._get_linkedin_ghostwriter_state())
        
        # Initially, onboarded should be False (AND of False, False)
        result = user_state.get_state([["linkedin_ghostwriter", "onboarded"]])
        self.assertFalse(result["linkedin_ghostwriter/onboarded"])
        
        # Update one page to complete
        updates = [StateUpdate(keys=["linkedin_ghostwriter", "onboarded", "page_1_linkedin"], update_value=True, set_parents=True)]
        user_state.state_update(updates)
        
        # Should still be False (AND of True, False)
        result = user_state.get_state([["linkedin_ghostwriter", "onboarded"]])
        self.assertFalse(result["linkedin_ghostwriter/onboarded"])
        
        # Update second page to complete
        updates = [StateUpdate(keys=["linkedin_ghostwriter", "onboarded", "page_2_sources"], update_value=True, set_parents=True)]
        user_state.state_update(updates)
        
        # Should now be True (AND of True, True)
        result = user_state.get_state([["linkedin_ghostwriter", "onboarded"]])
        self.assertTrue(result["linkedin_ghostwriter/onboarded"])

    def test_linkedin_ghostwriter_state_update(self):
        """Test updating linkedin_ghostwriter states."""
        user_state = UserState.initialize(self._get_linkedin_ghostwriter_state())
        
        # Update is_active
        updates = [StateUpdate(keys=["linkedin_ghostwriter", "is_active"], update_value=False)]
        changed = user_state.state_update(updates)
        self.assertTrue(changed)
        
        result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
        self.assertFalse(result["linkedin_ghostwriter/is_active"])


class TestAIAnswerOptimizationState(unittest.TestCase):
    """Test the ai_answer_optimization application state structure."""

    def _get_ai_answer_optimization_state(self):
        """Helper to create an ai_answer_optimization state."""
        return {
            "states": {
                "ai_answer_optimization": {
                    "state_value_type_name": "dict",
                    "description": "AI answer optimization application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the AI answer optimization is active.",
                            "state_value": True
                        },
                        "company_name": {
                            "state_value_type_name": "str",
                            "description": "The company name for optimization.",
                            "state_value": "Test Company"
                        }
                    }
                }
            }
        }

    def test_ai_answer_optimization_initialization(self):
        """Test initialization of ai_answer_optimization state."""
        user_state = UserState.initialize(self._get_ai_answer_optimization_state())
        self.assertIn("ai_answer_optimization", user_state.states)
        
        # Test accessing nested states
        result = user_state.get_state([["ai_answer_optimization", "is_active"]])
        self.assertTrue(result["ai_answer_optimization/is_active"])
        
        result = user_state.get_state([["ai_answer_optimization", "company_name"]])
        self.assertEqual(result["ai_answer_optimization/company_name"], "Test Company")

    def test_ai_answer_optimization_state_update(self):
        """Test updating ai_answer_optimization states."""
        user_state = UserState.initialize(self._get_ai_answer_optimization_state())
        
        # Update company_name
        updates = [StateUpdate(keys=["ai_answer_optimization", "company_name"], update_value="Updated Company")]
        changed = user_state.state_update(updates)
        self.assertTrue(changed)
        
        result = user_state.get_state([["ai_answer_optimization", "company_name"]])
        self.assertEqual(result["ai_answer_optimization/company_name"], "Updated Company")


class TestBothApplicationsState(unittest.TestCase):
    """Test state structure with both applications present."""

    def _get_both_applications_state(self):
        """Helper to create a state with both applications."""
        return {
            "states": {
                "linkedin_ghostwriter": {
                    "state_value_type_name": "dict",
                    "description": "LinkedIn ghostwriter application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the LinkedIn ghostwriter is active.",
                            "state_value": True
                        },
                        "linkedin_profile_url": {
                            "state_value_type_name": "str",
                            "description": "The user's LinkedIn profile URL.",
                            "state_value": "https://linkedin.com/in/testuser"
                        }
                    }
                },
                "ai_answer_optimization": {
                    "state_value_type_name": "dict",
                    "description": "AI answer optimization application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the AI answer optimization is active.",
                            "state_value": False
                        },
                        "company_name": {
                            "state_value_type_name": "str",
                            "description": "The company name for optimization.",
                            "state_value": "Test Company"
                        }
                    }
                }
            }
        }

    def test_both_applications_initialization(self):
        """Test initialization with both applications."""
        user_state = UserState.initialize(self._get_both_applications_state())
        self.assertIn("linkedin_ghostwriter", user_state.states)
        self.assertIn("ai_answer_optimization", user_state.states)
        
        # Test accessing both applications
        linkedin_result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
        self.assertTrue(linkedin_result["linkedin_ghostwriter/is_active"])
        
        ai_result = user_state.get_state([["ai_answer_optimization", "is_active"]])
        self.assertFalse(ai_result["ai_answer_optimization/is_active"])

    def test_both_applications_get_all_states(self):
        """Test getting all states when both applications are present."""
        user_state = UserState.initialize(self._get_both_applications_state())
        
        # Get all top-level states
        all_states = user_state.get_state([])
        self.assertIn("linkedin_ghostwriter", all_states)
        self.assertIn("ai_answer_optimization", all_states)
        
        # The values should be the dict values (empty dicts in this case)
        self.assertEqual(all_states["linkedin_ghostwriter"], {})
        self.assertEqual(all_states["ai_answer_optimization"], {})

    def test_both_applications_multiple_path_retrieval(self):
        """Test retrieving multiple paths across both applications."""
        user_state = UserState.initialize(self._get_both_applications_state())
        
        paths = [
            ["linkedin_ghostwriter", "is_active"],
            ["ai_answer_optimization", "company_name"],
            ["linkedin_ghostwriter", "linkedin_profile_url"]
        ]
        
        result = user_state.get_state(paths)
        self.assertTrue(result["linkedin_ghostwriter/is_active"])
        self.assertEqual(result["ai_answer_optimization/company_name"], "Test Company")
        self.assertEqual(result["linkedin_ghostwriter/linkedin_profile_url"], "https://linkedin.com/in/testuser")


class TestStateUpdateWithTargetApplication(unittest.TestCase):
    """Test state updates with target_application functionality."""

    def _get_both_applications_state(self):
        """Helper to create a state with both applications."""
        return {
            "states": {
                "linkedin_ghostwriter": {
                    "state_value_type_name": "dict",
                    "description": "LinkedIn ghostwriter application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the LinkedIn ghostwriter is active.",
                            "state_value": True
                        }
                    }
                },
                "ai_answer_optimization": {
                    "state_value_type_name": "dict",
                    "description": "AI answer optimization application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the AI answer optimization is active.",
                            "state_value": False
                        }
                    }
                }
            }
        }

    def test_update_with_target_application_linkedin(self):
        """Test updating with target_application set to linkedin_ghostwriter."""
        user_state = UserState.initialize(self._get_both_applications_state())
        
        # Create updates as if coming from UpdateUserStateRequest with target_application="linkedin_ghostwriter"
        original_updates = [StateUpdate(keys=["is_active"], update_value=False)]
        
        # Simulate the target_application logic
        processed_updates = []
        for update in original_updates:
            prefixed_keys = ["linkedin_ghostwriter"] + update.keys
            processed_update = StateUpdate(
                keys=prefixed_keys,
                update_value=update.update_value,
                set_parents=update.set_parents
            )
            processed_updates.append(processed_update)
        
        changed = user_state.state_update(processed_updates)
        self.assertTrue(changed)
        
        # Verify the update
        result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
        self.assertFalse(result["linkedin_ghostwriter/is_active"])
        
        # Verify ai_answer_optimization was not affected
        result = user_state.get_state([["ai_answer_optimization", "is_active"]])
        self.assertFalse(result["ai_answer_optimization/is_active"])

    def test_update_with_target_application_ai(self):
        """Test updating with target_application set to ai_answer_optimization."""
        user_state = UserState.initialize(self._get_both_applications_state())
        
        # Create updates as if coming from UpdateUserStateRequest with target_application="ai_answer_optimization"
        original_updates = [StateUpdate(keys=["is_active"], update_value=True)]
        
        # Simulate the target_application logic
        processed_updates = []
        for update in original_updates:
            prefixed_keys = ["ai_answer_optimization"] + update.keys
            processed_update = StateUpdate(
                keys=prefixed_keys,
                update_value=update.update_value,
                set_parents=update.set_parents
            )
            processed_updates.append(processed_update)
        
        changed = user_state.state_update(processed_updates)
        self.assertTrue(changed)
        
        # Verify the update
        result = user_state.get_state([["ai_answer_optimization", "is_active"]])
        self.assertTrue(result["ai_answer_optimization/is_active"])
        
        # Verify linkedin_ghostwriter was not affected
        result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
        self.assertTrue(result["linkedin_ghostwriter/is_active"])

    def test_update_without_target_application(self):
        """Test updating without target_application (full paths)."""
        user_state = UserState.initialize(self._get_both_applications_state())
        
        # Update both applications directly with full paths
        updates = [
            StateUpdate(keys=["linkedin_ghostwriter", "is_active"], update_value=False),
            StateUpdate(keys=["ai_answer_optimization", "is_active"], update_value=True)
        ]
        
        changed = user_state.state_update(updates)
        self.assertTrue(changed)
        
        # Verify both updates
        linkedin_result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
        self.assertFalse(linkedin_result["linkedin_ghostwriter/is_active"])
        
        ai_result = user_state.get_state([["ai_answer_optimization", "is_active"]])
        self.assertTrue(ai_result["ai_answer_optimization/is_active"])


class TestActiveStateDetection(unittest.TestCase):
    """Test active state detection logic for both applications."""

    def test_linkedin_ghostwriter_active_only(self):
        """Test active detection when only linkedin_ghostwriter is active."""
        state_dict = {
            "states": {
                "linkedin_ghostwriter": {
                    "state_value_type_name": "dict",
                    "description": "LinkedIn ghostwriter application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the LinkedIn ghostwriter is active.",
                            "state_value": True
                        }
                    }
                }
            }
        }
        
        user_state = UserState.initialize(state_dict)
        
        # Test active detection logic
        linkedin_active = False
        ai_active = False
        
        try:
            linkedin_result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
            if linkedin_result.get("linkedin_ghostwriter/is_active"):
                linkedin_active = True
        except Exception:
            pass
        
        try:
            ai_result = user_state.get_state([["ai_answer_optimization", "is_active"]])
            if ai_result.get("ai_answer_optimization/is_active"):
                ai_active = True
        except Exception:
            pass
        
        self.assertTrue(linkedin_active)
        self.assertFalse(ai_active)

    def test_ai_answer_optimization_active_only(self):
        """Test active detection when only ai_answer_optimization is active."""
        state_dict = {
            "states": {
                "ai_answer_optimization": {
                    "state_value_type_name": "dict",
                    "description": "AI answer optimization application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the AI answer optimization is active.",
                            "state_value": True
                        }
                    }
                }
            }
        }
        
        user_state = UserState.initialize(state_dict)
        
        # Test active detection logic
        linkedin_active = False
        ai_active = False
        
        try:
            linkedin_result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
            if linkedin_result.get("linkedin_ghostwriter/is_active"):
                linkedin_active = True
        except Exception:
            pass
        
        try:
            ai_result = user_state.get_state([["ai_answer_optimization", "is_active"]])
            if ai_result.get("ai_answer_optimization/is_active"):
                ai_active = True
        except Exception:
            pass
        
        self.assertFalse(linkedin_active)
        self.assertTrue(ai_active)

    def test_both_applications_active(self):
        """Test active detection when both applications are active."""
        state_dict = {
            "states": {
                "linkedin_ghostwriter": {
                    "state_value_type_name": "dict",
                    "description": "LinkedIn ghostwriter application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the LinkedIn ghostwriter is active.",
                            "state_value": True
                        }
                    }
                },
                "ai_answer_optimization": {
                    "state_value_type_name": "dict",
                    "description": "AI answer optimization application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the AI answer optimization is active.",
                            "state_value": True
                        }
                    }
                }
            }
        }
        
        user_state = UserState.initialize(state_dict)
        
        # Test active detection logic
        linkedin_active = False
        ai_active = False
        
        try:
            linkedin_result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
            if linkedin_result.get("linkedin_ghostwriter/is_active"):
                linkedin_active = True
        except Exception:
            pass
        
        try:
            ai_result = user_state.get_state([["ai_answer_optimization", "is_active"]])
            if ai_result.get("ai_answer_optimization/is_active"):
                ai_active = True
        except Exception:
            pass
        
        self.assertTrue(linkedin_active)
        self.assertTrue(ai_active)

    def test_neither_application_active(self):
        """Test active detection when neither application is active."""
        state_dict = {
            "states": {
                "linkedin_ghostwriter": {
                    "state_value_type_name": "dict",
                    "description": "LinkedIn ghostwriter application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the LinkedIn ghostwriter is active.",
                            "state_value": False
                        }
                    }
                },
                "ai_answer_optimization": {
                    "state_value_type_name": "dict",
                    "description": "AI answer optimization application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the AI answer optimization is active.",
                            "state_value": False
                        }
                    }
                }
            }
        }
        
        user_state = UserState.initialize(state_dict)
        
        # Test active detection logic
        linkedin_active = False
        ai_active = False
        
        try:
            linkedin_result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
            if linkedin_result.get("linkedin_ghostwriter/is_active"):
                linkedin_active = True
        except Exception:
            pass
        
        try:
            ai_result = user_state.get_state([["ai_answer_optimization", "is_active"]])
            if ai_result.get("ai_answer_optimization/is_active"):
                ai_active = True
        except Exception:
            pass
        
        self.assertFalse(linkedin_active)
        self.assertFalse(ai_active)


class TestApplicationStateStructure(unittest.TestCase):
    """Test the overall application state structure and edge cases."""

    def test_available_applications_detection(self):
        """Test detecting available applications in a state."""
        state_dict = {
            "states": {
                "linkedin_ghostwriter": {
                    "state_value_type_name": "dict",
                    "description": "LinkedIn ghostwriter application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the LinkedIn ghostwriter is active.",
                            "state_value": True
                        }
                    }
                },
                "ai_answer_optimization": {
                    "state_value_type_name": "dict",
                    "description": "AI answer optimization application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the AI answer optimization is active.",
                            "state_value": False
                        }
                    }
                }
            }
        }
        
        user_state = UserState.initialize(state_dict)
        
        # Simulate the available applications detection logic
        available_applications = []
        if "linkedin_ghostwriter" in user_state.states:
            available_applications.append("linkedin_ghostwriter")
        if "ai_answer_optimization" in user_state.states:
            available_applications.append("ai_answer_optimization")
        
        self.assertEqual(set(available_applications), {"linkedin_ghostwriter", "ai_answer_optimization"})

    def test_missing_application_handling(self):
        """Test handling when one application is missing."""
        state_dict = {
            "states": {
                "linkedin_ghostwriter": {
                    "state_value_type_name": "dict",
                    "description": "LinkedIn ghostwriter application state.",
                    "state_value": {},
                    "sub_states": {
                        "is_active": {
                            "state_value_type_name": "bool",
                            "description": "Whether the LinkedIn ghostwriter is active.",
                            "state_value": True
                        }
                    }
                }
                # ai_answer_optimization is missing
            }
        }
        
        user_state = UserState.initialize(state_dict)
        
        # Test that missing application doesn't cause errors
        linkedin_result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
        self.assertTrue(linkedin_result["linkedin_ghostwriter/is_active"])
        
        # Test that accessing missing application returns None
        ai_result = user_state.get_state([["ai_answer_optimization", "is_active"]])
        self.assertIsNone(ai_result["ai_answer_optimization/is_active"])

    def test_empty_state_handling(self):
        """Test handling of completely empty state."""
        state_dict = {"states": {}}
        
        user_state = UserState.initialize(state_dict)
        
        # Test that empty state doesn't cause errors
        all_states = user_state.get_state([])
        self.assertEqual(all_states, {})
        
        # Test that accessing non-existent applications returns None
        linkedin_result = user_state.get_state([["linkedin_ghostwriter", "is_active"]])
        self.assertIsNone(linkedin_result["linkedin_ghostwriter/is_active"])
        
        ai_result = user_state.get_state([["ai_answer_optimization", "is_active"]])
        self.assertIsNone(ai_result["ai_answer_optimization/is_active"])


if __name__ == "__main__":
    unittest.main()
