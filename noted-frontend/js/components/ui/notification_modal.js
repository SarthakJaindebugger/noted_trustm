/**
 * NotificationModal — success/error/info notification dialog.
 */

import BaseModal from './base_modal.js';

export default {
    name: 'NotificationModal',
    components: { BaseModal },
    props: {
        show: { type: Boolean, default: false },
        title: { type: String, default: '' },
        message: { type: String, default: '' },
        type: { type: String, default: 'info' }, // 'success' | 'error' | 'info'
    },
    emits: ['close'],
    template: `
        <BaseModal :show="show" @close="$emit('close')">
            <div class="text-center">
                <div :class="[
                    'w-12 h-12 mx-auto mb-4 rounded-full flex items-center justify-center',
                    type === 'success' ? 'bg-green-100 text-green-600' :
                    type === 'error' ? 'bg-red-100 text-red-600' :
                    'bg-blue-100 text-blue-600'
                ]">
                    <svg v-if="type === 'success'" class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
                    </svg>
                    <svg v-else-if="type === 'error'" class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
                    </svg>
                    <svg v-else class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
                    </svg>
                </div>
                <h3 class="text-lg font-medium text-gray-900 mb-2">{{ title }}</h3>
                <p class="text-sm text-gray-600 mb-6">{{ message }}</p>
                <button
                    @click="$emit('close')"
                    class="w-full px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors"
                >
                    OK
                </button>
            </div>
        </BaseModal>
    `,
};
