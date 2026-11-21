# SecureRole team demonstration

Use a disposable local copy of the demonstration database. Start from Raj's
mark of 88 and Kunal's empty record state. Each presenter signs in with their
existing team account using credentials kept privately by the team. Use separate
browser profiles for convenient handoffs. Open the
[screenshot index](screenshot-index.md) as a fallback if the live demo is interrupted.

## Demonstration order

1. **Satvik · Admin.** Open **Overview** and explain where the dashboard counts
   come from. Open **Users**, find Kunal and show the Student role and Maulik's
   teacher assignment. Open the account form and cancel after showing the controls.
   Open **Access logs**, point out event-time actor roles and the verified audit
   status, and demonstrate applying a decision filter. Explain least privilege,
   authorization decisions and the difference between local verification and
   verification against a separately stored checkpoint. See figures 3, 9–13.

2. **Shubham · Teacher.** Open **My students** and find Raj. Explain why the row
   is available and why the permission summary restricts deletion and account
   administration. Edit Raj's academic record, keep the existing course and
   change the mark from 88 to 90. Save and point out the success message.
   Explain assignment-based authorization and how the record change and
   Allowed audit event are committed together. See figures 14–15.

3. **Raj · Student.** Open **My academic record**. Point out Cryptography and
   Network Security, the updated mark of 90 and Shubham as the assigned teacher.
   Explain that the Student policy matches the current account to the record
   owner and grants personal read access only. See figure 18.

4. **Kunal · Student, first visit.** Open **My academic record** and show the
   empty state and Maulik as the assigned teacher. Explain that an account can
   exist before it owns an academic record. Keep this browser profile open.
   See figure 19.

5. **Maulik · Teacher.** Open **My students**, find Kunal marked **Awaiting
   record**, and choose **Add record**. Enter Cryptography and Network Security
   and a mark of 79. Save and show the success message. Explain why the backend
   evaluates the target Student account when there is no record ID yet.
   See figures 16–17 and 21.

6. **Kunal · Student, second visit.** Refresh the dashboard and explain why the
   record and mark of 79 are now visible to the record owner. Point out the
   permission summary. Satvik can finish by finding the new Allowed events in
   **Access logs** and verifying the journal again. See figures 20 and 33.

## Viva questions

- Why does login verify a password hash, and what does the server store for an active session?
- What changes when an Admin reassigns a Student to a different Teacher?
- Where does creation check the role and assignment when a record has yet to be created?
- How does the database enforce one academic record per Student?
- Why should a record change and its Allowed audit event share a transaction?
- What does a historical actor role tell an investigator after an account changes roles?
- How does each previous-entry MAC link the audit journal, and why retain a checkpoint elsewhere?
- What happens on the next protected request after the account revokes that browser's session?

The [implementation excerpts](implementation.md) show the code paths behind these answers.
