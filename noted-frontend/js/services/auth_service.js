import { apiClient } from './api_client.js';

class AuthService {
    constructor() {
        this.token = sessionStorage.getItem('auth_token');
        this.user = JSON.parse(sessionStorage.getItem('user') || 'null');
    }

    async login(username, password) {
        try {
            const data = await apiClient.post('/auth/login', { username, password }, {
                skipAuth: true,
            });
            this.token = data.access_token;
            this.user = data.user;

            sessionStorage.setItem('auth_token', this.token);
            sessionStorage.setItem('user', JSON.stringify(this.user));

            return this.user;
        } catch (error) {
            console.error('Login error:', error);
            return false;
        }
    }

    logout() {
        this.token = null;
        this.user = null;
        sessionStorage.removeItem('auth_token');
        sessionStorage.removeItem('user');
        localStorage.removeItem('isAdmin');
    }

    isAuthenticated() {
        return !!this.token;
    }

    getUser() {
        return this.user;
    }

    isAdmin() {
        return this.user?.role === 'admin';
    }

    getToken() {
        return this.token;
    }

    getAuthHeaders() {
        return {
            'Authorization': `Bearer ${this.token}`,
            'Content-Type': 'application/json',
        };
    }
}

export const authService = new AuthService();
