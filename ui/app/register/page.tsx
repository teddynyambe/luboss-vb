'use client';

import { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

interface RegisterData {
  email: string;
  password: string;
  confirmPassword: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  nrc_number: string;
  physical_address: string;
  bank_account: string;
  bank_name: string;
  bank_branch: string;
  first_name_next_of_kin: string;
  last_name_next_of_kin: string;
  phone_number_next_of_kin: string;
}

export default function RegisterPage() {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState<RegisterData>({
    email: '',
    password: '',
    confirmPassword: '',
    first_name: '',
    last_name: '',
    phone_number: '',
    nrc_number: '',
    physical_address: '',
    bank_account: '',
    bank_name: '',
    bank_branch: '',
    first_name_next_of_kin: '',
    last_name_next_of_kin: '',
    phone_number_next_of_kin: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const router = useRouter();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const validateStep1 = () => {
    if (!formData.email || !formData.password || !formData.confirmPassword) {
      setError('All fields are required');
      return false;
    }
    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match');
      return false;
    }
    if (formData.password.length < 6) {
      setError('Password must be at least 6 characters');
      return false;
    }
    return true;
  };

  const handleNext = () => {
    if (step === 1 && validateStep1()) {
      setError('');
      setStep(2);
    } else if (step === 2) {
      // Step 2 has no required fields, so we can proceed directly
      setError('');
      setStep(3);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const { confirmPassword, ...registerData } = formData;
    console.log('Attempting registration with data:', { ...registerData, password: '***' });
    const result = await register(registerData);
    console.log('Registration result:', result);
    
    if (result.success) {
      router.push('/pending');
    } else {
      const errorMsg = result.error || 'Registration failed. Please try again.';
      console.error('Registration error details:', {
        error: result.error,
        fullResult: result
      });
      setError(errorMsg);
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200 py-8 px-4">
      <div className="max-w-md w-full space-y-6 md:space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl md:text-4xl font-extrabold text-blue-900">
            Register for Village Banking
          </h2>
          <p className="mt-2 text-center text-base md:text-lg text-blue-700 font-medium">
            Step {step} of 3
          </p>
        </div>

        {error && (
          <div className="bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
            {error}
          </div>
        )}

        <form onSubmit={step === 3 ? handleSubmit : (e) => { e.preventDefault(); handleNext(); }}>
          {step === 1 && (
            <div className="space-y-4 md:space-y-6">
              <div>
                <label htmlFor="email" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Email *
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  required
                  className="w-full"
                  placeholder="Enter your email"
                  value={formData.email}
                  onChange={handleChange}
                />
              </div>
              <div>
                <label htmlFor="password" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Password *
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  className="w-full"
                  placeholder="Create a password"
                  value={formData.password}
                  onChange={handleChange}
                />
              </div>
              <div>
                <label htmlFor="confirmPassword" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Confirm Password *
                </label>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  required
                  className="w-full"
                  placeholder="Confirm your password"
                  value={formData.confirmPassword}
                  onChange={handleChange}
                />
              </div>
              <button
                type="submit"
                className="btn-primary w-full"
              >
                Next
              </button>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4 md:space-y-6">
              <div>
                <label htmlFor="first_name" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  First Name
                </label>
                <input
                  id="first_name"
                  name="first_name"
                  type="text"
                  className="w-full"
                  placeholder="Enter your first name"
                  value={formData.first_name}
                  onChange={handleChange}
                />
              </div>
              <div>
                <label htmlFor="last_name" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Last Name
                </label>
                <input
                  id="last_name"
                  name="last_name"
                  type="text"
                  className="w-full"
                  placeholder="Enter your last name"
                  value={formData.last_name}
                  onChange={handleChange}
                />
              </div>
              <div>
                <label htmlFor="phone_number" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Phone Number
                </label>
                <input
                  id="phone_number"
                  name="phone_number"
                  type="tel"
                  className="w-full"
                  placeholder="Enter your phone number"
                  value={formData.phone_number}
                  onChange={handleChange}
                />
              </div>
              <div>
                <label htmlFor="nrc_number" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  NRC Number
                </label>
                <input
                  id="nrc_number"
                  name="nrc_number"
                  type="text"
                  className="w-full"
                  placeholder="Enter your NRC number"
                  value={formData.nrc_number}
                  onChange={handleChange}
                />
              </div>
              <div>
                <label htmlFor="physical_address" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Physical Address
                </label>
                <textarea
                  id="physical_address"
                  name="physical_address"
                  className="w-full min-h-[100px]"
                  placeholder="Enter your physical address"
                  value={formData.physical_address}
                  onChange={handleChange}
                />
              </div>
              <div className="flex flex-col sm:flex-row gap-3 md:gap-4">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="btn-secondary flex-1"
                >
                  Back
                </button>
                <button
                  type="submit"
                  className="btn-primary flex-1"
                >
                  Next
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4 md:space-y-6">
              <div className="border-b-2 border-blue-200 pb-4">
                <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Bank Details</h3>
                <div className="space-y-4 md:space-y-6">
                  <div>
                    <label htmlFor="bank_account" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Bank Account
                    </label>
                    <input
                      id="bank_account"
                      name="bank_account"
                      type="text"
                      className="w-full"
                      placeholder="Enter your bank account number"
                      value={formData.bank_account}
                      onChange={handleChange}
                    />
                  </div>
                  <div>
                    <label htmlFor="bank_name" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Bank Name
                    </label>
                    <input
                      id="bank_name"
                      name="bank_name"
                      type="text"
                      className="w-full"
                      placeholder="Enter your bank name"
                      value={formData.bank_name}
                      onChange={handleChange}
                    />
                  </div>
                  <div>
                    <label htmlFor="bank_branch" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Bank Branch
                    </label>
                    <input
                      id="bank_branch"
                      name="bank_branch"
                      type="text"
                      className="w-full"
                      placeholder="Enter your bank branch"
                      value={formData.bank_branch}
                      onChange={handleChange}
                    />
                  </div>
                </div>
              </div>

              <div className="border-b-2 border-blue-200 pb-4">
                <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Next of Kin Information</h3>
                <div className="space-y-4 md:space-y-6">
                  <div>
                    <label htmlFor="first_name_next_of_kin" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Next of Kin First Name
                    </label>
                    <input
                      id="first_name_next_of_kin"
                      name="first_name_next_of_kin"
                      type="text"
                      className="w-full"
                      placeholder="Enter next of kin first name"
                      value={formData.first_name_next_of_kin}
                      onChange={handleChange}
                    />
                  </div>
                  <div>
                    <label htmlFor="last_name_next_of_kin" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Next of Kin Last Name
                    </label>
                    <input
                      id="last_name_next_of_kin"
                      name="last_name_next_of_kin"
                      type="text"
                      className="w-full"
                      placeholder="Enter next of kin last name"
                      value={formData.last_name_next_of_kin}
                      onChange={handleChange}
                    />
                  </div>
                  <div>
                    <label htmlFor="phone_number_next_of_kin" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Next of Kin Phone Number
                    </label>
                    <input
                      id="phone_number_next_of_kin"
                      name="phone_number_next_of_kin"
                      type="tel"
                      className="w-full"
                      placeholder="Enter next of kin phone number"
                      value={formData.phone_number_next_of_kin}
                      onChange={handleChange}
                    />
                  </div>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row gap-3 md:gap-4">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="btn-secondary flex-1"
                >
                  Back
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="btn-primary flex-1 disabled:opacity-50"
                >
                  {loading ? 'Registering...' : 'Register'}
                </button>
              </div>
            </div>
          )}
        </form>

        <div className="text-center">
          <Link
            href="/login"
            className="text-base md:text-lg text-blue-600 hover:text-blue-800 font-semibold"
          >
            Already have an account? Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
