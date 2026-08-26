Feature: Alert rule remove customization
  As a COS admin
  I want to remove alert rules via a YAML config
  So that I can drop irrelevant alerts

  Background:
    Given a set of relation alerts from two apps

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
