/**
 * TranscriptViewer — displays and optionally edits session transcript
 * as a conversation between Customer and Advisor.
 */

import { ref } from 'vue';
export default {
    name: 'TranscriptViewer',
    props: {
        sessionRef: { type: String, default: '' },
        transcriptData: { type: Array, default: () => [] },
        loading: { type: Boolean, default: false },
        editing: { type: Boolean, default: false },
        editedEntries: { type: Array, default: () => [] },
    },
    emits: ['close', 'start-edit', 'save', 'cancel-edit', 'update:editedEntries'],
    setup(props, { emit }) {
        const updateEntry = (index, value) => {
            const updated = [...props.editedEntries];
            updated[index] = { ...updated[index], text: value };
            emit('update:editedEntries', updated);
        };

        const isAdvisor = (speaker) => {
            if (!speaker) return false;
            const s = speaker.toLowerCase();
            return s === 'advisor' || s.includes('advisor') || s === 'assistant' || s.includes('assistant');
        };

        return { updateEntry, isAdvisor };
    },
    template: `
        <div class="bg-white border border-gray-200 rounded-lg">
            <div class="p-4 border-b border-gray-200">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-3">
                        <h4 class="text-lg font-medium text-gray-900">Session Transcript</h4>
                        <span class="text-sm text-gray-500">{{ sessionRef || '' }}</span>
                    </div>
                    <div class="flex items-center space-x-2">
                        <button
                            v-if="!editing"
                            @click="$emit('start-edit')"
                            class="px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
                        >Edit</button>
                        <div v-else class="flex space-x-2">
                            <button
                                @click="$emit('save')"
                                class="px-3 py-1.5 text-xs font-medium text-white bg-black rounded-md hover:bg-gray-800 transition-colors"
                            >Save</button>
                            <button
                                @click="$emit('cancel-edit')"
                                class="px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
                            >Cancel</button>
                        </div>
                        <button
                            @click="$emit('close')"
                            class="ml-2 text-gray-400 hover:text-gray-600 text-lg leading-none"
                        >&times;</button>
                    </div>
                </div>
            </div>

            <!-- Loading -->
            <div v-if="loading" class="text-center py-8">
                <div class="text-gray-500 text-sm">Loading transcript...</div>
            </div>

            <!-- Conversation -->
            <div v-else-if="transcriptData.length > 0" class="max-h-[32rem] overflow-y-auto p-4">
                <div class="space-y-3">
                    <div
                        v-for="(entry, index) in (editing ? editedEntries : transcriptData)"
                        :key="index"
                        :class="['flex', isAdvisor(entry.speaker) ? 'justify-end' : 'justify-start']"
                    >
                        <div
                            :class="[
                                'max-w-[80%] rounded-lg px-4 py-3',
                                isAdvisor(entry.speaker)
                                    ? 'bg-blue-50 rounded-tr-none'
                                    : 'bg-gray-100 rounded-tl-none'
                            ]"
                        >
                            <div class="mb-1">
                                <span
                                    :class="[
                                        'text-xs font-semibold',
                                        isAdvisor(entry.speaker) ? 'text-blue-600' : 'text-gray-600'
                                    ]"
                                >{{ entry.speaker }}</span>
                            </div>

                            <!-- Edit Mode -->
                            <textarea
                                v-if="editing"
                                :value="editedEntries[index].text"
                                @input="updateEntry(index, $event.target.value)"
                                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm bg-white resize-y"
                                :rows="Math.max(3, Math.ceil((editedEntries[index]?.text?.length || 0) / 60))"
                            ></textarea>

                            <!-- View Mode -->
                            <p v-else class="text-sm text-gray-800 leading-relaxed">{{ entry.text }}</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Empty -->
            <div v-else class="text-center py-8 text-gray-500">
                <p class="text-sm mb-1">No transcript data available.</p>
                <p class="text-xs text-gray-400">The session may not have been recorded yet or is still processing.</p>
            </div>
        </div>
    `,
};
