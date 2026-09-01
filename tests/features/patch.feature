Feature: Alert rule patch customization
  As a COS admin
  I want to modify existing alert rules via a YAML config
  So that I can tweak thresholds, labels, and annotations

  Background:
    Given the sample alerts from "sample_alerts.yaml"

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
