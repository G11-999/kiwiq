from sqlalchemy.orm import selectinload, joinedload, subqueryload
from pprint import pprint
from typing import List, Tuple, Type, Dict, Callable # Added Type hints
from sqlalchemy.orm.interfaces import LoaderOption # Type hint for options

# ==============================================================================
# Functions to Build Eager Loading Options Using Provided Models
#
# Assumptions:
#   - The query root model is defined by the base model of the first tuple.
#   - All dotted relation strings should ultimately originate from the query root.
#
# Input Example:
#
#     load_relations = [
#         (models.User, "organization_links"), 
#         (models.UserOrganizationRole, "organization_links.organization"), 
#         (models.UserOrganizationRole, "organization_links.role"),
#         (models.User, "other_rels"),
#     ]
#
# Expected Tree for Query Root (User):
#
#            User
#            ├── organization_links { _model: models.UserOrganizationRole }
#            │       ├── organization
#            │       └── role
#            └── other_rels
#
# Diagram Explanation:
#   - The branch "organization_links" comes from models.User.
#   - The nested dotted paths (e.g. "organization_links.organization") come from
#     a tuple whose provided model is models.UserOrganizationRole. In that branch,
#     the special key "_model" stores models.UserOrganizationRole.
#
# These are later converted into options:
#
#    selectinload(User.organization_links)
#         .options(
#             selectinload(UserOrganizationRole.organization),
#             selectinload(UserOrganizationRole.role)
#         )
#    selectinload(User.other_rels)
#
# ==============================================================================
# def build_load_tree(load_relations):
#     """
#     Build a nested dictionary (tree) representing the dotted relationship chains,
#     storing the provided model in the node under the key "_model" when the base model
#     is not the query root.
    
#     Parameters:
#         load_relations (List[Tuple[Model, str]]):
#             A list of tuples where:
#               - The first element is a model class (the provided model for this relation).
#               - The second element is a dotted string specifying nested relationships.
    
#     Remapping Logic:
#       - The query root is assumed to be the base model from the first tuple.
#       - For any tuple where the base model differs from the query root, we assume
#         that the dotted relation starts with a prefix that is an attribute on the query root.
#         In that case, we store the provided model in that branch under "_model".
    
#     Example Input:
#         load_relations = [
#             (User, "organization_links"),
#             (UserOrganizationRole, "organization_links.organization"),
#             (UserOrganizationRole, "organization_links.role"),
#             (User, "other_rels"),
#         ]
    
#     Expected Tree for Query Root (User):
#         {
#             "organization_links": {
#                 "_model": models.UserOrganizationRole,
#                 "organization": {},
#                 "role": {}
#             },
#             "other_rels": {}
#         }
    
#     Diagram:
#             User
#             ├── organization_links { _model: models.UserOrganizationRole }
#             │       ├── organization
#             │       └── role
#             └── other_rels
    
#     Returns:
#         trees (dict): A dictionary mapping the query root to its nested relationship tree.
#         query_root (Model): The query root model.
    
#     Edge Cases:
#       - An empty relation string raises a ValueError.
#     """
#     if not load_relations:
#         raise ValueError("load_relations must not be empty")
    
#     # The query root is the base model of the first tuple.
#     query_root = load_relations[0][0]
#     trees = {query_root: {}}
    
#     for base_model, rel_str in load_relations:
#         if not rel_str:
#             raise ValueError(f"Empty relation string provided for base model {base_model.__name__}")
#         parts = rel_str.split(".")
        
#         current = trees[query_root]
#         if base_model != query_root:
#             # For tuples with a provided model different from query root,
#             # process the first part specially.
#             key = parts[0]
#             current = current.setdefault(key, {})
#             # Store the provided model in this branch.
#             if "_model" in current:
#                 if current["_model"] != base_model:
#                     raise ValueError(f"Inconsistent provided model for branch '{key}'")
#             else:
#                 current["_model"] = base_model
#             # Process the remaining parts, if any.
#             for part in parts[1:]:
#                 current = current.setdefault(part, {})
#         else:
#             # For tuples where base model equals query root, process all parts normally.
#             for part in parts:
#                 current = current.setdefault(part, {})
    
#     print("Constructed Trees:")
#     for model, tree in trees.items():
#         print(f"Query Root: {model.__name__}")
#         pprint(tree, indent=4)
#     return trees, query_root

# def build_option(model, tree):
#     """
#     Recursively build SQLAlchemy selectinload options from the relationship tree.
    
#     Parameters:
#         model (Model):
#             The model class from which to retrieve the relationship attribute.
#         tree (dict):
#             A nested dictionary representing the relationship chain. If a branch was
#             remapped using a provided model, that model is stored under the key "_model".
    
