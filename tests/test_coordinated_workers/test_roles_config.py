import pytest
import logging
from types import SimpleNamespace

from src.cosl.coordinated_workers.coordinator import validate_roles_config



# TODO Consider a function that generates the SimpleNameSpace
# TODO Propose an alternative to the validate_roles_config function
    # Do we want to import it every time? Options: Pydantic model, data class, add validate inside the function?
    # Validation may be different for Loki, Mimir, Tempo
# TODO Consider error handling in constructor and combining with is_coherant


# TODO Form an opinion versus ClusterRolesConfig and validate_roles_config
    # Look how its used in Loki, Mimir, Tempo
    # Think about metrics: easier to test, less/cleaner code
class MetaRoles:
    def __init__(self, meta_roles: Dict[str, Set[str]], extra_roles: Set(str)) -> None:
        pass
        # Validate in constructor?
        # roles are derived from combination of meta and extra
    
    def set_minimal(self, spec: Dict[str, int]):
        # 
        pass

    def set_recommended(self, spec: Dict[str, int]):
        # Can this be part of plain charm code, is it specific to a charm?
        pass

def test_if_meta_keys_not_subset():
    # The meta role keys must be a subset of roles

    # GIVEN a ClusterRolesConfig with meta_roles keys not in roles
    roles = SimpleNamespace(
        roles={"meta", "role1", "role2"},
        meta_roles={"I AM NOT A SUBSET OF ROLES": {"role1", "role2"}},
        minimal_deployment={"meta"},
        recommended_deployment={"role2": 1},
    )
    # WHEN validate_roles_config checks that meta_roles keys are a subset of roles
    # THEN raise an AssertionError
    with pytest.raises(AssertionError):
        validate_roles_config(roles)

def test_should_raise_if_meta_values_not_subset():
    # The meta role values must be a subset of roles

    roles = SimpleNamespace(
        roles={"meta", "role1", "role2"},
        meta_roles={"meta": {"I AM NOT A SUBSET OF ROLES", "role2"}},
        minimal_deployment={"meta"},
        recommended_deployment={"role2": 1},
    )
    with pytest.raises(AssertionError):
        validate_roles_config(roles)

def test_should_raise_if_minimal_keys_not_subset():
    # The minimal_deployment values must be a subset of roles

    roles = SimpleNamespace(
        roles={"meta", "role1", "role2"},
        meta_roles={"meta": {"role1", "role2"}},
        minimal_deployment={"I AM NOT A SUBSET OF ROLES"},
        recommended_deployment={"role2": 1},
    )
    with pytest.raises(AssertionError):
        validate_roles_config(roles)

def test_should_raise_if_recommended_keys_not_subset():
    # The recommended_deployment keys must be a subset of roles

    roles = SimpleNamespace(
        roles={"meta", "role1", "role2"},
        meta_roles={"meta": {"role1", "role2"}},
        minimal_deployment={"meta"},
        recommended_deployment={"I AM NOT A SUBSET OF ROLES": 1},
    )
    with pytest.raises(AssertionError):
        validate_roles_config(roles)

def test_should_return_none_when_valid():
    # The recommended_deployment keys must be a subset of roles

    roles = SimpleNamespace(
        roles={"meta", "role1", "role2"},
        meta_roles={"meta": {"role1", "role2"}},
        minimal_deployment={"meta"},
        recommended_deployment={"role1": 1},
    )
    assert None is validate_roles_config(roles)
