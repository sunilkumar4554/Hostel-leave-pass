# Bug Review and Fixes

## Fixes applied

1. **Concurrent gate actions could report success more than once.** Check-out and check-in now verify that the database state transition actually changed one document before writing gate/audit logs. A simultaneous or repeated action returns HTTP 409 instead of logging a duplicate successful event.
2. **Date checks used local system date inconsistently through `datetime.now().date()`.** These checks now use `date.today()` directly, keeping date-only comparisons explicit.
3. **Monthly report date range was harder to reason about.** The query now calculates the first day of the next month explicitly, including December-to-January rollover.
4. **Monthly report default could select the wrong month near midnight/month boundaries in some time zones.** The frontend now builds the month from local year/month instead of UTC `toISOString()`.

## Validation performed

- Python syntax compilation passed (`python -m compileall -q backend`).
- JavaScript syntax checks passed (`node --check` for all files in `frontend/js/`).
- Full runtime/API tests were not run because Flask, PyMongo, and Werkzeug are not installed in this review environment, and no MongoDB server is available here. Install `requirements.txt` and run against a test database before relying on the application.

## Important remaining risks / recommended next fixes

- The default Flask secret key is a known development value. Set a long random `FLASK_SECRET_KEY` in `.env` and never use the fallback for a public deployment.
- CSRF protection and login/password-reset rate limiting are not implemented; do not expose this prototype to the public internet.
- Password-reset OTPs have an expiry but no attempt counter/rate limit. Add throttling and invalidate an OTP after a small number of failed attempts.
- Uploaded proofs are checked by filename extension, not file content. Validate MIME/file signatures and consider malware scanning before production use.
- If leave creation fails after a proof file has been written, the uploaded file may be left orphaned on disk. Add cleanup around database insert failures.
- Gate status changes and their gate/audit log inserts are not in a MongoDB transaction. The status transition is now guarded against duplicate events, but a database failure between the state update and log inserts could still leave incomplete logs.
- Dates use the host machine's local timezone while stored timestamps use UTC. Configure and consistently use the institution's timezone for deployments.
