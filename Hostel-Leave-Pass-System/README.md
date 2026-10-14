# Hostel Leave Pass Management System

A student/warden/guard hostel leave workflow starter project. The frontend is plain HTML, CSS and JavaScript. The backend is Python + Flask, with local MongoDB accessed through PyMongo. MongoDB Compass is used to inspect and manage the local database.

## Included in this version

- Separate Student, Warden and Guard login screens
- Student registration with hostel and room details
- Role-based login, password hashing and sessions
- Leave requests with dates, reason, notes and optional PDF/JPG/PNG proof
- Warden approvals and rejections
- QR image generated for an approved pass
- Guard manual Leave ID validation and optional browser camera QR scanning
- Check-out and check-in timestamps and gate activity history
- Student search and leave history in the Warden portal
- Monthly Excel report export
- CSV student import with a temporary password
- Leave extension request workflow
- Forgot password by email OTP (requires SMTP settings in `.env`)

This is a local college-project prototype, not a production deployment. AI assistant integration, PDF leave-pass export, formal email notifications for approval/rejection, CSRF protection, rate limiting and production deployment hardening are not implemented in this starter ZIP yet. Do not deploy it publicly as-is.

## 1. Install prerequisites

Install these on Windows:

1. **Python 3.10 or newer**
2. **MongoDB Community Server** (the database server)
3. **MongoDB Compass** (GUI to view and manage the database)
4. **VS Code** (recommended)

> Important: Compass is only the database GUI. It does not run the MongoDB server by itself. The server must be installed and running on your computer.

## 2. Start MongoDB and connect Compass

1. Start the MongoDB service from Windows Services (the service is commonly named `MongoDB`), or start the server using your installation's `mongod` service setup.
2. Open MongoDB Compass.
3. Use this connection string:

   ```text
   mongodb://127.0.0.1:27017/
   ```

4. Click **Connect**. The app will create the `hostel_leave_system` database and its collections after the first API request.

If Compass cannot connect, start/install MongoDB Community Server first. Keep the default local URI unless you configured another port.

## 3. Install Python packages

Open a terminal in the extracted `Hostel-Leave-Pass-System` folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, you can skip activation and run `.venv\Scripts\python.exe -m pip install -r requirements.txt`, then `.venv\Scripts\python.exe backend\app.py`.

## 4. Configure the project

Copy `.env.example` to `.env`. The default database settings are for local MongoDB:

```env
MONGO_URI=mongodb://127.0.0.1:27017/
MONGO_DB_NAME=hostel_leave_system
FLASK_SECRET_KEY=change-this-to-a-long-random-secret
```

A `.env` file is optional for local testing because the app includes local defaults, but setting a secret key is recommended. Keep `.env` private and do not upload it to GitHub.

## 5. Run the website

From the project root, run:

```powershell
python backend\app.py
```

Then open this address in the browser on the same computer:

```text
http://127.0.0.1:5000
```

To test from a phone on the same trusted Wi-Fi network, find your computer's local IPv4 address with `ipconfig` and open `http://YOUR-PC-IP:5000` on the phone. The Python server binds to `0.0.0.0` for local-network testing; do not expose it to the public internet. Keep Flask debug mode disabled when another device can connect.

Do not double-click an HTML file to open the website. Open the local Flask address above so the frontend can call the Python APIs.

## 6. Demo accounts

The application creates these local demo accounts when it can connect to MongoDB for the first time:

| Role | Email | Password |
|---|---|---|
| Warden | `warden@hostel.local` | `Warden@123` |
| Guard | `guard@hostel.local` | `Guard@123` |

Register a new account from **Student Portal → Create an account**. These demo credentials are only for local testing; change or remove them before any deployment.

## 7. Test the main flow

1. Log in as the demo Warden in one browser tab.
2. Register a student in another tab or a private browser window.
3. As the student, submit a leave request with a start date of today or a future date.
4. Return to the Warden portal and approve the pending request.
5. Open Student Portal → Leave history to see the QR code after approval.
6. Log in to the Guard portal, scan the QR code (camera library requires internet access) or manually paste the Leave ID.
7. Confirm Check-Out. Validate the same ID again and confirm Check-In when the student returns.
8. Use Warden → Reports & import to download an Excel report, or import a CSV.

For camera access, use `http://127.0.0.1:5000` (localhost) and allow browser camera permission. Manual Leave ID entry is available if the camera or QR library is unavailable.

## 8. CSV format for student import

The Warden CSV import requires these exact headers (header case and spaces are normalized):

```csv
name,email,registration_no,branch,hostel_type,hostel_name,year,room_no,phone
Riya Kumar,riya@example.edu,24AIML001,AI & ML,Boys Hostel,Block A,2nd Year,204,9876543210
Aman Singh,aman@example.edu,24CSE002,CSE,Boys Hostel,Block B,2nd Year,108,9876543211
```

The Warden selects a temporary password to apply to newly imported accounts. Existing email addresses or registration numbers are skipped. Share temporary passwords securely and do not send them in public group chats.

## 9. Password reset email (optional setup)

Password reset sends a one-time code by SMTP. Add real SMTP details to `.env`, for example:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_FROM=HostelPass <noreply@example.com>
```

Use your mail provider's appropriate SMTP host and credentials. If SMTP is not set, the reset page will display a configuration message. Never commit SMTP secrets to source control.

## Database collections

The app uses these MongoDB collections under `hostel_leave_system`:

- `users`
- `leaves`
- `gate_logs`
- `audit_logs`
- `password_reset_otps`

The collections and indexes are created automatically as the application runs.

## Troubleshooting

- **MongoDB Compass connection refused:** Start MongoDB Community Server; Compass alone is not the server.
- **Website opens but login says MongoDB unavailable:** Check that `mongodb://127.0.0.1:27017/` connects in Compass and that MongoDB service is running.
- **`ModuleNotFoundError`:** Activate the virtual environment and run `pip install -r requirements.txt`.
- **QR camera doesn't open:** Allow camera permission and use localhost. If the external QR library cannot load, use manual Leave ID entry.
- **Port 5000 is already in use:** Change `PORT=5001` in `.env`, restart the app, and open `http://127.0.0.1:5001`.
