/**
 * BaseModal — reusable modal wrapper component.
 */

import { ref } from 'vue';
export default {
    name: 'BaseModal',
    props: {
        show: { type: Boolean, default: false },
        maxWidth: { type: String, default: 'max-w-md' },
    },
    emits: ['close'],
    setup(props, { emit }) {
        const close = () => emit('close');
        return { close };
    },
    template: `
        <div
            v-if="show"
            class="fixed inset-0 backdrop-blur-sm bg-white/30 flex items-center justify-center z-50"
            @click="close"
        >
            <div
                :class="['bg-white rounded-lg shadow-xl w-full mx-4 p-6', maxWidth]"
                @click.stop
            >
                <slot />
            </div>
        </div>
    `,
};
