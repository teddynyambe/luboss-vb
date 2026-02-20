'use client';

import { useState } from 'react';
import Link from 'next/link';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
    } catch {
      // Ignore network errors — always show generic success
    }
    setSubmitted(true);
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200 py-8 px-4">
      <div className="max-w-md w-full space-y-6 bg-white rounded-2xl shadow-xl border-2 border-blue-200 px-8 py-10">
        <div>
          <h2 className="text-center text-3xl font-extrabold text-blue-900">
            Forgot Password
          </h2>
          <p className="mt-2 text-center text-base text-blue-700 font-medium">
            Luboss95 Village Banking
          </p>
        </div>

        {submitted ? (
          <div className="space-y-6">
            <div className="bg-green-50 border-2 border-green-400 text-green-800 px-4 py-4 rounded-xl text-base font-medium">
              If that email is registered, a password reset link has been sent. Please check your inbox.
            </div>
            <div className="text-center">
              <Link href="/login" className="text-blue-600 hover:text-blue-800 font-semibold text-base">
                Back to Sign in
              </Link>
            </div>
          </div>
        ) : (
          <form className="space-y-5" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="email" className="block text-base font-semibold text-blue-900 mb-2">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                className="w-full"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div>
              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? 'Sending...' : 'Send Reset Link'}
              </button>
            </div>

            <div className="text-center">
              <Link href="/login" className="text-sm text-blue-600 hover:text-blue-800 font-medium">
                Back to Sign in
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
