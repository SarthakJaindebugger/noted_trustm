import { ref } from 'vue';
import { sessionService } from '../services/session_service.js';

export function useSessionTopics({
    selectedSession,
    selectedSessionDbId,
    sessionSummary,
    originalTopics,
    originalSessionSummary,
    cloneValue,
    showNotification,
}) {
    const topics = ref([]);
    const editingTopic = ref(null);
    const editingTopicDraft = ref({
        content: '',
        action_items: [],
        related_services: [],
    });
    const showAddTopicPopup = ref(false);
    const newTopicReference = ref('');
    const generatingTopic = ref(false);

    const createEmptyTopicDraft = () => ({
        content: '',
        action_items: [],
        related_services: [],
    });

    const normalizeTopicActionItems = (items = []) => (
        Array.isArray(items)
            ? items
                .map(item => typeof item === 'string' ? item.trim() : '')
                .filter(Boolean)
            : []
    );

    const normalizeTopicRelatedServices = (services = []) => (
        Array.isArray(services)
            ? services
                .map(service => {
                    if (typeof service === 'string') {
                        const name = service.trim();
                        return name ? { name, url: '' } : null;
                    }

                    const name = typeof service?.name === 'string' ? service.name.trim() : '';
                    const url = typeof service?.url === 'string' ? service.url.trim() : '';

                    if (!name && !url) {
                        return null;
                    }

                    return {
                        name: name || url,
                        url,
                    };
                })
                .filter(Boolean)
            : []
    );

    const mapSummaryToTopics = (summary) => {
        if (summary?.topics_discussed && summary.topics_discussed.length > 0) {
            const mappedTopics = summary.topics_discussed
                .filter(topicData => topicData && typeof topicData === 'object' && !Array.isArray(topicData))
                .map((topicData, index) => {
                    const topicName = topicData.topic || topicData.name || `Topic ${index + 1}`;
                    const content = topicData.summary || topicData.content || `Discussion about ${topicName.toLowerCase()}.`;

                    return {
                        id: index + 1,
                        name: topicName,
                        reference: topicName,
                        tags: [topicName],
                        expanded: false,
                        content,
                        key_points: Array.isArray(topicData.key_points) ? topicData.key_points : [],
                        action_items: Array.isArray(topicData.action_items) ? topicData.action_items : [],
                        decisions_made: Array.isArray(topicData.decisions_made) ? topicData.decisions_made : [],
                        related_services: Array.isArray(topicData.related_services) ? topicData.related_services : [],
                        importance: topicData.importance || topicData.importance_level || 'Medium',
                    };
                });

            if (mappedTopics.length > 0) {
                return mappedTopics;
            }
        }

        return [{
            id: 1,
            name: 'General Discussion',
            reference: 'General Discussion',
            tags: ['General'],
            expanded: false,
            content: summary?.overview || 'Session discussion content.',
            action_items: summary?.action_items || [],
            related_services: summary?.related_services || [],
        }];
    };

    const applyTopicDraft = (topic, draft = editingTopicDraft.value) => {
        if (!topic) {
            return;
        }

        topic.content = (draft.content || '').trim();
        topic.action_items = normalizeTopicActionItems(draft.action_items);
        topic.related_services = normalizeTopicRelatedServices(draft.related_services);
    };

    const buildTopicSummaryPayload = (topic) => ({
        topic: topic.name || topic.reference || 'Topic',
        summary: topic.content || '',
        key_points: Array.isArray(topic.key_points) ? topic.key_points : [],
        action_items: normalizeTopicActionItems(topic.action_items),
        decisions_made: Array.isArray(topic.decisions_made) ? topic.decisions_made : [],
        related_services: normalizeTopicRelatedServices(topic.related_services),
        importance: topic.importance || 'Medium',
    });

    const setTopicsFromSummary = (summary) => {
        topics.value = mapSummaryToTopics(summary);
    };

    const finalizeTopicEdit = (saveChanges = false, collapseTopic = false) => {
        if (!editingTopic.value) {
            return;
        }

        const topic = topics.value.find(t => t.id === editingTopic.value);
        if (topic) {
            if (saveChanges) {
                applyTopicDraft(topic);
            }
            if (collapseTopic) {
                topic.expanded = false;
            }
        }

        editingTopic.value = null;
        editingTopicDraft.value = createEmptyTopicDraft();
    };

    const saveTopicsSummary = async () => {
        if (!selectedSessionDbId.value) {
            throw new Error('No session selected');
        }

        const topicsPayload = topics.value.map(buildTopicSummaryPayload);
        await sessionService.updateSessionSummary(selectedSessionDbId.value, {
            topics_discussed: topicsPayload,
        });

        const updatedSummary = {
            ...(sessionSummary.value || {}),
            topics_discussed: topicsPayload,
        };
        sessionSummary.value = updatedSummary;
        originalSessionSummary.value = cloneValue(updatedSummary);
        originalTopics.value = cloneValue(topics.value);
    };

    const toggleTopic = (topicId) => {
        const topic = topics.value.find(t => t.id === topicId);
        if (topic) {
            topic.expanded = !topic.expanded;
        }
    };

    const deleteTopic = (topicId) => {
        topics.value = topics.value.filter(t => t.id !== topicId);
    };

    const showAddTopicDialog = () => {
        showAddTopicPopup.value = true;
        newTopicReference.value = '';
    };

    const closeAddTopicPopup = () => {
        showAddTopicPopup.value = false;
        newTopicReference.value = '';
        generatingTopic.value = false;
    };

    const generateNewTopic = async () => {
        if (!newTopicReference.value.trim()) {
            showNotification('Warning', 'Please enter a topic reference', 'info');
            return;
        }

        if (!selectedSession.value) {
            showNotification('Warning', 'No session selected', 'info');
            return;
        }

        generatingTopic.value = true;
        try {
            const topicData = await sessionService.generateTopicSummary(
                selectedSessionDbId.value,
                newTopicReference.value
            );

            const topicName = topicData.topic || newTopicReference.value;
            topics.value.push({
                id: Date.now(),
                name: topicName,
                reference: topicName,
                tags: [topicName],
                expanded: true,
                content: topicData.summary || 'Generated summary not available.',
                action_items: [],
                related_services: [],
                snippets: topicData.snippets || [],
            });

            closeAddTopicPopup();
        } catch (error) {
            console.error('Failed to generate topic:', error);
            showNotification('Error', 'Failed to generate topic summary. Please try again.', 'error');
        } finally {
            generatingTopic.value = false;
        }
    };

    const addTopic = () => {
        showAddTopicDialog();
    };

    const startEditingTopic = (topicId) => {
        const topic = topics.value.find(t => t.id === topicId);
        if (topic) {
            topic.expanded = true;
            editingTopic.value = topicId;
            editingTopicDraft.value = {
                content: topic.content || '',
                action_items: Array.isArray(topic.action_items) ? [...topic.action_items] : [],
                related_services: normalizeTopicRelatedServices(topic.related_services),
            };
        }
    };

    const saveTopicEdit = async () => {
        if (!editingTopic.value) {
            return;
        }

        if (!selectedSession.value) {
            showNotification('Warning', 'No session selected', 'info');
            return;
        }

        const topic = topics.value.find(t => t.id === editingTopic.value);
        if (!topic) {
            return;
        }

        const topicId = editingTopic.value;
        const previousTopic = cloneValue(topic);
        const previousDraft = cloneValue(editingTopicDraft.value);

        finalizeTopicEdit(true);

        try {
            await saveTopicsSummary();
            showNotification('Success', 'Topic summary updated successfully.', 'success');
        } catch (error) {
            console.error('Failed to save topic summary:', error);
            Object.assign(topic, previousTopic);
            topic.expanded = true;
            editingTopic.value = topicId;
            editingTopicDraft.value = previousDraft;
            showNotification('Error', 'Failed to save topic changes. Please try again.', 'error');
        }
    };

    const cancelTopicEdit = () => {
        finalizeTopicEdit();
    };

    return {
        topics,
        editingTopic,
        editingTopicDraft,
        showAddTopicPopup,
        newTopicReference,
        generatingTopic,
        setTopicsFromSummary,
        finalizeTopicEdit,
        toggleTopic,
        deleteTopic,
        addTopic,
        showAddTopicDialog,
        closeAddTopicPopup,
        generateNewTopic,
        startEditingTopic,
        saveTopicEdit,
        cancelTopicEdit,
    };
}
