/**
 * CRM Encounter Form — auto-filled from session summary.
 */

import { ref, onMounted, computed } from 'vue';
import { crmService } from '../services/crm_service.js';

export default {
    name: 'CRMForm',
    props: {
        sessionId: { type: String, default: null },
    },
    setup(props) {
        const loading = ref(true);
        const saving = ref(false);
        const formData = ref(null);
        const error = ref(null);
        const successMessage = ref('');

        const encounterTypes = ['in-person', 'phone', 'video', 'email'];
        const outcomeOptions = ['resolved', 'follow-up needed', 'referred', 'pending', 'cancelled'];

        const isSubmitted = computed(() => formData.value?.status === 'submitted');

        const loadOrGenerateForm = async () => {
            if (!props.sessionId) return;
            loading.value = true;
            error.value = null;

            try {
                // Try loading existing form first
                formData.value = await crmService.getForm(props.sessionId);
            } catch (e) {
                if (e.status === 404) {
                    // No form yet — generate one from summary
                    try {
                        formData.value = await crmService.generateForm(props.sessionId);
                    } catch (genError) {
                        error.value = 'Failed to generate CRM form. Make sure the session has a summary.';
                    }
                } else {
                    error.value = 'Failed to load CRM form.';
                }
            } finally {
                loading.value = false;
            }
        };

        const saveForm = async (submitForm = false) => {
            if (!formData.value) return;
            saving.value = true;
            error.value = null;
            successMessage.value = '';

            try {
                const payload = { ...formData.value };
                if (submitForm) {
                    payload.status = 'submitted';
                }
                formData.value = await crmService.saveForm(props.sessionId, payload);
                successMessage.value = submitForm ? 'Form submitted successfully!' : 'Draft saved.';
                setTimeout(() => { successMessage.value = ''; }, 3000);
            } catch (e) {
                error.value = 'Failed to save form.';
            } finally {
                saving.value = false;
            }
        };

        const addActionItem = () => {
            if (!formData.value.action_items) formData.value.action_items = [];
            formData.value.action_items.push('');
        };

        const removeActionItem = (index) => {
            formData.value.action_items.splice(index, 1);
        };

        const addReferral = () => {
            if (!formData.value.referrals) formData.value.referrals = [];
            formData.value.referrals.push('');
        };

        const removeReferral = (index) => {
            formData.value.referrals.splice(index, 1);
        };

        const goBack = () => {
            window.history.back();
        };

        onMounted(() => {
            loadOrGenerateForm();
        });

        return {
            loading, saving, formData, error, successMessage,
            encounterTypes, outcomeOptions, isSubmitted,
            saveForm, addActionItem, removeActionItem,
            addReferral, removeReferral, goBack,
        };
    },
    template: `
        <div class="min-h-screen bg-gray-50">
            <header class="bg-white border-b border-gray-200 px-6 py-4">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-4">
                        <button @click="goBack" class="flex items-center space-x-2 text-gray-600 hover:text-gray-900">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
                            </svg>
                            <span>Back</span>
                        </button>
                        <h1 class="text-xl font-semibold text-gray-900">CRM Encounter Form</h1>
                    </div>
                    <div v-if="formData" class="flex items-center space-x-3">
                        <span v-if="isSubmitted" class="px-3 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full">Submitted</span>
                        <span v-else class="px-3 py-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded-full">Draft</span>
                    </div>
                </div>
            </header>

            <main class="max-w-3xl mx-auto px-6 py-8">
                <!-- Loading -->
                <div v-if="loading" class="text-center py-16 text-gray-500">Loading form...</div>

                <!-- Error -->
                <div v-else-if="error && !formData" class="text-center py-16">
                    <p class="text-red-600 mb-4">{{ error }}</p>
                    <button @click="goBack" class="px-4 py-2 bg-gray-200 rounded-md text-sm">Go Back</button>
                </div>

                <!-- Form -->
                <div v-else-if="formData" class="space-y-8">
                    <!-- Success/Error banners -->
                    <div v-if="successMessage" class="p-3 bg-green-50 border border-green-200 rounded-md text-sm text-green-800">{{ successMessage }}</div>
                    <div v-if="error" class="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-800">{{ error }}</div>

                    <!-- Encounter Details -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
                        <h2 class="text-lg font-medium text-gray-900 border-b border-gray-200 pb-2">Encounter Details</h2>

                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Encounter Type</label>
                                <select v-model="formData.encounter_type" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100">
                                    <option v-for="t in encounterTypes" :key="t" :value="t">{{ t }}</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Encounter Date</label>
                                <input type="date" :value="formData.encounter_date?.split('T')[0]" @input="formData.encounter_date = $event.target.value" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"/>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Advisor Name</label>
                                <input v-model="formData.advisor_name" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Advisor name"/>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Client Name</label>
                                <input v-model="formData.client_name" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Client name"/>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Client ID</label>
                                <input v-model="formData.client_id" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Client ID"/>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Outcome</label>
                                <select v-model="formData.outcome" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100">
                                    <option value="">— Select —</option>
                                    <option v-for="o in outcomeOptions" :key="o" :value="o">{{ o }}</option>
                                </select>
                            </div>
                        </div>
                    </section>

                    <!-- Topics Discussed (auto-filled) -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-3">
                        <h2 class="text-lg font-medium text-gray-900 border-b border-gray-200 pb-2">Topics Discussed</h2>
                        <div v-if="formData.topics_discussed && formData.topics_discussed.length">
                            <div v-for="(topic, i) in formData.topics_discussed" :key="i" class="flex items-center space-x-2 py-1">
                                <span class="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">{{ typeof topic === 'string' ? topic : (topic.topic || 'Topic ' + (i+1)) }}</span>
                            </div>
                        </div>
                        <p v-else class="text-sm text-gray-400 italic">No topics auto-detected.</p>
                    </section>

                    <!-- Action Items -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-3">
                        <div class="flex items-center justify-between border-b border-gray-200 pb-2">
                            <h2 class="text-lg font-medium text-gray-900">Action Items</h2>
                            <button v-if="!isSubmitted" @click="addActionItem" class="text-sm text-blue-600 hover:text-blue-800">+ Add</button>
                        </div>
                        <div v-if="formData.action_items && formData.action_items.length" class="space-y-2">
                            <div v-for="(item, i) in formData.action_items" :key="i" class="flex items-center space-x-2">
                                <input v-model="formData.action_items[i]" :disabled="isSubmitted" class="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" :placeholder="'Action item ' + (i+1)"/>
                                <button v-if="!isSubmitted" @click="removeActionItem(i)" class="text-red-400 hover:text-red-600">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                                </button>
                            </div>
                        </div>
                        <p v-else class="text-sm text-gray-400 italic">No action items.</p>
                    </section>

                    <!-- Follow-up -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
                        <h2 class="text-lg font-medium text-gray-900 border-b border-gray-200 pb-2">Follow-up</h2>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Follow-up Date</label>
                                <input type="date" :value="formData.follow_up_date?.split('T')[0]" @input="formData.follow_up_date = $event.target.value" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"/>
                            </div>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Follow-up Notes</label>
                            <textarea v-model="formData.follow_up_notes" :disabled="isSubmitted" rows="3" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Notes for follow-up..."></textarea>
                        </div>
                    </section>

                    <!-- Referrals -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-3">
                        <div class="flex items-center justify-between border-b border-gray-200 pb-2">
                            <h2 class="text-lg font-medium text-gray-900">Referrals</h2>
                            <button v-if="!isSubmitted" @click="addReferral" class="text-sm text-blue-600 hover:text-blue-800">+ Add</button>
                        </div>
                        <div v-if="formData.referrals && formData.referrals.length" class="space-y-2">
                            <div v-for="(ref, i) in formData.referrals" :key="i" class="flex items-center space-x-2">
                                <input v-model="formData.referrals[i]" :disabled="isSubmitted" class="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" :placeholder="'Service / department'"/>
                                <button v-if="!isSubmitted" @click="removeReferral(i)" class="text-red-400 hover:text-red-600">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                                </button>
                            </div>
                        </div>
                        <p v-else class="text-sm text-gray-400 italic">No referrals added.</p>
                    </section>

                    <!-- Notes -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-3">
                        <h2 class="text-lg font-medium text-gray-900 border-b border-gray-200 pb-2">Additional Notes</h2>
                        <textarea v-model="formData.notes" :disabled="isSubmitted" rows="4" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Any additional notes..."></textarea>
                    </section>

                    <!-- Actions -->
                    <div v-if="!isSubmitted" class="flex items-center justify-end space-x-3 pb-8">
                        <button @click="saveForm(false)" :disabled="saving" class="px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 disabled:opacity-50">
                            {{ saving ? 'Saving...' : 'Save Draft' }}
                        </button>
                        <button @click="saveForm(true)" :disabled="saving" class="px-4 py-2 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-800 disabled:opacity-50">
                            {{ saving ? 'Submitting...' : 'Submit Form' }}
                        </button>
                    </div>
                </div>
            </main>
        </div>
    `,
};
