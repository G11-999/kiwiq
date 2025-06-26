import unittest

from pydantic import HttpUrl, ValidationError

# Models and services to test
from kiwi_app.workflow_app.app_state import (
    UserStateEntry,
    UserState,
    StateUpdate,
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

if __name__ == "__main__":
    unittest.main()
