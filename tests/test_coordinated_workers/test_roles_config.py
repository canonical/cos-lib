import pytest

from src.cosl.coordinated_workers.coordinator import ClusterRolesConfig, ClusterRolesConfigError


def test_meta_role_keys_not_in_roles():
    # Test that the meta roles keys are a subset of roles

    # GIVEN an invalid_role_config
    # WHEN ClusterRolesConfig is instantiated
    # THEN the __post_init__ method raises a ClusterRolesConfigError
    with pytest.raises(ClusterRolesConfigError):
        ClusterRolesConfig(
            roles={"read"},
            meta_roles={"I AM NOT A SUBSET OF ROLES": {"read"}},
            minimal_deployment={"read"},
            recommended_deployment={"read": 3},
        )


def test_meta_role_values_not_in_roles():
    # Test that the meta roles values are a subset of roles

    # GIVEN an invalid_role_config
    # WHEN ClusterRolesConfig is instantiated
    # THEN the __post_init__ method raises a ClusterRolesConfigError
    with pytest.raises(ClusterRolesConfigError):
        ClusterRolesConfig(
            roles={"read"},
            meta_roles={"read": {"I AM NOT A SUBSET OF ROLES"}},
            minimal_deployment={"read"},
            recommended_deployment={"read": 3},
        )


def test_minimal_deployment_roles_not_in_roles():
    # Test that the minimal deployment roles are a subset of roles

    # GIVEN an invalid_role_config
    # WHEN ClusterRolesConfig is instantiated
    # THEN the __post_init__ method raises a ClusterRolesConfigError
    with pytest.raises(ClusterRolesConfigError):
        ClusterRolesConfig(
            roles={"read"},
            meta_roles={"read": {"read"}},
            minimal_deployment={"I AM NOT A SUBSET OF ROLES"},
            recommended_deployment={"read": 3},
        )


def test_recommended_deployment_roles_not_in_roles():
    # Test that the recommended deployment roles are a subset of roles

    # GIVEN an invalid_role_config
    # WHEN ClusterRolesConfig is instantiated
    # THEN the __post_init__ method raises a ClusterRolesConfigError
    with pytest.raises(ClusterRolesConfigError):
        ClusterRolesConfig(
            roles={"read"},
            meta_roles={"read": {"read"}},
            minimal_deployment={"read"},
            recommended_deployment={"I AM NOT A SUBSET OF ROLES": 3},
        )
