# High CPU Usage Runbook

## Immediate response

1. Confirm the affected service and time range in the monitoring dashboard.
2. Check the top CPU-consuming processes or pods.
3. Compare the spike with recent deployments, traffic changes, and scheduled jobs.
4. If user traffic is affected, scale the service horizontally when capacity allows.
5. Roll back the most recent deployment if it introduced the regression.

## Follow-up

Capture CPU graphs, pod logs, and the deployment revision in the incident ticket.
