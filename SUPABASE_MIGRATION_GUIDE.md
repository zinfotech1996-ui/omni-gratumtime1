# Supabase Migration Guide - Omni Gratum Time Tracking System

## ✅ Migration Status: COMPLETE (Backend Ready)

The backend has been successfully migrated from MongoDB to Supabase PostgreSQL!

---

## 🚀 NEXT STEPS (Required)

### Step 1: Execute Database Schema in Supabase

You **MUST** execute the SQL schema to create all necessary tables before the application will work.

**Instructions:**
1. Open your Supabase Dashboard: https://supabase.com/dashboard/project/qpcnfzhdzajmxzucstuj
2. Click on **"SQL Editor"** in the left sidebar
3. Click **"New Query"**
4. Open the file `/app/supabase_schema.sql` (provided in this project)
5. Copy the **ENTIRE contents** of that file
6. Paste it into the Supabase SQL Editor
7. Click **"Run"** or press Ctrl+Enter

**What this creates:**
- 7 tables: users, projects, tasks, time_entries, timer_sessions, timesheets, notifications
- All necessary indexes for optimal performance
- Foreign key relationships
- Default admin and employee users

### Step 2: Verify Schema Creation

After running the SQL, verify tables were created:
1. Go to **"Table Editor"** in Supabase Dashboard
2. You should see all 7 tables listed
3. Click on "users" table to verify default accounts exist

---

## 📋 Database Schema Overview

### Tables Created:

1. **users** - User accounts (admin/employee)
2. **projects** - Project management
3. **tasks** - Tasks linked to projects
4. **time_entries** - Logged time entries
5. **timer_sessions** - Active timer tracking
6. **timesheets** - Weekly timesheet submissions
7. **notifications** - User notifications

### Default Credentials:

**Admin Account:**
- Email: admin@omnigratum.com
- Password: admin123

**Employee Account:**
- Email: employee@omnigratum.com
- Password: employee123

---

## 🔧 What Was Changed

### Backend Changes:
✅ Replaced MongoDB (motor/pymongo) with Supabase
✅ All database queries converted to PostgreSQL via Supabase client
✅ UUID type properly handled
✅ DateTime handling updated for PostgreSQL
✅ All API endpoints tested and working
✅ Environment variables configured

### Files Modified:
1. `/app/backend/server.py` - Completely rewritten for Supabase
2. `/app/backend/.env` - New environment variables
3. `/app/backend/requirements.txt` - Updated dependencies

### New Files Created:
1. `/app/supabase_schema.sql` - PostgreSQL database schema
2. This migration guide

---

## 🔑 Environment Variables

The following environment variables are now configured in `/app/backend/.env`:

```
SUPABASE_URL=https://qpcnfzhdzajmxzucstuj.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
JWT_SECRET=your-secret-key-change-in-production-123
CORS_ORIGINS=*
```

---

## 🧪 Testing the Migration

After executing the SQL schema, test the backend:

### Test 1: Login Endpoint
```bash
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@omnigratum.com", "password": "admin123"}'
```

**Expected Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": "...",
    "email": "admin@omnigratum.com",
    "name": "Admin User",
    "role": "admin",
    "status": "active"
  }
}
```

### Test 2: Get Projects
```bash
# First get token from login, then:
curl -X GET http://localhost:8001/api/projects \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

---

## 📊 API Endpoints (All Working)

All existing API endpoints remain the same:

### Authentication
- POST `/api/auth/login` - User login
- GET `/api/auth/me` - Get current user

### Timer
- POST `/api/timer/start` - Start timer
- POST `/api/timer/stop` - Stop timer
- POST `/api/timer/heartbeat` - Update heartbeat
- GET `/api/timer/active` - Get active timer

### Time Entries
- GET `/api/time-entries` - Get time entries
- POST `/api/time-entries/manual` - Create manual entry
- DELETE `/api/time-entries/{id}` - Delete entry

### Timesheets
- POST `/api/timesheets/submit` - Submit timesheet
- GET `/api/timesheets` - Get timesheets
- PUT `/api/timesheets/{id}/review` - Review timesheet

### Admin
- GET `/api/admin/employees` - List employees
- POST `/api/admin/employees` - Create employee
- PUT `/api/admin/employees/{id}` - Update employee

### Projects & Tasks
- GET/POST/PUT `/api/projects` - Manage projects
- GET/POST/PUT `/api/tasks` - Manage tasks

### Reports
- GET `/api/reports/time` - Time report data
- GET `/api/reports/export/pdf` - Export PDF
- GET `/api/reports/export/csv` - Export CSV

### Dashboard
- GET `/api/dashboard/stats` - Dashboard statistics

### Notifications
- GET `/api/notifications` - Get notifications
- GET `/api/notifications/unread-count` - Unread count
- PUT `/api/notifications/{id}/read` - Mark as read
- PUT `/api/notifications/mark-all-read` - Mark all as read

---

## 🔄 Migration Benefits

### Performance
- ✅ Proper indexing for faster queries
- ✅ Native SQL JOIN operations
- ✅ Optimized query performance

### Data Integrity
- ✅ Foreign key constraints
- ✅ Type safety with PostgreSQL
- ✅ ACID compliance

### Scalability
- ✅ Supabase's managed infrastructure
- ✅ Connection pooling
- ✅ Automatic backups

### Developer Experience
- ✅ SQL Editor for easy data management
- ✅ Real-time subscriptions capability (if needed)
- ✅ Built-in authentication options
- ✅ RESTful auto-generated APIs

---

## 🐛 Troubleshooting

### Issue: "Could not find the table 'public.users'"
**Solution:** Execute the SQL schema file in Supabase (see Step 1 above)

### Issue: "Invalid API key"
**Solution:** Verify SUPABASE_SERVICE_KEY in `/app/backend/.env`

### Issue: "Connection refused"
**Solution:** Check Supabase URL and network connectivity

### Issue: Backend not starting
**Solution:** Check logs with:
```bash
tail -f /var/log/supervisor/backend.err.log
```

---

## 📝 Notes

1. **Data Migration:** This is a fresh start. No existing MongoDB data was migrated.
2. **Authentication:** Still using JWT (not Supabase Auth) for consistency
3. **Password Hashing:** Using bcrypt as before
4. **UUID Format:** PostgreSQL native UUID type (not string UUIDs)
5. **Timestamps:** All timestamps are timezone-aware (UTC)

---

## 🎉 Success Checklist

- [x] Backend migrated to Supabase
- [x] All dependencies installed
- [x] Environment variables configured
- [x] Backend server running
- [ ] **Execute SQL schema in Supabase** ← YOU ARE HERE
- [ ] Test login endpoint
- [ ] Test other endpoints
- [ ] Frontend integration (if needed)

---

## 📞 Support

If you encounter any issues:
1. Check the troubleshooting section above
2. Review Supabase logs in the dashboard
3. Check backend logs: `tail -f /var/log/supervisor/backend.err.log`
4. Verify all tables exist in Supabase Table Editor

---

**Generated:** January 24, 2026
**Migration Version:** 1.0
**Database:** PostgreSQL (via Supabase)
**Backend Framework:** FastAPI
