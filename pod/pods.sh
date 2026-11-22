#!/bin/bash
# cleanup-bad-pods.sh
# Deletes faulty pods across all namespaces and sends Slack notification if any were removed.

# ------------------------------
# User-configurable
# ------------------------------
BAD_STATUSES=("Error" "ErrImagePull" "Evicted" "CrashLoopBackOff" "ImagePullBackOff" "Failed" "Unknown")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGFILE="${POD_CLEANUP_LOGFILE:-$SCRIPT_DIR/k8s-pod-cleanup.log}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"  # set webhook here if needed
DRY_RUN=${DRY_RUN:-false}  # can be set externally

# ------------------------------
# Environment
# ------------------------------
KUBECTL=$(which kubectl)
if [[ -z "$KUBECTL" ]]; then
    echo "kubectl not found in PATH. Exiting."
    exit 1
fi

# Prefer existing KUBECONFIG; otherwise default to ~/.kube/config
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

# Delete log file if it's older than 7 days
if [ -f "$LOGFILE" ] && [ $(find "$LOGFILE" -mtime +7 -print) ]; then
    rm -f "$LOGFILE"
fi

# Cluster name
CLUSTER_NAME=$($KUBECTL config current-context | awk -F'/' '{print $2}')
[[ -z "$CLUSTER_NAME" ]] && CLUSTER_NAME=$($KUBECTL config current-context)

# Server IP
SERVER_IP=$(hostname -I | awk '{print $1}')

# Timestamp
RUN_TIME=$(date +"%Y-%m-%d %H:%M:%S %Z")

echo "[$RUN_TIME] 🚀 Starting pod cleanup job on cluster: $CLUSTER_NAME, server: $SERVER_IP" | tee -a "$LOGFILE"

DELETED_COUNT=0
DELETED_PODS=()

for STATUS in "${BAD_STATUSES[@]}"; do
    echo "[$RUN_TIME] 🔍 Checking for pods with status: $STATUS" | tee -a "$LOGFILE"

    PODS=$($KUBECTL get pods --all-namespaces -o json \
      | jq -r --arg STATUS "$STATUS" '
        .items[]
        | select(
            .status.phase==$STATUS
            or (.status.containerStatuses[]?.state.waiting.reason==$STATUS)?
          )
        | "\(.metadata.namespace)|\(.metadata.name)|\(.status.phase // "N/A")|\(.status.containerStatuses[0]?.state.waiting.reason // "N/A")"
      ')

    if [[ -n "$PODS" ]]; then
        while IFS="|" read -r NAMESPACE POD POD_PHASE POD_REASON; do
            echo "[$RUN_TIME] ❌ Found pod $POD in namespace $NAMESPACE (phase: $POD_PHASE, reason: $POD_REASON)" | tee -a "$LOGFILE"

            if [[ "$DRY_RUN" == "true" ]]; then
                echo "[$RUN_TIME] 🧪 DRY-RUN: Would delete pod $POD" | tee -a "$LOGFILE"
            else
                $KUBECTL delete pod "$POD" -n "$NAMESPACE" --grace-period=0 --force
            fi

            ((DELETED_COUNT++))
            DELETED_PODS+=("• $NAMESPACE/$POD ($POD_PHASE, reason: $POD_REASON)")
        done <<< "$PODS"
    else
        echo "[$RUN_TIME] ✅ No pods found with status: $STATUS" | tee -a "$LOGFILE"
    fi
done

echo "[$RUN_TIME] 🎯 Pod cleanup completed. Total pods deleted: $DELETED_COUNT" | tee -a "$LOGFILE"

# ------------------------------
# Slack Notification
# ------------------------------
if [[ $DELETED_COUNT -gt 0 && -n "$SLACK_WEBHOOK_URL" ]]; then
    POD_LIST=$(printf "%s\n" "${DELETED_PODS[@]}")
    PAYLOAD=$(cat <<EOF
{
  "attachments": [
    {
      "color": "#FF0000",
      "title": "Kubernetes Pod Cleanup Report 🗑️",
      "fields": [
        { "title": "Cluster", "value": "$CLUSTER_NAME", "short": true },
        { "title": "Server IP", "value": "$SERVER_IP", "short": true },
        { "title": "Run Time", "value": "$RUN_TIME", "short": false },
        { "title": "Total Pods Deleted", "value": "$DELETED_COUNT", "short": false },
        { "title": "Deleted Pods", "value": "$POD_LIST", "short": false }
      ]
    }
  ]
}
EOF
)
    curl -s -X POST -H 'Content-type: application/json' --data "$PAYLOAD" "$SLACK_WEBHOOK_URL" > /dev/null
fi
