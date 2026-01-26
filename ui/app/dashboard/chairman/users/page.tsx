'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';

interface User {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  role: string;
  approved?: boolean;
  member_id?: string;
  member_status?: string; // active, inactive
  member_activated_at?: string;
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
type FilterStatus = 'inactive' | 'active' | 'all';

export default function UserManagementPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [members, setMembers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');
  
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
    loadMembers();
    loadCycles();
  }, []);

  useEffect(() => {
    if (selectedCycle && showCreditRatingModal) {
      loadTiersForCycle(selectedCycle);
    }
  }, [selectedCycle, showCreditRatingModal]);

  useEffect(() => {
    loadUsers();
    loadMembers();
  }, [filterStatus]);

  const loadUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get<User[]>('/api/chairman/users');
      if (response.data && Array.isArray(response.data)) {
        setUsers(response.data);
      } else {
        setError(response.error || 'Failed to load users');
        setUsers([]);
      }
    } catch (err: any) {
      console.error('Error loading users:', err);
      setError(err?.response?.data?.detail || err?.message || 'Failed to load users');
      setUsers([]);
    } finally {
      setLoading(false);
    }
  };

  const loadMembers = async () => {
    try {
      const endpoint = filterStatus === 'all' 
        ? '/api/chairman/members'
        : filterStatus === 'inactive'
        ? '/api/chairman/members?status=inactive'
        : '/api/chairman/members?status=active';
      const response = await api.get<any[]>(endpoint);
      if (response.data && Array.isArray(response.data)) {
        setMembers(response.data);
        // Merge member data with users
        const members = Array.isArray(response.data) ? response.data : [];
        const memberMap = new Map(members.map((m: any) => [m.user_id, m]));
        setUsers(prevUsers => 
          prevUsers.map(user => {
            const member = memberMap.get(user.id);
            return {
              ...user,
              member_id: member?.id,
              member_status: member?.status,
              member_activated_at: member?.activated_at
            };
          })
        );
      } else {
        console.error('Error loading members: response.data is not an array', response);
        setMembers([]);
      }
    } catch (err) {
      console.error('Error loading members:', err);
      setMembers([]);
    }
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
      await loadMembers();
    } else {
      setError(response.error || 'Failed to update user role');
      showMessage('error', response.error || 'Failed to update user role');
    }
    setUpdating(null);
  };


  const handleToggleMemberStatus = async (memberId: string) => {
    setToggling(memberId);
    setError(null);
    const response = await api.post(`/api/chairman/members/${memberId}/toggle-status`);
    if (!response.error) {
      const status = (response.data as { status?: string })?.status;
      const statusText = status === 'active' ? 'activated' : 'deactivated';
      showMessage('success', `Member ${statusText} successfully`);
      await loadUsers();
      await loadMembers();
    } else {
      setError(response.error || 'Failed to toggle member status');
      showMessage('error', response.error || 'Failed to toggle member status');
    }
    setToggling(null);
  };

  const loadCycles = async () => {
    try {
      const response = await api.get<Cycle[]>('/api/chairman/cycles');
      if (response.data && Array.isArray(response.data)) {
        const activeCycles = response.data.filter(c => c.status === 'active');
        setCycles(activeCycles);
        if (activeCycles.length > 0) {
          setSelectedCycle(activeCycles[0].id);
          // Load credit ratings for all members when cycles are loaded
          loadCreditRatingsForUsers(activeCycles[0].id);
        }
      } else {
        setCycles([]);
      }
    } catch (err: any) {
      // 403 is expected if user doesn't have permission (e.g., Admin accessing cycles)
      if (err?.response?.status === 403) {
        console.log('User does not have permission to access cycles');
      } else {
        console.error('Error loading cycles:', err);
      }
      setCycles([]);
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
      const members = Array.isArray(membersResponse.data) ? membersResponse.data : [];
      for (const member of members) {
        try {
          const ratingResponse = await api.get(`/api/chairman/members/${member.id}/credit-rating/${cycleId}`);
          const ratingData = ratingResponse.data as { tier_name?: string; tier_order?: number } | undefined;
          if (ratingData && ratingData.tier_name) {
            ratings[member.user_id] = {
              tier_name: ratingData.tier_name,
              tier_order: ratingData.tier_order || 0
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
        const tiers = Array.isArray(response.data) ? response.data : [];
        if (tiers.length > 0) {
          setSelectedTier(tiers[0].id);
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
        const members = Array.isArray(membersResponse.data) ? membersResponse.data : [];
        const member = members.find((m: any) => m.user_id === userId);
        if (member && selectedCycle) {
          // Load existing credit rating if any
          const ratingResponse = await api.get(`/api/chairman/members/${member.id}/credit-rating/${selectedCycle}`);
          const ratingData = ratingResponse.data as { tier_id?: string; notes?: string } | undefined;
          if (ratingData) {
            setSelectedTier(ratingData.tier_id || '');
            setRatingNotes(ratingData.notes || '');
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
        const members = Array.isArray(membersResponse.data) ? membersResponse.data : [];
        const member = members.find((m: any) => m.user_id === showCreditRatingModal);
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

  // Filter users based on filterStatus
  const filteredUsers = users.filter(user => {
    if (filterStatus === 'all') return true;
    if (filterStatus === 'inactive') {
      // Show users with inactive member status or no member profile (defaults to inactive)
      return !user.member_status || user.member_status === 'inactive';
    }
    if (filterStatus === 'active') {
      // Show users with active member status
      return user.member_status === 'active';
    }
    return true;
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/chairman" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back to Chairman
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">User Management</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
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
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 md:mb-6 gap-4">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900">
              Manage User Roles & Members
            </h2>
            
            {/* Filter Toggle */}
            <div className="flex gap-2 bg-blue-100 p-1 rounded-lg border-2 border-blue-300">
              <button
                onClick={() => setFilterStatus('inactive')}
                className={`px-3 md:px-4 py-2 rounded-md font-semibold text-xs md:text-sm transition-all ${
                  filterStatus === 'inactive'
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'text-blue-700 hover:bg-blue-200'
                }`}
              >
                Inactive
              </button>
              <button
                onClick={() => setFilterStatus('active')}
                className={`px-3 md:px-4 py-2 rounded-md font-semibold text-xs md:text-sm transition-all ${
                  filterStatus === 'active'
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'text-blue-700 hover:bg-blue-200'
                }`}
              >
                Active
              </button>
              <button
                onClick={() => setFilterStatus('all')}
                className={`px-3 md:px-4 py-2 rounded-md font-semibold text-xs md:text-sm transition-all ${
                  filterStatus === 'all'
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'text-blue-700 hover:bg-blue-200'
                }`}
              >
                All
              </button>
            </div>
          </div>

          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
              <p className="mt-4 text-blue-700 text-lg">Loading users...</p>
            </div>
          ) : filteredUsers.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-blue-700 text-lg">No {filterStatus === 'all' ? '' : filterStatus} users found.</p>
            </div>
          ) : (
            <>
              {/* Desktop Table View */}
              <div className="hidden md:block overflow-x-auto">
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
                        Role
                      </th>
                      <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                        Member Status
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
                    {filteredUsers.map((user) => (
                      <tr
                        key={user.id}
                        className="border-b border-blue-200 hover:bg-blue-50 transition-colors"
                      >
                        <td className="p-3 md:p-4 text-sm md:text-base text-blue-800">
                          {user.first_name || user.last_name
                            ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
                            : 'N/A'}
                        </td>
                        <td className="p-3 md:p-4 text-sm md:text-base text-blue-800 break-words">
                          {user.email}
                        </td>
                        <td className="p-3 md:p-4">
                          <span className="inline-block px-3 py-1 rounded-full text-xs md:text-sm font-semibold bg-blue-200 text-blue-800 capitalize">
                            {user.role}
                          </span>
                        </td>
                        <td className="p-3 md:p-4">
                          {user.member_status ? (
                            <div className="flex items-center gap-2">
                              <span
                                className={`inline-block px-3 py-1 rounded-full text-xs md:text-sm font-semibold capitalize ${
                                  user.member_status === 'active'
                                    ? 'bg-green-200 text-green-800'
                                    : 'bg-gray-200 text-gray-800'
                                }`}
                              >
                                {user.member_status === 'active' ? 'Active' : 'In-Active'}
                              </span>
                              {user.member_activated_at && user.member_status === 'active' && (
                                <span className="text-xs text-blue-600">
                                  ({new Date(user.member_activated_at).toLocaleDateString()})
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-xs text-blue-600">No member profile</span>
                          )}
                        </td>
                        <td className="p-3 md:p-4">
                          <div className="flex flex-col gap-2">
                            <select
                              value={user.role}
                              onChange={(e) => handleRoleUpdate(user.id, e.target.value)}
                              disabled={updating === user.id}
                              className="px-3 py-2 border-2 border-blue-300 rounded-xl bg-white text-blue-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              {ROLES.map((role) => (
                                <option key={role} value={role} className="capitalize">
                                  {role}
                                </option>
                              ))}
                            </select>
                            <div className="flex gap-2">
                              {user.member_id && (
                                <button
                                  onClick={() => handleToggleMemberStatus(user.member_id!)}
                                  disabled={toggling === user.member_id || updating === user.id}
                                  className={`flex-1 px-3 py-2 border-2 rounded-xl text-white disabled:opacity-50 disabled:cursor-not-allowed text-xs md:text-sm font-semibold transition-all duration-200 ${
                                    user.member_status === 'active'
                                      ? 'bg-gradient-to-br from-red-500 to-red-600 border-red-600 hover:from-red-600 hover:to-red-700'
                                      : 'bg-gradient-to-br from-green-500 to-green-600 border-green-600 hover:from-green-600 hover:to-green-700'
                                  }`}
                                >
                                  {toggling === user.member_id 
                                    ? (user.member_status === 'active' ? 'Deactivating...' : 'Activating...')
                                    : (user.member_status === 'active' ? 'Deactivate' : 'Activate')
                                  }
                                </button>
                              )}
                            </div>
                            {updating === user.id && (
                              <span className="text-blue-600 text-xs">Updating role...</span>
                            )}
                          </div>
                        </td>
                        <td className="p-3 md:p-4">
                          {user.role !== 'admin' && (
                            <div className="flex flex-col gap-2">
                              <button
                                onClick={() => openCreditRatingModal(user.id)}
                                className="px-3 py-2 bg-gradient-to-br from-purple-500 to-purple-600 border-2 border-purple-600 text-white rounded-xl hover:from-purple-600 hover:to-purple-700 text-xs md:text-sm font-semibold transition-all duration-200"
                              >
                                Assign Rating
                              </button>
                              {userCreditRatings[user.id] && (
                                <div className="text-xs text-blue-700 font-medium">
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

              {/* Mobile Card View */}
              <div className="md:hidden space-y-4">
                {filteredUsers.map((user) => (
                  <div
                    key={user.id}
                    className="bg-gradient-to-r from-blue-50 to-blue-100 border-2 border-blue-300 rounded-xl p-4 space-y-3"
                  >
                    <div>
                      <h3 className="font-bold text-base text-blue-900">
                        {user.first_name || user.last_name
                          ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
                          : 'N/A'}
                      </h3>
                      <p className="text-sm text-blue-700 break-words">{user.email}</p>
                    </div>
                    
                    <div className="flex flex-wrap gap-2">
                      <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-blue-200 text-blue-800 capitalize">
                        {user.role}
                      </span>
                      {user.member_status && (
                        <span
                          className={`inline-block px-3 py-1 rounded-full text-xs font-semibold capitalize ${
                            user.member_status === 'active'
                              ? 'bg-green-200 text-green-800'
                              : 'bg-gray-200 text-gray-800'
                          }`}
                        >
                          {user.member_status === 'active' ? 'Active' : 'In-Active'}
                        </span>
                      )}
                    </div>

                    <div className="space-y-2">
                      <select
                        value={user.role}
                        onChange={(e) => handleRoleUpdate(user.id, e.target.value)}
                        disabled={updating === user.id}
                        className="w-full px-3 py-2 border-2 border-blue-300 rounded-xl bg-white text-blue-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role} className="capitalize">
                            {role}
                          </option>
                        ))}
                      </select>
                      
                      <div className="flex flex-col gap-2">
                        {user.member_id && (
                          <button
                            onClick={() => handleToggleMemberStatus(user.member_id!)}
                            disabled={toggling === user.member_id || updating === user.id}
                            className={`w-full px-3 py-2 border-2 rounded-xl text-white disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition-all duration-200 ${
                              user.member_status === 'active'
                                ? 'bg-gradient-to-br from-red-500 to-red-600 border-red-600 hover:from-red-600 hover:to-red-700'
                                : 'bg-gradient-to-br from-green-500 to-green-600 border-green-600 hover:from-green-600 hover:to-green-700'
                            }`}
                          >
                            {toggling === user.member_id 
                              ? (user.member_status === 'active' ? 'Deactivating...' : 'Activating...')
                              : (user.member_status === 'active' ? 'Deactivate' : 'Activate')
                            }
                          </button>
                        )}
                        {user.role !== 'admin' && (
                          <button
                            onClick={() => openCreditRatingModal(user.id)}
                            className="w-full px-3 py-2 bg-gradient-to-br from-purple-500 to-purple-600 border-2 border-purple-600 text-white rounded-xl hover:from-purple-600 hover:to-purple-700 text-sm font-semibold transition-all duration-200"
                          >
                            Assign Credit Rating
                          </button>
                        )}
                      </div>
                      
                      {userCreditRatings[user.id] && (
                        <div className="text-xs text-blue-700 font-medium">
                          <span className="text-blue-600">Rating: </span>
                          <span className="font-semibold text-blue-900">{userCreditRatings[user.id].tier_name}</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
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
                      className="w-full px-3 py-2 border-2 border-blue-300 rounded-xl bg-white text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                          className="w-full px-3 py-2 border-2 border-blue-300 rounded-xl bg-white text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                          className="w-full px-3 py-2 border-2 border-blue-300 rounded-xl bg-white text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
