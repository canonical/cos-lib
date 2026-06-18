Feature: Sigma Rules processing
  As a charm developer
  I want to load and manage Sigma detection rules
  So that observability pipelines can evaluate security and operational alerts

  Background:
    Given a Juju topology for model "testmodel" and application "myapp"

  # --- Adding rules from dicts ---

  Scenario: Adding a single Sigma rule from a dict
    When I add a single sigma rule titled "Test Rule"
    Then the rules collection contains 1 rule
    And the rule titled "Test Rule" exists

  Scenario: Adding a collection of Sigma rules from a dict
    When I add a collection containing rules "Rule A" and "Rule B"
    Then the rules collection contains 2 rules
    And the rule titled "Rule A" exists
    And the rule titled "Rule B" exists

  Scenario: Adding an empty dict does nothing
    When I add an empty dict
    Then the rules collection is empty

  # --- Topology injection ---

  Scenario: Topology labels are injected into rules
    When I add a single sigma rule titled "Labeled Rule"
    Then the rule has label "juju_model" set to "testmodel"
    And the rule has label "juju_application" set to "myapp"
    And the rule has a label named "juju_model_uuid"

  Scenario: Topology does not overwrite existing labels
    When I add a sigma rule with labels "team=security" and "juju_application=custom-app"
    Then the rule has label "team" set to "security"
    And the rule has label "juju_application" set to "custom-app"
    And the rule has label "juju_model" set to "testmodel"

  Scenario: No topology means no labels added
    Given no Juju topology
    When I add a single sigma rule titled "No Topo Rule"
    Then the rule has no labels

  # --- Loading from filesystem ---

  Scenario: Loading a single Sigma rule file
    When I load the valid sigma rule file "ssh_failed_login.yaml"
    Then the rules collection contains 1 rule
    And the rule titled "Failed SSH Login Attempt" exists
    And the rule has id "5f3a4e20-1b2c-4d5e-9f8a-7b6c3d4e5f6a"

  # 3 single-rule files + 1 collection file containing 2 rules = 5
  Scenario: Loading a directory loads all rule files
    When I load the sigma rules directory
    Then the rules collection contains 5 rules

  Scenario: A collection file expands into multiple rules
    When I load the valid sigma rule file "collection.yaml"
    Then the rules collection contains 2 rules
    And the rule titled "Disk Space Critical" exists
    And the rule titled "Memory Exhaustion Warning" exists

  Scenario: Loading a nonexistent path does nothing
    When I load the valid sigma rule file "nonexistent.yaml"
    Then the rules collection is empty

  Scenario: Topology is injected when loading from file
    When I load the valid sigma rule file "high_cpu_process.yaml"
    Then the rule has label "juju_model" set to "testmodel"
    And the rule has label "juju_application" set to "myapp"

  Scenario: Existing file labels are preserved on load
    When I load the valid sigma rule file "unauthorized_api_access.yaml"
    Then the rule has label "team" set to "security"
    And the rule has label "juju_model" set to "testmodel"

  # --- Isolation ---

  Scenario: Adding a rule does not mutate the caller's input
    When I add a sigma rule and keep a reference to the original dict
    Then the original dict is unchanged

  # --- Rule validation ---

  Scenario: Loading an invalid rule
    When I load the invalid sigma rule file "invalid_rule.yaml"
    Then the rules collection is empty

  Scenario: Loading a mix of valid and invalid rules
    When I load the invalid sigma rule file "valid_and_invalid.yaml"
    Then the rules collection contains 1 rule
