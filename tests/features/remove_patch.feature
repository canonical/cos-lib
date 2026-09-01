Feature: Alert rule remove and patch interaction
  As a COS admin
  I want to combine remove and patch operations
  So that I can rely on the correct ordering and immutability guarantees

  Scenario: The original input is not mutated by apply
    Given the sample alerts from "sample_alerts.yaml"
    When I apply a customization that removes alert "LowThroughput" and patches alert "HighLatency"
    Then the original input is unchanged

  Scenario: Operations are applied in order remove then patch
    Given a rule named "GoneForever" and a rule named "Survivor"
    When I apply a customization that removes "GoneForever" and patches "Survivor" for to "2m"
    Then alert "GoneForever" is absent from identifier "app"
    And alert "Survivor" has for equal to "2m"

  Scenario: The customization instance is reusable across different inputs
    Given the sample alerts from "sample_alerts.yaml"
    When I apply the same remove customization to two different inputs
    Then alert "HostDown" is absent from both results
