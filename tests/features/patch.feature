Feature: Alert rule patch customization
  As a COS admin
  I want to modify existing alert rules via a YAML config
  So that I can tweak thresholds, labels, and annotations

  Scenario: Patch updates the for duration of a matching alert

    Given the following alert rules
    """
    app-1:
      groups:
        - name: group_a
          rules:
            - alert: HighLatency
              expr: latency > 100
              for: 10m
    """

    When the following customization is applied
    """
    patch:
      - where:
          alert: HighLatency
        set:
          for: 30m
    """

    Then alert "HighLatency" has "for" equal to "30m"

  Scenario: Rename alert using the patch directive

    Given the following alert rules
    """
    app-1:
      groups:
        - name: group_a
          rules:
            - alert: HighLatency
              expr: latency > 100
              for: 10m
    """

    When the following customization is applied
    """
    patch:
      - where:
          alert: HighLatency
        set:
          alert: RenamedLatency
    """

    Then alert "RenamedLatency" is present
    And alert "HighLatency" is absent

  Scenario: Patch replaces the expression

    Given the following alert rules
    """
    app-1:
      groups:
        - name: group_b
          rules:
            - alert: HostDown
              expr: up < 1
    """

    When the following customization is applied
    """
    patch:
      - where:
          alert: HostDown
        set:
          expr: up == 0
    """

    Then alert "HostDown" has "expr" equal to "up == 0"

  Scenario: Patch overwrites an existing label and adds a new one leaving others untouched

    Given the following alert rules
    """
    app-1:
      groups:
        - name: group_a
          rules:
            - alert: HighLatency
              expr: latency > 100
              for: 10m
              labels:
                severity: critical
                juju_application: app-1
    """

    When the following customization is applied
    """
    patch:
      - where:
          alert: HighLatency
        set:
          labels:
            severity: page
            extra: added
    """

    Then alert "HighLatency" has label "severity" equal to "page"
    And alert "HighLatency" has label "extra" equal to "added"
    And alert "HighLatency" has label "juju_application" equal to "app-1"

  Scenario: Patch updates a juju topology label

    Given the following alert rules
    """
    app-1:
      groups:
        - name: group_a
          rules:
            - alert: HighLatency
              expr: latency > 100
              for: 10m
              labels:
                juju_application: app-1
    """

    When the following customization is applied
    """
    patch:
      - where:
          alert: HighLatency
        set:
          labels:
            juju_application: other-app
    """

    Then alert "HighLatency" has label "juju_application" equal to "other-app"

  Scenario: Patch merges annotations

    Given the following alert rules
    """
    app-1:
      groups:
        - name: group_a
          rules:
            - alert: HighLatency
              expr: latency > 100
              for: 10m
              annotations:
                summary: latency is high
    """

    When the following customization is applied
    """
    patch:
      - where:
          alert: HighLatency
        set:
          annotations:
            summary: new summary
            description: new description
    """

    Then alert "HighLatency" has annotation "summary" equal to "new summary"
    And alert "HighLatency" has annotation "description" equal to "new description"

  Scenario: Patch does not affect recording rules

    Given the following alert rules
    """
    app-1:
      groups:
        - name: group_a
          rules:
            - alert: HighLatency
              expr: latency > 100
              for: 10m
            - record: job:latency:mean5m
              expr: avg(latency)
    """

    When the following customization is applied
    """
    patch:
      - where:
          group: group_a
        set:
          expr: hacked
    """

    Then recording rule "job:latency:mean5m" has "expr" equal to "avg(latency)"
    And alert "HighLatency" has "expr" equal to "hacked"

  Scenario: Patch matches by label value across rules

    Given the following alert rules
    """
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
              labels:
                severity: warning
    """

    When the following customization is applied
    """
    patch:
      - where:
          labels:
            severity: warning
        set:
          labels:
            severity: critical
    """

    Then alert "LowThroughput" has label "severity" equal to "critical"
    And recording rule "job:latency:mean5m" has label "severity" equal to "warning"

  Scenario: Patch renames matching alerts across all groups

    Given the following alert rules
    """
    app-1:
      groups:
        - name: group_a
          rules:
            - alert: HighLatency
              expr: latency > 100
        - name: group_b
          rules:
            - alert: HighLatency
              expr: latency > 200
    """

    When the following customization is applied
    """
    patch:
      - where:
          alert: HighLatency
        set:
          alert: RenamedLatency
    """

    Then alert "HighLatency" is absent
    And alert "RenamedLatency" is present in group "group_a" of "app-1"
    And alert "RenamedLatency" is present in group "group_b" of "app-1"
