/**
 * Session store — centralized session state.
 * Replaces scattered session data refs across components.
 */

import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useSessionStore = defineStore('session', () => {
    // Current recording session data
    const currentSession = ref(null);

    // All sessions list (cached from dashboard)
    const sessions = ref([]);

    // Loading state
    const loading = ref(false);

    function setCurrentSession(data) {
        currentSession.value = data;
    }

    function clearCurrentSession() {
        currentSession.value = null;
    }

    function setSessions(list) {
        sessions.value = list;
    }

    function updateSession(sessionId, updates) {
        const idx = sessions.value.findIndex(s => s.id === sessionId || s.reference === sessionId);
        if (idx !== -1) {
            sessions.value[idx] = { ...sessions.value[idx], ...updates };
        }
    }

    function removeSession(sessionId) {
        sessions.value = sessions.value.filter(s => s.id !== sessionId);
    }

    return {
        currentSession,
        sessions,
        loading,
        setCurrentSession,
        clearCurrentSession,
        setSessions,
        updateSession,
        removeSession,
    };
});
