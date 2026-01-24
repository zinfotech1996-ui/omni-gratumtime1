from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta, date
from passlib.context import CryptContext
import jwt
from enum import Enum
import io
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Supabase connection
supabase_url = os.environ['SUPABASE_URL']
supabase_key = os.environ['SUPABASE_SERVICE_KEY']
supabase: Client = create_client(supabase_url, supabase_key)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production-123')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Security
security = HTTPBearer()

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# Enums
class UserRole(str, Enum):
    ADMIN = "admin"
    EMPLOYEE = "employee"

class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class EntryType(str, Enum):
    TIMER = "timer"
    MANUAL = "manual"

class TimesheetStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    DENIED = "denied"

# Models
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: EmailStr
    name: str
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE
    default_project: Optional[str] = None
    default_task: Optional[str] = None
    created_at: datetime

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: UserRole = UserRole.EMPLOYEE
    status: UserStatus = UserStatus.ACTIVE
    default_project: Optional[str] = None
    default_task: Optional[str] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    status: Optional[UserStatus] = None
    default_project: Optional[str] = None
    default_task: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    token: str
    user: User

class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    description: Optional[str] = None
    created_by: str
    status: str = "active"
    created_at: datetime

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None

class Task(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    description: Optional[str] = None
    project_id: str
    status: str = "active"
    created_at: datetime

class TaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: str

class TimeEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    project_id: str
    task_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: int = 0  # seconds
    entry_type: EntryType
    date: str  # YYYY-MM-DD
    notes: Optional[str] = None
    created_at: datetime

class TimeEntryCreate(BaseModel):
    project_id: str
    task_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[int] = None
    entry_type: EntryType = EntryType.TIMER
    notes: Optional[str] = None

class TimerSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    project_id: str
    task_id: str
    start_time: datetime
    last_heartbeat: datetime
    is_active: bool = True
    date: str  # YYYY-MM-DD

class TimerStartRequest(BaseModel):
    project_id: str
    task_id: str

class TimerStopRequest(BaseModel):
    notes: Optional[str] = None

class Timesheet(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    week_start: str  # YYYY-MM-DD
    week_end: str  # YYYY-MM-DD
    total_hours: float
    status: TimesheetStatus
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    admin_comment: Optional[str] = None
    created_at: datetime

class TimesheetSubmit(BaseModel):
    week_start: str
    week_end: str

class TimesheetReview(BaseModel):
    status: TimesheetStatus
    admin_comment: Optional[str] = None

class NotificationType(str, Enum):
    TIMESHEET_SUBMITTED = "timesheet_submitted"
    TIMESHEET_APPROVED = "timesheet_approved"
    TIMESHEET_DENIED = "timesheet_denied"

class Notification(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    type: NotificationType
    title: str
    message: str
    read: bool = False
    related_timesheet_id: Optional[str] = None
    created_at: datetime


# Utility functions
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def create_notification(user_id: str, notification_type: NotificationType, title: str, message: str, related_timesheet_id: Optional[str] = None):
    """Helper function to create a notification"""
    notification_data = {
        "user_id": user_id,
        "type": notification_type.value,
        "title": title,
        "message": message,
        "related_timesheet_id": related_timesheet_id,
        "read": False
    }
    result = supabase.table('notifications').insert(notification_data).execute()
    return result.data[0] if result.data else None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    result = supabase.table('users').select('*').eq('id', user_id).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="User not found")
    
    user_data = result.data[0]
    user = User(**user_data)
    if user.status == UserStatus.INACTIVE:
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    return user

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Auth routes
@api_router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    result = supabase.table('users').select('*').eq('email', request.email).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user_data = result.data[0]
    if not verify_password(request.password, user_data.get('password', '')):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = User(**user_data)
    if user.status == UserStatus.INACTIVE:
        raise HTTPException(status_code=403, detail="Account is inactive. Contact administrator.")
    
    token = create_access_token({"sub": user.id, "role": user.role.value})
    return LoginResponse(token=token, user=user)

@api_router.get("/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# Timer routes
@api_router.post("/timer/start")
async def start_timer(request: TimerStartRequest, current_user: User = Depends(get_current_user)):
    today = datetime.now(timezone.utc).date().isoformat()
    
    # Check for existing active timer
    result = supabase.table('timer_sessions').select('*').eq('user_id', current_user.id).eq('is_active', True).execute()
    if result.data:
        raise HTTPException(status_code=400, detail="Timer already running. Stop current timer first.")
    
    # Create new timer session
    now = datetime.now(timezone.utc)
    timer_data = {
        "user_id": current_user.id,
        "project_id": request.project_id,
        "task_id": request.task_id,
        "start_time": now.isoformat(),
        "last_heartbeat": now.isoformat(),
        "is_active": True,
        "date": today
    }
    
    result = supabase.table('timer_sessions').insert(timer_data).execute()
    timer = result.data[0] if result.data else None
    
    return {"success": True, "timer": timer}

@api_router.post("/timer/heartbeat")
async def timer_heartbeat(current_user: User = Depends(get_current_user)):
    result = supabase.table('timer_sessions').select('*').eq('user_id', current_user.id).eq('is_active', True).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="No active timer found")
    
    timer = result.data[0]
    now = datetime.now(timezone.utc)
    
    supabase.table('timer_sessions').update({
        "last_heartbeat": now.isoformat()
    }).eq('id', timer['id']).execute()
    
    return {"success": True, "last_heartbeat": now}

@api_router.post("/timer/stop")
async def stop_timer(request: TimerStopRequest, current_user: User = Depends(get_current_user)):
    result = supabase.table('timer_sessions').select('*').eq('user_id', current_user.id).eq('is_active', True).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="No active timer found")
    
    timer = result.data[0]
    
    # Calculate duration
    start_time = datetime.fromisoformat(timer['start_time'].replace('Z', '+00:00'))
    end_time = datetime.now(timezone.utc)
    duration = int((end_time - start_time).total_seconds())
    
    # Create time entry
    time_entry_data = {
        "user_id": current_user.id,
        "project_id": timer['project_id'],
        "task_id": timer['task_id'],
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration": duration,
        "entry_type": EntryType.TIMER.value,
        "date": timer['date'],
        "notes": request.notes
    }
    
    entry_result = supabase.table('time_entries').insert(time_entry_data).execute()
    
    # Deactivate timer
    supabase.table('timer_sessions').update({
        "is_active": False
    }).eq('id', timer['id']).execute()
    
    return {"success": True, "time_entry": entry_result.data[0] if entry_result.data else None}

@api_router.get("/timer/active")
async def get_active_timer(current_user: User = Depends(get_current_user)):
    result = supabase.table('timer_sessions').select('*').eq('user_id', current_user.id).eq('is_active', True).execute()
    if not result.data:
        return {"active": False, "timer": None}
    
    timer = result.data[0]
    return {"active": True, "timer": timer}

# Time entries routes
@api_router.get("/time-entries", response_model=List[TimeEntry])
async def get_time_entries(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    query = supabase.table('time_entries').select('*')
    
    # Admins can see all entries, employees only their own
    if current_user.role == UserRole.EMPLOYEE:
        query = query.eq('user_id', current_user.id)
    elif user_id:
        query = query.eq('user_id', user_id)
    
    if start_date and end_date:
        query = query.gte('date', start_date).lte('date', end_date)
    elif start_date:
        query = query.gte('date', start_date)
    elif end_date:
        query = query.lte('date', end_date)
    
    result = query.order('start_time', desc=True).limit(1000).execute()
    return result.data

@api_router.post("/time-entries/manual", response_model=TimeEntry)
async def create_manual_entry(entry: TimeEntryCreate, current_user: User = Depends(get_current_user)):
    if not entry.end_time:
        raise HTTPException(status_code=400, detail="End time required for manual entry")
    
    # Calculate duration if not provided
    if entry.duration is None:
        duration = int((entry.end_time - entry.start_time).total_seconds())
    else:
        duration = entry.duration
    
    time_entry_data = {
        "user_id": current_user.id,
        "project_id": entry.project_id,
        "task_id": entry.task_id,
        "start_time": entry.start_time.isoformat(),
        "end_time": entry.end_time.isoformat(),
        "duration": duration,
        "entry_type": EntryType.MANUAL.value,
        "date": entry.start_time.date().isoformat(),
        "notes": entry.notes
    }
    
    result = supabase.table('time_entries').insert(time_entry_data).execute()
    return result.data[0] if result.data else None

@api_router.delete("/time-entries/{entry_id}")
async def delete_time_entry(entry_id: str, current_user: User = Depends(get_current_user)):
    result = supabase.table('time_entries').select('*').eq('id', entry_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    entry = result.data[0]
    
    # Only owner or admin can delete
    if entry['user_id'] != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    supabase.table('time_entries').delete().eq('id', entry_id).execute()
    return {"success": True}

# Timesheets routes
@api_router.post("/timesheets/submit")
async def submit_timesheet(request: TimesheetSubmit, current_user: User = Depends(get_current_user)):
    # Check if already submitted
    result = supabase.table('timesheets').select('*').eq('user_id', current_user.id).eq('week_start', request.week_start).eq('week_end', request.week_end).execute()
    
    existing = result.data[0] if result.data else None
    
    if existing and existing.get('status') in [TimesheetStatus.SUBMITTED.value, TimesheetStatus.APPROVED.value]:
        raise HTTPException(status_code=400, detail="Timesheet already submitted for this period")
    
    # Calculate total hours
    entries_result = supabase.table('time_entries').select('*').eq('user_id', current_user.id).gte('date', request.week_start).lte('date', request.week_end).execute()
    
    total_seconds = sum(entry.get('duration', 0) for entry in entries_result.data)
    total_hours = round(total_seconds / 3600, 2)
    
    now = datetime.now(timezone.utc)
    
    if existing:
        # Update existing
        update_data = {
            "total_hours": total_hours,
            "status": TimesheetStatus.SUBMITTED.value,
            "submitted_at": now.isoformat()
        }
        supabase.table('timesheets').update(update_data).eq('id', existing['id']).execute()
        timesheet_id = existing['id']
    else:
        # Create new
        timesheet_data = {
            "user_id": current_user.id,
            "week_start": request.week_start,
            "week_end": request.week_end,
            "total_hours": total_hours,
            "status": TimesheetStatus.SUBMITTED.value,
            "submitted_at": now.isoformat()
        }
        
        result = supabase.table('timesheets').insert(timesheet_data).execute()
        timesheet_id = result.data[0]['id'] if result.data else None
    
    # Create notifications for all admins
    admins_result = supabase.table('users').select('*').eq('role', UserRole.ADMIN.value).execute()
    for admin in admins_result.data:
        await create_notification(
            user_id=admin['id'],
            notification_type=NotificationType.TIMESHEET_SUBMITTED,
            title="New Timesheet Submission",
            message=f"{current_user.name} submitted a timesheet for {request.week_start}",
            related_timesheet_id=timesheet_id
        )
    
    return {"success": True, "timesheet_id": timesheet_id}

@api_router.get("/timesheets", response_model=List[Timesheet])
async def get_timesheets(
    status: Optional[TimesheetStatus] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    query = supabase.table('timesheets').select('*')
    
    # Employees see only their own
    if current_user.role == UserRole.EMPLOYEE:
        query = query.eq('user_id', current_user.id)
    elif user_id:
        query = query.eq('user_id', user_id)
    
    if status:
        query = query.eq('status', status.value)
    
    result = query.order('created_at', desc=True).limit(1000).execute()
    return result.data

@api_router.put("/timesheets/{timesheet_id}/review")
async def review_timesheet(
    timesheet_id: str,
    review: TimesheetReview,
    admin_user: User = Depends(get_admin_user)
):
    result = supabase.table('timesheets').select('*').eq('id', timesheet_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    timesheet = result.data[0]
    
    if review.status == TimesheetStatus.DENIED and not review.admin_comment:
        raise HTTPException(status_code=400, detail="Comment required when denying timesheet")
    
    now = datetime.now(timezone.utc)
    update_data = {
        "status": review.status.value,
        "reviewed_at": now.isoformat(),
        "reviewed_by": admin_user.id,
        "admin_comment": review.admin_comment
    }
    
    supabase.table('timesheets').update(update_data).eq('id', timesheet_id).execute()
    
    # Create notification for the employee
    employee_id = timesheet['user_id']
    if review.status == TimesheetStatus.APPROVED:
        notification_type = NotificationType.TIMESHEET_APPROVED
        title = "Timesheet Approved"
        message = f"Your timesheet for {timesheet['week_start']} has been approved"
    else:
        notification_type = NotificationType.TIMESHEET_DENIED
        title = "Timesheet Denied"
        message = f"Your timesheet for {timesheet['week_start']} has been denied"
        if review.admin_comment:
            message += f": {review.admin_comment}"
    
    await create_notification(
        user_id=employee_id,
        notification_type=notification_type,
        title=title,
        message=message,
        related_timesheet_id=timesheet_id
    )
    
    return {"success": True}

# Admin - Employee Management
@api_router.get("/admin/employees", response_model=List[User])
async def get_employees(admin_user: User = Depends(get_admin_user)):
    result = supabase.table('users').select('id, email, name, role, status, default_project, default_task, created_at').order('created_at', desc=True).execute()
    return result.data

@api_router.post("/admin/employees", response_model=User)
async def create_employee(employee: UserCreate, admin_user: User = Depends(get_admin_user)):
    # Check if email exists
    result = supabase.table('users').select('*').eq('email', employee.email).execute()
    if result.data:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_data = {
        "email": employee.email,
        "name": employee.name,
        "password": hash_password(employee.password),
        "role": employee.role.value,
        "status": employee.status.value,
        "default_project": employee.default_project,
        "default_task": employee.default_task
    }
    
    result = supabase.table('users').insert(user_data).execute()
    return result.data[0] if result.data else None

@api_router.put("/admin/employees/{user_id}", response_model=User)
async def update_employee(
    user_id: str,
    update: UserUpdate,
    admin_user: User = Depends(get_admin_user)
):
    result = supabase.table('users').select('*').eq('id', user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = update.model_dump(exclude_unset=True)
    if 'password' in update_data:
        update_data['password'] = hash_password(update_data['password'])
    
    result = supabase.table('users').update(update_data).eq('id', user_id).execute()
    return result.data[0] if result.data else None

# Projects Management
@api_router.get("/projects", response_model=List[Project])
async def get_projects(current_user: User = Depends(get_current_user)):
    result = supabase.table('projects').select('*').order('created_at', desc=True).execute()
    return result.data

@api_router.post("/projects", response_model=Project)
async def create_project(project: ProjectCreate, admin_user: User = Depends(get_admin_user)):
    project_data = {
        "name": project.name,
        "description": project.description,
        "created_by": admin_user.id,
        "status": "active"
    }
    
    result = supabase.table('projects').insert(project_data).execute()
    return result.data[0] if result.data else None

@api_router.put("/projects/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    update: ProjectCreate,
    admin_user: User = Depends(get_admin_user)
):
    result = supabase.table('projects').select('*').eq('id', project_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    update_data = update.model_dump(exclude_unset=True)
    result = supabase.table('projects').update(update_data).eq('id', project_id).execute()
    return result.data[0] if result.data else None

# Tasks Management
@api_router.get("/tasks", response_model=List[Task])
async def get_tasks(project_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    query = supabase.table('tasks').select('*')
    if project_id:
        query = query.eq('project_id', project_id)
    
    result = query.order('created_at', desc=True).execute()
    return result.data

@api_router.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, admin_user: User = Depends(get_admin_user)):
    task_data = {
        "name": task.name,
        "description": task.description,
        "project_id": task.project_id,
        "status": "active"
    }
    
    result = supabase.table('tasks').insert(task_data).execute()
    return result.data[0] if result.data else None

@api_router.put("/tasks/{task_id}", response_model=Task)
async def update_task(
    task_id: str,
    update: TaskCreate,
    admin_user: User = Depends(get_admin_user)
):
    result = supabase.table('tasks').select('*').eq('id', task_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    
    update_data = update.model_dump(exclude_unset=True)
    result = supabase.table('tasks').update(update_data).eq('id', task_id).execute()
    return result.data[0] if result.data else None

# Reports
@api_router.get("/reports/time")
async def get_time_report(
    start_date: str,
    end_date: str,
    group_by: str = "user",  # user, project, task, date
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    # Build query
    query = supabase.table('time_entries').select('*').gte('date', start_date).lte('date', end_date)
    
    if current_user.role == UserRole.EMPLOYEE:
        query = query.eq('user_id', current_user.id)
    elif user_id:
        query = query.eq('user_id', user_id)
    
    if project_id:
        query = query.eq('project_id', project_id)
    
    # Get entries
    entries_result = query.execute()
    entries = entries_result.data
    
    # Get related data
    users_result = supabase.table('users').select('*').execute()
    users = {u['id']: u for u in users_result.data}
    
    projects_result = supabase.table('projects').select('*').execute()
    projects = {p['id']: p for p in projects_result.data}
    
    tasks_result = supabase.table('tasks').select('*').execute()
    tasks = {t['id']: t for t in tasks_result.data}
    
    # Group data
    grouped = {}
    for entry in entries:
        key = None
        if group_by == "user":
            key = entry['user_id']
            label = users.get(key, {}).get('name', 'Unknown')
        elif group_by == "project":
            key = entry['project_id']
            label = projects.get(key, {}).get('name', 'Unknown')
        elif group_by == "task":
            key = entry['task_id']
            label = tasks.get(key, {}).get('name', 'Unknown')
        elif group_by == "date":
            key = entry['date']
            label = entry['date']
        else:
            key = "all"
            label = "All"
        
        if key not in grouped:
            grouped[key] = {
                "id": key,
                "label": label,
                "total_seconds": 0,
                "total_hours": 0,
                "entry_count": 0
            }
        
        grouped[key]['total_seconds'] += entry.get('duration', 0)
        grouped[key]['entry_count'] += 1
    
    # Calculate hours
    for item in grouped.values():
        item['total_hours'] = round(item['total_seconds'] / 3600, 2)
    
    return {
        "data": list(grouped.values()),
        "summary": {
            "total_seconds": sum(g['total_seconds'] for g in grouped.values()),
            "total_hours": round(sum(g['total_seconds'] for g in grouped.values()) / 3600, 2),
            "total_entries": sum(g['entry_count'] for g in grouped.values())
        }
    }

@api_router.get("/reports/export/pdf")
async def export_pdf(
    start_date: str,
    end_date: str,
    user_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    # Build query
    query = supabase.table('time_entries').select('*').gte('date', start_date).lte('date', end_date)
    
    if current_user.role == UserRole.EMPLOYEE:
        query = query.eq('user_id', current_user.id)
    elif user_id:
        query = query.eq('user_id', user_id)
    
    # Get entries
    entries_result = query.execute()
    entries = entries_result.data
    
    # Get related data
    users_result = supabase.table('users').select('*').execute()
    users = {u['id']: u for u in users_result.data}
    
    projects_result = supabase.table('projects').select('*').execute()
    projects = {p['id']: p for p in projects_result.data}
    
    tasks_result = supabase.table('tasks').select('*').execute()
    tasks = {t['id']: t for t in tasks_result.data}
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title = Paragraph(f"Time Report ({start_date} to {end_date})", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.3*inch))
    
    # Table data
    data = [['Date', 'Employee', 'Project', 'Task', 'Duration (hrs)']]
    total_seconds = 0
    
    for entry in entries:
        user_name = users.get(entry['user_id'], {}).get('name', 'Unknown')
        project_name = projects.get(entry['project_id'], {}).get('name', 'Unknown')
        task_name = tasks.get(entry['task_id'], {}).get('name', 'Unknown')
        hours = round(entry.get('duration', 0) / 3600, 2)
        
        data.append([
            entry['date'],
            user_name,
            project_name,
            task_name,
            str(hours)
        ])
        total_seconds += entry.get('duration', 0)
    
    # Add total
    data.append(['', '', '', 'Total', str(round(total_seconds / 3600, 2))])
    
    # Create table
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=time_report_{start_date}_{end_date}.pdf"}
    )

@api_router.get("/reports/export/csv")
async def export_csv(
    start_date: str,
    end_date: str,
    user_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    # Build query
    query = supabase.table('time_entries').select('*').gte('date', start_date).lte('date', end_date)
    
    if current_user.role == UserRole.EMPLOYEE:
        query = query.eq('user_id', current_user.id)
    elif user_id:
        query = query.eq('user_id', user_id)
    
    # Get entries
    entries_result = query.execute()
    entries = entries_result.data
    
    # Get related data
    users_result = supabase.table('users').select('*').execute()
    users = {u['id']: u for u in users_result.data}
    
    projects_result = supabase.table('projects').select('*').execute()
    projects = {p['id']: p for p in projects_result.data}
    
    tasks_result = supabase.table('tasks').select('*').execute()
    tasks = {t['id']: t for t in tasks_result.data}
    
    # Build CSV
    csv_data = "Date,Employee,Project,Task,Duration (hours)\n"
    
    for entry in entries:
        user_name = users.get(entry['user_id'], {}).get('name', 'Unknown')
        project_name = projects.get(entry['project_id'], {}).get('name', 'Unknown')
        task_name = tasks.get(entry['task_id'], {}).get('name', 'Unknown')
        hours = round(entry.get('duration', 0) / 3600, 2)
        
        csv_data += f"{entry['date']},{user_name},{project_name},{task_name},{hours}\n"
    
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=time_report_{start_date}_{end_date}.csv"}
    )

# Dashboard stats
@api_router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: User = Depends(get_current_user)):
    if current_user.role == UserRole.ADMIN:
        # Admin stats
        total_employees_result = supabase.table('users').select('id', count='exact').eq('role', UserRole.EMPLOYEE.value).execute()
        total_employees = total_employees_result.count or 0
        
        active_employees_result = supabase.table('users').select('id', count='exact').eq('role', UserRole.EMPLOYEE.value).eq('status', UserStatus.ACTIVE.value).execute()
        active_employees = active_employees_result.count or 0
        
        pending_timesheets_result = supabase.table('timesheets').select('id', count='exact').eq('status', TimesheetStatus.SUBMITTED.value).execute()
        pending_timesheets = pending_timesheets_result.count or 0
        
        total_projects_result = supabase.table('projects').select('id', count='exact').execute()
        total_projects = total_projects_result.count or 0
        
        # Active timers
        active_timers_result = supabase.table('timer_sessions').select('id', count='exact').eq('is_active', True).execute()
        active_timers = active_timers_result.count or 0
        
        return {
            "total_employees": total_employees,
            "active_employees": active_employees,
            "pending_timesheets": pending_timesheets,
            "total_projects": total_projects,
            "active_timers": active_timers
        }
    else:
        # Employee stats
        today = datetime.now(timezone.utc).date().isoformat()
        week_start = (datetime.now(timezone.utc).date() - timedelta(days=datetime.now(timezone.utc).weekday())).isoformat()
        
        today_entries_result = supabase.table('time_entries').select('duration').eq('user_id', current_user.id).eq('date', today).execute()
        today_seconds = sum(e.get('duration', 0) for e in today_entries_result.data)
        
        week_entries_result = supabase.table('time_entries').select('duration').eq('user_id', current_user.id).gte('date', week_start).execute()
        week_seconds = sum(e.get('duration', 0) for e in week_entries_result.data)
        
        return {
            "today_hours": round(today_seconds / 3600, 2),
            "week_hours": round(week_seconds / 3600, 2),
            "total_entries": len(week_entries_result.data)
        }


# Notification routes
@api_router.get("/notifications", response_model=List[Notification])
async def get_notifications(
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get user's notifications"""
    result = supabase.table('notifications').select('*').eq('user_id', current_user.id).order('created_at', desc=True).limit(limit).execute()
    return result.data

@api_router.get("/notifications/unread-count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    """Get count of unread notifications"""
    result = supabase.table('notifications').select('id', count='exact').eq('user_id', current_user.id).eq('read', False).execute()
    return {"count": result.count or 0}

@api_router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark a notification as read"""
    result = supabase.table('notifications').select('*').eq('id', notification_id).eq('user_id', current_user.id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    supabase.table('notifications').update({"read": True}).eq('id', notification_id).execute()
    
    return {"success": True}

@api_router.put("/notifications/mark-all-read")
async def mark_all_notifications_read(current_user: User = Depends(get_current_user)):
    """Mark all user's notifications as read"""
    supabase.table('notifications').update({"read": True}).eq('user_id', current_user.id).eq('read', False).execute()
    
    return {"success": True}


# Include router
app.include_router(api_router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    logger.info("Omni Gratum Time Tracking System started with Supabase")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Omni Gratum Time Tracking System")
