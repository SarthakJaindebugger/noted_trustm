/**
 * CRM Service — API calls for encounter form CRUD.
 */

import { apiClient } from './api_client.js';

class CRMService {
    /**
     * Generate a pre-filled CRM form from session summary.
     */
    async generateForm(sessionId) {
        return apiClient.post(`/sessions/${sessionId}/crm-form`);
    }

    /**
     * Get a saved CRM form.
     */
    async getForm(sessionId) {
        return apiClient.get(`/sessions/${sessionId}/crm-form`);
    }

    /**
     * Save/update a CRM form.
     */
    async saveForm(sessionId, formData) {
        return apiClient.put(`/sessions/${sessionId}/crm-form`, formData);
    }
}

export const crmService = new CRMService();
