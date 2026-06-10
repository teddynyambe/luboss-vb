'use client';

import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import UserMenu from '@/components/UserMenu';
import { api } from '@/lib/api';

interface TodoItem {
  kind: string;
  priority: number;
  title: string;
  description: string;
  link: string;
  declaration_id?: string;
  effective_month?: string;
}

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [todos, setTodos] = useState<TodoItem[]>([]);

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
    if (!loading && user && !user.approved) {
      router.push('/pending');
    }
  }, [user, loading, router]);

  useEffect(() => {
    if (!loading && user && user.approved) {
      api
        .get<{ todos: TodoItem[]; count: number }>('/api/member/todos')
        .then((res) => {
          if (res.data) setTodos(res.data.todos || []);
        })
        .catch(() => {
          // Silent — the to-do list is best-effort and only meaningful for users
          // with a member profile. Non-members simply get an empty list back.
        });
    }
  }, [loading, user]);

  if (loading || !user) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center">
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">
                Luboss95 Village Banking v2
              </h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24 space-y-4 md:space-y-6">
        {/* To-Do List — only rendered when there are pending member actions.
            Non-member users (treasurer-only, admin-only, etc.) get an empty
            payload from the backend and never see this card. */}
        {todos.length > 0 && (
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl md:text-2xl font-bold text-blue-900">Your To-Do List</h2>
              <span className="px-3 py-1 bg-amber-500 text-white text-sm font-semibold rounded-full">
                {todos.length} pending
              </span>
            </div>
            <ul className="space-y-2">
              {todos.map((t, i) => {
                const tone = (() => {
                  switch (t.kind) {
                    case 'declare_current_month': return 'bg-blue-50 border-blue-300 hover:bg-blue-100';
                    case 'repair_rejected_declaration': return 'bg-red-50 border-red-300 hover:bg-red-100';
                    case 'submit_pop_current_month': return 'bg-indigo-50 border-indigo-300 hover:bg-indigo-100';
                    case 'repair_rejected_pop': return 'bg-red-50 border-red-300 hover:bg-red-100';
                    case 'submit_unsubmitted_pop': return 'bg-amber-50 border-amber-300 hover:bg-amber-100';
                    default: return 'bg-blue-50 border-blue-300 hover:bg-blue-100';
                  }
                })();
                return (
                  <li key={i}>
                    <Link
                      href={t.link}
                      className={`flex items-start gap-3 p-3 md:p-4 rounded-lg border-2 ${tone} transition-colors`}
                    >
                      <span className="shrink-0 inline-flex items-center justify-center w-7 h-7 rounded-full bg-white border border-current text-xs font-bold">
                        {i + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-blue-900">{t.title}</p>
                        <p className="text-xs md:text-sm text-blue-700 mt-0.5">{t.description}</p>
                      </div>
                      <span className="shrink-0 text-blue-700 self-center">→</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        <div className="card">
          <h2 className="text-2xl md:text-3xl font-bold text-blue-900 mb-6 md:mb-8">
            Welcome {user?.roles && Array.isArray(user.roles) && user.roles.length > 0 && (
              <span className="text-blue-700 font-normal">
                {user.roles.map(r => {
                  const roleStr = String(r);
                  return roleStr.charAt(0).toUpperCase() + roleStr.slice(1).toLowerCase();
                }).join(', ')}{' '}
              </span>
            )}{user ? `${user.first_name || ''} ${user.last_name || ''}`.trim() || 'User' : 'User'} to your Dashboard
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
            <Link
              href="/dashboard/member"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-400 to-blue-500 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-600"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Member Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                View statements, make declarations, apply for loans
              </p>
            </Link>

            <Link
              href="/dashboard/admin"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Admin Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                System settings, user management
              </p>
            </Link>

            <Link
              href="/dashboard/chairman"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Chairman Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                Approve members, manage cycles, upload constitution
              </p>
            </Link>

            <Link
              href="/dashboard/treasurer"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Treasurer Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                Approve deposits, manage penalties, credit ratings
              </p>
            </Link>

            <Link
              href="/dashboard/compliance"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Compliance Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                Create and manage penalty records
              </p>
            </Link>

            <Link
              href="/dashboard/chairman/payment-requests"
              className="block p-5 md:p-6 bg-gradient-to-br from-green-500 to-green-600 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-green-700"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Payment Requests
              </h3>
              <p className="text-sm md:text-base text-green-100">
                Create and manage expense & payout requests
              </p>
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
