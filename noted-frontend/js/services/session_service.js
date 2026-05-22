import { authService } from './auth_service.js';
import { apiClient } from './api_client.js';

class SessionService {
    get baseURL() {
        return apiClient.baseURL;
    }

    formatSessionResponse(session) {
        if (!session) {
            return null;
        }

        const createdAt = session.created_at ? new Date(session.created_at) : null;
        const formattedDate = createdAt
            ? createdAt.toLocaleDateString().replace(/\//g, '-')
            : '';
        const statusValue = typeof session.status === 'string'
            ? session.status
            : session.status?.value;

        return {
            id: session.db_id,
            reference: session.session_name,
            date: formattedDate,
            topic: session.service_type || 'General',
            status: statusValue || 'active',
            processing_progress: Number(session.processing_progress ?? 0),
            processing_stage: session.processing_stage || null,
            processing_message: session.processing_message || null,
            created_at: session.created_at,
            updated_at: session.updated_at,
            client_name: session.client_name,
            advisor_name: session.advisor_name,
            websocket_session_id: session.websocket_session_id || null
        };
    }

    async getUserSessions() {
        try {
            const sessions = await apiClient.get('/sessions?active_only=false');
            return sessions.map(session => this.formatSessionResponse(session));
        } catch (error) {
            console.error('Failed to fetch sessions:', error);
            return [];
        }
    }

    async getSessionTranscript(sessionId) {
        try {
            return await apiClient.get(`/sessions/${sessionId}/transcript`);
        } catch (error) {
            console.error('Failed to fetch session transcript:', error);
            return [];
        }
    }

    async getNextSessionName() {
        try {
            const data = await apiClient.get('/sessions/next-name');
            return data.next_session_name;
        } catch (error) {
            console.error('Failed to get next session name:', error);
            return 'SES-00001';
        }
    }

    async createSession(sessionName = null) {
        try {
            let path = '/sessions';
            if (sessionName) {
                const params = new URLSearchParams();
                params.append('session_name', sessionName);
                path += `?${params.toString()}`;
            }

            const sessionData = await apiClient.post(path, null, {
                credentials: 'include',
            });

            if (sessionData.websocket_session_id) {
                this.setWebSocketSessionId(sessionData.websocket_session_id);
            }

            return sessionData;
        } catch (error) {
            console.error('Failed to create session:', error);
            throw error;
        }
    }

    // Get session ID from cookie
    getSessionId() {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'session_id') {
                return value;
            }
        }
        return null;
    }

    // Get WebSocket session ID from cookie or localStorage
    getWebSocketSessionId() {
        // First try to get from localStorage (for cross-origin scenarios)
        const storedId = localStorage.getItem('websocket_session_id');
        if (storedId) {
            return storedId;
        }
        
        // Fallback to cookies
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'websocket_session_id') {
                return value;
            }
        }
        return null;
    }

    // Store WebSocket session ID for later use
    setWebSocketSessionId(websocketSessionId) {
        localStorage.setItem('websocket_session_id', websocketSessionId);
    }

    async updateSession(sessionId, sessionData) {
        try {
            return await apiClient.put(`/sessions/${sessionId}`, sessionData);
        } catch (error) {
            console.error('Failed to update session:', error);
            throw error;
        }
    }

    async renameSession(sessionIdentifier, newName) {
        try {
            const session = await apiClient.put(`/sessions/${sessionIdentifier}/rename`, {
                session_name: newName,
            });
            return this.formatSessionResponse(session);
        } catch (error) {
            console.error('Failed to rename session:', error);
            throw error;
        }
    }

    async uploadAudioFile(sessionName, file, onUploadProgress) {
        return new Promise((resolve, reject) => {
            const url = `${this.baseURL}/sessions/${sessionName}/upload-audio`;
            const xhr = new XMLHttpRequest();
            const formData = new FormData();
            formData.append('file', file);

            xhr.open('POST', url, true);

            // Add authorization headers
            const authHeaders = authService.getAuthHeaders();
            for (const header in authHeaders) {
                if (header.toLowerCase() !== 'content-type') { // content-type is set by browser for FormData
                    xhr.setRequestHeader(header, authHeaders[header]);
                }
            }

            // Track upload progress
            if (onUploadProgress && typeof onUploadProgress === 'function') {
                xhr.upload.onprogress = onUploadProgress;
            }

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(JSON.parse(xhr.responseText));
                } else {
                    reject(new Error(`Upload failed with status: ${xhr.status} ${xhr.statusText}`));
                }
            };

            xhr.onerror = () => reject(new Error('Upload failed due to a network error.'));

            xhr.send(formData);
        });
    }

    async deleteSession(sessionId) {
        try {
            await apiClient.delete(`/sessions/${sessionId}`);
            return true;
        } catch (error) {
            console.error('Failed to delete session:', error);
            return false;
        }
    }

    async bulkDeleteSessions(sessionIds) {
        try {
            return await apiClient.delete('/sessions/bulk', sessionIds);
        } catch (error) {
            console.error('Failed to bulk delete sessions:', error);
            throw error;
        }
    }

    async getSession(sessionId) {
        try {
            return await apiClient.get(`/sessions/${sessionId}`);
        } catch (error) {
            console.error('Failed to fetch session:', error);
            throw error;
        }
    }

    async getSessionSummary(sessionId) {
        try {
            return await apiClient.get(`/sessions/${sessionId}/summary`);
        } catch (error) {
            console.error('Failed to fetch session summary:', error);
            return {
                session_id: sessionId,
                overview: "Unable to load session summary.",
                action_items: [],
                topics_discussed: [],
                related_services: []
            };
        }
    }

    async updateSessionSummary(sessionId, summaryData) {
        try {
            return await apiClient.put(`/sessions/${sessionId}/summary`, summaryData);
        } catch (error) {
            console.error('Failed to update session summary:', error);
            throw error;
        }
    }

    async getSessionNotes(sessionIdentifier) {
        try {
            const data = await apiClient.get(`/sessions/${sessionIdentifier}/notes`);
            return data.notes || '';
        } catch (error) {
            console.error('Failed to fetch session notes:', error);
            return '';
        }
    }

    async updateSessionNotes(sessionIdentifier, notes) {
        try {
            return await apiClient.put(`/sessions/${sessionIdentifier}/notes`, { notes });
        } catch (error) {
            console.error('Failed to update session notes:', error);
            throw error;
        }
    }

    async updateSessionOverview(sessionIdentifier, overview) {
        try {
            return await apiClient.put(`/sessions/${sessionIdentifier}/overview`, { overview });
        } catch (error) {
            console.error('Failed to update session overview:', error);
            throw error;
        }
    }

    async generateTopicSummary(sessionIdentifier, topic) {
        try {
            const query = encodeURIComponent(topic);
            return await apiClient.get(`/topic-summary/${sessionIdentifier}?topic=${query}`);
        } catch (error) {
            console.error('Failed to generate topic summary:', error);
            throw error;
        }
    }

    async updateSessionTranscript(sessionIdentifier, transcriptEntries) {
        try {
            return await apiClient.put(`/sessions/${sessionIdentifier}/transcript`, {
                transcript_entries: transcriptEntries,
            });
        } catch (error) {
            console.error('Failed to update session transcript:', error);
            throw error;
        }
    }

    async translateSessionSummary(sessionIdentifier, language) {
        try {
            return await apiClient.post(`/sessions/${sessionIdentifier}/translate-summary`, {
                language,
            });
        } catch (error) {
            console.error('Failed to translate session summary:', error);
            throw error;
        }
    }

    async endSession(sessionIdentifier) {
        try {
            return await apiClient.put(`/sessions/${sessionIdentifier}/end`);
        } catch (error) {
            console.error('Failed to end session:', error);
            throw error;
        }
    }
}

export const sessionService = new SessionService();
