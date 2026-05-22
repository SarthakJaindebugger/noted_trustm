/**
 * Auth store for the current user session.
 */

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { authService } from '../services/auth_service.js';

export const useAuthStore = defineStore('auth', () => {
    const user = ref(authService.getUser());
    const isAuthenticated = ref(authService.isAuthenticated());

    async function login(username, password) {
        const success = await authService.login(username, password);
        if (success) {
            user.value = authService.getUser();
            isAuthenticated.value = true;
        }
        return success;
    }

    function logout() {
        authService.logout();
        user.value = null;
        isAuthenticated.value = false;
    }

    function checkAuth() {
        isAuthenticated.value = authService.isAuthenticated();
        user.value = authService.getUser();
    }

    const userName = computed(() => user.value?.name || 'User');

    return { user, isAuthenticated, userName, login, logout, checkAuth };
});
