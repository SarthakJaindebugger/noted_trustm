/**
 * TopicCard — displays a single topic with expand/collapse, edit, and delete.
 */
export default {
    name: 'TopicCard',
    props: {
        topic: { type: Object, required: true },
        isEditing: { type: Boolean, default: false },
        editingDraft: {
            type: Object,
            default: () => ({
                content: '',
                action_items: [],
                related_services: [],
            }),
        },
    },
    emits: ['toggle', 'delete', 'start-edit', 'save-edit', 'cancel-edit', 'update:editingDraft'],
    methods: {
        updateDraft(field, value) {
            this.$emit('update:editingDraft', {
                ...this.editingDraft,
                [field]: value,
            });
        },
        updateActionItem(index, value) {
            const nextItems = [...(this.editingDraft.action_items || [])];
            nextItems[index] = value;
            this.updateDraft('action_items', nextItems);
        },
        addActionItem() {
            this.updateDraft('action_items', [...(this.editingDraft.action_items || []), '']);
        },
        removeActionItem(index) {
            const nextItems = [...(this.editingDraft.action_items || [])];
            nextItems.splice(index, 1);
            this.updateDraft('action_items', nextItems);
        },
        updateRelatedService(index, field, value) {
            const nextServices = (this.editingDraft.related_services || []).map(service => ({
                name: service?.name || '',
                url: service?.url || '',
            }));
            if (!nextServices[index]) {
                nextServices[index] = { name: '', url: '' };
            }
            nextServices[index][field] = value;
            this.updateDraft('related_services', nextServices);
        },
        addRelatedService() {
            this.updateDraft('related_services', [
                ...(this.editingDraft.related_services || []),
                { name: '', url: '' },
            ]);
        },
        removeRelatedService(index) {
            const nextServices = [...(this.editingDraft.related_services || [])];
            nextServices.splice(index, 1);
            this.updateDraft('related_services', nextServices);
        },
    },
    template: `
        <div class="bg-white border border-gray-200 rounded-lg">
            <div class="p-4">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-3">
                        <button
                            @click="$emit('toggle', topic.id)"
                            class="text-gray-400 hover:text-gray-600"
                        >
                            <svg
                                class="w-4 h-4 transition-transform"
                                :class="{ 'rotate-90': topic.expanded }"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                            >
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
                            </svg>
                        </button>
                        <span class="text-sm font-medium text-gray-900">Topic:</span>
                        <div class="flex flex-wrap gap-2">
                            <span
                                v-for="(tag, index) in topic.tags"
                                :key="tag"
                                :class="[
                                    'px-2 py-1 text-xs rounded-md border border-gray-300 inline-block',
                                    index === 0 ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800'
                                ]"
                            >
                                {{ tag }}
                            </span>
                        </div>
                    </div>
                    <div class="flex items-center space-x-2">
                        <button
                            @click="$emit('delete', topic.id)"
                            class="flex items-center space-x-1 px-2 py-1 text-xs text-gray-600 hover:text-gray-800"
                        >
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                            </svg>
                            <span>Delete Topic</span>
                        </button>
                        <button
                            @click="$emit('start-edit', topic.id)"
                            class="flex items-center space-x-1 px-2 py-1 text-xs text-gray-600 hover:text-gray-800"
                        >
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                            </svg>
                            <span>Edit Output</span>
                        </button>
                    </div>
                </div>
            </div>

            <!-- Collapsible Content -->
            <div
                v-if="topic.expanded"
                class="border-t border-gray-200 p-4 bg-gray-50 animate-fade-in"
            >
                <div class="space-y-3">
                    <div>
                        <div class="flex items-center justify-between mb-2">
                            <h5 class="text-sm font-medium text-gray-900">Summary:</h5>
                            <div v-if="isEditing" class="flex space-x-2">
                                <button
                                    @click="$emit('save-edit')"
                                    class="flex items-center space-x-1 px-2 py-1 text-xs text-green-600 hover:text-green-800 bg-green-50 rounded"
                                >
                                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                                    </svg>
                                    <span>Save</span>
                                </button>
                                <button
                                    @click="$emit('cancel-edit')"
                                    class="flex items-center space-x-1 px-2 py-1 text-xs text-gray-600 hover:text-gray-800 bg-gray-50 rounded"
                                >
                                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                    </svg>
                                    <span>Cancel</span>
                                </button>
                            </div>
                        </div>

                        <!-- Edit Mode -->
                        <div v-if="isEditing">
                            <textarea
                                :value="editingDraft.content"
                                @input="updateDraft('content', $event.target.value)"
                                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                                rows="4"
                                placeholder="Enter topic summary..."
                            ></textarea>
                        </div>

                        <!-- View Mode -->
                        <p v-else class="text-sm text-gray-700">{{ topic.content }}</p>
                    </div>
                    <div v-if="isEditing || (topic.action_items && topic.action_items.length > 0)">
                        <h5 class="text-sm font-medium text-gray-900 mb-2">Action Items:</h5>
                        <div v-if="isEditing" class="space-y-2">
                            <div
                                v-for="(item, index) in (editingDraft.action_items || [])"
                                :key="index"
                                class="flex items-start space-x-2"
                            >
                                <input
                                    :value="item"
                                    @input="updateActionItem(index, $event.target.value)"
                                    class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                                    :placeholder="'Action item ' + (index + 1)"
                                />
                                <button
                                    @click="removeActionItem(index)"
                                    class="px-2 py-2 text-xs text-gray-500 hover:text-red-600"
                                >
                                    Remove
                                </button>
                            </div>
                            <button
                                @click="addActionItem"
                                class="inline-flex items-center px-3 py-1.5 text-xs text-blue-600 hover:text-blue-800 bg-blue-50 rounded"
                            >
                                Add Action Item
                            </button>
                        </div>
                        <ul v-else class="text-sm text-gray-700 space-y-1">
                            <li v-for="item in topic.action_items" :key="item">• {{ item }}</li>
                        </ul>
                    </div>
                    <div v-if="isEditing || (topic.related_services && topic.related_services.length > 0)">
                        <h5 class="text-sm font-medium text-gray-900 mb-2">Related Services:</h5>
                        <div v-if="isEditing" class="space-y-2">
                            <div
                                v-for="(service, index) in (editingDraft.related_services || [])"
                                :key="index"
                                class="grid grid-cols-1 gap-2 sm:grid-cols-3"
                            >
                                <input
                                    :value="service.name"
                                    @input="updateRelatedService(index, 'name', $event.target.value)"
                                    class="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                                    placeholder="Service name"
                                />
                                <input
                                    :value="service.url"
                                    @input="updateRelatedService(index, 'url', $event.target.value)"
                                    class="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                                    placeholder="Service URL"
                                />
                                <button
                                    @click="removeRelatedService(index)"
                                    class="px-2 py-2 text-xs text-gray-500 hover:text-red-600"
                                >
                                    Remove
                                </button>
                            </div>
                            <button
                                @click="addRelatedService"
                                class="inline-flex items-center px-3 py-1.5 text-xs text-blue-600 hover:text-blue-800 bg-blue-50 rounded"
                            >
                                Add Related Service
                            </button>
                        </div>
                        <ul v-else class="text-sm space-y-1">
                            <li v-for="service in topic.related_services" :key="service.name">
                                <a v-if="service.url" :href="service.url" class="text-blue-600 hover:text-blue-800 underline">{{ service.name }}</a>
                                <span v-else class="text-gray-700">{{ service.name }}</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    `,
};
