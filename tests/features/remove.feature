Feature: Alert rule remove customization
  As a COS admin
  I want to remove alert rules via a YAML config
  So that I can drop irrelevant alerts

  Scenario: Remove an alert by name

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HighLatency
                expr: latency > 100
                for: 10m
              - alert: LowThroughput
                expr: throughput < 10
                for: 5m
              - record: job:latency:mean5m
                expr: avg(latency)

    When the following customization is applied:
      remove:
        - where:
            alert: LowThroughput

    Then alert "LowThroughput" is absent
    And alert "HighLatency" is present
    And recording rule "job:latency:mean5m" is present

  Scenario: Remove an entire group by group name drops everything including recording rules

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HighLatency
                expr: latency > 100
              - record: job:latency:mean5m
                expr: avg(latency)
          - name: group_b
            rules:
              - alert: HostDown
                expr: up < 1

    When the following customization is applied:
      remove:
        - where:
            group: group_a

    Then group "group_a" is absent from identifier "app-1"
    And group "group_b" is present in identifier "app-1"

  Scenario: Remove with group and another selector only removes matching alerting rules

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HighLatency
                expr: latency > 100
                for: 10m
              - alert: LowThroughput
                expr: throughput < 10
                for: 5m
              - record: job:latency:mean5m
                expr: avg(latency)

    When the following customization is applied:
      remove:
        - where:
            group: group_a
            alert: LowThroughput

    Then alert "LowThroughput" is absent
    And alert "HighLatency" is present
    And recording rule "job:latency:mean5m" is present

  Scenario: Remove by label value

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
                labels:
                  severity: warning
              - record: job:latency:mean5m
                expr: avg(latency)

    When the following customization is applied:
      remove:
        - where:
            labels:
              severity: warning

    Then alert "LowThroughput" is absent
    And alert "HighLatency" is present
    And recording rule "job:latency:mean5m" is present

  Scenario: Remove by annotation value

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HighLatency
                expr: latency > 100
                for: 10m
                annotations:
                  summary: latency is high
              - alert: LowThroughput
                expr: throughput < 10
                for: 5m

    When the following customization is applied:
      remove:
        - where:
            annotations:
              summary: latency is high

    Then alert "HighLatency" is absent
    And alert "LowThroughput" is present

  Scenario: Remove by juju topology label

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HighLatency
                expr: latency > 100
                for: 10m
                labels:
                  juju_application: app-1
              - alert: LowThroughput
                expr: throughput < 10
                for: 5m

    When the following customization is applied:
      remove:
        - where:
            labels:
              juju_application: app-1

    Then alert "HighLatency" is absent
    And alert "LowThroughput" is present

  Scenario: Multiple remove entries are OR'd

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HighLatency
                expr: latency > 100
              - alert: LowThroughput
                expr: throughput < 10
          - name: group_b
            rules:
              - alert: HostDown
                expr: up < 1
      app-2:
        groups:
          - name: group_c
            rules:
              - alert: OtherAlert
                expr: x > 0

    When the following customization is applied:
      remove:
        - where:
            alert: HighLatency
        - where:
            alert: OtherAlert

    Then alert "HighLatency" is absent
    And alert "OtherAlert" is absent
    And alert "LowThroughput" is present
    And alert "HostDown" is present

  Scenario: Removing the only rule in a group prunes the empty group

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HighLatency
                expr: latency > 100
          - name: group_b
            rules:
              - alert: HostDown
                expr: up < 1

    When the following customization is applied:
      remove:
        - where:
            alert: HostDown

    Then group "group_b" is absent from identifier "app-1"
    And group "group_a" is present in identifier "app-1"

  Scenario: Removing all rules from an identifier drops the identifier entirely

    Given the following alert rules:
      app-1:
        groups:
          - name: group_a
            rules:
              - alert: HighLatency
                expr: latency > 100
      app-2:
        groups:
          - name: group_c
            rules:
              - alert: OtherAlert
                expr: x > 0

    When the following customization is applied:
      remove:
        - where:
            alert: OtherAlert

    Then identifier "app-2" is absent
    And identifier "app-1" is present
