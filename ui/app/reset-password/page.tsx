'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token') || '';

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      if (res.ok) {
        setSuccess(true);
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || 'Failed to reset password. The link may have expired.');
      }
    } catch {
      setError('Network error. Please try again.');
    }
    setLoading(false);
  };

  if (!token) {
    return (
      <div className="bg-red-100 border-2 border-red-400 text-red-800 px-4 py-4 rounded-xl text-base font-medium">
        Invalid reset link. Please request a new one.{' '}
        <Link href="/forgot-password" className="underline font-semibold">
          Forgot password?
        </Link>
      </div>
    );
  }

  if (success) {
    return (
      <div className="space-y-4">
        <div className="bg-green-50 border-2 border-green-400 text-green-800 px-4 py-4 rounded-xl text-base font-medium">
          Password reset successfully!
        </div>
        <div className="text-center">
          <Link href="/login" className="btn-primary inline-block">
            Sign in now
          </Link>
        </div>
      </div>
    );
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      {error && (
        <div className="bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 rounded-xl text-base font-medium">
          {error}
        </div>
      )}

      <div>
        <label htmlFor="newPassword" className="block text-base font-semibold text-blue-900 mb-2">
          New Password
        </label>
        <input
          id="newPassword"
          name="newPassword"
          type="password"
          autoComplete="new-password"
          required
          className="w-full"
          placeholder="Enter new password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
      </div>

      <div>
        <label htmlFor="confirmPassword" className="block text-base font-semibold text-blue-900 mb-2">
          Confirm Password
        </label>
        <input
          id="confirmPassword"
          name="confirmPassword"
          type="password"
          autoComplete="new-password"
          required
          className="w-full"
          placeholder="Confirm new password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
        />
      </div>

      <div>
        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? 'Resetting...' : 'Reset Password'}
        </button>
      </div>

      <div className="text-center">
        <Link href="/login" className="text-sm text-blue-600 hover:text-blue-800 font-medium">
          Back to Sign in
        </Link>
      </div>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200 py-8 px-4">
      <div className="max-w-md w-full space-y-6 bg-white rounded-2xl shadow-xl border-2 border-blue-200 px-8 py-10">
        <div>
          <h2 className="text-center text-3xl font-extrabold text-blue-900">
            Reset Password
          </h2>
          <p className="mt-2 text-center text-base text-blue-700 font-medium">
            Luboss95 Village Banking
          </p>
        </div>

        <Suspense fallback={<div className="text-blue-700 text-center">Loading...</div>}>
          <ResetPasswordForm />
        </Suspense>
      </div>
    </div>
  );
}
