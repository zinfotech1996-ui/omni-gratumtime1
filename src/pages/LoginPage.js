import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { Clock } from 'lucide-react';

export const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    const result = await login(email, password);
    setLoading(false);

    if (result.success) {
      toast.success('Login successful!');
      navigate('/dashboard');
    } else {
      toast.error(result.error);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left side - Login Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8 bg-background">
        <div className="w-full max-w-md space-y-8">
          {/* Logo */}
          <div className="text-center">
          <div className="inline-flex items-center justify-center w-60 h-26 mb-2">
              {/* <Clock className="h-8 w-8 text-primary-foreground" /> */}
              <img 
                src="/omni_gratum_logo_whitebg.jpg" 
                alt="Omni Gratum Logo" 
                className="h-full w-auto object-contain"
              />
            </div>
            <h1 className="text-4xl font-bold tracking-tight" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
              Omni Gratum
            </h1>
            <p className="text-muted-foreground mt-2">Time Tracking System</p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-6" data-testid="login-form">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="admin@omnigratum.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                data-testid="login-email-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                data-testid="login-password-input"
              />
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={loading}
              data-testid="login-submit-btn"
            >
              {loading ? 'Logging in...' : 'Login'}
            </Button>
          </form>

          {/* Demo credentials */}
          <div className="text-center text-sm text-muted-foreground border-t border-border pt-6">
            <p className="font-medium mb-2">Demo Credentials:</p>
            <p>Admin: admin@omnigratum.com / admin123</p>
            <p>Employee: employee@omnigratum.com / employee123</p>
          </div>
        </div>
      </div>

      {/* Right side - Image/Pattern */}
      <div
        className="hidden lg:block lg:w-1/2 bg-cover bg-center relative"
        style={{
          backgroundImage: `url('login_bg.jpg')`,
        }}
      >
        <div className="absolute inset-0 bg-primary/10 "></div>
      </div>
    </div>
  );
};
