import React, { useState } from 'react';
import { Outlet, useLocation, Navigate, Link } from 'react-router-dom'; // Add Link here
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { Clock, LayoutDashboard, Users, FolderKanban, FileText, BarChart3, Settings, LogOut, Moon, Sun, Globe, Bell } from 'lucide-react';
import { Button } from './ui/button';
import { StickyTimerWidget } from './StickyTimerWidget';
import { useTranslation } from 'react-i18next';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { NotificationDropdown } from './NotificationDropdown';

export const DashboardLayout = () => {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const [currentLanguage, setCurrentLanguage] = useState(i18n.language);

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const changeLanguage = (lng) => {
    i18n.changeLanguage(lng);
    setCurrentLanguage(lng);
  };

  const languages = [
    { code: 'en', name: t('language.english'), flag: '🇬🇧' },
    { code: 'es', name: t('language.spanish'), flag: '🇪🇸' },
    { code: 'fr', name: t('language.french'), flag: '🇫🇷' },
  ];

  const isAdmin = user.role === 'admin';

  const navigation = isAdmin
    ? [
        { name: t('nav.dashboard'), href: '/dashboard', icon: LayoutDashboard },
        { name: t('nav.approvals'), href: '/admin/approvals', icon: FileText },
        { name: t('nav.team'), href: '/admin/team', icon: Users },
        { name: t('nav.projectsTasks'), href: '/admin/projects', icon: FolderKanban },
        { name: t('nav.reports'), href: '/reports', icon: BarChart3 },
        { name: t('nav.settings'), href: '/settings', icon: Settings },
      ]
    : [
        { name: t('nav.dashboard'), href: '/dashboard', icon: LayoutDashboard },
        { name: t('nav.timeTracker'), href: '/tracker', icon: Clock },
        { name: t('nav.timesheets'), href: '/timesheets', icon: FileText },
        { name: t('nav.reports'), href: '/reports', icon: BarChart3 },
        { name: t('nav.settings'), href: '/settings', icon: Settings },
      ];

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 w-64 bg-card border-r border-border">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-6 border-b border-border">
            <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
              {t('app.title')}
            </h1>
            <p className="text-xs text-muted-foreground mt-1">{t('app.subtitle')}</p>
          </div>

          {/* Navigation - CHANGED FROM <a> TO <Link> */}
          <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  to={item.href}   
                  data-testid={`nav-${item.name.toLowerCase().replace(/\s+/g, '-')}`}
                  className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-foreground hover:bg-muted'
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  {item.name}
                </Link>
              );
            })}
          </nav>

          {/* User section */}
          <div className="p-4 border-t border-border space-y-2">
            <div className="flex items-center gap-3 px-3 py-2">
              <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-semibold text-sm">
                {user.name.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{user.name}</p>
                <p className="text-xs text-muted-foreground capitalize">{user.role}</p>
              </div>
            </div>
            <div className="flex gap-2">
              <NotificationDropdown />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    data-testid="language-toggle-btn"
                    className="flex-1"
                  >
                    <Globe className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {languages.map((lang) => (
                    <DropdownMenuItem
                      key={lang.code}
                      onClick={() => changeLanguage(lang.code)}
                      className={currentLanguage === lang.code ? 'bg-muted' : ''}
                    >
                      <span className="mr-2">{lang.flag}</span>
                      {lang.name}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
              <Button
                variant="ghost"
                size="sm"
                onClick={toggleTheme}
                data-testid="theme-toggle-btn"
                className="flex-1"
              >
                {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={logout}
                data-testid="logout-btn"
                className="flex-1"
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="ml-64 min-h-screen">
        <div className="p-6 md:p-8 lg:p-12">
          <Outlet />
        </div>
      </main>

      {/* Sticky Timer Widget for employees */}
      {!isAdmin && <StickyTimerWidget />}
    </div>
  );
};