'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';
import { memberApi } from '@/lib/memberApi';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';

interface Declaration {
  id: string;
  cycle_id: string;
  effective_month: string;
  declared_savings_amount?: number;
  declared_social_fund?: number;
  declared_admin_fund?: number;
  declared_penalties?: number;
  declared_interest_on_loan?: number;
  declared_loan_repayment?: number;
  status: string;
}

export default function UploadDepositProofPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [declarations, setDeclarations] = useState<Declaration[]>([]);
  const [selectedDeclaration, setSelectedDeclaration] = useState<string>('');
  const [amount, setAmount] = useState<string>('');
  const [reference, setReference] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [calculatingTotal, setCalculatingTotal] = useState(false);

  useEffect(() => {
    loadDeclarations();
  }, []);

  const loadDeclarations = async () => {
    try {
      const response = await memberApi.getDeclarations();
      if (response.data) {
        // Filter for PENDING declarations (those that need proof)
        const pending = response.data.filter(d => d.status === 'pending');
        setDeclarations(pending);
      }
    } catch (err) {
      console.error('Error loading declarations:', err);
      setError('Failed to load declarations');
    }
  };

  const calculateTotal = (declaration: Declaration): number => {
    return (
      (declaration.declared_savings_amount || 0) +
      (declaration.declared_social_fund || 0) +
      (declaration.declared_admin_fund || 0) +
      (declaration.declared_penalties || 0) +
      (declaration.declared_interest_on_loan || 0) +
      (declaration.declared_loan_repayment || 0)
    );
  };

  const handleDeclarationChange = (declarationId: string) => {
    setSelectedDeclaration(declarationId);
    const declaration = declarations.find(d => d.id === declarationId);
    if (declaration) {
      const total = calculateTotal(declaration);
      setAmount(total.toFixed(2));
    } else {
      setAmount('');
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess(false);
    setLoading(true);

    if (!selectedDeclaration) {
      setError('Please select a declaration');
      setLoading(false);
      return;
    }

    if (!amount || parseFloat(amount) <= 0) {
      setError('Please enter a valid amount');
      setLoading(false);
      return;
    }

    if (!file) {
      setError('Please select a file to upload');
      setLoading(false);
      return;
    }

    // Verify amount matches declaration total
    const declaration = declarations.find(d => d.id === selectedDeclaration);
    if (declaration) {
      const expectedTotal = calculateTotal(declaration);
      const enteredAmount = parseFloat(amount);
      if (Math.abs(enteredAmount - expectedTotal) > 0.01) {
        setError(`Amount must match declaration total: K${expectedTotal.toFixed(2)}`);
        setLoading(false);
        return;
      }
    }

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('declaration_id', selectedDeclaration);
      formData.append('amount', amount);
      if (reference) {
        formData.append('reference', reference);
      }

      const response = await api.postFormData('/api/member/deposits/upload', formData);

      if (response.data) {
        setSuccess(true);
        setTimeout(() => {
          router.push('/dashboard/member');
        }, 2000);
      } else {
        setError(response.error || 'Failed to upload deposit proof');
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred while uploading the proof');
    } finally {
      setLoading(false);
    }
  };

  const selectedDecl = declarations.find(d => d.id === selectedDeclaration);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/member" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Upload Deposit Proof</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
        <div className="card">
          {success && (
            <div className="mb-4 md:mb-6 bg-green-100 border-2 border-green-400 text-green-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
              ✓ Deposit proof uploaded successfully! Declaration status updated to APPROVED. Redirecting...
            </div>
          )}

          {error && (
            <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
              {error}
            </div>
          )}

          {declarations.length === 0 ? (
            <div className="text-center py-12">
              <div className="mb-6">
                <svg className="mx-auto h-24 w-24 text-blue-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h2 className="text-2xl md:text-3xl font-bold text-blue-900 mb-4">No Pending Declarations</h2>
              <p className="text-lg md:text-xl text-blue-700 mb-6">
                You don't have any pending declarations that require deposit proof.
              </p>
              <Link
                href="/dashboard/member/declarations"
                className="btn-primary inline-block"
              >
                Create Declaration
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4 md:space-y-6">
              <div>
                <label htmlFor="declaration_id" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Select Declaration *
                </label>
                <select
                  id="declaration_id"
                  value={selectedDeclaration}
                  onChange={(e) => handleDeclarationChange(e.target.value)}
                  required
                  className="w-full"
                >
                  <option value="">-- Select a declaration --</option>
                  {declarations.map((decl) => (
                    <option key={decl.id} value={decl.id}>
                      {new Date(decl.effective_month).toLocaleDateString('en-US', { year: 'numeric', month: 'long' })} - 
                      Total: K{calculateTotal(decl).toFixed(2)}
                    </option>
                  ))}
                </select>
              </div>

              {selectedDecl && (
                <div className="bg-blue-50 border-2 border-blue-300 rounded-xl p-4 md:p-5">
                  <h3 className="text-lg font-bold text-blue-900 mb-3">Declaration Breakdown</h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">
                    {selectedDecl.declared_savings_amount !== null && selectedDecl.declared_savings_amount !== undefined && (
                      <div>
                        <p className="text-xs text-blue-600 font-medium">Savings</p>
                        <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_savings_amount.toLocaleString()}</p>
                      </div>
                    )}
                    {selectedDecl.declared_social_fund !== null && selectedDecl.declared_social_fund !== undefined && (
                      <div>
                        <p className="text-xs text-blue-600 font-medium">Social Fund</p>
                        <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_social_fund.toLocaleString()}</p>
                      </div>
                    )}
                    {selectedDecl.declared_admin_fund !== null && selectedDecl.declared_admin_fund !== undefined && (
                      <div>
                        <p className="text-xs text-blue-600 font-medium">Admin Fund</p>
                        <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_admin_fund.toLocaleString()}</p>
                      </div>
                    )}
                    {selectedDecl.declared_penalties !== null && selectedDecl.declared_penalties !== undefined && (
                      <div>
                        <p className="text-xs text-blue-600 font-medium">Penalties</p>
                        <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_penalties.toLocaleString()}</p>
                      </div>
                    )}
                    {selectedDecl.declared_interest_on_loan !== null && selectedDecl.declared_interest_on_loan !== undefined && (
                      <div>
                        <p className="text-xs text-blue-600 font-medium">Interest on Loan</p>
                        <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_interest_on_loan.toLocaleString()}</p>
                      </div>
                    )}
                    {selectedDecl.declared_loan_repayment !== null && selectedDecl.declared_loan_repayment !== undefined && (
                      <div>
                        <p className="text-xs text-blue-600 font-medium">Loan Repayment</p>
                        <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_loan_repayment.toLocaleString()}</p>
                      </div>
                    )}
                  </div>
                  <div className="mt-4 pt-4 border-t-2 border-blue-200">
                    <p className="text-sm text-blue-600 font-medium">Total Amount</p>
                    <p className="text-2xl font-bold text-blue-900">K{calculateTotal(selectedDecl).toFixed(2)}</p>
                  </div>
                </div>
              )}

              <div>
                <label htmlFor="amount" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Deposit Amount (K) *
                </label>
                <input
                  type="number"
                  id="amount"
                  step="0.01"
                  min="0"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                  className="w-full"
                  placeholder="0.00"
                />
                <p className="mt-2 text-sm md:text-base text-blue-700">
                  This should match the total from your declaration
                </p>
              </div>

              <div>
                <label htmlFor="reference" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Payment Reference (Optional)
                </label>
                <input
                  type="text"
                  id="reference"
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                  className="w-full"
                  placeholder="e.g., Transaction ID, Reference Number"
                />
              </div>

              <div>
                <label htmlFor="file" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Upload Proof of Payment *
                </label>
                <input
                  type="file"
                  id="file"
                  accept=".pdf,.jpg,.jpeg,.png,.gif"
                  onChange={handleFileChange}
                  required
                  className="w-full"
                />
                <p className="mt-2 text-sm md:text-base text-blue-700">
                  Accepted formats: PDF, JPG, JPEG, PNG, GIF
                </p>
                {file && (
                  <p className="mt-2 text-sm text-green-700 font-medium">
                    Selected: {file.name} ({(file.size / 1024).toFixed(2)} KB)
                  </p>
                )}
              </div>

              <div className="flex flex-col sm:flex-row justify-end gap-3 md:gap-4 pt-6 border-t-2 border-blue-200">
                <Link
                  href="/dashboard/member"
                  className="btn-secondary text-center"
                >
                  Cancel
                </Link>
                <button
                  type="submit"
                  disabled={loading}
                  className="btn-primary disabled:opacity-50"
                >
                  {loading ? 'Uploading...' : 'Upload Proof'}
                </button>
              </div>
            </form>
          )}
        </div>
      </main>
    </div>
  );
}
