import { ref, computed, onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { sessionService } from '../services/session_service.js';
import { apiClient } from '../services/api_client.js';

export default {
    name: 'Dashboard',
    setup() {
        const router = useRouter();
        const fileInput = ref(null);
        const isUploading = ref(false);
        const uploadProgress = ref(0);
        const message = ref('');
        const error = ref('');

        // ----- Analyze Audio State -----
        const completedAudioFiles = ref([]);
        const newAudioFiles = ref([]);
        const audioFiles = ref([]);
        const selectedPaths = reactive(new Set()); // Multi-select: audio paths (only from newAudioFiles)
        const processingQueue = ref([]); // Queue of paths to process
        const currentProcessingPath = ref(null); // Currently processing audio
        const processingProgress = ref(null); // { path, percent, status }
        const analysisResults = reactive({}); // { path: result }
        const crmFormStatusCache = reactive({}); // { filename: exists }

        // Computed helpers
        const isAnalyzing = computed(() => processingQueue.value.length > 0 || currentProcessingPath.value !== null);

        const selectAllChecked = computed(() => {
            return newAudioFiles.value.length > 0 && newAudioFiles.value.every(af => selectedPaths.has(af.path));
        });

        const selectAllIndeterminate = computed(() => {
            return selectedPaths.size > 0 && !selectAllChecked.value;
        });

        // Parse date/time from audio file path or use file modification time
        const parseAudioFileInfo = (audioFile) => {
            const name = audioFile.display_name || audioFile.name;
            // Try to extract date from path, fallback to current date
            const date = new Date().toLocaleDateString('de-DE'); // DD.MM.YYYY
            const time = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            return { name, date, time };
        };

        const toggleAudioSelection = (audioPath) => {
            if (selectedPaths.has(audioPath)) {
                selectedPaths.delete(audioPath);
            } else {
                selectedPaths.add(audioPath);
            }
        };

        const toggleSelectAll = () => {
            if (selectAllChecked.value) {
                selectedPaths.clear();
            } else {
                newAudioFiles.value.forEach(af => selectedPaths.add(af.path));
            }
        };

        const chooseAudio = () => {
            fileInput.value?.click();
        };

        const logout = async () => {
            authService.logout();
            await router.push({ name: 'login' });
        };

        const uploadAudio = async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;

            isUploading.value = true;
            uploadProgress.value = 0;
            message.value = '';
            error.value = '';

            try {
                const result = await sessionService.uploadUserAudio(file, (progress) => {
                    uploadProgress.value = progress;
                });
                uploadProgress.value = 100;
                message.value = result.message || 'Uploaded successfully.';
                await loadAudioFiles();
            } catch (uploadError) {
                error.value = uploadError.message || 'Unable to upload the audio file.';
            } finally {
                isUploading.value = false;
                event.target.value = '';
            }
        };

        const loadAudioFiles = async () => {
            try {
                const data = await apiClient.get('/audio/analyze-files-categorized');
                completedAudioFiles.value = (data.completed || []).sort((a, b) => a.name.localeCompare(b.name));
                newAudioFiles.value = (data.new || []).sort((a, b) => a.name.localeCompare(b.name));
                audioFiles.value = [...completedAudioFiles.value, ...newAudioFiles.value];
                selectedPaths.clear();
            } catch (loadError) {
                console.error('Failed to load audio files', loadError);
                error.value = loadError.message || 'Failed to load audio files.';
            }
        };

        const checkCrmFormStatus = async (audioFilename) => {
            try {
                const response = await apiClient.get(`/audio/crm-form-status?audio_filename=${encodeURIComponent(audioFilename)}`);
                crmFormStatusCache[audioFilename] = response.crm_form_exists || false;
            } catch (err) {
                console.error('Failed to check CRM form status', err);
                crmFormStatusCache[audioFilename] = false;
            }
        };

        const isCrmFormAvailable = (audioFile) => {
            // CRM is available if: analysis is complete (in results) OR form already exists
            const hasAnalysis = analysisResults[audioFile.path];
            const formExists = crmFormStatusCache[audioFile.name];
            return hasAnalysis || formExists;
        };

        const startBatchAnalysis = async () => {
            if (selectedPaths.size === 0) {
                error.value = 'Please select at least one audio file.';
                return;
            }

            // Sort selected paths alphabetically and queue them
            processingQueue.value = Array.from(selectedPaths).sort();
            selectedPaths.clear();
            error.value = '';
            message.value = '';
            
            // Process queue sequentially
            await processQueueSequentially();
        };

        const processQueueSequentially = async () => {
            while (processingQueue.value.length > 0) {
                const audioPath = processingQueue.value.shift();
                currentProcessingPath.value = audioPath;
                processingProgress.value = { path: audioPath, percent: 0, status: 'Starting analysis...' };

                try {
                    processingProgress.value.status = 'Analyzing audio...';
                    processingProgress.value.percent = 50;

                    const result = await apiClient.post('/audio/analyze', { audio_path: audioPath });
                    analysisResults[audioPath] = result;

                    processingProgress.value.percent = 100;
                    processingProgress.value.status = 'Analysis complete';
                    
                    // Check if CRM form now exists
                    const audioFile = audioFiles.value.find(af => af.path === audioPath);
                    if (audioFile) {
                        await checkCrmFormStatus(audioFile.name);
                    }

                    // Wait briefly before next analysis
                    await new Promise(resolve => setTimeout(resolve, 1000));
                } catch (analyzeError) {
                    console.error('Audio analysis failed for', audioPath, analyzeError);
                    processingProgress.value.status = `Analysis failed: ${analyzeError.message || 'Unknown error'}`;
                    processingProgress.value.percent = 100;
                    
                    // Continue with next file
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }

            currentProcessingPath.value = null;
            processingProgress.value = null;
            message.value = 'Batch analysis complete.';
            await loadAudioFiles();
        };

        const cancelBatchAnalysis = () => {
            processingQueue.value = [];
            currentProcessingPath.value = null;
            processingProgress.value = null;
            message.value = '';
        };

        const openCrmForm = async (audioFile) => {
            // Try in-memory result first, then fall back to fetching from backend
            let result = analysisResults[audioFile.path];

            if (!result) {
                // Already analyzed (page refresh) — fetch the result paths from backend
                try {
                    result = await apiClient.get(`/audio/analyze-result?audio_path=${encodeURIComponent(audioFile.path)}`);
                    if (result) {
                        analysisResults[audioFile.path] = result;
                    }
                } catch (fetchErr) {
                    console.error('Could not fetch existing analysis result', fetchErr);
                }
            }

            if (!result) {
                error.value = 'No analysis result found. Please analyze this file first.';
                return;
            }

            const htmlPath = result.crm_form_html_path || result.result?.crm_form_html_path || '';
            if (!htmlPath) {
                error.value = 'No CRM form HTML is available yet.';
                return;
            }

            // Copy the CRM JSON to submitted_crm_forms when user opens the form
            try {
                await apiClient.post('/audio/crm-form/submit', { audio_filename: audioFile.name });
                // Update CRM form status cache
                crmFormStatusCache[audioFile.name] = true;
            } catch (submitErr) {
                console.warn('Could not copy CRM JSON on open:', submitErr.message);
                // Non-fatal — still open the form
            }

            try {
                const response = await apiClient.request(`/audio/file-content?path=${encodeURIComponent(htmlPath)}`);
                if (!response.ok) {
                    const errText = await response.text();
                    throw new Error(errText || `Failed to open CRM form: ${response.status}`);
                }

                const data = await response.json();
                let htmlContent = data.content || '';

                // Inject auth token and backend URL so the popup can POST back on submit
                const { config } = await import('../config.js');
                const backendUrl = config.getApiBaseUrl().replace('/api/v1', '');
                const authToken = sessionStorage.getItem('auth_token') || '';
                const tokenScript = `<script>window.crmBackendUrl = ${JSON.stringify(backendUrl)};window.crmAuthToken = ${JSON.stringify(authToken)};<\/script>`;

                if (htmlContent.includes('</head>')) {
                    htmlContent = htmlContent.replace('</head>', `${tokenScript}</head>`);
                } else {
                    htmlContent = tokenScript + htmlContent;
                }

                const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
                const blobUrl = URL.createObjectURL(blob);
                const popup = window.open(blobUrl, '_blank', 'noopener,noreferrer');
                if (!popup) {
                    throw new Error('Popup blocked. Please allow popups for this site.');
                }
                setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
                message.value = 'CRM form opened in a new window.';
            } catch (openError) {
                console.error('Failed to open CRM form', openError);
                error.value = openError.message || 'Failed to open CRM form.';
            }
        };

        onMounted(() => {
            loadAudioFiles();
        });

        return {
            fileInput, isUploading, uploadProgress, message, error, chooseAudio, uploadAudio, logout,
            audioFiles, completedAudioFiles, newAudioFiles,
            selectedPaths, isAnalyzing, selectAllChecked, selectAllIndeterminate,
            processingProgress, analysisResults, crmFormStatusCache,
            loadAudioFiles, toggleAudioSelection, toggleSelectAll, startBatchAnalysis, cancelBatchAnalysis,
            isCrmFormAvailable, openCrmForm, parseAudioFileInfo,
        };
    },
    template: `
        <main class="audio-upload-dashboard">
            <button type="button" class="logout-button" @click="logout">Logout</button>
            <input
                ref="fileInput"
                type="file"
                accept="audio/*"
                class="sr-only"
                @change="uploadAudio"
            >
            <button type="button" class="upload-button" :disabled="isUploading" @click="chooseAudio">
                {{ isUploading ? 'Uploading…' : 'Upload audio' }}
            </button>
            <div v-if="isUploading" class="upload-progress" role="progressbar" :aria-valuenow="uploadProgress" aria-valuemin="0" aria-valuemax="100">
                <div class="upload-progress__bar" :style="{ width: uploadProgress + '%' }"></div>
            </div>
            <p v-if="isUploading" class="status">Uploading {{ uploadProgress }}%</p>
            <p v-if="message" class="status success">{{ message }}</p>
            <p v-if="error" class="status error">{{ error }}</p>

            <hr class="divider">

            <!-- Processing Progress Display -->
            <div v-if="isAnalyzing" class="analysis-progress-container">
                <div class="analysis-progress" role="progressbar" aria-label="Analysis in progress">
                    <div class="analysis-progress__bar"></div>
                </div>
                <p class="analysis-status-label">{{ processingProgress?.status || 'Processing...' }}</p>
                <button type="button" class="cancel-button" @click="cancelBatchAnalysis">Cancel</button>
            </div>

            <!-- ===== Side-by-side tables ===== -->
            <div class="tables-row" style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; align-items: start;">

                <!-- Left: Completed Audio Analysis -->
                <section class="analyze-section">
                    <h2 class="analyze-title">Completed Audio Analysis</h2>
                    <p class="analyze-hint">Analyzed recordings with CRM forms available.</p>

                    <div v-if="completedAudioFiles.length > 0" class="table-container">
                        <table class="audio-files-table">
                            <thead>
                                <tr>
                                    <th class="col-sno">S.No.</th>
                                    <th class="col-name">Audio File Name</th>
                                    <th class="col-crm">CRM Form</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="(audioFile, index) in completedAudioFiles" :key="audioFile.path" class="audio-row">
                                    <td class="col-sno">{{ index + 1 }}</td>
                                    <td class="col-name">{{ parseAudioFileInfo(audioFile).name }}</td>
                                    <td class="col-crm">
                                        <button
                                            type="button"
                                            class="crm-button"
                                            @click="openCrmForm(audioFile)"
                                        >
                                            Open CRM
                                        </button>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <p v-else class="status">No completed analyses yet.</p>
                </section>

                <!-- Right: New Audios -->
                <section class="analyze-section">
                    <h2 class="analyze-title">New Audios</h2>
                    <p class="analyze-hint">Select recordings to analyze. CRM forms available after analysis.</p>

                    <div v-if="!isAnalyzing && newAudioFiles.length > 0" class="table-container">
                        <table class="audio-files-table">
                            <thead>
                                <tr>
                                    <th class="col-checkbox">
                                        <input
                                            type="checkbox"
                                            @change="toggleSelectAll"
                                            :checked="selectAllChecked"
                                            :indeterminate="selectAllIndeterminate"
                                            class="select-all-checkbox"
                                        />
                                    </th>
                                    <th class="col-sno">S.No.</th>
                                    <th class="col-name">Audio File Name</th>
                                    <th class="col-crm">CRM Form</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="(audioFile, index) in newAudioFiles" :key="audioFile.path" class="audio-row">
                                    <td class="col-checkbox">
                                        <input
                                            type="checkbox"
                                            @change="toggleAudioSelection(audioFile.path)"
                                            :checked="selectedPaths.has(audioFile.path)"
                                            class="audio-checkbox"
                                        />
                                    </td>
                                    <td class="col-sno">{{ index + 1 }}</td>
                                    <td class="col-name">{{ parseAudioFileInfo(audioFile).name }}</td>
                                    <td class="col-crm">
                                        <button
                                            type="button"
                                            class="crm-button"
                                            :disabled="!isCrmFormAvailable(audioFile)"
                                            @click="openCrmForm(audioFile)"
                                        >
                                            Open CRM
                                        </button>
                                    </td>
                                </tr>
                            </tbody>
                        </table>

                        <div class="analyze-controls">
                            <button type="button" class="refresh-button" @click="loadAudioFiles">Refresh List</button>
                            <button
                                type="button"
                                class="analyze-button"
                                :disabled="selectedPaths.size === 0"
                                @click="startBatchAnalysis"
                            >
                                Analyze Selected ({{ selectedPaths.size }})
                            </button>
                        </div>
                    </div>

                    <p v-else-if="!isAnalyzing && newAudioFiles.length === 0 && completedAudioFiles.length > 0" class="status">All audio files have been analyzed.</p>
                    <p v-else-if="!isAnalyzing" class="status">No audio files found. Upload some audio files to get started.</p>
                </section>

            </div>
        </main>
    `,
};
