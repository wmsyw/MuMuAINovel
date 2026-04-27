"""Static audit tests for AI entity generation bypasses."""

import ast
from pathlib import Path

API_FILES = [
    "backend/app/api/characters.py",
    "backend/app/api/organizations.py",
    "backend/app/api/careers.py",
    "backend/app/api/wizard_stream.py",
    "backend/app/api/outlines.py",
]

SERVICE_FILES = [
    "backend/app/services/character_state_update_service.py",
    "backend/app/services/auto_character_service.py",
    "backend/app/services/auto_organization_service.py",
]

def get_ast(file_path: Path) -> ast.AST:
    return ast.parse(file_path.read_text())

def test_legacy_services_marked_deprecated():
    """Verify that legacy services have [DEPRECATED] in their docstrings."""
    root = Path(__file__).parent.parent.parent
    for service_file in SERVICE_FILES:
        path = root / service_file
        assert path.exists(), f"Service file {service_file} not found"
        content = path.read_text()
        assert "[DEPRECATED]" in content, f"Service in {service_file} not marked as deprecated"
        assert "Migration Note" in content, f"Service in {service_file} missing migration notes"

def test_character_state_update_respects_pipeline_flag():
    """Verify CharacterStateUpdateService checks EXTRACTION_PIPELINE_ENABLED before legacy mutation."""
    root = Path(__file__).parent.parent.parent
    path = root / "backend/app/services/character_state_update_service.py"
    tree = get_ast(path)
    
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "update_from_analysis":
            method = node
            break
            
    assert method is not None, "update_from_analysis method not found"
    
    found_flag_check = False
    for node in ast.walk(method):
        if isinstance(node, ast.Attribute) and node.attr == "EXTRACTION_PIPELINE_ENABLED":
            found_flag_check = True
            break
            
    assert found_flag_check, "EXTRACTION_PIPELINE_ENABLED check not found in update_from_analysis"
    
    found_routing = False
    for node in ast.walk(method):
        if isinstance(node, ast.Attribute) and node.attr == "_stage_candidates_from_analysis":
            found_routing = True
            break
            
    assert found_routing, "Routing to _stage_candidates_from_analysis not found in update_from_analysis"

def get_calls_in_order(node: ast.AST) -> list[str]:
    calls: list[str] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute):
                calls.append(func.attr)
            elif isinstance(func, ast.Name):
                calls.append(func.id)
        calls.extend(get_calls_in_order(child))
    return calls

def test_auto_services_guardrail_ordering():
    """Verify AutoCharacterService and AutoOrganizationService evaluate policy before creation."""
    root = Path(__file__).parent.parent.parent
    
    services = [
        ("backend/app/services/auto_character_service.py", "check_and_create_missing_characters", "_generate_character_details", "_create_character_record"),
        ("backend/app/services/auto_organization_service.py", "check_and_create_missing_organizations", "_generate_organization_details", "_create_organization_record")
    ]
    
    for service_file, method_name, gen_helper, create_helper in services:
        path = root / service_file
        tree = get_ast(path)
        
        method = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == method_name:
                method = node
                break
        
        assert method is not None, f"{method_name} not found in {service_file}"
        
        calls = get_calls_in_order(method)
        
        assert "evaluate_for_user" in calls, f"evaluate_for_user not called in {method_name}"
        
        eval_idx = calls.index("evaluate_for_user")
        
        if gen_helper in calls:
            gen_idx = calls.index(gen_helper)
            assert eval_idx < gen_idx, f"evaluate_for_user must be called before {gen_helper} in {method_name}"
            
        if create_helper in calls:
            create_idx = calls.index(create_helper)
            assert eval_idx < create_idx, f"evaluate_for_user must be called before {create_helper} in {method_name}"
            
        assert "record_override_audit" in calls, f"record_override_audit not called in {method_name}"
        audit_idx = calls.index("record_override_audit")
        
        if create_helper in calls:
            last_create_idx = len(calls) - 1 - calls[::-1].index(create_helper)
            assert last_create_idx < audit_idx, f"record_override_audit must be called after {create_helper} in {method_name}"



def test_api_call_sites_pass_auth_context():
    """Verify that calls to auto-services in API files pass user_id and is_admin."""
    root = Path(__file__).parent.parent.parent
    
    target_methods = ["check_and_create_missing_characters", "check_and_create_missing_organizations"]
    
    for api_file in ["backend/app/api/outlines.py", "backend/app/api/wizard_stream.py"]:
        path = root / api_file
        if not path.exists(): continue
        tree = get_ast(path)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                method_name = ""
                if isinstance(func, ast.Attribute):
                    method_name = func.attr
                elif isinstance(func, ast.Name):
                    method_name = func.id
                
                if method_name in target_methods:
                    arg_names = [kw.arg for kw in node.keywords]
                    assert "user_id" in arg_names, f"Missing user_id in call to {method_name} in {api_file}"
                    assert "is_admin" in arg_names, f"Missing is_admin in call to {method_name} in {api_file}"

def test_no_direct_private_record_creation():
    """Verify that private _create_*_record helpers are not called outside their services."""
    root = Path(__file__).parent.parent.parent
    
    private_helpers = ["_create_character_record", "_create_organization_record"]
    
    for api_file in API_FILES:
        path = root / api_file
        if not path.exists(): continue
        content = path.read_text()
        for helper in private_helpers:
            assert helper not in content, f"Direct call to private helper {helper} found in {api_file}"
