import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { sessionService } from '../services/session_service.js';

export default {
    name: 'NewSession',
    setup() {
        const router = useRouter();
        const sessionId = ref('');
        const user = ref(authService.getUser());

        // State for Recording Section
        const recordingPreviousSessionRef = ref('');
        const recordingConsentGiven = ref(false);
        const isLoadingRecording = ref(false);

        // State for Upload Section
        const uploadPreviousSessionRef = ref('');
        const uploadConsentGiven = ref(false);
        const isLoadingUpload = ref(false);
        const selectedFile = ref(null);
        const uploadError = ref('');
        const uploadProgress = ref(0);
        const isDragging = ref(false);
        const showUploadProcessingSummary = ref(false);
        const uploadProcessingMessages = ref([]);
        const processingSessionName = ref(null);
        let processingStatusIntervalId = null;
        let isCheckingProcessingStatus = false;

        const addUploadProcessingMessage = (message) => {
            uploadProcessingMessages.value = [
                ...uploadProcessingMessages.value,
                {
                    id: Date.now() + Math.random(),
                    message
                }
            ];
        };

        const resetUploadProcessingSummary = () => {
            showUploadProcessingSummary.value = false;
            uploadProcessingMessages.value = [];
        };

        // Computed property for recording button
        const canStartRecording = computed(() => {
            return recordingConsentGiven.value && !isLoadingRecording.value;
        });

        // Computed property for upload button
        const canStartUpload = computed(() => {
            return (
                uploadConsentGiven.value &&
                selectedFile.value &&
                !isLoadingUpload.value
            );
        });

        // Generate next session ID from backend
        const generateSessionId = async () => {
            try {
                // Fetch the actual next session name from backend
                const nextName = await sessionService.getNextSessionName();
                sessionId.value = nextName;
            } catch (error) {
                console.error('Failed to get next session name:', error);
                sessionId.value = 'SES-00001'; // Fallback
            }
        };

        const handleFileSelect = (file) => {
            if (file && file.type.startsWith('audio/')) {
                selectedFile.value = file;
                uploadError.value = '';
            } else if (file) {
                selectedFile.value = null;
                uploadError.value = 'Invalid file type. Please upload an audio file.';
            } else {
                selectedFile.value = null;
            }
        };

        const onFileChange = (event) => {
            const file = event.target.files[0];
            handleFileSelect(file);
        };

        const handleDrop = (event) => {
            isDragging.value = false;
            const file = event.dataTransfer.files[0];
            handleFileSelect(file);
            document.getElementById('audio-upload').files = event.dataTransfer.files; // Sync with input
        };

        const removeSelectedFile = () => {
            selectedFile.value = null;
            uploadError.value = '';
            document.getElementById('audio-upload').value = null; // Reset file input
        };

        const handleStartRecording = async () => {
            if (!canStartRecording.value) {
                return;
            }

            isLoadingRecording.value = true;
            
            try {
                // Create the session in the backend (ID will be generated and set as cookie)
                const session = await sessionService.createSession(recordingPreviousSessionRef.value || null);
                
                // Update the displayed session ID
                sessionId.value = session.session_name;
                
                await router.push({
                    name: 'recording',
                    params: { sessionId: session.session_name }
                });
            } catch (error) {
                console.error('Failed to start session:', error);
                alert('Failed to start recording session. Please try again.');
            } finally {
                isLoadingRecording.value = false;
            }
        };

        const handleUploadAndProcess = async () => {
            stopProcessingStatusPolling();

            if (!selectedFile.value) {
                uploadError.value = 'Please select a file to upload.';
                return;
            }

            if (!uploadConsentGiven.value) {
                uploadError.value = 'Please confirm consent before processing the file.';
                return;
            }

            isLoadingUpload.value = true;
            uploadError.value = '';
            uploadProgress.value = 0;
            resetUploadProcessingSummary();

            try {
                // 1. Create the session
                const session = await sessionService.createSession(uploadPreviousSessionRef.value || null);
                sessionId.value = session.session_name;

                // 2. Upload the audio file for processing
                await sessionService.uploadAudioFile(session.session_name, selectedFile.value, (progressEvent) => {
                    uploadProgress.value = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                });

                // 3. Surface background processing state
                showUploadProcessingSummary.value = true;
                addUploadProcessingMessage(`Session ${session.session_name} created successfully.`);
                addUploadProcessingMessage('Upload complete. We are now processing the audio in the background.');
                addUploadProcessingMessage('You can return to the dashboard at any time to monitor progress.');
                addUploadProcessingMessage('We will automatically open this session once processing finishes.');
                startProcessingStatusPolling(session);

                // Reset inputs for optional next upload
                removeSelectedFile();
                uploadConsentGiven.value = false;
                uploadPreviousSessionRef.value = '';
            } catch (error) {
                console.error('Failed to upload and process session:', error);
                uploadError.value = 'Failed to process file. Please ensure it is a valid audio file and try again.';
                resetUploadProcessingSummary();
            } finally {
                isLoadingUpload.value = false;
                uploadProgress.value = 0;
            }
        };

        const goBackToDashboard = async () => {
            await router.push({ name: 'dashboard' });
        };

        const acknowledgeUploadProcessing = () => {
            stopProcessingStatusPolling();
            resetUploadProcessingSummary();
            goBackToDashboard();
        };

        const startAnotherSession = async () => {
            // Reset form and generate new session ID
            stopProcessingStatusPolling();
            resetUploadProcessingSummary();
            recordingPreviousSessionRef.value = '';
            recordingConsentGiven.value = false;
            selectedFile.value = null;
            uploadPreviousSessionRef.value = '';
            uploadConsentGiven.value = false;
            await generateSessionId();
        };

        const startExperiment = async () => {
            await router.push({
                name: 'experiment',
                params: {
                    sessionId: sessionId.value || undefined
                }
            });
        };

        const stopProcessingStatusPolling = () => {
            if (processingStatusIntervalId) {
                clearInterval(processingStatusIntervalId);
                processingStatusIntervalId = null;
            }
            processingSessionName.value = null;
            isCheckingProcessingStatus = false;
        };

        const openSessionDetailsAfterNavigation = (sessionIdentifier) => {
            if (!sessionIdentifier) {
                goBackToDashboard();
                return;
            }
            router.push({
                name: 'session-detail',
                params: { sessionId: sessionIdentifier }
            });
        };

        const checkProcessingStatus = async () => {
            if (!processingSessionName.value || isCheckingProcessingStatus) {
                return;
            }

            isCheckingProcessingStatus = true;

            try {
                const session = await sessionService.getSession(processingSessionName.value);
                const normalizedStatus = (session.status || '').toString().toLowerCase();

                if (normalizedStatus === 'completed') {
                    addUploadProcessingMessage('Processing complete. Redirecting to session details...');
                    stopProcessingStatusPolling();
                    openSessionDetailsAfterNavigation(session.db_id || session.session_name);
                } else if (normalizedStatus === 'error') {
                    addUploadProcessingMessage('Processing failed. Please review the session from the dashboard.');
                    stopProcessingStatusPolling();
                }
            } catch (error) {
                console.error('Failed to check processing status:', error);
            } finally {
                isCheckingProcessingStatus = false;
            }
        };

        const startProcessingStatusPolling = (session) => {
            stopProcessingStatusPolling();

            if (!session || !session.session_name) {
                return;
            }

            processingSessionName.value = session.session_name;
            checkProcessingStatus();
            processingStatusIntervalId = setInterval(checkProcessingStatus, 5000);
        };

        // Initialize session ID on mount
        onMounted(async () => {
            await generateSessionId();
        });

        onUnmounted(() => {
            stopProcessingStatusPolling();
        });

        return {
            sessionId,
            user,
            // Recording state
            recordingPreviousSessionRef,
            recordingConsentGiven,
            isLoadingRecording,
            canStartRecording,
            handleStartRecording,
            // Upload state
            uploadPreviousSessionRef,
            uploadConsentGiven,
            isLoadingUpload,
            canStartUpload,
            selectedFile,
            uploadError,
            uploadProgress,
            isDragging,
            showUploadProcessingSummary,
            uploadProcessingMessages,
            handleDrop,
            onFileChange,
            removeSelectedFile,
            handleUploadAndProcess,
            acknowledgeUploadProcessing,
            goBackToDashboard,
            startAnotherSession,
            startExperiment
        };
    },
    template: `
        <div class="min-h-screen bg-gray-50">
            <!-- Header -->
            <header class="bg-white border-b border-gray-200 px-6 py-4">
                <div class="flex items-center justify-between">
                    <h1 class="text-xl font-semibold text-gray-900">Note'd Dashboard</h1>
                    
                    <!-- User Menu -->
                    <div class="flex items-center space-x-4">
                        <div class="flex items-center space-x-2">
                            <div class="w-8 h-8 bg-gray-400 rounded-full flex items-center justify-center">
                                <span class="text-white text-sm font-medium">
                                    {{ user?.name?.charAt(0) || 'U' }}
                                </span>
                            </div>
                            <button class="text-gray-600 hover:text-gray-900">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                                </svg>
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            <!-- Main Content -->
            <main class="px-6 py-6">
                <!-- Session Info and Start Another Button -->
                <div class="flex items-center justify-between mb-12">
                    
                    <div class="flex items-center space-x-6">
                        <button 
                            @click="goBackToDashboard"
                            class="flex items-center space-x-2 px-3 py-2 text-gray-600 hover:text-gray-900 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                        >
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>
                            </svg>
                            <span>Back to Sessions</span>
                        </button>

                        <div class="flex items-center space-x-4">
                            <span class="text-lg font-medium text-gray-900">Session:</span>
                            <span class="text-lg font-semibold text-gray-900">{{ sessionId }}</span>
                        </div>
                    </div>
                    
                    <div class="flex items-center">
                        <button 
                            @click="startAnotherSession"
                            class="flex items-center space-x-2 px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
                        >
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5v14l11-7z"/>
                            </svg>
                            <span>Start Another Session</span>
                        </button>
                    </div>
                </div>

                <!-- Center Content -->
                <div class="flex items-center justify-center min-h-96">
                    <div class="w-full max-w-2xl space-y-8">
                        <!-- Recording Section -->
                        <div class="bg-white p-8 rounded-lg border border-gray-200 space-y-6 shadow-sm">
                            <h3 class="text-lg font-semibold text-gray-900 text-center">Start a Live Recording</h3>
                            
                            <!-- Previous Session Reference -->
                            <div>
                                <label for="recordingPreviousRef" class="block text-sm font-medium text-gray-900 mb-2">
                                    Previous Session Reference (Optional)
                                </label>
                                <input
                                    id="recordingPreviousRef"
                                    v-model="recordingPreviousSessionRef"
                                    type="text"
                                    placeholder="e.g., SES-00123"
                                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                />
                            </div>

                            <!-- Consent Checkbox -->
                            <div class="flex items-center space-x-3">
                                <input
                                    id="recordingConsent"
                                    v-model="recordingConsentGiven"
                                    type="checkbox"
                                    class="w-4 h-4 text-black border-gray-300 rounded focus:ring-black focus:ring-offset-0"
                                    style="accent-color: black;"
                                />
                                <label for="recordingConsent" class="text-sm text-gray-900">
                                    I have received consent from the client to record this conversation.
                                </label>
                            </div>

                            <!-- Start Recording Button -->
                            <div class="pt-2">
                                <button
                                    @click="handleStartRecording"
                                    :disabled="!canStartRecording"
                                    :class="[
                                        'w-full flex items-center justify-center space-x-2 px-6 py-3 text-sm font-medium rounded-md transition-colors',
                                        canStartRecording 
                                            ? 'bg-black text-white hover:bg-gray-800' 
                                            : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                    ]"
                                >
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5v14l11-7z"/>
                                    </svg>
                                    <span v-if="!isLoadingRecording">Start Recording</span>
                                    <span v-else>Starting...</span>
                                </button>
                                <p v-if="!recordingConsentGiven" class="text-xs text-center text-gray-500 mt-2">
                                    Please confirm consent to enable recording.
                                </p>
                            </div>
                        </div>
                        
                        <!-- OR Separator -->
                        <div class="relative flex py-2 items-center">
                            <div class="flex-grow border-t border-gray-300"></div>
                            <span class="flex-shrink mx-4 text-gray-500">OR</span>
                            <div class="flex-grow border-t border-gray-300"></div>
                        </div>

                        <div class="bg-white p-8 rounded-lg border border-gray-200 space-y-6 shadow-sm">
                            <h3 class="text-lg font-semibold text-gray-900 text-center">Process a Pre-recorded File</h3>

                            <!-- Previous Session Reference -->
                            <div>
                                <label for="uploadPreviousRef" class="block text-sm font-medium text-gray-900 mb-2">
                                    Previous Session Reference (Optional)
                                </label>
                                <input
                                    id="uploadPreviousRef"
                                    v-model="uploadPreviousSessionRef"
                                    type="text"
                                    placeholder="e.g., SES-00123"
                                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                />
                            </div>

                            <!-- File Upload -->
                            <div>
                                <div 
                                    @dragover.prevent="isDragging = true"
                                    @dragleave.prevent="isDragging = false"
                                    @drop.prevent="handleDrop"
                                    :class="['flex justify-center px-6 pt-5 pb-6 border-2 border-dashed rounded-md transition-colors',
                                        isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300']"
                                >
                                    <div class="space-y-1 text-center">
                                        <svg class="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48" aria-hidden="true">
                                            <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                                        </svg>
                                        <div class="flex text-sm text-gray-600">
                                            <label for="audio-upload" class="relative cursor-pointer bg-white rounded-md font-medium text-blue-600 hover:text-blue-500 focus-within:outline-none focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-blue-500">
                                                <span>Upload a file</span>
                                                <input id="audio-upload" name="audio-upload" type="file" class="sr-only" @change="onFileChange" accept="audio/*">
                                            </label>
                                            <p class="pl-1">or drag and drop</p>
                                        </div>
                                        <p class="text-xs text-gray-500">MP3, WAV, FLAC, M4A up to 50MB</p>
                                    </div>
                                </div>
                                <div v-if="selectedFile" class="mt-2 flex items-center justify-between text-sm text-gray-700 bg-gray-100 p-2 rounded-md">
                                    <span class="truncate">Selected: {{ selectedFile.name }}</span>
                                    <button @click="removeSelectedFile" class="ml-2 flex-shrink-0 text-red-500 hover:text-red-700 font-medium">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                        </svg>
                                        <span class="sr-only">Remove file</span>
                                    </button>
                                </div>
                                <p v-if="uploadError" class="mt-2 text-sm text-red-500">{{ uploadError }}</p>
                            </div>

                            <!-- Consent Checkbox -->
                            <div class="flex items-center space-x-3">
                                <input
                                    id="uploadConsent"
                                    v-model="uploadConsentGiven"
                                    type="checkbox"
                                    class="w-4 h-4 text-black border-gray-300 rounded focus:ring-black focus:ring-offset-0"
                                    style="accent-color: black;"
                                />
                                <label for="uploadConsent" class="text-sm text-gray-900">
                                    I have received consent from the client for this recording.
                                </label>
                            </div>

                            <!-- Process File Button -->
                            <div class="pt-2">
                                <button
                                    @click="handleUploadAndProcess"
                                    :disabled="!canStartUpload"
                                    :class="[
                                        'w-full flex items-center justify-center space-x-2 px-6 py-3 text-sm font-medium rounded-md transition-colors',
                                        canStartUpload 
                                            ? 'bg-black text-white hover:bg-gray-800' 
                                            : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                    ]"
                                >
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                                    </svg>
                                    <span v-if="!isLoadingUpload">Upload and Process File</span>
                                    <span v-else>Uploading File... ({{ uploadProgress }}%)</span>
                                </button>
                                <div v-if="isLoadingUpload" class="w-full bg-gray-200 rounded-full h-2.5 mt-2">
                                    <div class="bg-blue-600 h-2.5 rounded-full" :style="{ width: uploadProgress + '%' }"></div>
                                </div>
                                <p v-if="!selectedFile || !uploadConsentGiven" class="text-xs text-center text-gray-500 mt-2">
                                    Please select a file and confirm consent to proceed.
                                </p>
                                <div 
                                    v-if="showUploadProcessingSummary"
                                    class="mt-4 border border-gray-200 rounded-lg bg-gray-50 p-4 space-y-3"
                                >
                                    <div class="flex items-start space-x-3">
                                        <svg class="w-5 h-5 text-gray-700 animate-spin mt-0.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
                                        </svg>
                                        <div>
                                            <p class="text-sm font-semibold text-gray-900">Processing uploaded recording</p>
                                            <p class="text-xs text-gray-600">We are transcribing and summarizing this session in the background.</p>
                                        </div>
                                    </div>
                                    <ul class="text-xs text-gray-600 space-y-1">
                                        <li 
                                            v-for="message in uploadProcessingMessages"
                                            :key="message.id"
                                            class="flex items-center space-x-2"
                                        >
                                            <span class="w-1.5 h-1.5 rounded-full bg-gray-500"></span>
                                            <span>{{ message.message }}</span>
                                        </li>
                                    </ul>
                                    <div class="flex flex-col sm:flex-row sm:space-x-3 space-y-2 sm:space-y-0">
                                        <button
                                            @click="acknowledgeUploadProcessing"
                                            class="flex-1 px-4 py-2 text-sm font-medium text-white bg-black rounded-md hover:bg-gray-800 transition-colors"
                                        >
                                            Go to Dashboard
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    `
};
