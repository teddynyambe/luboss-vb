'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';

interface User {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  role: string;
  approved?: boolean;
  member_id?: string; // Add member_id if user has a member profile
}

interface Cycle {
  id: string;
  year: string;
  status: string;
}

interface CreditRatingTier {
  id: string;
  tier_name: string;
  tier_order: number;
  description?: string;
  multiplier?: number;
}

interface UserCreditRating {
  tier_name: string;
  tier_order: number;
}

const ROLES = ['admin', 'treasurer', 'member', 'compliance', 'chairman'] as const;

export default function UserManagementPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);
  const [approving, setApproving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  
  // Credit rating assignment state
  const [showCreditRatingModal, setShowCreditRatingModal] = useState<string | null>(null);
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [selectedCycle, setSelectedCycle] = useState<string>('');
  const [tiers, setTiers] = useState<CreditRatingTier[]>([]);
  const [selectedTier, setSelectedTier] = useState<string>('');
  const [ratingNotes, setRatingNotes] = useState<string>('');
  const [assigningRating, setAssigningRating] = useState(false);
  const [userCreditRatings, setUserCreditRatings] = useState<Record<string, UserCreditRating>>({});

  useEffect(() => {
    loadUsers();
    loadCycles();
  }, []);

  useEffect(() => {
    if (selectedCycle && showCreditRatingModal) {
      loadTiersForCycle(selectedCycle);
    }
  }, [selectedCycle, showCreditRatingModal]);

  const loadUsers = async () => {
    setLoading(true);
    setError(null);
    const response = await api.get<User[]>('/api/chairman/users');
    if (response.data) {
      setUsers(response.data);
    } else {
      setError(response.error || 'Failed to load users');
    }
    setLoading(false);
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const handleRoleUpdate = async (userId: string, newRole: string) => {
    setUpdating(userId);
    setError(null);
    const response = await api.put(`/api/chairman/users/${userId}/role`, { role: newRole });
    if (!response.error) {
      showMessage('success', 'User role updated successfully');
      await loadUsers();
    } else {
      setError(response.error || 'Failed to update user role');
      showMessage('error', response.error || 'Failed to update user role');
    }
    setUpdating(null);
  };

  const handleApprove = async (userId: string) => {
    setApproving(userId);
    setError(null);
    const response = await api.put(`/api/chairman/users/${userId}/approve`);
    if (!response.error) {
      showMessage('success', 'User approved successfully');
      await loadUsers();
    } else {
      setError(response.error || 'Failed to approve user');
      showMessage('error', response.error || 'Failed to approve user');
    }
    setApproving(null);
  };

  const loadCycles = async () => {
    try {
      const response = await api.get<Cycle[]>('/api/chairman/cycles');
      if (response.data) {
        const activeCycles = response.data.filter(c => c.status === 'active');
        setCycles(activeCycles);
        if (activeCycles.length > 0) {
          setSelectedCycle(activeCycles[0].id);
          // Load credit ratings for all members when cycles are loaded
          loadCreditRatingsForUsers(activeCycles[0].id);
        }
      }
    } catch (err) {
      console.error('Error loading cycles:', err);
    }
  };

  const loadCreditRatingsForUsers = async (cycleId: string) => {
    try {
      // Get all members
      const membersResponse = await api.get('/api/chairman/members');
      if (!membersResponse.data) {
        return;
      }

      const ratings: Record<string, UserCreditRating> = {};
      
      // Load credit rating for each member
      for (const member of membersResponse.data) {
        try {
          const ratingResponse = await api.get(`/api/chairman/members/${member.id}/credit-rating/${cycleId}`);
          if (ratingResponse.data && ratingResponse.data.tier_name) {
            ratings[member.user_id] = {
              tier_name: ratingResponse.data.tier_name,
              tier_order: ratingResponse.data.tier_order || 0
            };
          }
        } catch (err) {
          // Member might not have a rating, continue
          console.debug(`No credit rating for member ${member.id}`);
        }
      }
      
      setUserCreditRatings(ratings);
    } catch (err) {
      console.error('Error loading credit ratings:', err);
    }
  };

  const loadTiersForCycle = async (cycleId: string) => {
    try {
      const response = await api.get<CreditRatingTier[]>(`/api/chairman/credit-rating-tiers/${cycleId}`);
      if (response.data) {
        setTiers(response.data);
        if (response.data.length > 0) {
          setSelectedTier(response.data[0].id);
        }
      }
    } catch (err) {
      console.error('Error loading tiers:', err);
      setTiers([]);
    }
  };

  const openCreditRatingModal = async (userId: string) => {
    setShowCreditRatingModal(userId);
    setSelectedTier('');
    setRatingNotes('');
    // Load member profile to get member_id
    try {
      const membersResponse = await api.get('/api/chairman/members');
      if (membersResponse.data) {
        const member = membersResponse.data.find((m: any) => m.user_id === userId);
        if (member && selectedCycle) {
          // Load existing credit rating if any
          const ratingResponse = await api.get(`/api/chairman/members/${member.id}/credit-rating/${selectedCycle}`);
          if (ratingResponse.data) {
            setSelectedTier(ratingResponse.data.tier_id);
            setRatingNotes(ratingResponse.data.notes || '');
          }
        }
      }
    } catch (err) {
      console.error('Error loading member profile:', err);
    }
  };

  const handleAssignCreditRating = async () => {
    if (!showCreditRatingModal || !selectedCycle || !selectedTier) {
      showMessage('error', 'Please select a cycle and credit rating tier');
      return;
    }

    setAssigningRating(true);
    try {
      // Try to get member profile ID, but if not found, use user_id directly
      // The backend will create a member profile automatically if needed
      let memberId = showCreditRatingModal;
      
      const membersResponse = await api.get('/api/chairman/members');
      if (membersResponse.data) {
        const member = membersResponse.data.find((m: any) => m.user_id === showCreditRatingModal);
        if (member) {
          memberId = member.id; // Use member_id if found
        }
        // If not found, use user_id - backend will create member profile
      }

      const formData = new FormData();
      formData.append('tier_id', selectedTier);
      formData.append('cycle_id', selectedCycle);
      if (ratingNotes) {
        formData.append('notes', ratingNotes);
      }

      const response = await api.postFormData(`/api/chairman/members/${memberId}/credit-rating`, formData);
      if (!response.error) {
        showMessage('success', 'Credit rating assigned successfully');
        setShowCreditRatingModal(null);
        setSelectedTier('');
        setRatingNotes('');
        // Reload credit ratings to update the display
        if (selectedCycle) {
          loadCreditRatingsForUsers(selectedCycle);
        }
      } else {
        const errorMsg = typeof response.error === 'string' ? response.error : 'Failed to assign credit rating';
        showMessage('error', errorMsg);
      }
    } catch (err: any) {
      const errorMsg = err?.message || 'Failed to assign credit rating';
      showMessage('error', typeof errorMsg === 'string' ? errorMsg : 'Failed to assign credit rating');
    } finally {
      setAssigningRating(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/chairman" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back to Chairman
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">User Management</h1>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
        {/* Success/Error Message */}
        {message && (
          <div className={`mb-4 md:mb-6 p-4 rounded-xl border-2 font-medium text-base md:text-lg ${
            message.type === 'success'
              ? 'bg-green-100 border-green-400 text-green-800'
              : 'bg-red-100 border-red-400 text-red-800'
          }`}>
            {message.type === 'success' ? '✓ ' : '✗ '}{typeof message.text === 'string' ? message.text : JSON.stringify(message.text)}
          </div>
        )}

        {error && (
          <div className="mb-4 p-4 bg-red-100 border-2 border-red-400 text-red-800 rounded-xl text-base md:text-lg font-medium">
            {error}
          </div>
        )}

        <div className="card">
          <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">
            Manage User Roles
          </h2>

          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
              <p className="mt-4 text-blue-700 text-lg">Loading users...</p>
            </div>
          ) : users.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-blue-700 text-lg">No users found.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-blue-100 border-b-2 border-blue-300">
                    <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Name
                    </th>
                    <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Email
                    </th>
                    <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Current Role
                    </th>
                    <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Status
                    </th>
                    <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Actions
                    </th>
                    <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Credit Rating
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr
                      key={user.id}
                      className="border-b border-blue-200 hover:bg-blue-50 transition-colors"
                    >
                      <td className="p-3 md:p-4 text-sm md:text-base text-blue-800">
                        {user.first_name || user.last_name
                          ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
                          : 'N/A'}
                      </td>
                      <td className="p-3 md:p-4 text-sm md:text-base text-blue-800">
                        {user.email}
                      </td>
                      <td className="p-3 md:p-4">
                        <span className="inline-block px-3 py-1 rounded-full text-xs md:text-sm font-semibold bg-blue-200 text-blue-800 capitalize">
                          {user.role}
                        </span>
                      </td>
                      <td className="p-3 md:p-4">
                        <span
                          className={`inline-block px-3 py-1 rounded-full text-xs md:text-sm font-semibold ${
                            user.approved === true
                              ? 'bg-green-200 text-green-800'
                              : 'bg-yellow-200 text-yellow-800'
                          }`}
                        >
                          {user.approved === true ? 'Approved' : 'Pending'}
                        </span>
                      </td>
                      <td className="p-3 md:p-4">
                        <div className="flex flex-col md:flex-row gap-2 md:gap-3">
                          <select
                            value={user.role}
                            onChange={(e) => handleRoleUpdate(user.id, e.target.value)}
                            disabled={updating === user.id || approving === user.id}
                            className="flex-1 md:flex-none px-3 py-2 border-2 border-blue-300 rounded-xl bg-white text-blue-900 text-sm md:text-base focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {ROLES.map((role) => (
                              <option key={role} value={role} className="capitalize">
                                {role}
                              </option>
                            ))}
                          </select>
                          {user.approved !== true && (
                            <button
                              onClick={() => handleApprove(user.id)}
                              disabled={approving === user.id || updating === user.id}
                              className="px-4 py-2 bg-gradient-to-br from-green-500 to-green-600 border-2 border-green-600 text-white rounded-xl hover:from-green-600 hover:to-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm md:text-base font-semibold transition-all duration-200"
                            >
                              {approving === user.id ? 'Approving...' : 'Approve'}
                            </button>
                          )}
                          {updating === user.id && (
                            <span className="text-blue-600 text-sm self-center">Updating role...</span>
                          )}
                        </div>
                      </td>
                      <td className="p-3 md:p-4">
                        {user.role !== 'admin' && (
                          <div className="flex flex-col gap-2">
                            <button
                              onClick={() => openCreditRatingModal(user.id)}
                              className="px-3 py-2 bg-gradient-to-br from-purple-500 to-purple-600 border-2 border-purple-600 text-white rounded-xl hover:from-purple-600 hover:to-purple-700 text-sm md:text-base font-semibold transition-all duration-200"
                            >
                              Assign Rating
                            </button>
                            {userCreditRatings[user.id] && (
                              <div className="text-xs md:text-sm text-blue-700 font-medium">
                                <span className="text-blue-600">Rating: </span>
                                <span className="font-semibold text-blue-900">{userCreditRatings[user.id].tier_name}</span>
                              </div>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Credit Rating Assignment Modal */}
        {showCreditRatingModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="p-6 md:p-8">
                <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-6">
                  Assign Credit Rating
                </h2>

                <div className="space-y-4 md:space-y-6">
                  <div>
                    <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Cycle *
                    </label>
                    <select
                      value={selectedCycle}
                      onChange={(e) => setSelectedCycle(e.target.value)}
                      className="w-full"
                      required
                    >
                      <option value="">Select a cycle</option>
                      {cycles.map((cycle) => (
                        <option key={cycle.id} value={cycle.id}>
                          {cycle.year} ({cycle.status})
                        </option>
                      ))}
                    </select>
                  </div>

                  {selectedCycle && tiers.length > 0 && (
                    <>
                      <div>
                        <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                          Credit Rating Tier *
                        </label>
                        <select
                          value={selectedTier}
                          onChange={(e) => setSelectedTier(e.target.value)}
                          className="w-full"
                          required
                        >
                          <option value="">Select a tier</option>
                          {tiers.map((tier) => (
                            <option key={tier.id} value={tier.id}>
                              {tier.tier_name} {tier.multiplier ? `(${tier.multiplier}x multiplier)` : ''}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                          Notes (Optional)
                        </label>
                        <textarea
                          value={ratingNotes}
                          onChange={(e) => setRatingNotes(e.target.value)}
                          className="w-full"
                          rows={3}
                          placeholder="Add any notes about this credit rating assignment..."
                        />
                      </div>
                    </>
                  )}

                  {selectedCycle && tiers.length === 0 && (
                    <div className="bg-yellow-50 border-2 border-yellow-300 text-yellow-800 p-4 rounded-xl">
                      No credit rating tiers available for this cycle. Please configure credit rating scheme for this cycle first.
                    </div>
                  )}

                  <div className="flex justify-end gap-3 pt-4 border-t-2 border-blue-200">
                    <button
                      onClick={() => {
                        setShowCreditRatingModal(null);
                        setSelectedTier('');
                        setRatingNotes('');
                      }}
                      className="btn-secondary"
                      disabled={assigningRating}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleAssignCreditRating}
                      disabled={assigningRating || !selectedCycle || !selectedTier}
                      className="btn-primary disabled:opacity-50"
                    >
                      {assigningRating ? 'Assigning...' : 'Assign Rating'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
