/**
 * StatusBadge — session status indicator with optional spinner.
 */

const STATUS_META = {
    processing: {
        label: 'Processing',
        classes: 'border-yellow-300 bg-yellow-50 text-yellow-800',
        showSpinner: true,
    },
    active: {
        label: 'Active',
        classes: 'border-blue-300 bg-blue-50 text-blue-800',
        showSpinner: false,
    },
    paused: {
        label: 'Paused',
        classes: 'border-orange-300 bg-orange-50 text-orange-700',
        showSpinner: false,
    },
    completed: {
        label: 'Completed',
        classes: 'border-green-300 bg-green-50 text-green-800',
        showSpinner: false,
    },
    disconnected: {
        label: 'Disconnected',
        classes: 'border-orange-300 bg-orange-50 text-orange-700',
        showSpinner: false,
    },
    error: {
        label: 'Error',
        classes: 'border-red-300 bg-red-50 text-red-700',
        showSpinner: false,
    },
    default: {
        label: 'Unknown',
        classes: 'border-gray-300 bg-gray-50 text-gray-600',
        showSpinner: false,
    },
};

export function getStatusDisplay(status) {
    const normalized = (status || '').toLowerCase();
    return STATUS_META[normalized] || STATUS_META.default;
}

export function isProcessingStatus(status) {
    return (status || '').toLowerCase() === 'processing';
}

export default {
    name: 'StatusBadge',
    props: {
        status: { type: String, default: '' },
    },
    setup(props) {
        const display = computed(() => getStatusDisplay(props.status));
        return { display };
    },
    template: `
        <span
            class="inline-flex items-center space-x-1 px-2 py-1 text-xs font-medium border rounded-full"
            :class="display.classes"
        >
            <svg
                v-if="display.showSpinner"
                class="w-3 h-3 animate-spin text-current"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
            >
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke-width="3"></circle>
                <path class="opacity-75" stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M4 12a8 8 0 018-8"></path>
            </svg>
            <span>{{ display.label }}</span>
        </span>
    `,
};
import { computed } from 'vue';
