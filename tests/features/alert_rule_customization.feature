Feature: Alert rule customization
  As a COS admin
  I want to customize relation-derived alert rules via a YAML config
  So that I can remove, patch, or add rules without modifying charm code

  Background:
    Given a set of relation alerts from two apps

  # ---------------------------------------------------------------------------
  # Remove
  # ---------------------------------------------------------------------------

  Scenario: Remove an alert by name
    When I apply a customization that removes alert "LowThroughput"
    Then alert "LowThroughput" is absent from the result
    And alert "HighLatency" is present in the result
    And the recording rule "job:latency:mean5m" is present in the result

  Scenario: Remove an entire group by group name drops everything including recording rules
    When I apply a customization that removes group "group_a"
    Then group "group_a" is absent from identifier "app-1"
    And group "group_b" is present in identifier "app-1"

  Scenario: Remove with group and another selector only removes matching alerting rules
    When I apply a customization that removes alerts in group "group_a" with alert name "LowThroughput"
    Then alert "LowThroughput" is absent from the result
    And alert "HighLatency" is present in the result
    And the recording rule "job:latency:mean5m" is present in the result

  Scenario: Remove by label value
    When I apply a customization that removes alerts with label "severity" equal to "warning"
    Then alert "LowThroughput" is absent from the result
    And alert "HighLatency" is present in the result
    And the recording rule "job:latency:mean5m" is present in the result

  Scenario: Remove by annotation value
    When I apply a customization that removes alerts with annotation "summary" equal to "latency is high"
    Then alert "HighLatency" is absent from the result
    And alert "LowThroughput" is present in the result

  Scenario: Remove by juju topology label
    When I apply a customization that removes alerts with label "juju_application" equal to "app-1"
    Then alert "HighLatency" is absent from the result
    And alert "LowThroughput" is present in the result

  Scenario: Multiple remove entries are OR'd
    When I apply a customization that removes alert "HighLatency" and alert "OtherAlert"
    Then alert "HighLatency" is absent from the result
    And alert "OtherAlert" is absent from the result
    And alert "LowThroughput" is present in the result
    And alert "HostDown" is present in the result

  Scenario: Removing the only rule in a group prunes the empty group
    When I apply a customization that removes alert "HostDown"
    Then group "group_b" is absent from identifier "app-1"
    And group "group_a" is present in identifier "app-1"

  Scenario: Removing all rules from an identifier drops the identifier entirely
    When I apply a customization that removes alert "OtherAlert"
    Then identifier "app-2" is absent from the result
    And identifier "app-1" is present in the result

  # ---------------------------------------------------------------------------
  # Patch
  # ---------------------------------------------------------------------------

  Scenario: Patch updates the for duration of a matching alert
    When I apply a customization that patches alert "HighLatency" setting for to "30m"
    Then alert "HighLatency" has for equal to "30m"
    And alert "LowThroughput" has for equal to "5m"

  Scenario: Patch replaces the alert name
    When I apply a customization that patches alert "HighLatency" setting alert name to "RenamedLatency"
    Then alert "RenamedLatency" is present in the result
    And alert "HighLatency" is absent from the result

  Scenario: Patch replaces the expression
    When I apply a customization that patches alert "HostDown" setting expr to "up == 0"
    Then alert "HostDown" has expr equal to "up == 0"

  Scenario: Patch overwrites an existing label and adds a new one leaving others untouched
    When I apply a customization that patches alert "HighLatency" setting label "severity" to "page" and adding label "extra" as "added"
    Then alert "HighLatency" has label "severity" equal to "page"
    And alert "HighLatency" has label "extra" equal to "added"
    And alert "HighLatency" has label "juju_application" equal to "app-1"

  Scenario: Patch updates a juju topology label
    When I apply a customization that patches alert "HighLatency" setting label "juju_application" to "other-app"
    Then alert "HighLatency" has label "juju_application" equal to "other-app"

  Scenario: Patch merges annotations
    When I apply a customization that patches alert "HighLatency" setting annotation "summary" to "new summary" and adding annotation "description" as "new description"
    Then alert "HighLatency" has annotation "summary" equal to "new summary"
    And alert "HighLatency" has annotation "description" equal to "new description"

  Scenario: Patch does not affect recording rules
    When I apply a customization that patches all rules in group "group_a" setting expr to "hacked"
    Then the recording rule "job:latency:mean5m" has expr equal to "avg(latency)"
    And alert "HighLatency" has expr equal to "hacked"

  Scenario: Patch matches by label value across rules
    When I apply a customization that patches alerts with label "severity" equal to "warning" setting label "severity" to "critical"
    Then alert "LowThroughput" has label "severity" equal to "critical"
    And the recording rule "job:latency:mean5m" has label "severity" equal to "warning"

  # ---------------------------------------------------------------------------
  # Add
  # ---------------------------------------------------------------------------

  Scenario: Add inserts groups under the fixed key custom_alert_rules
    When I apply a customization that adds a group named "my-custom-alerts" with alert "MyAlert"
    Then identifier "custom_alert_rules" is present in the result
    And group "my-custom-alerts" is present in identifier "custom_alert_rules"
    And alert "MyAlert" is present in the result
    And identifier "app-1" is present in the result
    And identifier "app-2" is present in the result

  Scenario: Added rules receive no topology injection
    When I apply a customization that adds a group named "my-custom-alerts" with alert "MyAlert" and expr 'up{juju_model="prod"} == 0'
    Then alert "MyAlert" has expr equal to 'up{juju_model="prod"} == 0'
    And alert "MyAlert" has no labels

  Scenario: Added rules are deep copied so mutations do not affect subsequent apply calls
    When I apply the same customization twice with an add block
    And I mutate the alert name in the first result
    Then the second result still contains alert "MyAlert"

  # ---------------------------------------------------------------------------
  # Apply semantics
  # ---------------------------------------------------------------------------

  Scenario: The original input is not mutated by apply
    When I apply a customization that removes alert "LowThroughput" and patches alert "HighLatency"
    Then the original input is unchanged

  Scenario: Operations are applied in order remove then patch then add
    Given a rule named "GoneForever" and a rule named "Survivor"
    When I apply a customization that removes "GoneForever", patches "Survivor" for to "2m", and adds a new "GoneForever"
    Then alert "GoneForever" is absent from identifier "app"
    And alert "Survivor" has for equal to "2m"
    And identifier "custom_alert_rules" is present in the result
    And the added alert "GoneForever" does not have a for field

  Scenario: The customization instance is reusable across different inputs
    When I apply the same remove customization to two different inputs
    Then alert "HostDown" is absent from both results
