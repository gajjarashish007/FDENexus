# M11 Observability & SRE

Metrics, logs, traces, alerts, incidents, SLOs and reliability analytics.

Owner: SRE · Phase: P2 · UI: `observability.html` (sidebar → Operations → Observability)

## Capabilities

| Capability | Status | Notes |
|---|---|---|
| Centralized metrics | live | CloudWatch metrics/alarms fetched live from connected AWS accounts. |
| Logs | partial | CloudWatch Logs integration is partial (list log groups, fetch logs). |
| Distributed tracing | planned | Not built yet (future: X-Ray, OpenTelemetry). |
| Alert management | live | Create, acknowledge, resolve alerts; severity and source tracking. |
| Alert correlation | partial | Basic correlation by service_id; advanced correlation is planned. |
| Incident management | live | Full lifecycle: create, acknowledge, resolve, track duration, RCA field. |
| Root cause analysis | partial | RCA text field; automated analysis is planned. |
| SLO management | live | Define SLOs per service, record good/total events, track error budgets. |
| Error budgets | live | Calculated from SLO current vs target; negative = burning. |
| Service health | live | Manual health status (healthy/degraded/down/unknown) per service. |
| Dependency mapping | planned | Not built yet. |
| Runbook automation | planned | Future: link to M10 runbooks. |
| Capacity planning | partial | Uses M04 data; forecasting is planned. |
| Reliability analytics | partial | Basic incident/alert stats; advanced analytics is planned. |
| Post-incident reporting | live | Incident duration, severity, status, RCA recorded for reporting. |

## How it works

1. **Services** are defined with tier, team, owner, and SLO target.
2. **SLOs** are defined per service with a target (e.g., 99.9%) and window (e.g., 30 days).
3. **Events** are recorded via `/api/m11/slos/<id>/record` (good/total counts).
4. **Error budgets** are calculated: `current - target`. Negative = burning budget.
5. **Incidents** track outages from creation through resolution.
6. **Alerts** track firing/resolved states from CloudWatch or manual entry.
7. **CloudWatch** integration fetches live metrics and alarms.

## API

`/api/m11/...`: overview, services, services/<id>, incidents, incidents/<id>/acknowledge, incidents/<id>/resolve, alerts, alerts/<id>/acknowledge, alerts/<id>/resolve, slos, slos/<id>/record, cloudwatch/metrics, cloudwatch/alarms.

## CloudWatch integration

- Requires `M01_LIVE_READS=1` (default).
- Fetches metrics from CloudWatch for any namespace/metric.
- Lists CloudWatch alarms with state and configuration.
- Uses the same boto3 session as M01/M02 (profile/assume-role).

## SLO calculation

```
SLO current = (good_events / total_events) * 100
Error budget remaining = current - target
```

If `error_budget_remaining < 0`, the service is burning its error budget.