#     Example:
#         For model User and tree:
#             {
#                 "organization_links": {
#                     "_model": models.UserOrganizationRole,
#                     "organization": {},
#                     "role": {}
#                 },
#                 "other_rels": {}
#             }
#         The function returns options equivalent to:
#             selectinload(User.organization_links)
#                 .options(
#                     selectinload(UserOrganizationRole.organization),
#                     selectinload(UserOrganizationRole.role)
#                 )
#             and
#             selectinload(User.other_rels)
    
#     Returns:
#         options (List): A list of SQLAlchemy eager loading option objects.
    
#     Raises:
#         AttributeError: If the model does not have the requested relationship attribute.
#         Exception: If a nested branch requires a provided model and none is present.
#     """
#     options = []
#     for rel_attr, subtree in tree.items():
#         # Skip any special keys.
#         if rel_attr == "_model":
#             continue
        
#         try:
#             attr = getattr(model, rel_attr)
#         except AttributeError as e:
#             raise AttributeError(f"Model {model.__name__} does not have attribute '{rel_attr}'") from e
        
#         option = selectinload(attr)
#         if subtree:
#             # For nested relationships, use the provided model if available.
#             provided_model = subtree.get("_model", None)
#             if provided_model is None:
#                 # If no provided model exists but nested keys are present, we cannot determine the target.
#                 if any(key for key in subtree if key != "_model"):
#                     raise Exception(f"Missing provided model for nested relationship {model.__name__}.{rel_attr}")
#                 child_options = []
#             else:
#                 child_options = build_option(provided_model, subtree)
#             if child_options:
#                 option = option.options(*child_options)
#         options.append(option)
#     return options

# def build_load_options(load_relations):
#     """
#     Convert a list of (base_model, dotted_relation) tuples into a flat list of SQLAlchemy
#     eager loading options to be used on a query.
    
#     Parameters:
#         load_relations (List[Tuple[Model, str]]):
#             A list of tuples where:
#               - The first element is a model class (the provided model for the relation).
#               - The second element is a dotted string specifying nested relationships.
#             Note: Tuples with a base model not equal to the query root are remapped.
    
#     Process:
#         1. Build a tree (nested dictionary) for the query root model, remapping tuples as needed.
#            Provided models are stored in each node under "_model".
#         2. Recursively convert the tree into selectinload options.
    
#     Example Input:
#         load_relations = [
#             (User, "organization_links"),
#             (UserOrganizationRole, "organization_links.organization"),
#             (UserOrganizationRole, "organization_links.role"),
#             (User, "other_rels"),
#         ]
    
#     Expected Diagram for Query Root (User):
#             User
#             ├── organization_links { _model: models.UserOrganizationRole }
#             │       ├── organization
#             │       └── role
#             └── other_rels
    
#     Returns:
#         options (List): A list of SQLAlchemy eager loading options.
    
#     Edge Cases:
#         - Empty load_relations raises ValueError.
#         - Inconsistent provided models for the same branch raise ValueError.
#         - Missing provided models for nested relationships raises Exception.
#     """
#     trees, query_root = build_load_tree(load_relations)
#     options = build_option(query_root, trees[query_root])
#     print(f"Eager load options for query root {query_root.__name__}:")
#     pprint(options)
#     return options

# ==============================================================================
# Sample Usage:
#
# Given input:
#
#     load_relations = [
#         (models.User, "organization_links"), 
#         (models.UserOrganizationRole, "organization_links.organization"), 
#         (models.UserOrganizationRole, "organization_links.role"),
#         (models.User, "other_rels"),
#     ]
#
# The code remaps tuples with base model models.UserOrganizationRole to the query root,
# resulting in the unified tree:
#
#            User
#            ├── organization_links { _model: models.UserOrganizationRole }
#            │       ├── organization
#            │       └── role
#            └── other_rels
#
# Which produces eager loading options:
#
#    selectinload(User.organization_links)
#         .options(
#             selectinload(UserOrganizationRole.organization),
#             selectinload(UserOrganizationRole.role)
#         )
#    selectinload(User.other_rels)
#
# These options can then be applied to a query that selects from models.User.
# ==============================================================================








# Assume models are defined elsewhere, e.g.:
# class User: pass
# class Organization: pass
# class Role: pass
# class UserOrganizationRole: pass
# Or import them:
# import kiwi_app.auth.models as models

# ==============================================================================
# Functions to Build Eager Loading Options Using Provided Models
# Input format and tree structure remain the same as described previously.
# ==============================================================================

