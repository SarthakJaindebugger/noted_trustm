import { apiClient } from './api_client.js';

class ExperimentService {
    async generate(sessionId, { uiType, contentType }) {
        if (!sessionId) {
            throw new Error('Session ID is required to generate experiment output');
        }

        try {
            return await apiClient.post(`/sessions/${sessionId}/experiment-output`, {
                ui_type: uiType,
                content_type: contentType,
            });
        } catch (error) {
            const message = error?.message || 'Failed to generate experiment output';
            throw new Error(message);
        }
    }
}

export const experimentService = new ExperimentService();
