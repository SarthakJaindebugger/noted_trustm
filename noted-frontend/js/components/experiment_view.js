import { ref, computed, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { sessionService } from '../services/session_service.js';
import { experimentService } from '../services/experiment_service.js';
import { registerCJKFont } from '../utils/pdf.js';

import DOMPurify from 'dompurify';
import MarkdownIt from 'markdown-it';

const md = new MarkdownIt();

// Sanitize HTML to prevent XSS via v-html
const sanitize = (html) => DOMPurify.sanitize(html);
const renderInline = (text) => sanitize(md.renderInline(text));
const renderBlock = (text) => sanitize(md.render(text));

export default {
    name: 'ExperimentView',
    props: {
        sessionHint: {
            type: Object,
            default: null
        }
    },
    setup(props) {
        const router = useRouter();
        const sessions = ref([]);
        const isLoadingSessions = ref(true);
        const sessionLoadError = ref('');
        const selectedSessionId = ref(null);

        const showTranscript = ref(false);
        const transcriptEntries = ref([]);
        const transcriptLoading = ref(false);
        const transcriptError = ref('');

        const OUTPUT_CONFIGS = Object.freeze([
            { key: 'action_points', label: 'Action Points' },
            { key: 'recap', label: 'Recap' }
        ]);

        const outputs = ref({
            action_points: null,
            recap: null
        });
        const outputsError = ref('');
        const isGeneratingOutputs = ref(false);
        const isSaving = ref(false);

        const selectedSession = computed(() => {
            return sessions.value.find(session => session.id === selectedSessionId.value) || null;
        });

        const outputsReady = computed(() => {
            return OUTPUT_CONFIGS.every(({ key }) => Boolean(outputs.value[key]));
        });

        const outputSections = computed(() => {
            return OUTPUT_CONFIGS.map(({ key, label }) => {
                const data = outputs.value[key];
                return {
                    key,
                    label,
                    data,
                    title: data?.title || label,
                    description: data?.description || '',
                    items: Array.isArray(data?.items) ? data.items : [],
                    formattedOutput: data?.formatted_output || ''
                };
            });
        });

        const normalizeScore = (value) => {
            return typeof value === 'number' ? value : Number.NEGATIVE_INFINITY;
        };

        const gatherAllMatches = (outputsValue) => {
            const grouped = {
                vector: new Map(),
                keyword: new Map()
            };

            OUTPUT_CONFIGS.forEach(({ key }) => {
                const data = outputsValue[key];
                const context = data?.knowledge_context || {};

                const vectorMatches = context.vector_matches;
                if (vectorMatches && typeof vectorMatches === 'object') {
                    Object.values(vectorMatches).forEach(topicMatches => {
                        if (!Array.isArray(topicMatches)) {
                            return;
                        }
                        topicMatches.forEach(match => {
                            const name = match?.service_name;
                            const link = match?.service_link;
                            if (!name || !link) {
                                return;
                            }
                            const score = normalizeScore(match?.score);
                            const signature = `${name}|${link}`;
                            const existing = grouped.vector.get(signature);
                            if (!existing || score > existing.score) {
                                grouped.vector.set(signature, { name, link, score, topic: match?.topic || null });
                            }
                        });
                    });
                }

                const keywordMatches = Array.isArray(context.keyword_matches) ? context.keyword_matches : [];
                keywordMatches.forEach(match => {
                    const name = match?.service_name;
                    const link = match?.service_link;
                    if (!name || !link) {
                        return;
                    }
                    const score = normalizeScore(match?.match_ratio);
                    const description = match?.description || '';
                    const snippet = match?.snippet || '';
                    const signature = `${name}|${link}|${snippet}`;
                    const existing = grouped.keyword.get(signature);
                    if (!existing || score > existing.score) {
                        grouped.keyword.set(signature, { name, link, score, description, snippet });
                    }
                });
            });

            return grouped;
        };

        const knowledgeServices = computed(() => {
            const grouped = gatherAllMatches(outputs.value);
            const combined = new Map();

            grouped.vector.forEach((entry, signature) => {
                combined.set(signature, { ...entry, sourceType: 'vector', snippet: '', description: '' });
            });

            grouped.keyword.forEach((entry, signature) => {
                if (!combined.has(signature)) {
                    combined.set(signature, { ...entry, sourceType: 'keyword' });
                } else {
                    const existing = combined.get(signature);
                    combined.set(signature, {
                        ...existing,
                        sourceType: existing.sourceType === 'vector' ? 'both' : 'keyword',
                        description: entry.description || existing.description,
                        snippet: entry.snippet || existing.snippet
                    });
                }
            });

            return Array
                .from(combined.values())
                .sort((a, b) => (b.score ?? Number.NEGATIVE_INFINITY) - (a.score ?? Number.NEGATIVE_INFINITY));
        });

        const keywordMatches = computed(() => {
            const grouped = gatherAllMatches(outputs.value);
            return Array
                .from(grouped.keyword.values())
                .sort((a, b) => (b.score ?? Number.NEGATIVE_INFINITY) - (a.score ?? Number.NEGATIVE_INFINITY));
        });

        const resetOutputs = () => {
            outputs.value = {
                action_points: null,
                recap: null
            };
        };

        let requestCounter = 0;

        const applySessionHint = (hint, availableSessions = sessions.value) => {
            if (!hint || availableSessions.length === 0) {
                return;
            }

            const { sessionId, reference } = hint;
            let target = null;

            if (sessionId) {
                target = availableSessions.find(session => session.id === sessionId);
            }

            if (!target && reference) {
                target = availableSessions.find(session => session.reference === reference);
            }

            if (target) {
                selectedSessionId.value = target.id;
            }
        };

        const loadSessions = async () => {
            isLoadingSessions.value = true;
            sessionLoadError.value = '';
            outputsError.value = '';
            resetOutputs();
            try {
                const fetched = await sessionService.getUserSessions();
                sessions.value = fetched;

                const previousSelection = selectedSessionId.value;

                if (props.sessionHint) {
                    applySessionHint(props.sessionHint, fetched);
                }

                if (!selectedSessionId.value && fetched.length > 0) {
                    selectedSessionId.value = fetched[0].id;
                }

                if (selectedSessionId.value && selectedSessionId.value === previousSelection) {
                    const session = fetched.find(item => item.id === selectedSessionId.value);
                    if (session) {
                        generateOutputs(session);
                    }
                }
            } catch (error) {
                console.error('Failed to load sessions for experiment view:', error);
                sessionLoadError.value = 'Unable to load sessions. Refresh and try again.';
            } finally {
                isLoadingSessions.value = false;
            }
        };

        const refreshTranscript = async () => {
            transcriptError.value = '';
            if (!selectedSession.value) {
                transcriptEntries.value = [];
                return;
            }

            transcriptLoading.value = true;
            try {
                const transcript = await sessionService.getSessionTranscript(selectedSession.value.reference);
                transcriptEntries.value = Array.isArray(transcript) ? transcript : [];
            } catch (error) {
                console.error('Failed to load transcript for experiment view:', error);
                transcriptError.value = 'Could not load transcript for this session.';
                transcriptEntries.value = [];
            } finally {
                transcriptLoading.value = false;
            }
        };

        const toggleTranscript = async () => {
            if (!showTranscript.value) {
                await refreshTranscript();
            }
            showTranscript.value = !showTranscript.value;
        };

        const generateOutputs = async (sessionOrEvent = null) => {
            outputsError.value = '';

            let candidateSession = null;
            if (sessionOrEvent && typeof sessionOrEvent === 'object') {
                if ('id' in sessionOrEvent && sessionOrEvent.id) {
                    candidateSession = sessionOrEvent;
                }
            }

            const activeSession = candidateSession || selectedSession.value;
            if (!activeSession) {
                resetOutputs();
                return;
            }

            resetOutputs();

            const requestId = ++requestCounter;
            isGeneratingOutputs.value = true;

            const aggregated = {
                action_points: null,
                recap: null
            };

            try {
                for (const { key } of OUTPUT_CONFIGS) {
                    const result = await experimentService.generate(activeSession.id, {
                        uiType: 'full_text',
                        contentType: key
                    });
                    aggregated[key] = result;
                }

                if (requestCounter === requestId) {
                    outputs.value = aggregated;
                }
            } catch (error) {
                console.error('Experiment generation failed:', error);
                if (requestCounter === requestId) {
                    outputsError.value = error.message || 'Failed to generate experiment output.';
                    outputs.value = aggregated;
                }
            } finally {
                if (requestCounter === requestId) {
                    isGeneratingOutputs.value = false;
                }
                // Log results for debugging
                console.log('Experiment generation completed:', aggregated);
            }
        };

        const saveOutputsAsPdf = async () => {
            const session = selectedSession.value;

            if (!session) {
                outputsError.value = 'Select a session before saving.';
                return;
            }

            if (!outputsReady.value) {
                outputsError.value = 'Generate content before saving.';
                return;
            }

            isSaving.value = true;
            try {
                const { jsPDF } = window.jspdf || {};
                if (!jsPDF) {
                    throw new Error('PDF generator (jsPDF) not available.');
                }

                const doc = new jsPDF();
                await registerCJKFont(doc);
                const margin = 20;
                let yPosition = margin;

                const addLine = (text, fontSize = 12, options = {}) => {
                    if (!text) return;
                    doc.setFontSize(fontSize);
                    doc.setFont('NotoSansCJK', options.bold ? 'bold' : 'normal');
                    const lines = doc.splitTextToSize(text, doc.internal.pageSize.getWidth() - margin * 2);
                    lines.forEach(line => {
                        if (yPosition > doc.internal.pageSize.getHeight() - margin) {
                            doc.addPage();
                            yPosition = margin;
                        }
                        doc.text(line, margin, yPosition);
                        yPosition += fontSize * 0.6 + 2;
                    });
                    yPosition += 4;
                };

                addLine("Note'd Experiment Output", 18, { bold: true });
                addLine(`Session: ${session.reference}`, 12);
                addLine(new Date().toLocaleString(), 10);
                addLine('', 8);

                outputSections.value.forEach((section, index) => {
                    addLine(section.title, 16, { bold: true });
                    if (section.description) {
                        addLine(section.description, 12);
                    }

                    if (section.items.length) {
                        section.items.forEach(item => addLine(item, 12));
                    } else if (section.formattedOutput) {
                        addLine(section.formattedOutput, 12);
                    }

                    if (index < outputSections.value.length - 1) {
                        addLine('', 6);
                    }
                });

                if (knowledgeServices.value.length) {
                    addLine('', 6);
                    addLine('Referenced Services', 14, { bold: true });
                    knowledgeServices.value.forEach(service => {
                        addLine(`${service.name}: ${service.link}`, 11);
                    });
                }

                const filename = `experiment-${session.reference}-full_text.pdf`;
                doc.save(filename);
            } catch (error) {
                console.error('Failed to save experiment output:', error);
                outputsError.value = error.message || 'Unable to save PDF.';
            } finally {
                isSaving.value = false;
            }
        };

        const goBack = () => {
            router.push({ name: 'dashboard' });
        };

        onMounted(loadSessions);

        watch(() => props.sessionHint, (newHint) => {
            if (newHint) {
                applySessionHint(newHint);
            }
        });

        watch(selectedSessionId, (newId) => {
            showTranscript.value = false;
            outputsError.value = '';

            if (!newId) {
                resetOutputs();
                return;
            }

            const session = sessions.value.find(item => item.id === newId) || null;
            generateOutputs(session);
        });

        return {
            sessions,
            isLoadingSessions,
            sessionLoadError,
            selectedSessionId,
            selectedSession,
            outputsReady,
            outputSections,
            outputsError,
            isGeneratingOutputs,
            isSaving,
            knowledgeServices,
            keywordMatches,
            showTranscript,
            transcriptEntries,
            transcriptLoading,
            transcriptError,
            toggleTranscript,
            generateOutputs,
            saveOutputsAsPdf,
            goBack,
            renderInline,
            renderBlock
        };
    },
    template: /*html*/`
        <div class="min-h-screen bg-gray-50">
            <header class="bg-white border-b border-gray-200 px-6 py-4">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-4">
                        <button
                            @click="goBack"
                            class="flex items-center space-x-2 px-3 py-2 text-gray-600 hover:text-gray-900 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                        >
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                            </svg>
                            <span>Back</span>
                        </button>
                        <h1 class="text-xl font-semibold text-gray-900">Note'd Experiment Lab</h1>
                    </div>
                </div>
            </header>

            <main class="px-6 py-10">
                <div class="max-w-4xl mx-auto space-y-8">
                    <div class="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
                        <div class="mb-4">
                            <label class="text-sm font-medium text-gray-700 block mb-2">Choose Session</label>
                            <div class="flex items-center space-x-3">
                                <select
                                    v-model="selectedSessionId"
                                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                                    :disabled="isLoadingSessions"
                                >
                                    <option v-if="isLoadingSessions">Loading sessions...</option>
                                    <option
                                        v-for="session in sessions"
                                        :key="session.id"
                                        :value="session.id"
                                    >
                                        {{ session.reference }} - {{ session.topic }}
                                    </option>
                                </select>
                            </div>
                            <p v-if="sessionLoadError" class="text-xs text-red-500 mt-2">{{ sessionLoadError }}</p>
                        </div>

                        <div class="grid gap-4">
                            <button
                                @click="toggleTranscript"
                                :disabled="!selectedSession"
                                class="w-full flex items-center justify-center px-4 py-3 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-800 transition-colors disabled:opacity-50"
                            >
                                {{ showTranscript ? 'Hide Transcript' : 'View Transcript' }}
                            </button>

                            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                                <button
                                    @click="generateOutputs()"
                                    :disabled="isGeneratingOutputs || !selectedSession"
                                    class="flex items-center justify-center px-4 py-3 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors disabled:opacity-50"
                                >
                                    <span v-if="isGeneratingOutputs" class="animate-pulse">Generating...</span>
                                    <span v-else>Regenerate</span>
                                </button>
                                <button
                                    @click="saveOutputsAsPdf"
                                    :disabled="isSaving || !outputsReady"
                                    class="flex items-center justify-center px-4 py-3 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-800 transition-colors disabled:opacity-50"
                                >
                                    <span v-if="isSaving" class="animate-pulse">Saving...</span>
                                    <span v-else>Save PDF</span>
                                </button>
                            </div>

                            <p v-if="outputsError" class="text-xs text-red-500">{{ outputsError }}</p>
                        </div>
                    </div>

                    <div class="bg-white border border-gray-200 rounded-lg shadow-sm p-6 min-h-[320px]">
                        <div class="flex items-center justify-between mb-4">
                            <h2 class="text-lg font-semibold text-gray-900">Action Points & Recap</h2>
                            <span v-if="isGeneratingOutputs" class="text-xs text-gray-500 animate-pulse">Generating...</span>
                        </div>

                        <div v-if="outputsReady">
                            <div class="grid gap-6 md:grid-cols-2">
                                <div
                                    v-for="section in outputSections"
                                    :key="section.key"
                                    class="border border-gray-200 rounded-md p-4 space-y-3"
                                >
                                    <div>
                                        <h3 class="text-base font-semibold text-gray-900">{{ section.title }}</h3>
                                        <p v-if="section.description" class="text-sm text-gray-600 mt-1">{{ section.description }}</p>
                                    </div>

                                    <ul v-if="section.items.length" class="list-disc list-inside space-y-2 text-sm text-gray-700">
                                        <li
                                            v-for="(item, index) in section.items"
                                            :key="index"
                                            v-html="renderInline(item)"
                                        ></li>
                                    </ul>

                                    <div
                                        v-else-if="section.formattedOutput"
                                        class="text-sm text-gray-700 space-y-2"
                                        v-html="renderBlock(section.formattedOutput)"
                                    ></div>

                                    <p v-else class="text-sm text-gray-500">No content returned for this section.</p>
                                </div>
                            </div>

                            <div v-if="knowledgeServices.length" class="mt-6 border-t border-gray-200 pt-4 space-y-4">
                                <div>
                                    <h4 class="text-sm font-semibold text-gray-900 mb-2">Referenced Services</h4>
                                    <ul class="space-y-2">
                                        <li v-for="service in knowledgeServices" :key="service.link">
                                            <a
                                                :href="service.link"
                                                class="text-sm text-blue-600 hover:underline"
                                                target="_blank"
                                                rel="noopener"
                                            >
                                                {{ service.name }}
                                            </a>
                                            <span v-if="typeof service.score === 'number'" class="text-xs text-gray-500 ml-2">
                                                (score: {{ service.score.toFixed(3) }})
                                            </span>
                                        </li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                        <div v-else-if="isGeneratingOutputs" class="text-sm text-gray-500">
                            Generating action points and recap...
                        </div>
                        <div v-else class="text-sm text-gray-400 italic">
                            Select a session to automatically generate the action points and recap.
                        </div>
                    </div>
                </div>

                <div
                    v-if="showTranscript"
                    class="fixed inset-0 backdrop-blur-sm bg-white/30 flex items-center justify-center z-50"
                    @click="toggleTranscript"
                >
                    <div
                        class="bg-white rounded-lg shadow-xl max-w-3xl w-full mx-4 max-h-[80vh] overflow-y-auto"
                        @click.stop
                    >
                        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                            <h3 class="text-lg font-semibold text-gray-900">Transcript - {{ selectedSession?.reference }}</h3>
                            <button @click="toggleTranscript" class="text-gray-500 hover:text-gray-700">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>
                        <div class="px-6 py-4 space-y-4">
                            <p v-if="transcriptError" class="text-sm text-red-500">{{ transcriptError }}</p>
                            <p v-else-if="transcriptLoading" class="text-sm text-gray-500">Loading transcript...</p>
                            <div v-else-if="transcriptEntries.length > 0" class="space-y-3">
                                <div
                                    v-for="(entry, index) in transcriptEntries"
                                    :key="index"
                                    class="border border-gray-200 rounded-md p-3"
                                >
                                    <div class="text-xs text-gray-500 mb-1">
                                        {{ entry.speaker || 'Speaker' }} - {{ entry.start_time ? Math.round(entry.start_time) + 's' : '' }}
                                    </div>
                                    <p class="text-sm text-gray-700 whitespace-pre-wrap">{{ entry.text }}</p>
                                </div>
                            </div>
                            <p v-else class="text-sm text-gray-500">No transcript entries available yet for this session.</p>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    `
};
