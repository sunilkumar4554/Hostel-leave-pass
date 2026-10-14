# MongoDB data model notes

The app is document-oriented; MongoDB collections are created automatically at runtime.

## `users`
Common fields: `name`, `email`, `password_hash`, `role`, `active`, `created_at`. Student accounts also contain `registration_no`, `branch`, `hostel_type`, `hostel_name`, `year`, `room_no`, and `phone`.

## `leaves`
Contains the unique `leave_id`, student snapshot fields, `reason`, `start_date`, `end_date`, `return_time`, optional `proof_filename` and private `proof_storage_name`, `status`, approval/rejection metadata, optional `extension_request`, and `checked_out_at` / `checked_in_at` timestamps.

## `gate_logs`
Each successful checkout or check-in creates an event with the leave ID, student ID, guard ID and timestamp.

## `audit_logs`
Tracks actions such as leave submissions, warden decisions, bulk student imports, checkouts and check-ins.

## `password_reset_otps`
Stores a hash of the one-time code and an expiration time. MongoDB's TTL index is used to clean expired OTP records.

Indexes are initialized by `backend/app.py` when MongoDB becomes available.
