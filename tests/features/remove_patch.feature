Feature: Alert rule remove and patch interaction
  As a COS admin
  I want to combine remove and patch operations
  So that I can rely on the correct ordering and immutability guarantees

  Scenario: The original input is not mutated by apply

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HighLatency
                expr: latency > 100
                for: 10m
                labels:
                  severity: critical
              - alert: LowThroughput
                expr: throughput < 10
                for: 5m

    When the following customization is applied:
      remove:
        - where:
            alert: LowThroughput
      patch:
        - where:
            alert: HighLatency
          set:
            for: 1h
            labels:
              severity: page

    Then the original input is unchanged

  Scenario: Operations are applied in order remove then patch

    Given the following alert rules:
      app:
        groups:
          - name: g
            rules:
              - alert: GoneForever
                expr: x
                for: 10m
              - alert: Survivor
                expr: y
                for: 10m

    When the following customization is applied:
      remove:
        - where:
            alert: GoneForever
      patch:
        - where:
            alert: Survivor
          set:
            for: 2m

    Then alert "GoneForever" is absent from identifier "app"
    And alert "Survivor" has "for" equal to "2m"

  Scenario: The customization instance is reusable across different inputs

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HostDown
                expr: up < 1

    When the following customization is applied:
      remove:
        - where:
            alert: HostDown

    When the same customization is applied to a second input

    Then alert "HostDown" is absent from both results
