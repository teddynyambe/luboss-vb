const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002';

export interface ApiResponse<T> {
  data?: T;
  error?: string;
  detail?: string;
}

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('token');
    }
  }

  setToken(token: string | null) {
    this.token = token;
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem('token', token);
      } else {
        localStorage.removeItem('token');
      }
    }
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      // Handle non-JSON responses
      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        return {
          error: text || `HTTP ${response.status}: ${response.statusText}`,
        };
      }

      const data = await response.json();

      if (!response.ok) {
        // Handle FastAPI validation errors (array of error objects)
        let errorMessage = 'An error occurred';
        if (Array.isArray(data.detail)) {
          // Validation errors: extract messages from each error
          errorMessage = data.detail.map((err: any) => {
            const loc = Array.isArray(err.loc) ? err.loc.slice(1).join('.') : '';
            return `${loc ? `${loc}: ` : ''}${err.msg || err.message || 'Validation error'}`;
          }).join('; ');
        } else if (typeof data.detail === 'string') {
          errorMessage = data.detail;
        } else if (data.message) {
          errorMessage = data.message;
        }
        return {
          error: errorMessage,
          detail: data.detail,
        };
      }

      return { data };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : 'Network error',
      };
    }
  }

  async get<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  async post<T>(endpoint: string, body?: any): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async put<T>(endpoint: string, body?: any): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  }

  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  /** GET file as blob (e.g. PDF, images). Returns blob URL. */
  async getFileBlob(endpoint: string): Promise<string> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: HeadersInit = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const blob = await response.blob();
      return URL.createObjectURL(blob);
    } catch (error) {
      throw new Error(error instanceof Error ? error.message : 'Failed to fetch file');
    }
  }

  /** POST with FormData (e.g. file upload). Do not set Content-Type; browser sets multipart boundary. */
  async postFormData<T>(endpoint: string, formData: FormData): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: HeadersInit = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: formData,
      });

      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        return {
          error: text || `HTTP ${response.status}: ${response.statusText}`,
        };
      }

      const data = await response.json();
      if (!response.ok) {
        // Handle FastAPI validation errors (array of error objects)
        let errorMessage = 'An error occurred';
        if (Array.isArray(data.detail)) {
          // Validation errors: extract messages from each error
          errorMessage = data.detail.map((err: any) => {
            const loc = Array.isArray(err.loc) ? err.loc.slice(1).join('.') : '';
            return `${loc ? `${loc}: ` : ''}${err.msg || err.message || 'Validation error'}`;
          }).join('; ');
        } else if (typeof data.detail === 'string') {
          errorMessage = data.detail;
        } else if (data.message) {
          errorMessage = data.message;
        }
        return {
          error: errorMessage,
          detail: data.detail,
        };
      }
      return { data };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : 'Network error',
      };
    }
  }
}

export const api = new ApiClient(API_URL);

// Auth API
export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
  phone_number?: string;
  nrc_number?: string;
}

export interface User {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  approved?: boolean;
  roles?: string[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export const authApi = {
  login: (credentials: LoginRequest) =>
    api.post<TokenResponse>('/api/auth/login', credentials),
  register: (data: RegisterRequest) =>
    api.post<User>('/api/auth/register', data),
  getMe: () => api.get<User>('/api/auth/me'),
};