def build_load_tree(load_relations: List[Tuple[Type, str]]) -> Tuple[Dict[Type, Dict], Type]:
    """
    Build a nested dictionary (tree) representing the dotted relationship chains,
    storing the provided model in the node under the key "_model" when the base model
    is not the query root.

    Parameters:
        load_relations (List[Tuple[Model, str]]):
            A list of tuples where:
              - The first element is a model class (the provided model for this relation).
              - The second element is a dotted string specifying nested relationships.

    Returns:
        trees (dict): A dictionary mapping the query root to its nested relationship tree.
        query_root (Model): The query root model.

    (Implementation is the same as before)
    """
    if not load_relations:
        raise ValueError("load_relations must not be empty")

    # The query root is the base model of the first tuple.
    query_root = load_relations[0][0]
    trees = {query_root: {}}

    for base_model, rel_str in load_relations:
        if not rel_str:
            raise ValueError(f"Empty relation string provided for base model {base_model.__name__}")
        parts = rel_str.split(".")

        current = trees[query_root]
        # Determine the target node based on whether the base_model matches the query_root
        target_node_for_model_storage = current
        prefix_processed = False

        if base_model != query_root:
            # For tuples with a provided model different from query root,
            # process the first part specially to potentially store the model.
            key = parts[0]
            target_node_for_model_storage = current.setdefault(key, {})

            # Store the provided model in this branch if not already consistently set.
            if "_model" in target_node_for_model_storage:
                if target_node_for_model_storage["_model"] != base_model:
                    raise ValueError(f"Inconsistent provided model for branch '{key}'. "
                                     f"Existing: {target_node_for_model_storage['_model'].__name__}, "
                                     f"New: {base_model.__name__}")
            else:
                target_node_for_model_storage["_model"] = base_model

            # Move processing to the rest of the parts starting from the identified node
            current = target_node_for_model_storage
            parts_to_process = parts[1:] # Process remaining parts relative to this node
        else:
             # For tuples where base model equals query root, process all parts normally.
             parts_to_process = parts # Process all parts relative to root

        # Process the designated parts to build the subtree
        for part in parts_to_process:
             current = current.setdefault(part, {})


    # print("\nConstructed Load Tree:")
    # for model, tree in trees.items():
    #     print(f"Query Root: {model.__name__}")
    #     pprint(tree, indent=4)
    return trees, query_root

def build_option(model: Type, tree: Dict, strategy_func: Callable) -> List[LoaderOption]:
    """
    Recursively build SQLAlchemy eager loading options from the relationship tree
    using the specified loading strategy function (selectinload or joinedload).

    Parameters:
        model (Model):
            The model class from which to retrieve the relationship attribute.
        tree (dict):
            A nested dictionary representing the relationship chain. If a branch was
            remapped using a provided model, that model is stored under "_model".
        strategy_func (Callable):
            The SQLAlchemy loading function to use (e.g., selectinload, joinedload).

    Returns:
        options (List[LoaderOption]): A list of SQLAlchemy eager loading option objects.

    Raises:
        AttributeError: If the model does not have the requested relationship attribute.
        Exception: If a nested branch requires a provided model and none is present.
    """
    options = []
    for rel_attr, subtree in tree.items():
        # Skip any special keys.
        if rel_attr == "_model":
            continue

        try:
            # Get the relationship attribute object from the current model
            attr = getattr(model, rel_attr)
        except AttributeError as e:
            raise AttributeError(f"Model {model.__name__} does not have attribute '{rel_attr}'") from e

        # Apply the chosen loading strategy function (selectinload or joinedload)
        option = strategy_func(attr)

        # Check if there are nested relationships to load
        has_nested_keys = any(key for key in subtree if key != "_model")

        if has_nested_keys:
            # For nested relationships, determine the model for the *next* level
            # Use the provided model stored in the subtree if available, otherwise expect error.
            next_model = subtree.get("_model")
            if next_model is None:
                 # Attempt to infer next_model from relationship property if not provided
                 # This relies on SQLAlchemy relationship configuration having the class reference
                 try:
                     mapper_prop = model.mapper.attrs[rel_attr]
                     if hasattr(mapper_prop, 'mapper'):
                         next_model = mapper_prop.mapper.class_
                     else: # Handle scenarios like AssociationProxy
                         # This part might need refinement depending on specific proxy setups
                          raise Exception(f"Cannot automatically determine next model for relationship {model.__name__}.{rel_attr}. Provide it explicitly.")
                 except Exception as e_infer:
                     raise Exception(f"Missing provided model ('_model') for nested relationship "
                                     f"{model.__name__}.{rel_attr} and could not infer. "
                                     f"Original inference error: {e_infer}")

            # Recursively build options for the nested level using the determined next_model
            child_options = build_option(next_model, subtree, strategy_func)
            if child_options:
                # Apply nested options to the current option
                option = option.options(*child_options)
        elif subtree and not has_nested_keys and "_model" in subtree:
             # Node exists, potentially has _model, but no further relationships requested.
             # Do nothing extra, the base option = strategy_func(attr) is sufficient.
             pass


        options.append(option)
    return options

