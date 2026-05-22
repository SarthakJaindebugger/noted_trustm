import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { authService } from '../services/auth_service.js';
import { useLiveRecordingSession } from '../composables/use_live_recording_session.js';
import { useRecordingSessionControls } from '../composables/use_recording_session_controls.js';
import BaseModal from './ui/base_modal.js';

export default {
    name: 'RecordingView',
    components: { BaseModal },
    props: {
        sessionData: {
            type: Object,
            default: null
        },
        sessionId: {
            type: String,
            default: null
        }
    },
    setup(props) {
        const user = ref(authService.getUser());
        const audioLevel = ref(0);

        // Audio visualization: store normalized energy levels (0-100) for dynamic number of bars
        const audioBars = ref([]);
        const containerWidth = ref(0);
        const barWidth = 1; // 1px per bar
        const barSpacing = 4; // 4px spacing (space-x-1 in Tailwind)
        const maxBars = computed(() => Math.floor(containerWidth.value / (barWidth + barSpacing)) || 240);
        const analyser = ref(null);
        const transcriptContainer = ref(null);
        const audioBarsContainer = ref(null);

        // WebSocket and session management
        // Support both: new session (sessionData prop) and resume (sessionId route param)
        const sessionId = ref(
            (props.sessionData && props.sessionData.sessionId) ||
            props.sessionId ||
            null
        );
        const isResuming = ref(!props.sessionData && !!props.sessionId);

        let waveformInterval = null;

        // Real-time audio visualization
        const updateAudioVisualization = () => {
            if (!analyser.value) return;

            const dataArray = new Uint8Array(analyser.value.frequencyBinCount);
            analyser.value.getByteFrequencyData(dataArray);

            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {
                const v = dataArray[i] / 128.0;
                sum += v * v;
            }

            const rms = Math.sqrt(sum / dataArray.length);
            const energyPercentage = Math.min(100, rms * 100);
            audioLevel.value = energyPercentage;

            while (audioBars.value.length < maxBars.value) {
                audioBars.value.unshift(0);
            }
            while (audioBars.value.length > maxBars.value) {
                audioBars.value.shift();
            }

            audioBars.value.shift();
            audioBars.value.push(energyPercentage);
        };

        const startWaveformVisualization = () => {
            waveformInterval = setInterval(updateAudioVisualization, 100);
        };

        const stopWaveformVisualization = () => {
            if (waveformInterval) {
                clearInterval(waveformInterval);
                waveformInterval = null;
            }
        };

        const {
            recordingTime,
            formatTime,
            conversationEntries,
            currentLanguage,
            languageConfidence,
            languageSwitched,
            processingTime,
            summaryData,
            handleBackendMessage,
            loadExistingSession,
            startRecordingTimer,
            stopRecordingTimer,
            cleanupLiveSession,
        } = useLiveRecordingSession({
            sessionId,
            transcriptContainer,
        });
        const {
            isRecording,
            isPaused,
            isProcessingRecording,
            connectionStatus,
            showFinishSessionPopup,
            toggleRecording,
            showFinishSessionDialog,
            closeFinishSessionPopup,
            deleteSessionFromPopup,
            saveSessionFromPopup,
            saveAndEditSummary,
            actuallyFinishSession,
            startAnotherSession,
            initializeRecordingSession,
            cleanupRecordingSession,
        } = useRecordingSessionControls({
            sessionId,
            isResuming,
            handleBackendMessage,
            loadExistingSession,
            startRecordingTimer,
            stopRecordingTimer,
            startWaveformVisualization,
            stopWaveformVisualization,
            setAnalyser: (nextAnalyser) => {
                analyser.value = nextAnalyser;
            },
        });

        // Calculate container width and initialize bars
        const updateContainerSize = () => {
            const container = audioBarsContainer.value;
            if (container) {
                containerWidth.value = container.clientWidth;
                // Initialize bars array with correct length
                audioBars.value = Array.from({ length: maxBars.value }, () => 0);
            }
        };

        // Lifecycle hooks
        onMounted(async () => {
            // Listen for window resize to update container size
            window.addEventListener('resize', updateContainerSize);

            // Calculate initial container size
            await nextTick();
            updateContainerSize();

            await initializeRecordingSession();
        });

        onUnmounted(() => {
            cleanupLiveSession();
            stopWaveformVisualization();

            window.removeEventListener('resize', updateContainerSize);
            cleanupRecordingSession();
        });

        return {
            user,
            isRecording,
            isPaused,
            isProcessingRecording,
            recordingTime,
            formatTime,
            audioLevel,
            audioBars,
            maxBars,
            conversationEntries,
            summaryData,
            currentLanguage,
            languageConfidence,
            languageSwitched,
            processingTime,
            connectionStatus,
            sessionId,
            transcriptContainer,
            audioBarsContainer,
            showFinishSessionPopup,
            toggleRecording,
            showFinishSessionDialog,
            closeFinishSessionPopup,
            deleteSessionFromPopup,
            saveSessionFromPopup,
            saveAndEditSummary,
            actuallyFinishSession,
            startAnotherSession
        };
    },
    template: `
        <div class="min-h-screen bg-gray-50">
            <div 
                v-if="isProcessingRecording" 
                class="fixed inset-0 bg-gray-900 bg-opacity-40 flex items-center justify-center z-40 px-4"
            >
                <div class="bg-white rounded-lg shadow-xl max-w-sm w-full p-5 flex items-center space-x-3">
                    <svg class="w-5 h-5 text-gray-900 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
                    </svg>
                    <div>
                        <p class="text-sm font-semibold text-gray-900">Processing recording...</p>
                        <p class="text-xs text-gray-600">Hang tight while we finish saving your session.</p>
                    </div>
                </div>
            </div>
            <!-- Header -->
            <header class="bg-white border-b border-gray-200 px-6 py-4">
                <div class="flex items-center justify-between">
                    <h1 class="text-xl font-semibold text-gray-900">Note'd Dashboard</h1>
                    
                    <!-- Connection Status -->
                    <div class="flex items-center space-x-4">
                        <div :class="[
                            'flex items-center space-x-2 px-3 py-1 rounded-full text-sm',
                            connectionStatus === 'connected' ? 'bg-green-100 text-green-800' : 
                            connectionStatus === 'connecting' ? 'bg-yellow-100 text-yellow-800' :
                            'bg-red-100 text-red-800'
                        ]">
                            <div :class="[
                                'w-2 h-2 rounded-full',
                                connectionStatus === 'connected' ? 'bg-green-500' :
                                connectionStatus === 'connecting' ? 'bg-yellow-500' :
                                'bg-red-500'
                            ]"></div>
                            <span>{{ connectionStatus }}</span>
                        </div>
                        
                        <!-- User Menu -->
                        <div class="flex items-center space-x-2">
                            <div class="w-8 h-8 bg-gray-400 rounded-full flex items-center justify-center">
                                <span class="text-white text-sm font-medium">
                                    {{ user?.name?.charAt(0) || 'U' }}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </header>

            <!-- Main Content -->
            <main class="px-6 py-6">
                <!-- Session Header -->
                <div class="flex items-center justify-between mb-6">
                    <div class="flex items-center space-x-6">
                        <div class="flex items-center space-x-4">
                            <span class="text-lg font-medium text-gray-900">Session:</span>
                            <span class="text-lg font-semibold text-gray-900">{{ sessionId }}</span>
                        </div>
                        
                        <!-- Recording Status -->
                        <div class="flex items-center space-x-2 text-sm text-gray-600">
                            <div class="flex items-center space-x-1">
                                <div :class="['w-2 h-2 rounded-full', isPaused ? 'bg-yellow-500' : isRecording ? 'bg-red-500 animate-pulse' : 'bg-gray-500']"></div>
                                <span>{{ isPaused ? 'Paused' : isRecording ? 'Recording' : 'Stopped' }}</span>
                            </div>
                        </div>
                        
                        <!-- Language Info -->
                        <div v-if="currentLanguage !== 'unknown'" class="flex items-center space-x-2 text-sm">
                            <span class="text-gray-600">Language:</span>
                            <span :class="['px-2 py-1 rounded text-xs font-medium', languageSwitched ? 'bg-orange-100 text-orange-800' : 'bg-blue-100 text-blue-800']">
                                {{ currentLanguage.toUpperCase() }} 
                                <span class="text-xs">({{ Math.round(languageConfidence * 100) }}%)</span>
                            </span>
                            <span v-if="languageSwitched" class="text-orange-600 text-xs">Language switched!</span>
                        </div>
                    </div>
                    
                    <button 
                        @click="startAnotherSession"
                        class="flex items-center space-x-2 px-4 py-2 border border-black bg-white text-black text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5v14l11-7z"/>
                        </svg>
                        <span>Start Another Session</span>
                    </button>
                </div>

                <!-- Audio Waveform - Vertical Bars, Centered, Rounded, Grey -->
                <div class="bg-white rounded-lg border border-gray-200 p-6 mb-6">
                    <div class="relative h-32 w-full max-w-4xl mx-auto">
                        <!-- Center baseline -->
                        <div class="absolute left-0 right-0 h-0.5 bg-gray-200 top-1/2 z-10"></div>

                        <!-- Bars Container -->
                        <div ref="audioBarsContainer" class="audio-bars-container flex absolute inset-0 justify-start items-center h-full space-x-1 overflow-hidden">
                            <div
                                v-for="(level, index) in audioBars"
                                :key="index"
                                :style="{
                                    height: Math.max(4, level) + 'px',
                                    width: '1px',
                                    transform: \`translateY(\${50 - level * 0.8}%)\`
                                }"
                                class="bg-gray-400 rounded-full flex-shrink-0 transition-all duration-100 ease-out"
                                :class="[isPaused ? 'bg-gray-300 opacity-60' : 'bg-gray-500 opacity-90']"
                            ></div>
                        </div>
                    </div>

                    <!-- Stats -->
                    <div class="text-center mt-2 text-xs text-gray-500">
                        {{ formatTime }} elapsed | Audio Level: {{ Math.round(audioLevel) }}%
                        <span v-if="processingTime > 0" class="ml-2">| Processing: {{ (processingTime * 1000).toFixed(0) }}ms</span>
                    </div>
                </div>

                <!-- Control Buttons -->
                <div class="flex justify-end space-x-4 mb-8">
                    <button 
                        @click="toggleRecording"
                        :disabled="(!isRecording && !isPaused) || isProcessingRecording"
                        :class="[
                            'flex items-center space-x-2 px-6 py-3 text-sm font-medium rounded-md transition-colors',
                            isPaused 
                                ? 'bg-green-600 text-white hover:bg-green-700' 
                                : 'bg-yellow-500 text-white hover:bg-yellow-600',
                            ((!isRecording && !isPaused) || isProcessingRecording) ? 'opacity-50 cursor-not-allowed' : ''
                        ]"
                    >
                        <svg v-if="isPaused" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5v14l11-7z"/>
                        </svg>
                        <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
                        </svg>
                        <span>{{ isPaused ? 'Resume Recording' : 'Pause Recording' }}</span>
                    </button>

                    <button 
                        @click="showFinishSessionDialog"
                        :disabled="isProcessingRecording"
                        :class="[
                            'flex items-center space-x-2 px-6 py-3 text-sm font-medium rounded-md transition-colors',
                            'bg-black text-white hover:bg-gray-800',
                            isProcessingRecording ? 'opacity-50 cursor-not-allowed' : ''
                        ]"
                    >
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                        </svg>
                        <span>Finish Session</span>
                    </button>
                </div>

                <!-- Two Column Layout -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
                    <!-- Left Column: Live Transcription -->
                    <div class="space-y-6">
                        <div>
                            <h3 class="text-lg font-medium text-gray-900 mb-4">Live Conversation:</h3>
                            
                            <div ref="transcriptContainer" class="transcript-container space-y-4 max-h-96 overflow-y-auto scroll-smooth">
                                <div 
                                    v-for="entry in conversationEntries" 
                                    :key="entry.id"
                                    :class="[
                                        'bg-white border rounded-lg p-4 transition-all duration-500',
                                        entry.isNew ? 'border-blue-300 animate-fade-in' : 'border-gray-200'
                                    ]"
                                >
                                    <!-- <div class="flex items-center justify-between mb-3">
                                        <div class="flex items-center space-x-2">
                                            <span class="text-sm font-medium text-gray-900">{{ entry.speaker }}:</span>
                                            <span class="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded">
                                                {{ entry.language?.toUpperCase() || 'UNK' }}
                                            </span>
                                            <div class="flex items-center space-x-1">
                                                <div :class="[
                                                    'w-2 h-2 rounded-full',
                                                    entry.confidence > 0.8 ? 'bg-green-500' : 
                                                    entry.confidence > 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                                                ]"></div>
                                                <span class="text-xs text-gray-500">{{ Math.round(entry.confidence * 100) }}%</span>
                                            </div>
                                        </div>
                                        <span class="text-xs text-gray-400">{{ entry.timestamp }}</span>
                                    </div> -->
                                    <p class="text-sm text-gray-700 leading-relaxed">
                                        "{{ entry.content }}"
                                    </p>
                                </div>
                                
                                <!-- Empty state -->
                                <div v-if="conversationEntries.length === 0" class="bg-white border border-gray-200 rounded-lg p-6 text-center">
                                    <div class="text-gray-400 mb-2">
                                        <svg class="w-8 h-8 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 1a3 3 0 013 3v8a3 3 0 01-6 0V4a3 3 0 013-3zM19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8"></path>
                                        </svg>
                                    </div>
                                    <p class="text-sm text-gray-500">
                                        {{ connectionStatus === 'connected' ? 'Listening for conversation...' : 'Connecting to transcription service...' }}
                                    </p>
                                    <p class="text-xs text-gray-400 mt-1">
                                        Real-time transcription will appear here
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Right Column: Summary Overview -->
                    <div class="space-y-6">
                        <!-- Output For Tags -->
                        <div class="flex items-center space-x-4 mb-4">
                            <span class="text-sm font-medium text-gray-900">Topics Detected:</span>
                            <div class="flex flex-wrap gap-2">
                                <span 
                                    v-for="topic in summaryData.outputFor"
                                    :key="topic"
                                    class="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-md"
                                >
                                    {{ topic }}
                                </span>
                                <span v-if="summaryData.outputFor.length === 0" class="text-xs text-gray-500">
                                    Will be detected from conversation
                                </span>
                            </div>
                        </div>

                        <!-- Summary Document -->
                        <div class="bg-white border border-gray-300 rounded-lg shadow-sm p-8">
                            <!-- Summary Overview Section -->
                            <div class="mb-8">
                                <h3 class="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
                                    Summary Overview
                                </h3>
                                <div class="text-sm text-gray-700 leading-relaxed">
                                    {{ summaryData.overview }}
                                </div>
                            </div>

                            <!-- Action Items Section -->
                            <div class="mb-8">
                                <h4 class="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
                                    Action Items
                                </h4>
                                <ul class="space-y-3">
                                    <li 
                                        v-for="(item, index) in summaryData.actionItems"
                                        :key="index"
                                        class="flex items-start space-x-3 text-sm text-gray-700"
                                    >
                                        <span class="text-gray-400 mt-1">|</span>
                                        <span class="leading-relaxed">{{ item }}</span>
                                    </li>
                                    <li v-if="summaryData.actionItems.length === 0" class="text-sm text-gray-500 italic">
                                        Action items will be generated from conversation
                                    </li>
                                </ul>
                            </div>

                            <!-- Related Services Section -->
                            <div>
                                <h4 class="text-lg font-bold text-gray-900 mb-4 border-b border-gray-200 pb-2">
                                    Related Services
                                </h4>
                                <ul class="space-y-3">
                                    <li 
                                        v-for="(service, index) in summaryData.relatedServices"
                                        :key="index"
                                        class="text-sm"
                                    >
                                        <a 
                                            v-if="service.url && service.url !== '#'"
                                            :href="service.url"
                                            class="text-blue-600 hover:text-blue-800 underline leading-relaxed"
                                            target="_blank"
                                        >
                                            {{ service.name }}
                                        </a>
                                        <span v-else class="text-gray-700 leading-relaxed">
                                            {{ service.name }}
                                        </span>
                                    </li>
                                    <li v-if="summaryData.relatedServices.length === 0" class="text-sm text-gray-500 italic">
                                        Relevant services will be suggested based on conversation
                                    </li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            </main>

            <!-- Finish Session Popup Modal -->
            <BaseModal :show="showFinishSessionPopup" max-width="max-w-lg" @close="closeFinishSessionPopup">
                <div class="text-center">
                    <h3 class="text-lg font-medium text-gray-900 mb-4">
                        What would you like to do with your session?
                    </h3>
                    <p class="text-sm text-gray-600 mb-6">
                        You're about to finish this session.<br>
                        Choose what you'd like to do with your session notes and summary.
                    </p>

                    <div class="flex space-x-3">
                        <button
                            @click="deleteSessionFromPopup"
                            class="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
                        >
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                            </svg>
                            <span>Delete Session</span>
                        </button>

                        <button
                            @click="saveSessionFromPopup"
                            class="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
                        >
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3-3m0 0l-3 3m3-3v12"></path>
                            </svg>
                            <span>Save Session</span>
                        </button>

                        <button
                            @click="saveAndEditSummary"
                            class="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-800 transition-colors"
                        >
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                            </svg>
                            <span>Save & Edit Summary</span>
                        </button>
                    </div>
                </div>
            </BaseModal>
        </div>
    `
};
