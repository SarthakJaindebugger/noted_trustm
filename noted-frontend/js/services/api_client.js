/**
 * Centralized API client — wraps fetch with auth headers, error handling, base URL.
 * All service files should use this instead of raw fetch().
 */

import { config } from '../config.js';

class ApiClient {
    get baseURL() {
        return config.getApiBaseUrl();
    }

    getAuthHeaders() {
        const token = sessionStorage.getItem('auth_token');
        if (!token) {
            return {};
        }

        return {
            Authorization: `Bearer ${token}`,
        };
    }

    clearStoredAuth() {
        sessionStorage.removeItem('auth_token');
        sessionStorage.removeItem('user');
        localStorage.removeItem('isAdmin');
    }

    /**
     * Make an authenticated API request.
     * @param {string} path - API path (e.g., '/sessions')
     * @param {RequestInit} options - Fetch options
     * @returns {Promise<Response>}
     */
    async request(path, options = {}) {
        const { skipAuth = false, ...fetchOptions } = options;
        const url = `${this.baseURL}${path}`;

        const headers = {
            'Content-Type': 'application/json',
            ...(skipAuth ? {} : this.getAuthHeaders()),
            ...fetchOptions.headers,
        };

        // Don't set Content-Type for FormData (browser sets it with boundary)
        if (fetchOptions.body instanceof FormData) {
            delete headers['Content-Type'];
        }

        const response = await fetch(url, {
            ...fetchOptions,
            headers,
        });

        // Clear stale auth on 401 and let callers handle navigation.
        if (response.status === 401) {
            this.clearStoredAuth();
            throw new ApiError('Authentication expired', 401);
        }

        return response;
    }

    /**
     * GET request that returns parsed JSON.
     */
    async get(path, options = {}) {
        const response = await this.request(path, options);
        if (!response.ok) {
            throw new ApiError(`GET ${path} failed: ${response.status}`, response.status);
        }
        return response.json();
    }

    /**
     * POST request with JSON body, returns parsed JSON.
     */
    async post(path, body = null, options = {}) {
        const requestOptions = {
            ...options,
            method: 'POST',
        };
        if (body !== null) {
            requestOptions.body = body instanceof FormData ? body : JSON.stringify(body);
        }
        const response = await this.request(path, requestOptions);
        if (!response.ok) {
            const detail = await this._extractError(response);
            throw new ApiError(detail, response.status);
        }
        return response.json();
    }

    /**
     * PUT request with JSON body, returns parsed JSON.
     */
    async put(path, body = null, options = {}) {
        const requestOptions = {
            ...options,
            method: 'PUT',
        };
        if (body !== null) {
            requestOptions.body = body instanceof FormData ? body : JSON.stringify(body);
        }
        const response = await this.request(path, requestOptions);
        if (!response.ok) {
            const detail = await this._extractError(response);
            throw new ApiError(detail, response.status);
        }
        return response.json();
    }

    /**
     * DELETE request, returns true on success.
     */
    async delete(path, body = null, options = {}) {
        const requestOptions = {
            ...options,
            method: 'DELETE',
        };
        if (body !== null) {
            requestOptions.body = JSON.stringify(body);
        }
        const response = await this.request(path, requestOptions);
        if (!response.ok) {
            throw new ApiError(`DELETE ${path} failed: ${response.status}`, response.status);
        }
        // Some endpoints return JSON, some don't
        const text = await response.text();
        try {
            return JSON.parse(text);
        } catch {
            return response.ok;
        }
    }

    async _extractError(response) {
        try {
            const data = await response.json();
            return data.detail || `HTTP ${response.status}`;
        } catch {
            return `HTTP ${response.status}`;
        }
    }
}

export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
    }
}

export const apiClient = new ApiClient();