def build_load_options(
    load_relations: List[Tuple[Type, str]],
    strategy: str = 'selectinload' # Default strategy
) -> List[LoaderOption]:
    """
    Convert a list of (base_model, dotted_relation) tuples into a flat list of SQLAlchemy
    eager loading options using the specified strategy ('selectinload' or 'joinedload').

    Parameters:
        load_relations (List[Tuple[Model, str]]):
            A list of tuples defining relationships to load.
        strategy (str):
            The loading strategy to use: 'selectinload' (default) or 'joinedload'.

    Returns:
        options (List[LoaderOption]): A list of SQLAlchemy eager loading options.

    Raises:
        ValueError: If an invalid strategy is provided or input is invalid.
        AttributeError: If a relationship attribute doesn't exist on a model.
        Exception: If nested loading structure is ambiguous (missing '_model').
    """
    # Map strategy string to the actual SQLAlchemy function
    strategy_map = {
        'selectinload': selectinload,
        'joinedload': joinedload,
        # 'subqueryload': subqueryload # Could be added if needed
    }
    if strategy not in strategy_map:
        raise ValueError(f"Invalid loading strategy '{strategy}'. "
                         f"Choose from: {list(strategy_map.keys())}")

    strategy_func = strategy_map[strategy]

    # Build the intermediate tree structure
    trees, query_root = build_load_tree(load_relations)

    # Build the final options list using the chosen strategy function
    options = build_option(query_root, trees[query_root], strategy_func)

    # print(f"\nEager load options for query root {query_root.__name__} (using {strategy}):")
    # pprint(options)
    return options




if __name__ == "__main__":
    import kiwi_app.auth.models as models  # Your application's models

    load_relations = [
        (models.User, "organization_links"), 
        (models.UserOrganizationRole, "organization_links.organization"), 
        (models.UserOrganizationRole, "organization_links.role"),
        # (models.User, "other_rels"),
    ]

    # Build eager loading options.
    load_options = build_load_options(load_relations)

    # To apply these options:
    # from sqlmodel import select
    # stmt = select(models.User).options(*load_options)
    # result = session.exec(stmt)
    # user = result.one_or_none()

    # Working actual join queries in SQLAlchemy for User models below using 2 strategies:
    # statement = (
    #     select(models.User)
    #     .where(models.User.id == token_data.sub)
    #     .options(
    #         # 1. Eagerly load the 'organization_links' collection (list of UserOrganizationRole)
    #         selectinload(models.User.organization_links)
    #             # 2. For each UserOrganizationRole in that list, load its 'organization' attribute
    #             .selectinload(models.UserOrganizationRole.organization),

    #         # 3. Eagerly load the 'organization_links' collection again (needed for the separate path)
    #         selectinload(models.User.organization_links)
    #             # 4. For each UserOrganizationRole in that list, load its 'role' attribute
    #             .selectinload(models.UserOrganizationRole.role)
    #     )
    # )

    # print(f"\n\n\n\n--- Running SELECTINLOAD Query for User ID: {token_data.sub} ---\n\n\n\n")
    # # Use session.execute for ORM statements returning ORM objects
    # result = await db.execute(statement)

    # # scalars() gets the primary ORM object (User)
    # # unique() is good practice, though less critical for selectinload than joinedload
    # # first() gets the single result or None
    # user = result.scalars().unique().first()
    # print("--- Query Finished ---")

    # print(user.organization_links)
    # print(user.organization_links[0].organization)
    # print(user.organization_links[0].role)

    # statement = (
    #     select(models.User)
    #     .where(models.User.id == token_data.sub)
    #     .options(
    #         joinedload(models.User.organization_links)
    #             .joinedload(models.UserOrganizationRole.organization),
    #         joinedload(models.User.organization_links)
    #             .joinedload(models.UserOrganizationRole.role)
    #     )
    # )
    # result = await db.exec(statement)
    # # result = db.sync_session.exec(statement)
    # ans = result.scalars().unique().first()
    # print(ans.organization_links)
    # print(ans.organization_links[0].organization)
    # print(ans.organization_links[0].role)

    

    

