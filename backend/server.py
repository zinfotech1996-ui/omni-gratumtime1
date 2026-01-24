from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
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

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    name: str
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE
    default_project: Optional[str] = None
    default_task: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    created_by: str
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None

class Task(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    project_id: str
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: str

class TimeEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    project_id: str
    task_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: int = 0  # seconds
    entry_type: EntryType
    date: str  # YYYY-MM-DD
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    week_start: str  # YYYY-MM-DD
    week_end: str  # YYYY-MM-DD
    total_hours: float
    status: TimesheetStatus
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    admin_comment: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: NotificationType
    title: str
    message: str
    read: bool = False
    related_timesheet_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        related_timesheet_id=related_timesheet_id
    )
    notification_doc = notification.model_dump()
    notification_doc['created_at'] = notification_doc['created_at'].isoformat()
    await db.notifications.insert_one(notification_doc)
    return notification


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
    
    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user_doc is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    user = User(**user_doc)
    if user.status == UserStatus.INACTIVE:
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    return user

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Initialize default admin and employee
async def init_default_admin():
    existing_admin = await db.users.find_one({"role": UserRole.ADMIN.value}, {"_id": 0})
    if not existing_admin:
        admin_user = User(
            email="admin@omnigratum.com",
            name="Admin User",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        admin_doc = admin_user.model_dump()
        admin_doc['password'] = hash_password("admin123")
        admin_doc['created_at'] = admin_doc['created_at'].isoformat()
        await db.users.insert_one(admin_doc)
        logging.info("Default admin created: admin@omnigratum.com / admin123")
    
    # Create default employee user for testing timer widget
    existing_employee = await db.users.find_one({"email": "employee@omnigratum.com"}, {"_id": 0})
    if not existing_employee:
        employee_user = User(
            email="employee@omnigratum.com",
            name="John Employee",
            role=UserRole.EMPLOYEE,
            status=UserStatus.ACTIVE
        )
        employee_doc = employee_user.model_dump()
        employee_doc['password'] = hash_password("employee123")
        employee_doc['created_at'] = employee_doc['created_at'].isoformat()
        await db.users.insert_one(employee_doc)
        logging.info("Default employee created: employee@omnigratum.com / employee123")

# Auth routes
@api_router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    user_doc = await db.users.find_one({"email": request.email}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(request.password, user_doc.get('password', '')):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = User(**user_doc)
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
    existing_timer = await db.timer_sessions.find_one(
        {"user_id": current_user.id, "is_active": True},
        {"_id": 0}
    )
    if existing_timer:
        raise HTTPException(status_code=400, detail="Timer already running. Stop current timer first.")
    
    # Create new timer session
    now = datetime.now(timezone.utc)
    timer = TimerSession(
        user_id=current_user.id,
        project_id=request.project_id,
        task_id=request.task_id,
        start_time=now,
        last_heartbeat=now,
        is_active=True,
        date=today
    )
    
    timer_doc = timer.model_dump()
    timer_doc['start_time'] = timer_doc['start_time'].isoformat()
    timer_doc['last_heartbeat'] = timer_doc['last_heartbeat'].isoformat()
    await db.timer_sessions.insert_one(timer_doc)
    
    return {"success": True, "timer": timer}

@api_router.post("/timer/heartbeat")
async def timer_heartbeat(current_user: User = Depends(get_current_user)):
    timer_doc = await db.timer_sessions.find_one(
        {"user_id": current_user.id, "is_active": True},
        {"_id": 0}
    )
    if not timer_doc:
        raise HTTPException(status_code=404, detail="No active timer found")
    
    now = datetime.now(timezone.utc)
    await db.timer_sessions.update_one(
        {"id": timer_doc['id']},
        {"$set": {"last_heartbeat": now.isoformat()}}
    )
    
    return {"success": True, "last_heartbeat": now}

@api_router.post("/timer/stop")
async def stop_timer(request: TimerStopRequest, current_user: User = Depends(get_current_user)):
    timer_doc = await db.timer_sessions.find_one(
        {"user_id": current_user.id, "is_active": True},
        {"_id": 0}
    )
    if not timer_doc:
        raise HTTPException(status_code=404, detail="No active timer found")
    
    # Calculate duration
    start_time = datetime.fromisoformat(timer_doc['start_time'])
    end_time = datetime.now(timezone.utc)
    duration = int((end_time - start_time).total_seconds())
    
    # Create time entry
    time_entry = TimeEntry(
        user_id=current_user.id,
        project_id=timer_doc['project_id'],
        task_id=timer_doc['task_id'],
        start_time=start_time,
        end_time=end_time,
        duration=duration,
        entry_type=EntryType.TIMER,
        date=timer_doc['date'],
        notes=request.notes
    )
    
    entry_doc = time_entry.model_dump()
    entry_doc['start_time'] = entry_doc['start_time'].isoformat()
    entry_doc['end_time'] = entry_doc['end_time'].isoformat()
    entry_doc['created_at'] = entry_doc['created_at'].isoformat()
    await db.time_entries.insert_one(entry_doc)
    
    # Deactivate timer
    await db.timer_sessions.update_one(
        {"id": timer_doc['id']},
        {"$set": {"is_active": False}}
    )
    
    return {"success": True, "time_entry": time_entry}

@api_router.get("/timer/active")
async def get_active_timer(current_user: User = Depends(get_current_user)):
    timer_doc = await db.timer_sessions.find_one(
        {"user_id": current_user.id, "is_active": True},
        {"_id": 0}
    )
    if not timer_doc:
        return {"active": False, "timer": None}
    
    # Parse datetime
    if isinstance(timer_doc['start_time'], str):
        timer_doc['start_time'] = datetime.fromisoformat(timer_doc['start_time'])
    if isinstance(timer_doc['last_heartbeat'], str):
        timer_doc['last_heartbeat'] = datetime.fromisoformat(timer_doc['last_heartbeat'])
    
    timer = TimerSession(**timer_doc)
    return {"active": True, "timer": timer}

# Time entries routes
@api_router.get("/time-entries", response_model=List[TimeEntry])
async def get_time_entries(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    query = {}
    
    # Admins can see all entries, employees only their own
    if current_user.role == UserRole.EMPLOYEE:
        query['user_id'] = current_user.id
    elif user_id:
        query['user_id'] = user_id
    
    if start_date and end_date:
        query['date'] = {"$gte": start_date, "$lte": end_date}
    elif start_date:
        query['date'] = {"$gte": start_date}
    elif end_date:
        query['date'] = {"$lte": end_date}
    
    entries = await db.time_entries.find(query, {"_id": 0}).sort("start_time", -1).to_list(1000)
    
    # Parse datetime strings
    for entry in entries:
        if isinstance(entry['start_time'], str):
            entry['start_time'] = datetime.fromisoformat(entry['start_time'])
        if entry.get('end_time') and isinstance(entry['end_time'], str):
            entry['end_time'] = datetime.fromisoformat(entry['end_time'])
        if isinstance(entry['created_at'], str):
            entry['created_at'] = datetime.fromisoformat(entry['created_at'])
    
    return entries

@api_router.post("/time-entries/manual", response_model=TimeEntry)
async def create_manual_entry(entry: TimeEntryCreate, current_user: User = Depends(get_current_user)):
    if not entry.end_time:
        raise HTTPException(status_code=400, detail="End time required for manual entry")
    
    # Calculate duration if not provided
    if entry.duration is None:
        duration = int((entry.end_time - entry.start_time).total_seconds())
    else:
        duration = entry.duration
    
    time_entry = TimeEntry(
        user_id=current_user.id,
        project_id=entry.project_id,
        task_id=entry.task_id,
        start_time=entry.start_time,
        end_time=entry.end_time,
        duration=duration,
        entry_type=EntryType.MANUAL,
        date=entry.start_time.date().isoformat(),
        notes=entry.notes
    )
    
    entry_doc = time_entry.model_dump()
    entry_doc['start_time'] = entry_doc['start_time'].isoformat()
    entry_doc['end_time'] = entry_doc['end_time'].isoformat()
    entry_doc['created_at'] = entry_doc['created_at'].isoformat()
    await db.time_entries.insert_one(entry_doc)
    
    return time_entry

@api_router.delete("/time-entries/{entry_id}")
async def delete_time_entry(entry_id: str, current_user: User = Depends(get_current_user)):
    entry = await db.time_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    # Only owner or admin can delete
    if entry['user_id'] != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.time_entries.delete_one({"id": entry_id})
    return {"success": True}

# Timesheets routes
@api_router.post("/timesheets/submit")
async def submit_timesheet(request: TimesheetSubmit, current_user: User = Depends(get_current_user)):
    # Check if already submitted
    existing = await db.timesheets.find_one({
        "user_id": current_user.id,
        "week_start": request.week_start,
        "week_end": request.week_end
    }, {"_id": 0})
    
    if existing and existing.get('status') in [TimesheetStatus.SUBMITTED.value, TimesheetStatus.APPROVED.value]:
        raise HTTPException(status_code=400, detail="Timesheet already submitted for this period")
    
    # Calculate total hours
    entries = await db.time_entries.find({
        "user_id": current_user.id,
        "date": {"$gte": request.week_start, "$lte": request.week_end}
    }, {"_id": 0}).to_list(1000)
    
    total_seconds = sum(entry.get('duration', 0) for entry in entries)
    total_hours = round(total_seconds / 3600, 2)
    
    now = datetime.now(timezone.utc)
    
    if existing:
        # Update existing
        await db.timesheets.update_one(
            {"id": existing['id']},
            {"$set": {
                "total_hours": total_hours,
                "status": TimesheetStatus.SUBMITTED.value,
                "submitted_at": now.isoformat()
            }}
        )
        timesheet_id = existing['id']
    else:
        # Create new
        timesheet = Timesheet(
            user_id=current_user.id,
            week_start=request.week_start,
            week_end=request.week_end,
            total_hours=total_hours,
            status=TimesheetStatus.SUBMITTED,
            submitted_at=now
        )
        
        timesheet_doc = timesheet.model_dump()
        timesheet_doc['submitted_at'] = timesheet_doc['submitted_at'].isoformat()
        timesheet_doc['created_at'] = timesheet_doc['created_at'].isoformat()
        await db.timesheets.insert_one(timesheet_doc)
        timesheet_id = timesheet.id
    
    # Create notifications for all admins
    admins = await db.users.find({"role": UserRole.ADMIN.value}, {"_id": 0}).to_list(1000)
    for admin in admins:
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
    query = {}
    
    # Employees see only their own
    if current_user.role == UserRole.EMPLOYEE:
        query['user_id'] = current_user.id
    elif user_id:
        query['user_id'] = user_id
    
    if status:
        query['status'] = status.value
    
    timesheets = await db.timesheets.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    # Parse datetime strings
    for ts in timesheets:
        if ts.get('submitted_at') and isinstance(ts['submitted_at'], str):
            ts['submitted_at'] = datetime.fromisoformat(ts['submitted_at'])
        if ts.get('reviewed_at') and isinstance(ts['reviewed_at'], str):
            ts['reviewed_at'] = datetime.fromisoformat(ts['reviewed_at'])
        if isinstance(ts['created_at'], str):
            ts['created_at'] = datetime.fromisoformat(ts['created_at'])
    
    return timesheets

@api_router.put("/timesheets/{timesheet_id}/review")
async def review_timesheet(
    timesheet_id: str,
    review: TimesheetReview,
    admin_user: User = Depends(get_admin_user)
):
    timesheet = await db.timesheets.find_one({"id": timesheet_id}, {"_id": 0})
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    if review.status == TimesheetStatus.DENIED and not review.admin_comment:
        raise HTTPException(status_code=400, detail="Comment required when denying timesheet")
    
    now = datetime.now(timezone.utc)
    await db.timesheets.update_one(
        {"id": timesheet_id},
        {"$set": {
            "status": review.status.value,
            "reviewed_at": now.isoformat(),
            "reviewed_by": admin_user.id,
            "admin_comment": review.admin_comment
        }}
    )
    
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
    users = await db.users.find({}, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(1000)
    
    for user in users:
        if isinstance(user['created_at'], str):
            user['created_at'] = datetime.fromisoformat(user['created_at'])
    
    return users

@api_router.post("/admin/employees", response_model=User)
async def create_employee(employee: UserCreate, admin_user: User = Depends(get_admin_user)):
    # Check if email exists
    existing = await db.users.find_one({"email": employee.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=employee.email,
        name=employee.name,
        role=employee.role,
        status=employee.status,
        default_project=employee.default_project,
        default_task=employee.default_task
    )
    
    user_doc = user.model_dump()
    user_doc['password'] = hash_password(employee.password)
    user_doc['created_at'] = user_doc['created_at'].isoformat()
    await db.users.insert_one(user_doc)
    
    return user

@api_router.put("/admin/employees/{user_id}", response_model=User)
async def update_employee(
    user_id: str,
    update: UserUpdate,
    admin_user: User = Depends(get_admin_user)
):
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = update.model_dump(exclude_unset=True)
    if 'password' in update_data:
        update_data['password'] = hash_password(update_data['password'])
    
    await db.users.update_one({"id": user_id}, {"$set": update_data})
    
    updated_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if isinstance(updated_user['created_at'], str):
        updated_user['created_at'] = datetime.fromisoformat(updated_user['created_at'])
    
    return User(**updated_user)

# Projects Management
@api_router.get("/projects", response_model=List[Project])
async def get_projects(current_user: User = Depends(get_current_user)):
    projects = await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    for project in projects:
        if isinstance(project['created_at'], str):
            project['created_at'] = datetime.fromisoformat(project['created_at'])
    
    return projects

@api_router.post("/projects", response_model=Project)
async def create_project(project: ProjectCreate, admin_user: User = Depends(get_admin_user)):
    new_project = Project(
        name=project.name,
        description=project.description,
        created_by=admin_user.id
    )
    
    project_doc = new_project.model_dump()
    project_doc['created_at'] = project_doc['created_at'].isoformat()
    await db.projects.insert_one(project_doc)
    
    return new_project

@api_router.put("/projects/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    update: ProjectCreate,
    admin_user: User = Depends(get_admin_user)
):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    update_data = update.model_dump(exclude_unset=True)
    await db.projects.update_one({"id": project_id}, {"$set": update_data})
    
    updated = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if isinstance(updated['created_at'], str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    
    return Project(**updated)

# Tasks Management
@api_router.get("/tasks", response_model=List[Task])
async def get_tasks(project_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    query = {}
    if project_id:
        query['project_id'] = project_id
    
    tasks = await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    for task in tasks:
        if isinstance(task['created_at'], str):
            task['created_at'] = datetime.fromisoformat(task['created_at'])
    
    return tasks

@api_router.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, admin_user: User = Depends(get_admin_user)):
    new_task = Task(
        name=task.name,
        description=task.description,
        project_id=task.project_id
    )
    
    task_doc = new_task.model_dump()
    task_doc['created_at'] = task_doc['created_at'].isoformat()
    await db.tasks.insert_one(task_doc)
    
    return new_task

@api_router.put("/tasks/{task_id}", response_model=Task)
async def update_task(
    task_id: str,
    update: TaskCreate,
    admin_user: User = Depends(get_admin_user)
):
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    update_data = update.model_dump(exclude_unset=True)
    await db.tasks.update_one({"id": task_id}, {"$set": update_data})
    
    updated = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if isinstance(updated['created_at'], str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    
    return Task(**updated)

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
    query = {
        "date": {"$gte": start_date, "$lte": end_date}
    }
    
    if current_user.role == UserRole.EMPLOYEE:
        query['user_id'] = current_user.id
    elif user_id:
        query['user_id'] = user_id
    
    if project_id:
        query['project_id'] = project_id
    
    # Get entries
    entries = await db.time_entries.find(query, {"_id": 0}).to_list(10000)
    
    # Get related data
    users = {u['id']: u for u in await db.users.find({}, {"_id": 0}).to_list(1000)}
    projects = {p['id']: p for p in await db.projects.find({}, {"_id": 0}).to_list(1000)}
    tasks = {t['id']: t for t in await db.tasks.find({}, {"_id": 0}).to_list(1000)}
    
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
    query = {
        "date": {"$gte": start_date, "$lte": end_date}
    }
    
    if current_user.role == UserRole.EMPLOYEE:
        query['user_id'] = current_user.id
    elif user_id:
        query['user_id'] = user_id
    
    # Get entries
    entries = await db.time_entries.find(query, {"_id": 0}).to_list(10000)
    
    # Get related data
    users = {u['id']: u for u in await db.users.find({}, {"_id": 0}).to_list(1000)}
    projects = {p['id']: p for p in await db.projects.find({}, {"_id": 0}).to_list(1000)}
    tasks = {t['id']: t for t in await db.tasks.find({}, {"_id": 0}).to_list(1000)}
    
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
    query = {
        "date": {"$gte": start_date, "$lte": end_date}
    }
    
    if current_user.role == UserRole.EMPLOYEE:
        query['user_id'] = current_user.id
    elif user_id:
        query['user_id'] = user_id
    
    # Get entries
    entries = await db.time_entries.find(query, {"_id": 0}).to_list(10000)
    
    # Get related data
    users = {u['id']: u for u in await db.users.find({}, {"_id": 0}).to_list(1000)}
    projects = {p['id']: p for p in await db.projects.find({}, {"_id": 0}).to_list(1000)}
    tasks = {t['id']: t for t in await db.tasks.find({}, {"_id": 0}).to_list(1000)}
    
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
        total_employees = await db.users.count_documents({"role": UserRole.EMPLOYEE.value})
        active_employees = await db.users.count_documents({"role": UserRole.EMPLOYEE.value, "status": UserStatus.ACTIVE.value})
        pending_timesheets = await db.timesheets.count_documents({"status": TimesheetStatus.SUBMITTED.value})
        total_projects = await db.projects.count_documents({})
        
        # Active timers
        active_timers = await db.timer_sessions.count_documents({"is_active": True})
        
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
        
        today_entries = await db.time_entries.find({"user_id": current_user.id, "date": today}, {"_id": 0}).to_list(1000)
        today_seconds = sum(e.get('duration', 0) for e in today_entries)
        
        week_entries = await db.time_entries.find({
            "user_id": current_user.id,
            "date": {"$gte": week_start}
        }, {"_id": 0}).to_list(1000)
        week_seconds = sum(e.get('duration', 0) for e in week_entries)
        
        return {
            "today_hours": round(today_seconds / 3600, 2),
            "week_hours": round(week_seconds / 3600, 2),
            "total_entries": len(week_entries)
        }


# Notification routes
@api_router.get("/notifications", response_model=List[Notification])
async def get_notifications(
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get user's notifications"""
    notifications = await db.notifications.find(
        {"user_id": current_user.id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    # Parse datetime strings
    for notif in notifications:
        if isinstance(notif['created_at'], str):
            notif['created_at'] = datetime.fromisoformat(notif['created_at'])
    
    return notifications

@api_router.get("/notifications/unread-count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    """Get count of unread notifications"""
    count = await db.notifications.count_documents({
        "user_id": current_user.id,
        "read": False
    })
    return {"count": count}

@api_router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark a notification as read"""
    notification = await db.notifications.find_one({
        "id": notification_id,
        "user_id": current_user.id
    }, {"_id": 0})
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    await db.notifications.update_one(
        {"id": notification_id},
        {"$set": {"read": True}}
    )
    
    return {"success": True}

@api_router.put("/notifications/mark-all-read")
async def mark_all_notifications_read(current_user: User = Depends(get_current_user)):
    """Mark all user's notifications as read"""
    await db.notifications.update_many(
        {"user_id": current_user.id, "read": False},
        {"$set": {"read": True}}
    )
    
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
    await init_default_admin()
    logger.info("Omni Gratum Time Tracking System started")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
