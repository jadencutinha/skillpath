# Flow: Training Request Reminders

**TrainingRequests → New → Automation → Cloud flow → Scheduled**, name
`Training Request Reminders`. Repeat every **1 day**, at a morning hour in your time zone.

An approval times out after 7 days and the request becomes Expired
([`approval-flow.md`](approval-flow.md)). This flow makes that rare: from day 3 it emails whoever
the request is waiting on, once a day, with the link that opens their approval.

## Actions

**1. `List waiting requests`**: Dataverse *List rows*
- Table: Training Requests
- Select columns: `jc_title,jc_pendingwith,jc_approvallink,jc_submittedon,modifiedon`
- Filter rows:
  ```
  jc_requeststatus eq <SUBMITTED> and jc_approvallink ne null and modifiedon le @{addDays(utcNow(), -3)}
  ```

Why each part of the filter:

- `jc_approvallink ne null` limits the list to requests with a live approval. It skips the seeded
  demo rows and a request whose approval hasn't been created yet.
- `modifiedon` is when the current stage began. The last write to a waiting request is the approval
  flow's `Publish approval link`, so a second approver gets their own 3 days rather than inheriting
  the manager's. (If the requester edits the title or justification while waiting, the clock
  restarts, which is harmless.)

**2. `For each waiting request`**: *Apply to each* over `outputs('List_waiting_requests')?['body/value']`

- **`Send reminder`**: Office 365 Outlook *Send an email (V2)*
  - To: `items('For_each_waiting_request')?['jc_pendingwith']`
  - Subject: `Reminder: training request "@{items('For_each_waiting_request')?['jc_title']}" is waiting for you`
  - Body:
    ```
    This request was submitted on @{formatDateTime(items('For_each_waiting_request')?['jc_submittedon'], 'MMMM d')} and is waiting for your decision.

    Respond here: @{items('For_each_waiting_request')?['jc_approvallink']}

    If nobody responds within 7 days of it reaching you, the request expires and the requester has to start again.
    ```

This flow only reads. It never updates the request, so it can't interfere with the other two.

## Testing

Temporarily change the filter to `modifiedon le @{addMinutes(utcNow(), -2)}`, submit a request, wait
two minutes, and run the flow manually (**Test → Manually**). The approver gets one email whose link
opens the approval. Restore the filter.
