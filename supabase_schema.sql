-- Omni Gratum Time Tracking System - PostgreSQL Schema for Supabase
-- Execute this SQL in your Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('admin', 'employee')),
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    default_project UUID,
    default_task UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_by UUID NOT NULL REFERENCES users(id),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tasks table
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Time entries table
CREATE TABLE time_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id),
    task_id UUID NOT NULL REFERENCES tasks(id),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration INTEGER NOT NULL DEFAULT 0,
    entry_type VARCHAR(50) NOT NULL CHECK (entry_type IN ('timer', 'manual')),
    date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Timer sessions table
CREATE TABLE timer_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id),
    task_id UUID NOT NULL REFERENCES tasks(id),
    start_time TIMESTAMPTZ NOT NULL,
    last_heartbeat TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    date DATE NOT NULL
);

-- Timesheets table
CREATE TABLE timesheets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    total_hours DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) NOT NULL CHECK (status IN ('draft', 'submitted', 'approved', 'denied')),
    submitted_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES users(id),
    admin_comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Notifications table
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL CHECK (type IN ('timesheet_submitted', 'timesheet_approved', 'timesheet_denied')),
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    read BOOLEAN NOT NULL DEFAULT FALSE,
    related_timesheet_id UUID REFERENCES timesheets(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_status ON users(status);

CREATE INDEX idx_projects_created_by ON projects(created_by);
CREATE INDEX idx_projects_status ON projects(status);

CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_tasks_status ON tasks(status);

CREATE INDEX idx_time_entries_user_id ON time_entries(user_id);
CREATE INDEX idx_time_entries_project_id ON time_entries(project_id);
CREATE INDEX idx_time_entries_task_id ON time_entries(task_id);
CREATE INDEX idx_time_entries_date ON time_entries(date);
CREATE INDEX idx_time_entries_user_date ON time_entries(user_id, date);

CREATE INDEX idx_timer_sessions_user_id ON timer_sessions(user_id);
CREATE INDEX idx_timer_sessions_is_active ON timer_sessions(is_active);
CREATE INDEX idx_timer_sessions_user_active ON timer_sessions(user_id, is_active);

CREATE INDEX idx_timesheets_user_id ON timesheets(user_id);
CREATE INDEX idx_timesheets_status ON timesheets(status);
CREATE INDEX idx_timesheets_week ON timesheets(week_start, week_end);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_read ON notifications(read);
CREATE INDEX idx_notifications_user_read ON notifications(user_id, read);

-- Enable Row Level Security (RLS) - Optional but recommended for Supabase
-- You can configure RLS policies in Supabase dashboard if needed

-- Insert default admin user (password: admin123)
-- Password hash for 'admin123' using bcrypt
INSERT INTO users (email, name, password, role, status) 
VALUES (
    'admin@omnigratum.com', 
    'Admin User', 
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5oCvJ9J9pU8Kq',
    'admin', 
    'active'
);

-- Insert default employee user (password: employee123)
INSERT INTO users (email, name, password, role, status) 
VALUES (
    'employee@omnigratum.com', 
    'John Employee', 
    '$2b$12$8K1p/FwT/fWqJfMZJKLlZu5h3XQFm9bPjTJQHhJlNyJ1JVKJ1ZFQS',
    'employee', 
    'active'
);

-- Success message
SELECT 'Database schema created successfully!' as message;
